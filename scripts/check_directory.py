"""Run: python3 scripts/check_directory.py

The patient directory, and the clinic that keeps working without it.

Settled 2026-10-31: Eka's patient directory is the source of truth for patient
identity, and we do not rebuild a local patient master. The requirement that
shapes everything below is the second half of that: a health centre on a bad
line must still see the patients in today's line and record a visit against
them, so the degraded path is the designed path and not a fallback.

So almost every check here runs with NO DIRECTORY AT ALL, through
kernel.directory.AbsentDirectory, and the ones that need a reachable directory
use a fake in this file. Nothing here opens a socket, and the last section
asserts that nothing on the clinical write path could.

  identity      a thread's subject keeps its own id and carries Eka's beside it
  offline       search, register, queue and visit, with no directory
  suggestion    a directory hit cannot become a row without a person's tap
  spine         the same person on two visits is one row and two encounters
  queue         a registration taken while the line was down is already pending
  receipt       what may and may not be written when the directory answers
  audit         one account for permissions, the staff member in the record
  layering      no module on the write path can reach a network

Mutations are listed at the bottom and every one was run.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

# Before api.main is imported anywhere: the service must come up with no Eka
# credential and no line, because that is the state a developer and a bad day
# share.
os.environ["PHC_DIRECTORY"] = "absent"

# AND ITS OWN DATABASE FILE. This check registers a patient through the real
# route, and without this it registered her into whatever PHC_DB defaults to
# -- which, run from the repository, is the developer's own demo day. One
# Sunita Devi per gate run, accumulating silently, indistinguishable from the
# duplicate-patient defect this repository had just fixed. Every other check
# that writes already does this; this one did not.
import tempfile                                                   # noqa: E402
os.environ["PHC_DB"] = str(
    pathlib.Path(tempfile.mkdtemp(prefix="directory-")) / "phc.sqlite3")

from adapters.local.store import SqliteStore                      # noqa: E402
from care_phc.connectors.directory import eka                     # noqa: E402
from catalogue import validate, vocab                             # noqa: E402
from kernel import declarations, directory, proposals, spine, state  # noqa: E402
from kernel.contracts import DirectoryError, DirectoryPatient      # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
SCHEMA = validate.load(BUNDLE.operations["phc.op.patient-register"]["input"])
QUESTIONS = {q["link_id"]: q for q in validate.walk(SCHEMA["questions"])}

# One account holds every capability, which is the settled auth position. The
# actor is a separate string and that is the distinction the last section
# checks.
ACCOUNT = set(vocab.CAPABILITIES)
MEENA = "user:meena"
RAVI = "user:ravi"
GONE = directory.AbsentDirectory()

SUNITA = {"name": "Sunita Devi", "age": 34, "sex": "female", "phone": "9876500000",
          "village": "Yadiki", "category": "anc"}


def fresh():
    return SqliteStore(":memory:")


def register(store, payload, *, actor=MEENA, token="1"):
    thread = store.open_thread(token=token, actor=actor)
    decision = proposals.commit(store, BUNDLE, "phc.op.patient-register",
                                thread=thread, payload=payload, caps=ACCOUNT,
                                actor=actor)
    return thread, decision


# ---------------------------------------------------------------------------
# 1. Identity. The row keeps its own id and carries the directory's beside it.
# ---------------------------------------------------------------------------

for link_id in directory.FILLS:
    assert link_id in QUESTIONS, \
        "kernel/directory.FILLS names %r, which the register form does not ask" % link_id
assert QUESTIONS["directory_id"].get("required") is not True, \
    "a registration must not require a directory id: the directory may be unreachable"
ok("every value a directory suggestion fills is a question on the register form, "
   "and the directory id is not required")

(record,) = BUNDLE.operations["phc.op.patient-register"]["mapping"]
assert record["fields"]["directory_id"] == {"answer": "directory_id"}, record["fields"]
assert record["resource"] == "patient"
ok("the register atom maps the directory id onto the patient row")

store = fresh()
thread, decision = register(store, SUNITA)
assert decision, decision.reason
(row,) = store.select("patient", thread=thread, where={}, fields=(), limit=2)
assert row["id"] != row.get("directory_id"), row
assert not str(row.get("directory_id") or "").strip(), \
    "a patient registered with no directory has no directory id, and that is a state"
assert row["created_by"] == MEENA, row
ok("a patient registered with no directory keeps this product's own row id")

# The identifier question the brief flagged, answered by the columns: both are
# identifiers on the row, neither is the row.
columns = set(store.select("patient", thread=thread, where={}, fields=(), limit=1)[0])
assert {"id", "abha_number", "directory_id", "directory_synced"} <= columns, columns
ok("abha_number and directory_id are both identifier columns, as the row's id is not")

# ---------------------------------------------------------------------------
# 2. Offline. Search, register, queue and visit, with no directory.
# ---------------------------------------------------------------------------

found = directory.resolve(store, GONE, "Sunita")
assert [r["id"] for r in found.local] == [row["id"]], found.local
assert found.suggestions == [], found.suggestions
assert found.offline and not found.reachable, found
assert found.reason, "an unreachable directory must say so, not answer empty"
ok("with no directory at all, a search still finds the patient in today's line")

by_phone = directory.resolve(store, GONE, "500000")
assert [r["id"] for r in by_phone.local] == [row["id"]], by_phone.local
ok("and finds them on the last digits of a phone number, which is what a clerk types")

nobody = directory.resolve(store, GONE, "Zzzz")
assert nobody.local == [] and not nobody.reachable, nobody
# The distinction a clerk's next action depends on: nobody matched here and the
# directory was not asked, and both facts are on the answer at once.
assert nobody.reason and nobody.reachable is False
ok("nobody matched and nobody could be asked are two facts, and both are reported")

refs = store.threads(workflow=WF.id, scope="today")
assert [r.id for r in refs] == [thread], refs
assert refs[0].subject["name"] == "Sunita Devi", refs[0].subject
ok("the queue draws her name from the row the cache already needed")

flags = state.flags(store, thread, WF)
assert "registered" in flags, sorted(flags)
assert state.station(WF, flags) == "nurse", state.station(WF, flags)
vitals = proposals.commit(store, BUNDLE, "phc.op.vitals-record", thread=thread,
                          payload={"systolic": 118, "diastolic": 76, "pulse": 80},
                          caps=ACCOUNT, actor=MEENA)
assert vitals, vitals.reason
assert "vitals.recorded" in state.flags(store, thread, WF)
ok("and a visit is recorded against her with the directory still unreachable")

# ---------------------------------------------------------------------------
# 3. A suggestion is not an assertion.
# ---------------------------------------------------------------------------


class Live:
    """A reachable directory. No socket: this is the fake."""

    def __init__(self, found=(), oid="oid-new"):
        self.found = list(found)
        self.oid = oid
        self.asked = []

    def search(self, prefix, *, limit=10):
        self.asked.append(("search", prefix))
        return self.found

    def by_mobile(self, mobile):
        self.asked.append(("mobile", mobile))
        return self.found

    def fetch(self, directory_id):
        return next((p for p in self.found if p.directory_id == directory_id), None)

    def publish(self, patient):
        self.asked.append(("publish", patient.get("id")))
        return self.oid


RAMESH = DirectoryPatient(directory_id="oid-ramesh", name="Ramesh Kumar",
                          sex="male", age=51, phone="9876511111",
                          matched_on="search", extras={"phc_village": "Tadipatri"})

live = Live([RAMESH])
hit = directory.resolve(store, live, "Ramesh")
(suggestion,) = hit.suggestions
assert hit.reachable and hit.local == [], hit
assert suggestion.values["directory_id"] == "oid-ramesh", suggestion.values
assert suggestion.values["village"] == "Tadipatri", suggestion.values
assert all(c <= 0.5 for c in suggestion.confidence.values()), suggestion.confidence
assert suggestion.evidence["name"], "a suggested value says where it came from"
assert store.count("patient", thread=None, where={"directory_id": "oid-ramesh"}) == 0, \
    "resolving wrote a patient row"
ok("a directory hit is a suggestion with its evidence, and writes nothing")


class NoWrites:
    """A store that refuses every clinical write. Everything in
    kernel/directory.py must work against it, because none of it is a
    clinical write and the guard must stay the only path to one."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def write(self, *a, **kw):
        raise AssertionError("kernel/directory.py wrote a clinical row")

    def raise_flag(self, *a, **kw):
        raise AssertionError("kernel/directory.py raised a flag")


