"""Run: python3 scripts/check_front_desk.py

The front desk: the number a person is given, and how they got here.

What is being proved
--------------------
  sequence     tokens are numeric, one sequence per facility per day, and it
               increments whoever arrives
  one room     the desk's arrival and the poster's arrival draw from THE SAME
               sequence, interleaved in arrival order, so no two people in
               one waiting room are called the same number
  issued       the number is issued by the kernel. A client that asks for a
               particular one does not get it
  returned     the poster's arrival ANSWERS with the number, which is the
               channel by which it reaches the patient's own application
  provenance   a self registered arrival carries the mark its view declared,
               a desk arrival carries none, and the queue row carries it so
               the screen can filter by it
  declared     every word in all of that is the declaration's. The mark is
               read off the view, never spelled here

Why these and not the arithmetic
--------------------------------
The sequence rule itself is checked where it lives, by `python3 -m
kernel.tokens`, over a list and with no store at all. What that cannot reach
is whether the two ways into the queue actually share it, which is the whole
of the owner's decision and the one thing a second numbering scheme would
break silently: both routes would keep working and the waiting room would
have two number fours.

So this file drives the real service over a real SQLite file, through both
routes, and reads the queue back the way a screen does.

What this does NOT prove. No ABDM call is made and none is mocked. The
profile a scan-and-share patient consents to send arrives on a callback this
build does not have, by instruction: ABHA is on staging and real calls create
permanent national accounts. What is proved is the arrival half, which is the
half that owes somebody a number.

Mutations this is built to fail under are listed at the bottom.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

# Before api.main is imported: its own database file, so this check never
# reads or writes a developer's demo day, and no directory, because resolving
# who is standing at the desk is not what is being checked.
_DB = pathlib.Path(tempfile.mkdtemp(prefix="front-desk-")) / "phc.sqlite3"
os.environ["PHC_DB"] = str(_DB)
os.environ["PHC_DIRECTORY"] = "absent"

from kernel import declarations, tokens                       # noqa: E402
from kernel.contracts import Store                            # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")

# ---------------------------------------------------------------------------
# 0. What the declaration says. Nothing below spells any of this.
# ---------------------------------------------------------------------------

QUEUE = next(v for v in BUNDLE.views.values()
             if v.kind == "queue" and v.workflow == BUNDLE.workflow().id)
PROV = QUEUE.provenance
assert PROV, "this bundle's queue declares how an arrival got here"
assert set(PROV) == {"column", "mark", "label"}, PROV
COLUMN, MARK, LABEL = PROV["column"], PROV["mark"], PROV["label"]
assert COLUMN in QUEUE.columns, (COLUMN, QUEUE.columns)
assert COLUMN not in QUEUE.labels, \
    "a column is drawn as a pill or as a mark, never as both"
ok("the queue declares which column says how a row arrived, which value earns "
   "the mark, and what the chip for it is called; this file reads all three "
   "rather than spelling any of them")

try:
    from starlette.testclient import TestClient
except ImportError:                      # pragma: no cover
    print("warn starlette missing: the front desk check did not run")
    raise SystemExit(0)

from api.main import app, store                               # noqa: E402

DESK = {"X-PHC-Actor": "user:meena"}
API = "/api/v1/phc"


def numeric(token, where):
    assert token is not None and str(token).isdigit(), \
        "%s: %r is not a number, so it is not on anybody's sequence" % (where, token)
    return int(token)


def rows():
    """Today's queue, the way a screen reads it."""
    answer = client.get("%s/views/%s" % (API, QUEUE.id), headers=DESK)
    assert answer.status_code == 200, answer.text
    return answer.json()["rows"]


client = TestClient(app)

# ---------------------------------------------------------------------------
# 1. The seeded demo day is already one numeric sequence.
# ---------------------------------------------------------------------------

seeded = rows()
assert seeded, "the demo day seeded a line"
issued = sorted(numeric(r["subject"]["token"], r["thread"]) for r in seeded)
assert issued == list(range(1, len(issued) + 1)), \
    "the seeded day is not 1..n with no gap and no repeat: %s" % issued
