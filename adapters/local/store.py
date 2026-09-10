"""Adapter 0: a SQLite store satisfying kernel.contracts.Store.

Why this exists
---------------
So the kernel runs with no CARE, no Django and no network. One file on disk,
FHIR shaped tables named exactly as vocab.CARE_RESOURCES names them, and
columns named exactly as the query grammar in kernel/contracts.py names them.
A declaration that says {resource: observation, where: {category: vital-signs}}
turns into `SELECT ... FROM observation WHERE category = ?` with nothing in
between.

What this adapter knows that a declaration must not
---------------------------------------------------
How a resource joins to a thread. A thread is an encounter row; a patient
hangs off the encounter, everything else points back at it. That join table is
right below and it is the whole of this adapter's cleverness.

What it does not know
---------------------
The guard, state derivation, or what an operation means. It stores rows.

Honest limits
-------------
- Column names are taken from care/emr/models and are UNVERIFIED against a
  running CARE, same caveat as care_phc/queries.py. Adapter 1 maps them.
- write() takes one row, already shaped by the operation's declared mapping
  (kernel/mapping.py). This adapter no longer knows what a blood pressure is,
  which is the point: adapter 1 inherits the same mapping instead of deriving
  its own. It upserts, because linking an ABHA updates the patient row that
  registration created.
- One connection per thread, autocommit, WAL on a file. FastAPI runs sync
  endpoints in a thread pool, so one shared connection is not an option: it
  corrupts the file on the second concurrent request, which is how this was
  found ("database disk image is malformed" from a queue read racing a write).
  ponytail: thread local connections, add a real pool if more than one uvicorn
  worker ever runs.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

from kernel.contracts import AuditRecord, Proposal, ThreadRef

# One table per resource this bundle's operations read or write, plus the
# kernel's own three. Columns are query grammar field names, verbatim.
TABLES = {
    "patient": ("id", "name", "age", "sex", "phone", "village", "category",
                "abha_number", "created_by", "created_date"),
    "encounter": ("id", "patient", "status", "token", "created_by", "created_date"),
    "observation": ("id", "encounter", "category", "code", "value", "unit",
                    "created_by", "created_date"),
    "condition": ("id", "encounter", "code", "verification_status",
                  "created_by", "created_date"),
    "notes": ("id", "encounter", "text", "created_by", "created_date"),
    "medication_request": ("id", "encounter", "medication", "dosage_instruction",
                           "status", "created_by", "created_date"),
    "medication_dispense": ("id", "encounter", "medication", "quantity", "status",
                            "created_by", "created_date"),
    "service_request": ("id", "encounter", "code", "status",
                        "created_by", "created_date"),
    "diagnostic_report": ("id", "encounter", "code", "conclusion", "status",
                          "created_by", "created_date"),
    "specimen": ("id", "encounter", "code", "status", "created_by", "created_date"),
    "inventory_item": ("id", "encounter", "code", "quantity", "status",
                       "created_by", "created_date"),
    "questionnaire_response": ("id", "encounter", "questionnaire", "payload",
                               "created_by", "created_date"),
    "token_booking": ("id", "encounter", "patient", "status",
                      "created_by", "created_date"),
    # the kernel's own records
    "thread_flag": ("id", "thread", "flag", "created_by", "created_date"),
    "proposal": ("id", "thread", "operation", "payload", "proposed_by", "surface",
                 "status", "created_at", "flags_raised", "decided_by", "decided_at",
                 "final_payload"),
    "audit": ("id", "thread", "operation", "actor", "surface", "payload",
              "outcome", "at", "proposal"),
}

# The adapter's private knowledge: which column ties a row to its thread.
# "encounter" is the thread itself; a patient is reached through it.
THREAD_COLUMN = {"encounter": "id", "thread_flag": "thread", "patient": None}
DEFAULT_THREAD_COLUMN = "encounter"

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return "%s-%s" % (prefix[:4], uuid.uuid4().hex[:8])


class SqliteStore:
    """kernel.contracts.Store over a SQLite file. Pass ":memory:" for a test."""

    def __init__(self, path: str = ":memory:"):
        # A plain ":memory:" database is private to one connection, so give it
        # a name and a shared cache: otherwise the second thread opens an
        # empty database and a test starts passing for the wrong reason.
        self._uri = path == ":memory:"
        self.path = ("file:mem-%s?mode=memory&cache=shared" % uuid.uuid4().hex
                     if self._uri else path)
        self._local = threading.local()
        # The shared in memory database lives as long as a connection to it
        # does, so the store holds one open for its own lifetime.
        self._keepalive = self.db
        for table, columns in TABLES.items():
            cols = ", ".join(
                "%s TEXT%s" % (c, " PRIMARY KEY" if c == "id" else "") for c in columns)
            self.db.execute("CREATE TABLE IF NOT EXISTS %s (%s)" % (table, cols))

    @property
    def db(self):
        """This thread's connection. One per thread, never shared: sqlite3
        connections are not safe to use from two threads at once."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, uri=self._uri, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None  # autocommit; no multi row invariants
            if not self._uri:
                conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    # ----------------------------------------------------------------- reads

    def _where(self, resource, thread, where):
        """Turn (thread, query grammar where) into a SQL fragment and params."""
        columns = TABLES[resource]
        sql, params = [], []
        if thread is not None:
            column = THREAD_COLUMN.get(resource, DEFAULT_THREAD_COLUMN)
            if resource == "patient":
                sql.append("id IN (SELECT patient FROM encounter WHERE id = ?)")
            else:
                sql.append("%s = ?" % column)
            params.append(thread)
        for field, cond in (where or {}).items():
            if field not in columns:
                raise ValueError("%s has no field %r" % (resource, field))
            if cond == "*":
                sql.append("(%s IS NOT NULL AND %s != '')" % (field, field))
            elif isinstance(cond, dict):
                for op, symbol in (("gte", ">="), ("lt", "<"), ("gt", ">"), ("lte", "<=")):
                    if op in cond:
                        sql.append("%s %s ?" % (field, symbol))
                        params.append(_text(cond[op]))
            else:
                sql.append("%s = ?" % field)
                params.append(_text(cond))
        return (" AND ".join(sql) or "1=1"), params

    def count(self, resource, *, thread, where):
        clause, params = self._where(resource, thread, where)
        row = self.db.execute(
            "SELECT COUNT(*) AS n FROM %s WHERE %s" % (_table(resource), clause),
            params).fetchone()
        return row["n"]

    def select(self, resource, *, thread, where, fields, limit=50):
        for f in fields:
            if f not in TABLES[resource]:
                raise ValueError("%s has no field %r" % (resource, f))
        clause, params = self._where(resource, thread, where)
        cols = ", ".join(fields) if fields else "*"
        rows = self.db.execute(
            "SELECT %s FROM %s WHERE %s ORDER BY created_date, id LIMIT ?"
            % (cols, _table(resource), clause), params + [int(limit)]).fetchall()
        return [dict(r) for r in rows]

    def threads(self, *, workflow, scope="today"):
        """Every encounter in scope, newest first, with its subject fields.

        scope is a VIEW_SCOPES value. "open" means the encounter has not been
        closed at reception; whether the clinical line is finished is a
        question about flags, so the kernel answers it, not the store.
        """
        sql = "SELECT * FROM encounter"
        params = []
        if scope == "today":
            sql += " WHERE created_date >= ?"
            params.append(_start_of("day"))
        elif scope == "open":
            sql += " WHERE status != 'completed'"
        sql += " ORDER BY created_date DESC, id"
        out = []
        for row in self.db.execute(sql, params).fetchall():
            subject = {"encounter": row["id"], "token": row["token"],
                       "status": row["status"]}
            if row["patient"]:
                patient = self.db.execute(
                    "SELECT * FROM patient WHERE id = ?", [row["patient"]]).fetchone()
                if patient:
                    subject.update(dict(patient))
            out.append(ThreadRef(id=row["id"], workflow=workflow, subject=subject,
                                 opened_at=row["created_date"] or ""))
        return out

    def stored_flags(self, thread):
        rows = self.db.execute(
            "SELECT flag FROM thread_flag WHERE thread = ?", [thread]).fetchall()
        return frozenset(r["flag"] for r in rows)

    # ---------------------------------------------------------------- writes

    def write(self, resource, record, *, thread):
        """Write one row of `resource` and return its id.

        The kernel hands over a row the operation's mapping declaration
        produced, so nothing here reads a link_id or invents a unit. What is
        left is this adapter's own schema: the thread join, and the fact that
        a second patient row on a thread is an update of the first person and
        not a second person.

        Fan out happens above this line. Three vitals are three calls, because
        dispensed.complete is a count comparison and one row per prescription
        would break it.
        """
        record = dict(record)
        if resource == "patient" and "id" not in record:
            # Registration made the row; linking an ABHA updates it. Which one
            # this is does not need the operation's name, only the join.
            existing = self.select("patient", thread=thread, where={},
                                   fields=["id"], limit=1)
            if existing:
                record["id"] = existing[0]["id"]
        written = self._put(resource, record, thread=thread)
        if resource == "patient":
            # The adapter owns the join, so it also maintains it: a patient
            # registered against an empty thread is attached to it here.
            encounter = self.db.execute(
                "SELECT patient FROM encounter WHERE id = ?", [thread]).fetchone()
            if encounter and not encounter["patient"]:
                self._put("encounter", {"id": thread, "patient": written},
                          thread=thread)
        return written

    def _put(self, resource, record, *, thread):
        """Insert, or update the named columns when the id already exists.

        The thread column is filled in here so no caller has to know the join.
        """
        columns = TABLES[_table(resource)]
        # A column this table does not have is refused, not filtered away.
        # Silently dropping a mapped clinical value is the worst failure this
        # file could have, and a mapping typo is exactly how it would happen.
        unknown = sorted(set(record) - set(columns))
        if unknown:
            raise ValueError("%s has no column %s" % (resource, ", ".join(unknown)))
        record = {k: _text(v) for k, v in record.items()}
        column = THREAD_COLUMN.get(resource, DEFAULT_THREAD_COLUMN)
        if column and column != "id":
            record.setdefault(column, thread)
        elif resource == "encounter":
            record.setdefault("id", thread)
        record.setdefault("id", new_id(resource))
        record.setdefault("created_date", now())
        rid = record["id"]

        exists = self.db.execute(
            "SELECT 1 FROM %s WHERE id = ?" % _table(resource), [rid]).fetchone()
        if exists:
            sets = [k for k in record if k != "id"]
            self.db.execute(
                "UPDATE %s SET %s WHERE id = ?"
                % (_table(resource), ", ".join("%s = ?" % k for k in sets)),
                [record[k] for k in sets] + [rid])
        else:
            keys = list(record)
            self.db.execute(
                "INSERT INTO %s (%s) VALUES (%s)"
                % (_table(resource), ", ".join(keys), ", ".join("?" * len(keys))),
                [record[k] for k in keys])
        return rid

    def open_thread(self, *, token=None, actor=None):
        """Start an empty visit and return its thread id.

        Not one of the Store protocol's nine methods: the protocol has no way
        to say "open a thread", which is a gap worth reporting rather than
        working around. A thread being an encounter row is adapter knowledge,
        so making one lives here. It records no clinical fact.
        """
        thread = new_id("enc")
        self._put("encounter", {"id": thread, "status": "in_progress",
                                "token": token or thread[-3:], "created_by": actor},
                  thread=thread)
        return thread

    def raise_flag(self, thread, flag, *, actor=None):
        """Idempotent: raising a flag twice is one row, not two.

        The kernel checks the flag is one the workflow declares stored; this
        method does not, because the adapter has never read a workflow.
        """
        if flag in self.stored_flags(thread):
            return
        self.db.execute(
            "INSERT INTO thread_flag (id, thread, flag, created_by, created_date)"
            " VALUES (?, ?, ?, ?, ?)",
            [new_id("flag"), thread, flag, actor, now()])

    # -------------------------------------------------- proposals and audit

    def put_proposal(self, proposal):
        row = dict(proposal.__dict__)
        row["payload"] = json.dumps(row["payload"])
        row["flags_raised"] = json.dumps(row["flags_raised"])
        row["final_payload"] = (json.dumps(row["final_payload"])
                                if row["final_payload"] is not None else None)
        keys = [k for k in TABLES["proposal"] if k in row]
        self.db.execute(
            "INSERT OR REPLACE INTO proposal (%s) VALUES (%s)"
            % (", ".join(keys), ", ".join("?" * len(keys))), [row[k] for k in keys])

    def proposal(self, proposal_id):
        row = self.db.execute(
            "SELECT * FROM proposal WHERE id = ?", [proposal_id]).fetchone()
        return _proposal(row) if row else None

    def proposals(self, thread, *, status=None):
        sql = "SELECT * FROM proposal WHERE thread = ?"
        params = [thread]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at, id"
        return [_proposal(r) for r in self.db.execute(sql, params).fetchall()]

    def append_audit(self, record):
        row = dict(record.__dict__)
        row["payload"] = json.dumps(row["payload"])
        keys = list(TABLES["audit"])
        self.db.execute(
            "INSERT INTO audit (%s) VALUES (%s)"
            % (", ".join(keys), ", ".join("?" * len(keys))),
            [row.get(k) for k in keys])

    def audit(self, thread):
        rows = self.db.execute(
            "SELECT * FROM audit WHERE thread = ? ORDER BY at, id", [thread]).fetchall()
        return [AuditRecord(**dict(dict(r), payload=json.loads(r["payload"] or "{}")))
                for r in rows]


