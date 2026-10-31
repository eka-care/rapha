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
- Column names are taken from care/emr/models and are UNVERIFIED against any
  running system of record. They are kept because they are FHIR shaped, which
  costs nothing and keeps a second adapter cheap. Adapter 1 (adapters/care)
  used to record how each name was established; it was deleted when patients
  moved to Eka's directory, so there is no longer a second opinion on any name
  in here. Treat them as this file's own choices.
- write() takes one row, already shaped by the operation's declared mapping
  (kernel/mapping.py). This adapter no longer knows what a blood pressure is,
  which is the point: a second adapter inherits the same mapping instead of deriving
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
import os
import re
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from kernel.contracts import AuditRecord, Proposal, ThreadRef

# One table per resource this bundle's operations read or write, plus the
# kernel's own three. Columns are query grammar field names, verbatim.
TABLES = {
    # Two identifier columns, neither of them this row's identity.
    # `abha_number` is a national identifier and `directory_id` is Eka's own
    # (its `oid`); both are facts about a person rather than our name for
    # their row, which is why `id` stays ours. kernel/directory.py says why at
    # length, and the short version is that a record is created when a person
    # is in front of a clerk, which may be while no registry can be reached.
    #
    # `directory_synced` is freshness, not status. There is no
    # `directory_status`: a row with a directory_id is known to the directory
    # and one without is not, so one column decides and two facts cannot
    # disagree about whether somebody gets published twice.
    "patient": ("id", "name", "age", "sex", "phone", "village", "category",
                "abha_number", "directory_id", "directory_synced",
                "created_by", "created_date"),
    "encounter": ("id", "patient", "status", "token", "created_by", "created_date"),
    # A coding is three columns, not one: the code, the system it is from, and
    # the display the value set gave it. Flat, because a district count is
    # `WHERE code = '8480-6'` and a trend is an ORDER BY, and both want a
    # column rather than a JSON path. CARE stores codings in untyped
    # JSONFields (care/emr/models/observation.py:9-11), which is why nothing
    # there can count them without unpacking JSON in SQL.
    #
    # code_display is stored rather than looked up again on read for two
    # reasons. A screen that draws a row must not need a terminology to draw
    # it, and the display is part of what was recorded: a value set that
    # renames a concept next year must not silently restate what a nurse
    # wrote this year.
    "observation": ("id", "encounter", "category", "code", "code_system",
                    "code_display", "value", "unit", "unit_system",
                    "created_by", "created_date"),
    # A diagnosis is a coded condition, a clinical status, a verification
    # status and an onset, each of the three codes carrying the system it came
    # from. Flat for the reason observation is flat: a district count of a
    # condition is a WHERE on one column.
    "condition": ("id", "encounter", "code", "code_system", "code_display",
                  "clinical_status", "clinical_status_system",
                  "verification_status", "verification_status_system",
                  "onset", "created_by", "created_date"),
    "notes": ("id", "encounter", "text", "created_by", "created_date"),
    # A prescription line is five answers, not a sentence. `dosage_instruction`
    # is gone: it held the dose and the frequency as prose, so neither could be
    # counted and neither reached ABDM as a Dosage.
    "medication_request": ("id", "encounter", "medication", "medication_system",
                           "medication_display", "dose", "dose_unit",
                           "dose_unit_system", "route", "route_system",
                           "route_display", "frequency", "frequency_system",
                           "frequency_display", "duration", "duration_unit",
                           "duration_unit_system",
                           # R4 makes MedicationRequest.intent required and
                           # fixes nothing, so it is declared in the atom as a
                           # constant and stored, rather than hard-coded in
                           # kernel/fhir.py where the projection would be
                           # deciding what a prescription is.
                           "intent",
                           "status", "created_by", "created_date"),
    "medication_dispense": ("id", "encounter", "medication", "quantity", "status",
                            "created_by", "created_date"),
    "service_request": ("id", "encounter", "code", "status",
                        "created_by", "created_date"),
    # `code_system` for the same reason observation has one: a code with no
    # system is unresolvable in FHIR R4 and unexportable to ABDM. No
    # code_display here, because a report is read through its observations and
    # duplicating the display on both rows is two places for one fact.
    "diagnostic_report": ("id", "encounter", "code", "code_system", "conclusion",
                          "status", "created_by", "created_date"),
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

# The kernel's own two records join and date themselves differently from a
# clinical resource: {table: (thread column, date column)}. thread_flag does
# not, so it stays in THREAD_COLUMN above.
KERNEL_RECORD = {"proposal": ("thread", "created_at"), "audit": ("thread", "at")}

# What the seed writes as the author of a thread it opened. It is how a demo
# thread is told from a real one, which is what roll_seed_forward() needs.
SEED_ACTOR = "seed"

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
        self.roll_seed_forward()

    def roll_seed_forward(self):
        """Move a stale demo day to today, and return how many days it moved.

        Every queue view is `scope: today`, which is what a queue means, so a
        file seeded yesterday drew an empty workspace this morning and the
        documented fix was "delete the SQLite file and restart". That throws
        away whatever was done on it. Instead, the seeded threads walk
        forward: the whole demo day shifts by whole days, keeping the time of
        day and the order of every row inside it.

        Only threads the seed opened move, found by `encounter.created_by =
        'seed'`, and only rows dated on the seed's own day, so real work done
        on a seeded thread after that day keeps the date it happened on and
        nothing is ever pushed into the future. A thread a person opened is
        never touched: "today" still means today for real work.

        Called from __init__, so every process that opens the file gets it,
        including the ones this adapter does not own.
        """
        row = self.db.execute("SELECT MAX(created_date) AS d FROM encounter"
                              " WHERE created_by = ?", [SEED_ACTOR]).fetchone()
        if not row or not row["d"]:
            return 0
        try:
            seeded_on = date.fromisoformat(row["d"][:10])
        except ValueError:
            return 0        # a hand edited date is not worth a dead constructor
        days = (datetime.now(timezone.utc).date() - seeded_on).days
        if days <= 0:
            return 0
        cutoff = (seeded_on + timedelta(days=1)).isoformat()
        # The clamp this docstring already promises ("nothing is ever pushed
        # into the future") was never enforced: rolling forward by whole
        # DAYS while keeping the time of day means every row whose seeded
        # time-of-day is later than the current wall-clock time lands in the
        # future for the ~11-23 hours of "today" before that time-of-day
        # arrives. A future opened_at makes elapsedMinutes() negative, which
        # is what made the wait rule (a 2px bar clamped only above, at 1)
        # paint backwards out of the row's own container, and made
        # ageLabel's own Math.max(0, ...) print "0m" on every row all day.
        # ISO-8601 timestamps of the same +00:00 shape sort lexicographically
        # in the same order they sort chronologically, so a plain string MIN
        # against `now` is the whole clamp -- no date parsing needed.
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        threads = [r["id"] for r in self.db.execute(
            "SELECT id FROM encounter WHERE created_by = ?", [SEED_ACTOR]).fetchall()]
        marks = ", ".join("?" * len(threads))
        for table in TABLES:
            join, column = KERNEL_RECORD.get(
                table, (THREAD_COLUMN.get(table, DEFAULT_THREAD_COLUMN),
                        "created_date"))
            if table == "encounter":
                where = "id IN (%s)" % marks
            elif table == "patient":
                where = ("id IN (SELECT patient FROM encounter WHERE id IN (%s))"
                         % marks)
            else:
                where = "%s IN (%s)" % (join, marks)
            # SQLite's datetime() understands the +00:00 suffix and drops it,
            # returning "YYYY-MM-DD HH:MM:SS". Everything that compares these
            # columns compares strings, so the isoformat spelling is put back
            # before the two candidates are compared and the smaller (i.e.
            # not-later-than-now) one kept.
            self.db.execute(
                "UPDATE %s SET %s = MIN(replace(datetime(%s, ?), ' ', 'T') || '+00:00', ?)"
                " WHERE %s AND %s < ?" % (table, column, column, where, column),
                ["+%d days" % days, now] + threads + [cutoff])
        return days

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
            if not existing and str(record.get("directory_id") or "").strip():
                # The same person, on a second visit. Until there was a
                # directory id, "the same person" was a question this adapter
                # could not answer: a patient registered on Tuesday and again
                # on Friday was two rows, so kernel/spine.py showed each of
                # them one visit and a returning patient had no history. The
                # directory's identifier is what makes it answerable, and
                # answering it is this adapter's business because the join is.
                #
                # Scoped to a thread=None lookup on purpose: it is a question
                # about a person across visits, not within one.
                same = self.select("patient", thread=None,
                                   where={"directory_id": record["directory_id"]},
                                   fields=["id"], limit=1)
                if same:
                    existing = same
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
            # Authorship and the moment a row was opened are both written
            # once, for the same reason: linking an ABHA updates the patient
            # row registration created, and the person linking is not the
            # person who registered, so overwriting created_by would lose
            # the registrar. created_date is the same fact about time rather
            # than identity -- write("patient", ...) above joins a person to
            # an already-open thread by re-_put-ing the encounter row with
            # only {id, patient}, and record.setdefault("created_date",
            # now()) a few lines up means every such join used to silently
            # reset opened_at to the moment the person was ATTACHED, not the
            # moment the thread was OPENED. That is what made a seeded
            # thread's declared age (see seed()'s own `minutes_ago`) vanish
            # the instant its patient row was written, and would do the same
            # to a real visit's wait-rule clock the moment ABHA linking ran.
            sets = [k for k in record if k not in ("id", "created_by", "created_date")]
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

    def record_directory_id(self, patient_id, directory_id, *, at, profile=None):
        """Record that the patient directory knows this person, and when.

        Not one of the Store protocol's ten methods, and the second gap worth
        reporting rather than working around: the protocol has no way to say
        "record a receipt from an external registry". `open_thread` above is
        the first, for the same reason.

        Deliberately narrow. It writes the identifier, the moment we agreed,
        and optionally the handful of profile columns a refresh may rewrite,
        on a row that must already exist. It cannot create a patient, it
        cannot touch an encounter, and it raises no flag, so it is not a path
        to a clinical write and `catalogue.guard` stays the only one.

        `profile` is already narrowed by kernel/directory.CACHED before it
        gets here, and is narrowed again against this table's own columns,
        because a cache refresh must never overwrite a facility's own words
        about a person with a directory's guess at them.
        """
        columns = TABLES["patient"]
        row = {"directory_id": str(directory_id), "directory_synced": str(at)}
        for key, value in (profile or {}).items():
            if key not in columns:
                raise ValueError("patient has no column %r" % key)
            if key in ("id", "directory_id", "created_by", "created_date"):
                raise ValueError("%r is not a profile column a refresh may "
                                 "rewrite" % key)
            if value not in (None, ""):
                row[key] = _text(value)
        found = self.db.execute("SELECT 1 FROM patient WHERE id = ?",
                                [patient_id]).fetchone()
        if not found:
            raise ValueError("no patient %r to record a directory id against"
                             % patient_id)
        self.db.execute(
            "UPDATE patient SET %s WHERE id = ?"
            % ", ".join("%s = ?" % k for k in row),
            list(row.values()) + [patient_id])
        return patient_id

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
        sql += " ORDER BY created_at, rowid"
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
        """Oldest first, as kernel.contracts.ThreadView promises.

        The tiebreak is `rowid` and not `id`. AuditRecord.at is ISO 8601 to
        the second (kernel/proposals.now()), so two decisions on one thread
        inside the same second tie on `at`, and `id` is a random uuid hex, so
        the order between them was whatever the hex sorted to. That is not a
        cosmetic problem: an audit panel showing a refusal after the write it
        refused, or a registration after the vitals recorded on it, reads as a
        different sequence of events from the one that happened, and the audit
        trail is the record we would defend. SQLite's implicit rowid is
        insertion order, so this is oldest first by construction with nothing
        to keep in sync. Store.proposals above has the same tie and the same
        fix.
        """
        rows = self.db.execute(
            "SELECT * FROM audit WHERE thread = ? ORDER BY at, rowid", [thread]).fetchall()
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
# Seed. Declared data, written here.
#
# The rows are the bundle's (bundles/<id>/seed.yaml) and this function is the
# only thing that knows how to put them on disk. Until 2026.09.13 the rows
# themselves lived up there in Python, so every bundle got a primary health
# centre's demo day: a laboratory opened on six outpatients with tokens like
# A01 and a pending Amoxicillin on a specimen. A third bundle now brings its
# own seed without touching this file, and a bundle with no seed.yaml starts
# empty, which is a supported outcome.
# --------------------------------------------------------------------------

def declared_seed(bundle_id=None):
    """The active bundle's seed rows. Empty when it declares none.

    Imported here rather than at module scope: an adapter reaching into the
    kernel's loader at import time would invert the layering in
    kernel/ARCHITECTURE.md. Inside one function it is what it looks like, a
    caller asking the kernel where a facility's fixtures live.
    """
    from kernel import declarations
    return declarations.load(bundle_id or os.environ.get("PHC_BUNDLE", "phc")).seed


def seed(store, threads=None):
    """Populate an empty store from a bundle's declared seed.

    `threads` is what Bundle.seed holds; None means the bundle PHC_BUNDLE
    names, which is the bundle api/main.py loaded. Returns the thread ids in
    declaration order, so an empty seed returns an empty list and writes
    nothing.

    Row ids are `seed-NNNN` in declaration order because select() orders by
    created_date then id and every seeded row shares one stamp: without it a
    report would list four analytes in whatever order uuid4 chose.
    """
    if threads is None:
        threads = declared_seed()
    stamp = now()
    serial = [0]
    # thread id -> the patient row it created, so a later thread can declare
    # itself the same person returning. Without this every seeded thread makes
    # its own patient row and the spine (kernel/spine.py) can only ever show
    # one visit per person, which is the one shape that cannot demonstrate it.
    patient_of = {}

    def row_id():
        serial[0] += 1
        return "seed-%04d" % serial[0]

    def stamped(record):
        return dict({"id": row_id(), "created_by": SEED_ACTOR,
                     "created_date": stamp}, **record)

    for t in threads:
        thread = t["id"]
        # A thread's own `minutes_ago` backdates only its encounter row (the
        # one column opened_at is read from, store.threads() above), so the
        # wait rule has a seeded row that is actually past a declared
        # target_minutes: without one, the spec's own acceptance criterion
        # ("one row seeded past target: exactly one [data-over]") is
        # unsatisfiable against the shipped fixture, since every other row
        # shares the same "now" stamp. roll_seed_forward's later day-walk
        # only ever adds whole days, so this relative offset survives it.
        minutes_ago = t.get("minutes_ago")
        opened = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds") \
            if minutes_ago else stamp
        store._put("encounter", {"id": thread, "token": t.get("token"),
                                 "status": t.get("status") or "in_progress",
                                 "created_by": SEED_ACTOR, "created_date": opened},
                   thread=thread)
        returning = t.get("same_patient_as")
        if returning:
            # The same person, back again. Point this encounter at the row the
            # earlier thread created rather than writing a second person with
            # the same name, which is what a duplicate registration looks like
            # and is not what a returning patient is.
            known = patient_of.get(returning)
            if known is None:
                raise ValueError(
                    "seed thread %r: same_patient_as %r, which has no patient "
                    "(is it declared later in the file?)" % (thread, returning))
            store._put("encounter", {"id": thread, "patient": known}, thread=thread)
            patient_of[thread] = known
        elif t.get("patient"):
            # write(), not _put(): attaching the person to the thread is the
            # adapter's own join and it is already written down once.
            patient_of[thread] = store.write("patient", stamped(t["patient"]), thread=thread)
        for record in t.get("rows") or []:
            record = dict(record)
            store._put(record.pop("resource"), stamped(record), thread=thread)
        for flag in t.get("flags") or []:
            store.raise_flag(thread, flag, actor=SEED_ACTOR)
        for entry in t.get("audit") or []:
            # A seeded thread that claims work was done has to say who did it:
            # "not actor of lab.op.result-enter" is evaluated against this
            # trail, so without these rows the demo day cannot show the rule.
            #
            # And what was recorded, not only that something was. The thread
            # draws a posted operation's values from this payload, so an entry
            # without one is a receipt for something invisible: a card headed
            # "Record vitals and triage" with no vitals under it.
            store.append_audit(AuditRecord(
                id=row_id(), thread=thread, operation=entry["operation"],
                actor=entry.get("actor"), surface=entry.get("surface", "rendered"),
                payload=entry.get("payload") or {},
                outcome=entry.get("outcome", "confirmed"), at=stamp))
        for p in t.get("proposals") or []:
            pid = p.get("id") or row_id()
            payload = p.get("payload") or {}
            store.put_proposal(Proposal(
                id=pid, thread=thread, operation=p["operation"], payload=payload,
                proposed_by=p.get("proposed_by"), surface=p.get("surface", "mcp"),
                status=p.get("status", "pending"), created_at=stamp))
            store.append_audit(AuditRecord(
                id=row_id(), thread=thread, operation=p["operation"],
                actor=p.get("proposed_by"), surface=p.get("surface", "mcp"),
                payload=payload, outcome="proposed", at=stamp, proposal=pid))
    return [t["id"] for t in threads]