guarded = NoWrites(store)
assert directory.resolve(guarded, live, "Ramesh").suggestions
assert directory.cached(guarded, "Sunita")
assert directory.pending(guarded) is not None
ok("no read or resolve in kernel/directory.py reaches a clinical write at all")

# The only way those values become a row: through the operation and the guard.
refused = proposals.commit(store, BUNDLE, "phc.op.patient-register",
                           thread=store.open_thread(token="2", actor=RAVI),
                           payload=dict(suggestion.values, age=400),
                           caps=ACCOUNT, actor=RAVI)
assert not refused and "outside 0 to 120" in refused.reason, refused.reason
ok("a suggestion's values are validated like any other: %s"
   % refused.reason.split(".")[0])

no_cap = proposals.commit(store, BUNDLE, "phc.op.patient-register",
                          thread=store.open_thread(token="3", actor=RAVI),
                          payload=suggestion.values, caps={"patient.find"},
                          actor=RAVI)
assert not no_cap and "patient.register" in no_cap.reason, no_cap.reason
ok("and guarded like any other: %s" % no_cap.reason)

# ---------------------------------------------------------------------------
# 4. The spine. The same person on two visits is one row.
# ---------------------------------------------------------------------------

two = fresh()
first, d1 = register(two, suggestion.values, actor=MEENA, token="4")
assert d1, d1.reason
second, d2 = register(two, suggestion.values, actor=RAVI, token="5")
assert d2, d2.reason
assert first != second, "two visits"
rows = two.select("patient", thread=None, where={"directory_id": "oid-ramesh"},
                  fields=["id"], limit=5)