ok("the demo day opens on one numeric sequence, %s, with no gap and no number "
   "issued twice" % ", ".join(str(n) for n in issued))

# Nobody in the room wears a prefix any more. Asserted on the rows rather than
# by grepping the seed, because what matters is what a screen is handed.
for r in seeded:
    token = str(r["subject"]["token"])
    assert token.isdigit(), "%s still carries %r" % (r["thread"], token)
ok("and not one row carries a lettered token, which is what the renderer's "
   "idea of a token came from")

# ---------------------------------------------------------------------------
# 2. One sequence, both ways in, interleaved.
# ---------------------------------------------------------------------------

highest = max(issued)

first_desk = client.post("%s/threads" % API, json={}, headers=DESK)
assert first_desk.status_code == 200, first_desk.text
a = numeric(first_desk.json()["subject"]["token"], "the desk's arrival")

scan = client.post("%s/arrivals" % API, json={"counter": "front-1"})
assert scan.status_code == 200, scan.text
b = numeric(scan.json()["token"], "the poster's arrival")

second_desk = client.post("%s/threads" % API, json={}, headers=DESK)
assert second_desk.status_code == 200, second_desk.text
c = numeric(second_desk.json()["subject"]["token"], "the desk's second arrival")

assert [a, b, c] == [highest + 1, highest + 2, highest + 3], \
    "three arrivals, two routes, and the numbers are not consecutive: %s " \
    "after %d" % ([a, b, c], highest)
ok("a desk arrival, a poster arrival and a second desk arrival take %d, %d "
   "and %d: one sequence, in the order they actually walked in, and the "
   "poster saves the typing rather than a place in the line" % (a, b, c))

# The one this exists for. Two sequences would still pass every assertion
# above if each route counted its own, so the numbers are compared ACROSS the
# routes and not within them.
assert b not in (a, c) and len({a, b, c}) == 3, \
    "two arrivals share a number, which is two people answering to it"
ok("and no two of the three share a number, which is what a second sequence "
   "for the poster would have produced")

# ---------------------------------------------------------------------------
# 3. The number is the kernel's to issue.
# ---------------------------------------------------------------------------

asked = client.post("%s/threads" % API, json={"token": "4242"}, headers=DESK)
assert asked.status_code == 200, asked.text
got = numeric(asked.json()["subject"]["token"], "an arrival that asked for a number")
assert got != 4242, \
    "a client picked its own number, so nothing knows what it has given out"
assert got == c + 1, (got, c)
ok("a client that asks for a particular number is given the next one in the "
   "sequence instead, because a number nothing issued is a number nothing "
   "knows it has handed out")

# ---------------------------------------------------------------------------
# 4. Provenance: declared, carried, and on the row.
# ---------------------------------------------------------------------------

scanned_thread = scan.json()["thread"]
desk_thread = first_desk.json()["subject"]["encounter"]

by_thread = {r["thread"]: r for r in rows()}
assert scanned_thread in by_thread and desk_thread in by_thread, \
    "both arrivals are in today's queue"

assert by_thread[scanned_thread]["subject"][COLUMN] == MARK, \
    "the poster's arrival does not carry the mark its view declared"
assert not by_thread[desk_thread]["subject"].get(COLUMN), \
    "a desk arrival carries a provenance, so the mark no longer means anything"
ok("the poster's arrival carries the declared mark on its queue row and the "
   "desk's carries none, so the screen can tell them apart without being told "
   "what either one means")

# Filterable, which is the reason it is a column and not a flag: the queue is
# where anybody finds out that somebody registered themselves.
today = rows()
wearing = {r["thread"] for r in today
           if str(r["subject"].get(COLUMN) or "") == MARK}
assert scanned_thread in wearing, "the arrival that scanned is not in the filter"
assert desk_thread not in wearing, "a desk arrival is caught by the filter"
# The filter has to NARROW. Selecting everybody and selecting nobody would
# both satisfy a membership test on its own, so both ends are pinned.
assert 0 < len(wearing) < len(today), (len(wearing), len(today))
ok("and filtering today's %d rows by the declared column and value leaves the "
   "%d that registered themselves, which is what the chip above the list "
   "does" % (len(today), len(wearing)))

