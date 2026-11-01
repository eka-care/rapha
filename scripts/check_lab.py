"""Run: python3 scripts/check_lab.py

A laboratory value and its unit are one checked thing.

Two defects in `catalogue/ops/phc.op.lab-result-enter.md` are what this module
closed, and the first two sections are written so that reintroducing either
one fails here:

  1. `code: {answer: analyte}` put whatever free text the technician typed
     into the report's code column, which is the defect vitals had before a
     blood pressure stopped being called `systolic`.
  2. `conclusion: {joined: [value, unit]}` squashed the result into prose.
     **The number was not stored as a number anywhere**, so it could not be
     trended, counted or sent as a FHIR Quantity, and the trend on the
     prototype's screen was a drawing of something the data model could not
     produce.

Closing them needed the third binding form, `answer_value_set`, which
`kernel/terminology.py` had documented as deliberately absent on the rule that
an unused binding is a promise with no check behind it. The checks arrive here
with the use.

  value set    seven analytes, every display and unit from LOINC itself
  binding      the ANSWER carries the concept, resolved at write time
  agreement    the unit is the one LOINC reports that analyte in
  rows         a coded Observation with a real quantity, and a report that
               keeps a narrative instead of a reformatted number
  guard        a wrong code or a wrong unit is refused before anything is
               written, in a sentence
  portability  nothing in the kernel learns a health centre's analyte list

Mutations are listed at the bottom and every one was run. Also at the bottom:
what was tried and deliberately NOT kept, because a check that cannot fail
reads as coverage.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore, TABLES                 # noqa: E402
from catalogue import validate, vocab                                # noqa: E402
from kernel import declarations, fhir, mapping, proposals, state, terminology  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
OP = BUNDLE.operations["phc.op.lab-result-enter"]
SCHEMA = validate.load(OP["input"])
QUESTIONS = {q["link_id"]: q for q in validate.walk(SCHEMA["questions"])}
CAPS = set(vocab.CAPABILITIES)
TECH = "user:asha"
SLUG = "lab-analyte"
VOCAB = json.loads((ROOT / "terminology" / ("%s.json" % SLUG)).read_text())

RESULT = {"analyte": "718-7", "value": 9.4, "unit": "g/dL",
          "note": "repeat on a fresh sample, previous one haemolysed"}


# ---------------------------------------------------------------------------
# 1. The value set. Confirmed, not seeded, and its units are LOINC's own.
# ---------------------------------------------------------------------------

assert SLUG in terminology.LOCAL.cached(), terminology.LOCAL.cached()
assert VOCAB["system"] == "http://loinc.org", VOCAB["system"]
# The rule the previous module established: a seeded code and a confirmed code
# are indistinguishable once a row exists, so the difference is caught before
# one is written.
assert not VOCAB["verified"].startswith("unverified"), VOCAB["verified"]
for code, concept in sorted(VOCAB["concepts"].items()):
    assert not concept["verified"].startswith("unverified"), code
    assert "tx.fhir.org" in concept["verified"], (code, concept["verified"])
    assert concept["why"].strip(), "%s does not say why it, and not a neighbour" % code
ok("all %d analytes name where they were confirmed and why that code rather "
   "than a neighbour" % len(VOCAB["concepts"]))

for code, concept in sorted(VOCAB["concepts"].items()):
    assert concept.get("unit"), "%s records no unit" % code
    assert concept.get("unit_system") == "http://unitsofmeasure.org", code
    # The unit is not anybody's choice: it is LOINC's own EXAMPLE_UCUM_UNITS
    # for that code, fetched by scripts/seed_terminology.py.
    assert "EXAMPLE_UCUM_UNITS" in (concept.get("unit_verified") or ""), code
    assert terminology.LOCAL.validate(terminology.UNIT_BINDING, concept["unit"]), \
        "%s is reported in %r, which the UCUM cache does not hold" \
        % (code, concept["unit"])
ok("every analyte's unit is LOINC's own example unit, and is a unit UCUM holds")

# A primary source for WHICH tests, separate from the one for what a code
# means. The list is short on purpose and the file says where it came from.
assert "National Essential Diagnostics List" in VOCAB["source"], VOCAB["source"]
assert "Primary Health Centre" in VOCAB["source"], VOCAB["source"]
assert len(VOCAB["concepts"]) <= 12, \
    "a long list is a guessed list: %d concepts" % len(VOCAB["concepts"])
ok("the analyte list cites the national list it came from and stays short")


# ---------------------------------------------------------------------------
# 2. The two defects, closed.
# ---------------------------------------------------------------------------

records = {r["resource"]: r for r in OP["mapping"]}
assert set(records) == {"observation", "diagnostic_report", "specimen"}, sorted(records)
assert set(records) == set(OP["writes"]), (sorted(records), sorted(OP["writes"]))

observation = records["observation"]["fields"]
assert observation["code"] == {"answer_code": "analyte"}, observation["code"]
assert observation["code_system"] == {"answer_code_system": "analyte"}, observation
assert observation["value"] == {"answer": "value"}, observation["value"]
assert observation["unit"] == {"answer_code": "unit"}, observation["unit"]
assert observation["unit_system"] == {"answer_code_system": "unit"}, observation
assert observation["category"] == {"const": "laboratory"}, observation["category"]
# Defect 1, as a shape: no field anywhere in this operation puts a raw answer
# into a code column.
for resource, record in sorted(records.items()):
    for column, source in sorted(record["fields"].items()):
        if column in ("code", "code_system", "code_display"):
            assert "answer" not in source, \
                "%s.%s is filled from a raw answer: %r" % (resource, column, source)
ok("the result is a coded Observation, and no code column is filled from a "
   "raw answer in any of the three records")

# Defect 2, as a shape: the number is a column of its own and reaches no prose.
for resource, record in sorted(records.items()):
    for column, source in sorted(record["fields"].items()):
        if set(source) & {"joined", "note"}:
            consumed = list(source.values())[0]
            assert "value" not in consumed and "unit" not in consumed, \
                "%s.%s squashes the number into prose: %r" % (resource, column, source)
assert records["diagnostic_report"]["fields"]["conclusion"] == {"answer": "note"}, \
    records["diagnostic_report"]["fields"]
ok("the number is a column and nothing joins it into prose: the report's "
   "conclusion is a remark somebody wrote")

assert "value" in TABLES["observation"] and "unit" in TABLES["observation"]
assert "unit_system" in TABLES["observation"], TABLES["observation"]
assert "code_system" in TABLES["diagnostic_report"], TABLES["diagnostic_report"]
ok("the adapter has somewhere flat to put all of it")


# ---------------------------------------------------------------------------
# 3. The third binding form: the ANSWER carries the concept.
# ---------------------------------------------------------------------------

assert terminology.answer_binding(QUESTIONS["analyte"]) == SLUG
assert terminology.answer_binding(QUESTIONS["unit"]) == terminology.UNIT_BINDING
assert terminology.answer_binding(QUESTIONS["value"]) is None, \
    "a question whose answer is a number binds no value set"
assert terminology.unit_of(QUESTIONS["unit"]) == "analyte"
ok("the analyte and the unit bind their answers, and the value binds nothing")

# Resolved at write time, which is the whole difference from the other two
# forms: the concept is not known until somebody answers.
coding = terminology.answer_coding(QUESTIONS["analyte"], "718-7")
assert isinstance(coding, terminology.Coding), coding
assert coding.system == "http://loinc.org" and coding.valueset == SLUG, coding
assert coding.display == VOCAB["concepts"]["718-7"]["display"], coding
ok("an answer resolves to a coding through the question's own value set")

for bad in ("Haemoglobin", "9999-9", "718_7"):
    try:
        terminology.answer_coding(QUESTIONS["analyte"], bad)
    except terminology.UnboundCoding:
        continue
    raise AssertionError("%r became a coding" % bad)
ok("free text, a code the set does not hold, and a mistyped code all refuse "
   "to become codings")

try:
    terminology.answer_coding(QUESTIONS["value"], "9.4")
except terminology.UnboundCoding as broke:
    assert terminology.ANSWER_VALUE_SET in str(broke), broke
else:
    raise AssertionError("a question that binds nothing produced a coding")
ok("and a question that declares no binding produces no coding at all, rather "
   "than one nothing vouched for")


# An optional bound question that nobody answered is no coding and therefore
# no row, not a refusal. Checked because the branch is otherwise unreachable
# from the shipped forms, where both bound questions are required: a future
# optional coded answer would land on it, and a mutation of it passed
# unnoticed until this was written.
unanswered = mapping.records(OP, {"value": 9.4, "unit": "g/dL"}, actor=TECH)
written = {r for r, _ in unanswered}
assert "observation" not in written, unanswered
assert "diagnostic_report" not in written, unanswered
# This is the defect the mutation found rather than the one it was written
# for: the row used to be written anyway, carrying a value and a unit and no
# code, which is a clinical number with nothing saying what it measured.
for resource, row in unanswered:
    assert not (set(row) & {"code", "code_system", "code_display"}), (resource, row)
    assert "value" not in row, (resource, row)
ok("a record that codes a column from an answer writes nothing when that "
   "answer is absent, rather than a row with a value and no code")


# ---------------------------------------------------------------------------
# 4. The agreement rule, on the guard's first step.
# ---------------------------------------------------------------------------

check = proposals.validator(OP)
assert check(OP, RESULT) == [], check(OP, RESULT)
ok("a haemoglobin of 9.4 g/dL is a valid result")

wrong = check(OP, dict(RESULT, unit="mg/dL"))
assert len(wrong) == 1, wrong
assert "718-7 is reported in 'g/dL'" in wrong[0], wrong
ok("a haemoglobin in mg/dL is refused with the unit it should be in: %s"
   % wrong[0].split(".")[0])

# The point of the rule, stated as the clinical case rather than the shape: 12
# is a normal haemoglobin and a nonsense one, depending on a field that used
# to be free text.
assert check(OP, {"analyte": "718-7", "value": 12, "unit": "g/dL"}) == []
assert check(OP, {"analyte": "718-7", "value": 12, "unit": "mg/dL"}) != []
ok("so a value of 12 is accepted in one unit and refused in the other, which "
   "is the whole reason the two are one thing")

# Both halves of the validator run, so a technician is told everything at once
# rather than fixing one problem and discovering the next.
both = check(OP, {"analyte": "nonsense", "value": "not a number", "unit": "g/dL"})
assert len(both) == 2, both
assert any("must be decimal" in p for p in both), both
assert any("not a code in lab-analyte" in p for p in both), both
ok("the schema half and the terminology half both run and report together")

# An analyte that the value set holds but that records no unit cannot decide
# one, and says so rather than passing silently.
class NoUnit:
    def validate(self, valueset, code):
        return terminology.LOCAL.validate(valueset, code)

    def concepts(self, valueset):
        return {k: {kk: vv for kk, vv in v.items() if kk != "unit"}
                for k, v in terminology.LOCAL.concepts(valueset).items()}


silent = terminology.answer_problems(SCHEMA, RESULT, NoUnit())
assert silent and "no unit" in silent[0], silent
ok("an analyte with no unit recorded reports that it cannot decide one, "
   "rather than letting the unit through unchecked")

# A unit_of pointing at a question that does not exist is a rule that can
# never fire, which reads as a protection and is not one. The same reasoning
# the catalogue linter applies to an `actor of` naming a missing operation.
# Checked on a synthetic form rather than by breaking the shipped one, so the
# message itself is pinned.
DANGLING = {"questions": [
    {"link_id": "analyte", "text": "Analyte", "type": "choice",
     "answer_value_set": SLUG, "required": True},
    {"link_id": "unit", "text": "Unit", "type": "choice",
     "answer_value_set": terminology.UNIT_BINDING, "required": True,
     "styling_metadata": {"phc": {"unit_of": "nonsense"}}},
]}
dangling = terminology.answer_problems(DANGLING, {"analyte": "718-7", "unit": "g/dL"})
assert len(dangling) == 1, dangling
assert "not a question on this form" in dangling[0], dangling
assert "nonsense" in dangling[0], dangling
ok("a unit_of naming a question that does not exist is reported, not a rule "
   "that silently never fires")


# ---------------------------------------------------------------------------
# 5. End to end: a result through the guard, into rows, out as FHIR.
# ---------------------------------------------------------------------------

def thread_with_an_order():
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="L01", actor=TECH)
    for op_id, payload in (
            ("phc.op.patient-register",
             {"name": "Ramesh Kumar", "age": 51, "sex": "male",
              "phone": "9876511111", "village": "Tadipatri", "category": "ncd"}),
            ("phc.op.vitals-record", {"systolic": 118, "diastolic": 76, "pulse": 80}),
            ("phc.op.consult-document",
             {"assessment": "Anaemia suspected"}),
            ("phc.op.lab-order", {"investigations": [{"code": "Haemoglobin"}]})):
        decision = proposals.commit(store, BUNDLE, op_id, thread=thread,
                                    payload=payload, caps=CAPS, actor=TECH)
        assert decision, (op_id, decision.reason)
    return store, thread


store, thread = thread_with_an_order()
assert "lab.ordered" in state.flags(store, thread, WF), sorted(state.flags(store, thread, WF))

refused = proposals.commit(store, BUNDLE, "phc.op.lab-result-enter", thread=thread,
                           payload=dict(RESULT, unit="mg/dL"), caps=CAPS, actor=TECH)
assert not refused and "reported in 'g/dL'" in refused.reason, refused.reason
assert store.count("observation", thread=thread, where={"category": "laboratory"}) == 0, \
    "a refused result wrote a row"
ok("the wrong unit is refused on the write path too, and writes nothing")

allowed = proposals.commit(store, BUNDLE, "phc.op.lab-result-enter", thread=thread,
                           payload=RESULT, caps=CAPS, actor=TECH)
assert allowed, allowed.reason
(row,) = store.select("observation", thread=thread, where={"category": "laboratory"},
                      fields=["code", "code_system", "code_display", "value", "unit",
                              "unit_system", "created_by"], limit=5)
assert row["code"] == "718-7" and row["code_system"] == "http://loinc.org", row
assert row["code_display"] == VOCAB["concepts"]["718-7"]["display"], row
assert row["value"] == "9.4" and row["unit"] == "g/dL", row
assert row["unit_system"] == "http://unitsofmeasure.org", row
assert row["created_by"] == TECH, row
ok("a result commits to one flat laboratory Observation carrying its LOINC "
   "code, its quantity and its author")

assert store.count("observation", thread=None, where={"code": "718-7"}) == 1
assert store.count("observation", thread=None,
                   where={"code": "718-7", "category": "laboratory"}) == 1
ok("and is countable by its code, which is what a district count needs and "
   "what prose could never answer")

(report,) = store.select("diagnostic_report", thread=thread, where={},
                         fields=["code", "code_system", "conclusion", "status"],
                         limit=5)
assert report["conclusion"] == RESULT["note"], report
assert str(RESULT["value"]) not in (report["conclusion"] or ""), \
    "the number is back in the prose"
assert report["code"] == "718-7" and report["status"] == "preliminary", report
ok("the report keeps the narrative and the number is not in it")

(spec,) = store.select("specimen", thread=thread, where={},
                       fields=["code", "status", "created_by"], limit=5)
assert not (spec["code"] or ""), \
    "the specimen is labelled %r, which is a test name and not a specimen type" \
    % spec["code"]
assert spec["status"] == "available" and spec["created_by"] == TECH, spec
ok("the specimen no longer claims the test name is its type")

assert "lab.resulted" in state.flags(store, thread, WF), sorted(state.flags(store, thread, WF))
ok("and the thread moves on")


# ---------------------------------------------------------------------------
# 6. Out as FHIR, in the same shape the vitals slice produces.
# ---------------------------------------------------------------------------

doc = fhir.document(store, thread, profile="WellnessRecord",
                    sections_wanted={"OtherObservations": [
                        ("observation", {"category": "laboratory"})]},
                    now="2026-10-31T11:00:00+00:00")
lab = next(e["resource"] for e in doc["entry"]
           if e["resource"]["resourceType"] == "Observation")
assert lab["code"]["coding"] == [{
    "system": "http://loinc.org", "code": "718-7",
    "display": VOCAB["concepts"]["718-7"]["display"]}], lab["code"]
assert lab["valueQuantity"] == {"value": 9.4, "unit": "g/dL",
                                "system": "http://unitsofmeasure.org",
                                "code": "g/dL"}, lab["valueQuantity"]
assert isinstance(lab["valueQuantity"]["value"], float), lab["valueQuantity"]
assert lab["category"][0]["coding"][0] == {"system": fhir.HL7_CATEGORY,
                                           "code": "laboratory"}, lab["category"]
ok("it projects to a FHIR Observation with a LOINC code and a UCUM quantity, "
   "the same shape a vital sign produces")


# ---------------------------------------------------------------------------
# 7. Portability. The kernel did not learn a health centre's analyte list.
# ---------------------------------------------------------------------------

WORDS = sorted(set(VOCAB["concepts"]) | {SLUG})
assert len(WORDS) >= 8, WORDS
for module in ("kernel/terminology.py", "kernel/mapping.py", "kernel/fhir.py",
               "kernel/proposals.py", "kernel/state.py", "catalogue/validate.py",
               "adapters/local/store.py"):
    text = (ROOT / module).read_text()
    live = text.split("\ndef demo(")[0]
    typed = [w for w in WORDS if '"%s"' % w in live or "'%s'" % w in live]
    assert not typed, "%s types %r" % (module, typed)
ok("no engine module types an analyte's code or the name of the value set it "
   "is drawn from")

# The laboratory bundle is the portability proof and was not touched. Its own
# check runs in scripts/check.sh; this asserts the shared value set did not
# quietly become a PHC thing that the lab now depends on.
lab_bundle = declarations.load("lab")
for op in lab_bundle.operations.values():
    for record in op.get("mapping") or []:
        for source in (record.get("fields") or {}).values():
            assert SLUG not in str(source), \
                "the laboratory bundle now reads %s: %r" % (SLUG, source)
ok("and the laboratory bundle still binds none of it")

# ---------------------------------------------------------------------------
# 8. A bound answer has to be offerable, or the binding is a dead column.
# ---------------------------------------------------------------------------

assert not QUESTIONS["analyte"].get("answer_option"), \
    "the analyte lists its options AND binds a value set, which is the same " \
    "list twice and two things that can disagree"

try:
    from starlette.testclient import TestClient
except ImportError:                      # pragma: no cover
    print("warn starlette missing: the route half of this check did not run")
else:
    import os
    import tempfile

    os.environ.setdefault("PHC_DIRECTORY", "absent")
    # Its own database file. This half only READS a value set, so it wrote
    # nothing -- but importing api.main opens whatever PHC_DB points at, and
    # from the repository that is the developer's demo day: on a machine
    # where it does not exist yet, running this check creates and seeds one.
    # A check should leave no trace of having run.
    os.environ.setdefault(
        "PHC_DB", str(pathlib.Path(tempfile.mkdtemp(prefix="lab-")) / "phc.sqlite3"))
    from api.main import app

    client = TestClient(app)
    answer = client.get("/api/v1/phc/valuesets/%s" % SLUG)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    offered = {c["value"]: c for c in body["concepts"]}
    assert set(offered) == set(VOCAB["concepts"]), sorted(offered)
    one = offered["718-7"]
    assert one["system"] == "http://loinc.org" and one["display"], one
    # The unit travels with the concept, which is what lets a picker fill the
    # unit field without a second lookup and without the renderer knowing
    # what an analyte is.
    assert one["unit"] == "g/dL" and one["unit_system"], one
    ok("the value set expands on the API, so a bound answer can be offered "
       "with the unit it is reported in")

    narrowed = client.get("/api/v1/phc/valuesets/%s" % SLUG,
                          params={"q": "Hemoglobin"}).json()["concepts"]
    assert [c["value"] for c in narrowed] == ["718-7"], narrowed
    ok("and narrows on a query, which is what a picker in a four minute "
       "consultation needs")

    missing = client.get("/api/v1/phc/valuesets/not-a-valueset")
    assert missing.status_code == 404, missing.status_code
    ok("a value set this facility cannot check offline is a 404, not an empty list")

print("ok   lab result: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# Mutations this is built to fail under. Each was run.
#
#   catalogue/ops/phc.op.lab-result-enter.md  code: {answer: analyte}
#       ->  the "no code column from a raw answer" check fails
#   the same                                  conclusion: {joined: [value, unit]}
#       ->  the "nothing joins the number into prose" check fails
#   the same                                  drop the observation record
#       ->  the record set check fails, then every row and FHIR check
#   the same                                  unit: {answer: unit}
#       ->  the observation field check fails
#   questionnaires/phc.schema.lab-result-v1.json  drop answer_value_set from analyte
#       ->  the binding check fails, then the build refuses the mapping
#   the same                                  drop unit_of from the unit
#       ->  the agreement checks fail
#   kernel/terminology.py                     answer_problems skips the unit rule
#       ->  the mg/dL checks fail
#   kernel/terminology.py                     answer_coding skips validate
#       ->  the free text check fails
#   kernel/terminology.py                     a missing unit passes silently
#       ->  the NoUnit check fails
#   kernel/mapping.py                         an answer coding source needs no binding
#       ->  the lint check in test_mapping fails
#   kernel/proposals.py                       validator returns only the schema half
#       ->  the agreement and "both halves" checks fail
#   terminology/lab-analyte.json              a concept's unit removed
#       ->  the LOINC unit check fails
#   terminology/lab-analyte.json              verified -> "unverified ..."
#       ->  the confirmed check fails
#   adapters/local/store.py                   drop unit_system from observation
#       ->  the adapter check fails, then the row and FHIR checks
#
# TRIED AND DELIBERATELY NOT KEPT, because a check that cannot fail reads as
# coverage. Two of them, both of which looked like checks:
#
#   asserting an analyte concept's `unit` is in the UCUM value set, as proof
#   that the UNIT cache is complete. It is a real assertion and it is kept
#   above, but it was nearly written the other way round, as a loop over the
#   UCUM cache asserting each entry is used by an analyte. That one cannot
#   fail usefully: the UCUM cache also holds the vitals' units and the
#   laboratory bundle's, so the assertion would have had to exempt most of the
#   file and would then assert nothing.
#
#   asserting the Observation's code_display equals the value set's display.
#   The row takes its display from that file, so it compares a value with its
#   own source and cannot fail. Recorded in the previous module and deleted
#   again here when it was written a second time out of habit. What IS kept is
#   the comparison against the display LOINC returned, which is a different
#   file and a different source.
# ---------------------------------------------------------------------------