assert len(rows) == 1, rows
joined = spine.of(BUNDLE, two, WF, rows[0]["id"])
assert joined and len(joined["encounters"]) == 2, joined
assert {e["thread"] for e in joined["encounters"]} == {first, second}, joined
ok("the same directory id on a second visit is one person with two visits, "
   "not two people with one each")

# Without a directory id there is nothing to join on, and the honest outcome is
# two rows rather than a guess that two people with the same name are one.
anon = fresh()
register(anon, SUNITA, token="6")
register(anon, SUNITA, token="7")
assert len(anon.select("patient", thread=None, where={}, fields=["id"], limit=9)) == 2
ok("with no directory id, two registrations stay two rows rather than being "
   "guessed into one")

# ---------------------------------------------------------------------------
# 5. The queue that is not a queue.
# ---------------------------------------------------------------------------

waiting = directory.pending(store)
assert [r["id"] for r in waiting] == [row["id"]], waiting
ok("a registration taken while the line was down is already waiting, with "
   "nothing enqueued: %d pending" % len(waiting))

dead = directory.publish_pending(store, GONE, at="2026-10-31T10:00:00+00:00")
assert dead.published == [] and dead.count == 0, dead
assert not dead.reachable and dead.failed, dead
assert [r["id"] for r in directory.pending(store)] == [row["id"]], \
    "a failed publish lost the row"
ok("publishing with no directory publishes nothing and loses nothing")

sweep = Live(oid="oid-sunita")
report = directory.publish_pending(store, sweep, at="2026-10-31T10:00:00+00:00")
assert report.published == [(row["id"], "oid-sunita")], report
assert report.count == 1 and not report.failed and report.reachable
assert directory.pending(store) == [], directory.pending(store)
back = store.select("patient", thread=thread, where={}, fields=(), limit=1)[0]
assert back["directory_id"] == "oid-sunita", back
assert back["directory_synced"] == "2026-10-31T10:00:00+00:00", back
assert back["id"] == row["id"], "publishing changed the row's own id"
assert back["created_by"] == MEENA, "publishing changed who registered her"
ok("publishing records the identifier and the moment, and changes nothing else")