# The response to the scan is the only thing that reaches the patient, so it
# has to be the number and not a clinical panel.
body = scan.json()
assert set(body) == {"thread", "token"}, body
assert str(body["token"]).isdigit(), body
ok("the scan is answered with the number and the thread and nothing else: "
   "that response is how the number reaches the patient's own application, "
   "and an unauthenticated caller is told nothing clinical")

# ---------------------------------------------------------------------------
# 5. A facility with no poster.
# ---------------------------------------------------------------------------

refused = client.post("%s/arrivals" % API, json={})
assert refused.status_code == 400, refused.status_code
ok("a scan that does not say which counter it happened at is refused, because "
   "the counter is what makes the scan an arrival")

# ---------------------------------------------------------------------------
# 6. The sequence reads nothing but the Store protocol.
# ---------------------------------------------------------------------------

# The kernel's one known off-protocol Store call is held at exactly one by
# scripts/check_queues.py. Issuing a number must not become the second.
#
# IT READS TWO PROTOCOL METHODS NOW AND BOTH ARE DECLARED. Until 2026-11-01
# this section said the sequence "needed no eleventh method on the adapter
# interface", and that was the sentence the race lived behind: computing the
# number from reads alone is exactly what made issuing it two steps. The
# eleventh method exists, it is `issue_token`, and the property worth holding
# here was never "the protocol stays at ten" but "this module reaches nothing
# PAST the protocol". That is what is asserted.
source = (ROOT / "kernel" / "tokens.py").read_text()
body_only = "\n".join(l for l in source.splitlines()
                      if not l.lstrip().startswith(("#", '"', "'")))
assert "store.threads(" in body_only, "the sequence reads Store.threads"
assert "store.issue_token(" in body_only, \
    "the sequence reserves its number through the protocol rather than " \
    "computing it from reads, which is the two-step race"
declared = {n for n in vars(Store) if not n.startswith("_")}
assert "issue_token" in declared, \
    "issue_token must be ON the Store protocol, or the sequence has gained a " \
    "second off-protocol call instead of losing the race"
for off_protocol in ("open_thread", "record_directory_id", "_put", "db.", "execute("):
    assert off_protocol not in body_only, \
        "the sequence reaches past the Store protocol: %s" % off_protocol
ok("the day sequence reads Store.threads for the rule and Store.issue_token "
   "for the number, both declared on the protocol, and reaches past it nowhere")

# A day with nothing in it starts at the first number rather than at nothing.
# The fake issues from the floor, which is what an atomic adapter does on the
# first call of a day; what it may NOT do is invent a number of its own.
class _Empty:
    def threads(self, *, workflow, scope):
        return []

    def issue_token(self, *, workflow, scope, floor):
        return floor

assert tokens.issue(_Empty(), workflow=BUNDLE.workflow().id) == str(tokens.FIRST)
ok("a facility opening its first morning issues %d rather than failing or "
   "issuing nothing" % tokens.FIRST)

print("\n%d front desk checks passed" % checks)

# ---------------------------------------------------------------------------
# Mutations run against this file, each of which must FAIL it
# ---------------------------------------------------------------------------
# 1. api/main.py: have POST /threads honour body["token"] again.
#    -> section 3 fails: a client picked its own number.
# 2. api/main.py: give POST /arrivals its own counter, numbering the poster's
#    arrivals separately from the desk's.
#    -> section 2 fails: the three arrivals are not consecutive.
# 3. api/main.py: drop `arrival` from the poster's open_thread call.
#    -> section 4 fails: the poster's arrival does not carry the mark.
# 4. bundles/phc/seed.yaml: put a lettered token back on any thread.
#    -> section 1 fails: the day is not 1..n.
# 5. adapters/local/store.py: restore the token fallback that made one up out
#    of the row id.
#    -> section 3 fails: the number is not the next in the sequence.


