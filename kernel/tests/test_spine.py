"""Run: python3 -m kernel.tests.test_spine

The spine, against a real SQLite store, because the whole of what it does is a
where clause and an in-memory fake would not have one.

THE MUTATION THIS FILE EXISTS TO CATCH. The demo seed gives every patient
exactly one encounter, so an implementation that ignored the filter entirely
and returned every thread in the facility would look perfect on the demo
data and on any test built from it. Every case below therefore uses two
patients, one of whom has two visits, so "returns everything" and "returns
the right ones" produce different numbers.
"""
from __future__ import annotations

from adapters.local.store import SqliteStore
from kernel import declarations, spine
from kernel.contracts import AuditRecord

BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def build():
    store = SqliteStore(":memory:")
    # Two patients. Amina has come back; Bilal has not.
    store.write("patient", {"id": "p-amina", "name": "Amina Sheikh", "age": "44"}, thread="e-a1")
    store.write("patient", {"id": "p-bilal", "name": "Bilal Khan", "age": "29"}, thread="e-b1")
    for enc, patient, when in (("e-a1", "p-amina", "2026-03-02T09:00:00+00:00"),
                               ("e-a2", "p-amina", "2026-09-14T09:00:00+00:00"),
                               ("e-b1", "p-bilal", "2026-09-15T09:00:00+00:00")):
        store.db.execute(
            "INSERT OR REPLACE INTO encounter (id, patient, status, token, created_date)"
            " VALUES (?, ?, 'in_progress', ?, ?)", [enc, patient, enc[-2:], when])
    return store


store = build()

# -- the join is the point --------------------------------------------------

amina = spine.of(BUNDLE, store, WF, "p-amina")
bilal = spine.of(BUNDLE, store, WF, "p-bilal")

assert amina is not None and bilal is not None, "both subjects exist"
assert amina["subject"]["name"] == "Amina Sheikh"
ok("a subject comes back under its own declared resource")

assert len(amina["encounters"]) == 2, \
    "Amina has two visits, got %d" % len(amina["encounters"])
assert len(bilal["encounters"]) == 1, \
    "Bilal has one visit, got %d -- the filter is not filtering" % len(bilal["encounters"])
ok("each subject gets its own visits and nobody else's")

assert {e["thread"] for e in amina["encounters"]} == {"e-a1", "e-a2"}
assert {e["thread"] for e in bilal["encounters"]} == {"e-b1"}
ok("and they are the right threads, not merely the right count")

# -- newest first, because §26's timeline is read downwards -----------------

assert [e["thread"] for e in amina["encounters"]] == ["e-a2", "e-a1"], \
    "newest visit first"
ok("visits are ordered newest first")

# -- a subject that does not exist is not an empty person -------------------

assert spine.of(BUNDLE, store, WF, "p-nobody") is None
ok("an unknown subject is None, never a subject with no visits")

# -- a workflow with no spine declares no spine -----------------------------
#
# Not every bundle joins its threads up. One that does not must say so by
# declaring nothing, and this must answer None rather than guessing at which
# field means "the same person again".
import dataclasses
spineless = dataclasses.replace(WF, spine=None)
assert spine.declared(spineless) is None
assert spine.of(BUNDLE, store, spineless, "p-amina") is None
ok("a workflow declaring no spine has none, and is not given one by default")

assert spine.declared(WF) == "patient"
ok("the health centre's spine is its own declaration, not this file's guess")

# -- §26: a timeline entry says what the visit was --------------------------

store.append_audit(AuditRecord(
    id="a1", thread="e-a1", operation="phc.op.vitals-record", actor="user:nurse",
    surface="rendered", payload={}, outcome="committed", at="2026-03-02T09:05:00+00:00"))
store.append_audit(AuditRecord(
    id="a2", thread="e-a1", operation="phc.op.vitals-record", actor="user:nurse",
    surface="rendered", payload={}, outcome="committed", at="2026-03-02T09:06:00+00:00"))
store.append_audit(AuditRecord(
    id="a3", thread="e-a1", operation="phc.op.consult-document", actor="user:mo",
    surface="rendered", payload={}, outcome="denied: nope", at="2026-03-02T09:07:00+00:00"))

again = spine.of(BUNDLE, store, WF, "p-amina")
old = next(e for e in again["encounters"] if e["thread"] == "e-a1")
titles = [d["title"] for d in old["did"]]
assert titles == ["Record vitals and triage"], \
    "a visit says what it did, once per operation, refusals excluded: %r" % titles
ok("a visit's timeline entry carries the operation's own title, deduplicated")
ok("and a refusal is not something the visit did")

print("\nok   spine: %d checks" % checks)