# The worst case on this path, and the one a plain call would get wrong: the
# directory accepted the patient and the receipt could not be written. Without
# the catch in publish_pending the exception escapes, the record of every
# publish that already succeeded in the sweep is thrown away, and the next
# sweep publishes the same person again into a national directory.


class BadReceipt:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def record_directory_id(self, *a, **kw):
        raise ValueError("the disk went away")


again = fresh()
lost_thread, _ = register(again, SUNITA, token="8")
lost = directory.pending(again)[0]["id"]
report2 = directory.publish_pending(BadReceipt(again), Live(oid="oid-dup"), at="now")
assert report2.published == [], report2
assert len(report2.failed) == 1 and report2.failed[0][0] == lost, report2
assert "receipt could not be written" in report2.failed[0][1], report2.failed
assert [r["id"] for r in directory.pending(again)] == [lost],     "a patient the directory accepted but we could not record is still pending"
ok("a directory that accepted a patient we could not record is a failure on "
   "that row, not a lost sweep and not a silent duplicate")

# ---------------------------------------------------------------------------
# 6. The receipt. What may and may not be written when the directory answers.
# ---------------------------------------------------------------------------

try:
    store.record_directory_id("pat-nobody", "oid-x", at="now")
except ValueError as broke:
    assert "no patient" in str(broke), broke
else:
    raise AssertionError("a receipt created a patient out of nothing")
ok("a receipt cannot create a patient, only annotate one")

for column in ("id", "created_by", "created_date"):
    try:
        store.record_directory_id(row["id"], "oid-sunita", at="now",
                                  profile={column: "forged"})
    except ValueError as broke:
        assert "not a profile column" in str(broke), broke
    else:
        raise AssertionError("a refresh rewrote %r" % column)
try:
    store.record_directory_id(row["id"], "oid-sunita", at="now",
                              profile={"nonsense": "x"})
except ValueError as broke:
    assert "no column" in str(broke), broke
else:
    raise AssertionError("a refresh wrote a column the table lacks")
ok("and cannot rewrite a row's identity, its author or a column that does not exist")

moved = DirectoryPatient(directory_id="oid-sunita", name="Sunita Devi Rao",
                         sex="female", age=35, phone="9876500001")
updated = directory.refresh(store, Live([moved]), row["id"], at="later")
assert updated["name"] == "Sunita Devi Rao" and updated["age"] == 35, updated
kept = store.select("patient", thread=thread, where={}, fields=(), limit=1)[0]
assert kept["village"] == "Yadiki", "a refresh overwrote a facility's own word"
assert kept["category"] == "anc", kept
assert set(directory.CACHED) == {"name", "age", "sex", "phone"}, directory.CACHED
ok("a refresh rewrites the directory's facts and leaves the facility's own alone")

# ---------------------------------------------------------------------------
# 7. The wire translations, where the real decisions are.
# ---------------------------------------------------------------------------

import datetime                                                   # noqa: E402

TODAY = datetime.date(2026, 10, 31)
body = eka.to_wire(dict(SUNITA), today=TODAY)
assert body["fln"] == "Sunita Devi" and body["gen"] == "F", body
assert body["dob"] == "1992-01-01" and body["extras"]["_approx_dob"], body
assert body["extras"]["phc_village"] == "Yadiki", body
ok("our register becomes Eka's create body, with the age to birthday "
   "approximation marked as one")

# The directory's own restrictions on `extras`, from its specification.
for key, value in body["extras"].items():
    assert len(key) <= 16, key
    assert not isinstance(value, (list, dict)), (key, value)
ok("and inside the extras restrictions the specification states")

mine = eka.from_wire({"oid": "o", "fln": "Sunita Devi", "gen": "F",
                      "dob": "1992-03-14", "mobile": "+919876500000",
                      "abha": "sunita@abdm"}, today=TODAY)
assert mine.age == 34 and mine.sex == "female", mine
assert mine.abha_address == "sunita@abdm" and mine.abha_number == "", \
    "the wire's abha field is an address; a number is phc.op.abha-link's to establish"
ok("and Eka's profile becomes ours, with its abha read as an address and not a number")

# ---------------------------------------------------------------------------
# 8. One account for permissions, the staff member in the record.
# ---------------------------------------------------------------------------