# ---------------------------------------------------------------------------
# 6. Find before create, for real: a patient we already hold stays one person.
#
# THE DEFECT THIS EXISTS FOR. The desk searches this centre's own register and
# finds a returning patient, the clerk picks her, and the registration that
# follows wrote A SECOND PERSON: the form carries only the questionnaire's
# answers, and a patient's own id is not one of them, so the adapter saw a
# record with no id and no directory id and inserted. On a developer's own
# demo day that had produced seventy-two rows for one woman, every one of
# them identical, each with its own visit and its own half of her history.
#
# `directory_id` was the only cross-visit identity the adapter had, and no
# patient in a deployment without Eka's directory has one: 0 of 78 on the day
# this was found. So the dedupe branch was dead code and every registration
# was a new person.
# ---------------------------------------------------------------------------

HER = {"name": "Sunita Devi", "age": 34, "sex": "female",
       "phone": "9876500000", "village": "Yadiki", "category": "general"}


def register(thread, payload):
    reply = client.post("%s/operations/phc.op.patient-register/commit" % API,
                        json={"thread": thread, "payload": payload}, headers=DESK)
    assert reply.status_code == 200, reply.text
    return reply.json()


def her_rows():
    """Every patient row with her name, by the route the desk itself uses."""
    found = client.get("%s/patients/search" % API,
                       params={"q": HER["name"]}, headers=DESK)
    assert found.status_code == 200, found.text
    return [r for r in found.json()["local"] if r.get("name") == HER["name"]]


monday = client.post("%s/threads" % API, json={}, headers=DESK).json()["id"]
register(monday, HER)
first = her_rows()
assert len(first) == 1, "she was registered once and the register holds %d" % len(first)
hers = first[0]["id"]

# Friday. The clerk types her mobile, the desk answers with the row above,
# and the clerk picks it: that is the identity, and it travels in the form.
#
# Taken off the SEARCH RESULT, exactly as the screen does, rather than
# constructed here. A fix that only worked when a test typed the id would
# leave the clerk registering a second her, which is the whole defect.
picked, = [r for r in client.get("%s/patients/search" % API,
                                 params={"q": HER["phone"]}, headers=DESK).json()["local"]
           if r.get("name") == HER["name"]]
assert picked.get("patient_id") == hers, \
    "the desk found her and did not say which record she is: %s" % sorted(picked)
friday = client.post("%s/threads" % API, json={}, headers=DESK).json()["id"]
register(friday, dict(HER, patient_id=picked["patient_id"]))

again = her_rows()
assert len(again) == 1, \
    "picking the patient the desk found still created a second record of " \
    "her: %d rows now, %s" % (len(again), [r["id"] for r in again])
assert again[0]["id"] == hers, "she was replaced rather than kept"
ok("a returning patient the clerk picked off the desk is the same person: "
   "one record, not a second one with half her history")

# And the two visits are hers, which is the whole point of it being one row:
# the spine is what a doctor opens to see what happened last time.
spine = client.get("%s/subjects/%s" % (API, hers), headers=DESK)
assert spine.status_code == 200, spine.text
visits = [e["thread"] for e in spine.json()["encounters"]]
assert monday in visits and friday in visits, \
    "one record, but her two visits did not land on it: %s" % visits
ok("and both her visits hang off that one record, so the doctor on Friday "
   "can see what Monday found")

# The other half of the rule, and the one with a permanent cost: identity is
# the clerk's CHOICE, never a guess this code makes. Somebody who shares her
# mobile -- a daughter, a husband, the household's one handset -- registered
# without that choice is their own person.
daughter = client.post("%s/threads" % API, json={}, headers=DESK).json()["id"]
register(daughter, dict(HER, name="Lakshmi Devi", age=19))
shared = [r for r in client.get("%s/patients/search" % API,
                                params={"q": HER["phone"]}, headers=DESK).json()["local"]
          if r.get("phone") == HER["phone"]]
assert len(shared) == 2, \
    "two people on one household handset were merged into %d" % len(shared)
ok("and a second person on the same mobile is a second person: nothing here "
   "merges two patients on a number a household shares")