def _table(resource):
    if resource not in TABLES:
        raise ValueError("no table for resource %r" % resource)
    if not _IDENT.match(resource):
        raise ValueError("bad resource name %r" % resource)
    return resource


def _text(value):
    """Everything is TEXT. Numbers keep their ordering because the columns that
    get compared with gte or lt are ISO dates, which sort as strings."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value)


def _proposal(row):
    return Proposal(
        id=row["id"], thread=row["thread"], operation=row["operation"],
        payload=json.loads(row["payload"] or "{}"), proposed_by=row["proposed_by"],
        surface=row["surface"], status=row["status"], created_at=row["created_at"],
        flags_raised=json.loads(row["flags_raised"] or "[]"),
        decided_by=row["decided_by"], decided_at=row["decided_at"],
        final_payload=(json.loads(row["final_payload"])
                       if row["final_payload"] else None))


def _start_of(window):
    """The first instant of the metric window, as an ISO string to compare with.

    A week and a month are rolling, not calendar: seven and thirty days back.
    A PHC's "this week" question is "since last week", and a rolling window
    needs no locale.
    """
    day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "all":
        return "0000-01-01T00:00:00+00:00"
    days = {"day": 0, "week": 6, "month": 29}.get(window, 0)
    return (day - timedelta(days=days)).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Seed. A handful of patients standing at different points in the line, so the
# queue, the badges and the confirm flow all have something to draw.
# --------------------------------------------------------------------------

SEED_PEOPLE = [
    # (encounter, token, patient fields, how far along)
    ("enc-001", "A01", dict(name="Lakshmi Bai", age=29, sex="female",
                            village="Sonpur", phone="9800000001"), "walk_in"),
    ("enc-002", "A02", dict(name="Kamala Devi", age=34, sex="female",
                            village="Sonpur", phone="9800000002"), "registered"),
    ("enc-003", "A03", dict(name="Ramesh Kumar", age=61, sex="male",
                            village="Bhagwanpur", phone="9800000003",
                            abha_number="12-3456-7890-1234"), "vitals_critical"),
    ("enc-004", "A04", dict(name="Iqbal Ahmed", age=52, sex="male",
                            village="Sonpur", phone="9800000004",
                            abha_number="12-3456-7890-5678"), "at_lab"),
    ("enc-005", "A05", dict(name="Sunita Bai", age=27, sex="female",
                            village="Rampur", phone="9800000005"), "at_pharmacy"),
    ("enc-006", "A06", dict(name="Meera Patel", age=45, sex="female",
                            village="Rampur", phone="9800000006",
                            abha_number="12-3456-7890-9012"), "complete"),
]


def seed(store):
    """Populate an empty store. Returns the encounter ids, in queue order."""
    stamp = now()
    for i, (enc, token, person, stage) in enumerate(SEED_PEOPLE):
        store.db.execute(
            "INSERT INTO encounter (id, patient, status, token, created_by, created_date)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [enc, None if stage == "walk_in" else "pat-%03d" % (i + 1),
             "completed" if stage == "complete" else "in_progress",
             token, "seed", stamp])
        if stage == "walk_in":
            continue
        store.db.execute(
            "INSERT INTO patient (id, name, age, sex, phone, village, category,"
            " abha_number, created_by, created_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["pat-%03d" % (i + 1), person["name"], str(person["age"]), person["sex"],
             person["phone"], person["village"], "general",
             person.get("abha_number"), "seed", stamp])
        if stage == "registered":
            continue

        vitals = [("systolic", 186 if stage == "vitals_critical" else 118, "mm[Hg]"),
                  ("diastolic", 112 if stage == "vitals_critical" else 76, "mm[Hg]"),
                  ("pulse", 92, "/min")]
        for code, value, unit in vitals:
            store._put("observation", {"category": "vital-signs", "code": code,
                                        "value": value, "unit": unit,
                                        "created_by": "seed", "created_date": stamp},
                        thread=enc)
        if stage == "vitals_critical":
            store.raise_flag(enc, "vitals.flagged", actor="seed")
            continue

        store._put("notes", {"text": "Fever three days, no red flags on examination.",
                              "created_by": "seed", "created_date": stamp}, thread=enc)
        if stage == "at_lab":
            store._put("service_request", {"code": "CBC", "status": "active",
                                            "created_by": "seed",
                                            "created_date": stamp}, thread=enc)
            continue

        for medication, dose in (("Paracetamol 500mg", "1 tab TDS x 3 days"),
                                 ("ORS sachet", "1 sachet after each loose stool")):
            store._put("medication_request",
                        {"medication": medication, "dosage_instruction": dose,
                         "status": "active", "created_by": "seed",
                         "created_date": stamp}, thread=enc)
        if stage == "at_pharmacy":
            continue

        for medication in ("Paracetamol 500mg", "ORS sachet"):
            store._put("medication_dispense",
                        {"medication": medication, "quantity": "1", "status": "completed",
                         "created_by": "seed", "created_date": stamp}, thread=enc)

    # One proposal waiting for a human, so the confirm path has a subject on
    # screen the moment the app starts. Proposed by the agent, over MCP.
    store.put_proposal(Proposal(
        id="prop-seed-001", thread="enc-004", operation="phc.op.rx-prescribe",
        payload={"medications": [{"medication": "Amoxicillin 500mg",
                                  "dosage_instruction": "1 cap TDS x 5 days"}]},
        proposed_by="agent:demo", surface="mcp", status="pending", created_at=stamp))
    store.append_audit(AuditRecord(
        id=new_id("aud"), thread="enc-004", operation="phc.op.rx-prescribe",
        actor="agent:demo", surface="mcp",
        payload={"medications": [{"medication": "Amoxicillin 500mg"}]},
        outcome="proposed", at=stamp, proposal="prop-seed-001"))
    return [e for e, *_ in SEED_PEOPLE]