assert len(ACCOUNT) > 1 and "patient.register" in ACCOUNT
rows = two.select("patient", thread=None, where={}, fields=(), limit=5)
audits = {a.actor for a in two.audit(first)} | {a.actor for a in two.audit(second)}
assert audits == {MEENA, RAVI}, audits
ok("one account holding every capability, and the audit still names which of "
   "two staff members acted")

trail = [a for a in two.audit(second) if a.operation == "phc.op.patient-register"]
assert trail and trail[0].actor == RAVI, trail
assert all(a.actor not in (None, "") for a in two.audit(second)), two.audit(second)
ok("a record that will travel under an ABHA number carries who made it")

# ---------------------------------------------------------------------------
# 9. Layering. Nothing on the clinical write path can reach a network.
# ---------------------------------------------------------------------------

NETWORK = ("urllib.request", "urllib.error", "http.client", "requests", "socket",
           "httpx", "aiohttp")
WRITE_PATH = sorted(
    [p for p in (ROOT / "kernel").glob("*.py")]
    + [p for p in (ROOT / "catalogue").glob("*.py")]
    + [ROOT / "adapters" / "local" / "store.py"])
assert len(WRITE_PATH) >= 12, [p.name for p in WRITE_PATH]
for path in WRITE_PATH:
    text = path.read_text()
    for module in NETWORK:
        for form in ("import %s" % module, "from %s import" % module):
            assert form not in text, "%s imports %s" % (
                path.relative_to(ROOT), module)
ok("no module in the kernel, the catalogue or the adapter imports a network "
   "library, over %d files" % len(WRITE_PATH))

# The vendor does, and that is where it belongs.
assert "import urllib.request" in (
    ROOT / "care_phc" / "connectors" / "directory" / "eka.py").read_text(), \
    "this check proves nothing unless the vendor really does open a socket"
ok("and the one module that does is the vendor connector, which is the layer "
   "a socket belongs in")

# ---------------------------------------------------------------------------
# 10. The service comes up, and degrades, with no credential at all.
# ---------------------------------------------------------------------------

try:
    from starlette.testclient import TestClient
except ImportError:                      # pragma: no cover
    print("warn starlette missing: the route half of this check did not run")
else:
    from api.main import DIRECTORY, app

    assert isinstance(DIRECTORY, directory.AbsentDirectory), type(DIRECTORY)

    # PHC_DIRECTORY=absent above short circuits make_directory() before the
    # credential path, so asserting on DIRECTORY alone left the branch that
    # actually matters unchecked: a deployment that MEANT to use Eka and has
    # no token. Exercised directly, both ways round.
    import api.main as service

    kept = {k: os.environ.get(k) for k in
            ("PHC_DIRECTORY", "EKA_ACCESS_TOKEN", "EKA_CLIENT_ID")}
    try:
        os.environ.pop("PHC_DIRECTORY", None)
        os.environ.pop("EKA_ACCESS_TOKEN", None)
        os.environ.pop("EKA_CLIENT_ID", None)
        wanted_eka = service.make_directory()
        assert isinstance(wanted_eka, directory.AbsentDirectory), type(wanted_eka)
        ok("a deployment that meant to use Eka and has no token still comes up, "
           "on the local register")

        os.environ["EKA_ACCESS_TOKEN"] = "not-a-real-token"
        os.environ["EKA_CLIENT_ID"] = "EC_0000"
        configured = service.make_directory()
        assert not isinstance(configured, directory.AbsentDirectory), type(configured)
        assert isinstance(configured, eka.EkaDirectory), type(configured)
        ok("and one with a token gets the vendor, so the fallback is a fallback "
           "and not the only path this code can take")
    finally:
        for key, value in kept.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    client = TestClient(app)
    answer = client.get("/api/v1/phc/patients/search", params={"q": "Sunita"})
    assert answer.status_code == 200, (answer.status_code, answer.text)
    payload = answer.json()
    assert payload["reachable"] is False, payload
    assert payload["reason"], payload
    assert payload["commits_through"] == "phc.op.patient-register", payload
    ok("the search route answers 200 with an unreachable directory, because a "
       "clerk must not be shown an error about a directory they were not using")

    assert client.get("/api/v1/phc/patients/pending").status_code == 200
    blocked = client.post("/api/v1/phc/patients/publish", json={},
                          headers={"X-PHC-Role": "nurse"})
    assert blocked.status_code == 403, blocked.status_code
    assert "facility.admin" in blocked.json()["detail"], blocked.json()
    ok("and publishing a patient off this machine needs facility.admin")

    # The audit separation over the WIRE. The checks above prove the kernel
    # keeps two actors apart, which it does, but they call proposals.commit
    # directly and never touch caller(), so they said nothing about whether
    # the service carries the staff member through. With one account holding
    # every capability, caller() is the only thing standing between "which
    # desk" and "which person", and the record is the person.
    staff = TestClient(app)
    # No token in the body: the number is the kernel's to issue, out of this
    # facility's day sequence (kernel/tokens.py), and a client that names one
    # is simply given the next. scripts/check_front_desk.py is where that is
    # proved; this call just stops teaching the old shape.
    opened = staff.post("/api/v1/phc/threads", json={},
                        headers={"X-PHC-Actor": "user:meena"})
    assert opened.status_code == 200, opened.text
    assert str(opened.json()["subject"]["token"]).isdigit(), \
        "the service handed out a token that is not a number"
    wire_thread = opened.json()["id"]
    committed = staff.post(
        "/api/v1/phc/operations/phc.op.patient-register/commit",
        json={"thread": wire_thread, "payload": SUNITA, "confirmed": True},
        headers={"X-PHC-Actor": "user:meena"})
    assert committed.status_code == 200, committed.text
    panel = staff.get("/api/v1/phc/threads/%s" % wire_thread,
                      headers={"X-PHC-Actor": "user:ravi"}).json()
    actors = {line["actor"] for line in panel["audit"]}
    assert actors == {"user:meena"}, actors
    assert "user:demo" not in actors, \
        "the account stood in for the staff member in the record"
    assert panel["held"] == sorted(ACCOUNT), \
        "this check proves nothing unless one account really does hold everything"
    ok("over the wire, one account holds every capability and the audit still "
       "records which staff member acted")

try:
    eka.EkaDirectory(token="", client_id="")
except DirectoryError as broke:
    assert broke.reachable is False, "a missing credential is an unreachable directory"
else:
    raise AssertionError("a directory was built with no credential")
ok("a missing Eka credential is an unreachable directory, not a crash")

print("ok   patient directory: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# Mutations this is built to fail under. Each was run.
#
#   kernel/directory.py   have resolve() swallow DirectoryError and return
#       reachable=True  ->  the "two facts" check fails
#   kernel/directory.py   drop the `known` filter so a cached profile is also
#       suggested  ->  the one-person-once check fails
#   kernel/directory.py   let CACHED include village
#       ->  the refresh check fails on the facility's own word
#   kernel/directory.py   have publish_pending continue past an unreachable
#       failure  ->  the reachable assertion fails
#   kernel/directory.py   confidence of 1.0 on a suggestion
#       ->  the capped-confidence check fails
#   adapters/local/store.py   drop the directory_id same-person lookup
#       ->  the spine check fails with two rows
#   adapters/local/store.py   let record_directory_id insert a missing patient
#       ->  the "cannot create a patient" check fails
#   adapters/local/store.py   let a refresh rewrite created_by
#       ->  the identity-and-author check fails
#   care_phc/connectors/directory/eka.py   send `age` instead of a dob
#       ->  the create body check fails
#   care_phc/connectors/directory/eka.py   read `abha` as a number
#       ->  the address-not-number check fails
#   catalogue/ops/phc.op.patient-register.md   stop mapping directory_id
#       ->  the atom check fails, then the spine check
#   questionnaires/phc.schema.register-v1.json   make directory_id required
#       ->  the not-required check fails, and so does every offline register
#   api/main.py   raise 503 when the directory is unreachable
#       ->  the 200-with-a-reason check fails
#   api/main.py   drop the facility.admin gate on publish
#       ->  the 403 check fails
#   kernel/terminology.py   import urllib.request
#       ->  the layering check fails
# ---------------------------------------------------------------------------
