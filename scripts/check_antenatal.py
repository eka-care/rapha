"""Run: python3 scripts/check_antenatal.py

The three numbers an antenatal contact turns on, end to end, no socket.

An ANM records a fundal height, a fetal heart rate and a haemoglobin. Each
one lands as its own coded observation, with a LOINC code and a UCUM unit,
and travels into an ABDM DocumentBundle as a FHIR Observation.

THE TWO CHECKS THIS FILE EXISTS FOR are the last two, and everything above
them is scaffolding for being able to state them:

- The readings do NOT close an antenatal contact. Measuring somebody is not
  the same as having seen them, and a schedule discharged by a tape measure
  would read as care that did not happen. Only a committed antenatal VISIT
  closes a contact, and this proves the measurement cannot.
- The form cannot be reached at all without a pregnancy open on this
  centre's books. A fundal height on somebody who is not pregnant is not a
  cautious reading; it is a record of something that did not happen.

The third thing it catches is the ANM herself. She owns every antenatal
contact in bundles/phc/phc.sched.antenatal.md, and until 4 November 2026 she
could not record one. Her capability set is what drives the commits below, so
a change that quietly takes `encounter.document` or `vitals.record` off her
fails here rather than in a village.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore                  # noqa: E402
from catalogue import validate, vocab                         # noqa: E402
from kernel import declarations, fhir, proposals, schedule, spine, state, terminology  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
MEASURE = BUNDLE.operations["phc.op.antenatal-measure"]
SCHED = BUNDLE.schedules["phc.sched.antenatal"]
ANM = set(vocab.for_bundle("phc").roles["anm"])
AN_ANM = "user:jyothi"

# Twenty eight weeks ago, so she is inside the third contact's window on the
# day this runs. Written relative to today rather than frozen, because a
# schedule check pinned to a date passes for a week and then asserts nothing.
TODAY = date.today()
LMP = TODAY - timedelta(days=196)

# One low haemoglobin, so the flag path is exercised too.
READING = {"fundal_height": 28.0, "fetal_heart_rate": 142, "haemoglobin": 9.4}


def fresh():
    """A store with one registered patient on one open thread, no pregnancy."""
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="1", actor=AN_ANM)
    decision = proposals.commit(
        store, BUNDLE, "phc.op.patient-register", thread=thread,
        payload={"name": "Lakshmi Devi", "age": 27, "sex": "female",
                 "phone": "9876500001", "village": "Yadiki",
                 "category": "general"},
        caps=ANM, actor=AN_ANM)
    assert decision, decision.reason
    return store, thread


def conceive(store, thread):
    """Open a pregnancy dated from a last period 28 weeks ago."""
    decision = proposals.commit(
        store, BUNDLE, "phc.op.pregnancy-open", thread=thread,
        payload={"dating_basis": "last_menstrual_period",
                 "dating_date": LMP.isoformat()},
        caps=ANM, actor=AN_ANM)
    assert decision, decision.reason


def episode_of(store, thread):
    """This thread's open pregnancy, as the spine derives it."""
    (patient,) = store.select("patient", thread=thread, where={},
                              fields=["id"], limit=2)
    whole = spine.of(BUNDLE, store, WF, patient["id"])
    (pregnancy,) = [e for e in whole["episodes"] if e["type"] == "pregnancy"]
    return pregnancy


# ---------------------------------------------------------------------------
# 1. The ANM can do this at all. Both halves, because the schedule assigns
#    her the contact and the form assigns her the readings.
# ---------------------------------------------------------------------------

assert "vitals.record" in ANM, sorted(ANM)
assert "encounter.document" in ANM, sorted(ANM)
assert MEASURE["capability"] in ANM
assert BUNDLE.operations["phc.op.antenatal-visit"]["capability"] in ANM
for contact in SCHED.contacts:
    assert contact.owner == "anm", contact.id
ok("the ANM owns every antenatal contact and holds what both halves of one need")


# ---------------------------------------------------------------------------
# 2. Declarations. Every question binds a concept its value set vouched for
#    and declares a unit, and the atom says which columns each becomes.
# ---------------------------------------------------------------------------

SCHEMA = validate.load(MEASURE["input"])
QUESTIONS = {q["link_id"]: q for q in validate.walk(SCHEMA["questions"])}
assert set(QUESTIONS) == set(READING), sorted(QUESTIONS)

(record,) = MEASURE["mapping"]
compiled = {q["link_id"]: q for q in record["per_question"]}
assert set(compiled) == set(READING), sorted(compiled)
for link_id, q in compiled.items():
    assert terminology.LOCAL.validate(terminology.CODE_BINDING, q["code"]), q
    assert terminology.LOCAL.validate(terminology.UNIT_BINDING, q["unit"]), q
    assert q["code_system"] == "http://loinc.org", q
    assert q["unit_system"] == "http://unitsofmeasure.org", q
    assert q["code_display"], q
ok("every antenatal reading carries a code and a unit its value set vouched for")

# A seeded code and a confirmed code are indistinguishable once a row is
# written, so the difference has to be caught before one is.
VOCAB = json.loads((ROOT / "terminology/observation-code.json").read_text())
UNITS = json.loads((ROOT / "terminology/ucum-units.json").read_text())
for blob in (VOCAB, UNITS):
    assert not blob["verified"].startswith("unverified"), blob["slug"]
    for code, concept in blob["concepts"].items():
        assert not concept["verified"].startswith("unverified"), \
            "%s/%s is still seeded rather than confirmed" % (blob["slug"], code)
        assert concept.get("why"), "%s/%s does not say why" % (blob["slug"], code)
ok("every code and every unit names where it was confirmed, and why it is here")

# NO UNIT IN observation-code.json, which is a rule and not an omission: the
# unit of a question that IS a concept is the question's own, bound to UCUM.
# A second unit beside the code is a number that looks like a constraint with
# nothing enforcing it, and the two could then disagree about one reading.
for code, concept in VOCAB["concepts"].items():
    assert "unit" not in concept, \
        "%s carries a unit; see the rule in scripts/seed_terminology.py" % code
ok("and the observation codes carry no unit of their own, so none can disagree")


# ---------------------------------------------------------------------------
# 3. It cannot be reached without a pregnancy, and nothing is written trying.
# ---------------------------------------------------------------------------

store, thread = fresh()
assert "pregnancy.open" in (MEASURE.get("preconditions") or [])
before = proposals.commit(store, BUNDLE, "phc.op.antenatal-measure",
                          thread=thread, payload=dict(READING),
                          caps=ANM, actor=AN_ANM)
assert not before, "a fundal height was recorded on a woman with no pregnancy"
assert not store.select("observation", thread=thread, where={},
                        fields=["id"], limit=5), "it wrote anyway"
assert "pregnancy" in before.reason.lower() or "precondition" in before.reason.lower(), \
    before.reason
ok("no pregnancy open, no antenatal readings, and the refusal writes nothing")

# The audit still carries the attempt. A refusal nobody can see is a refusal
# nobody can review.
assert any(r.operation == "phc.op.antenatal-measure" and r.outcome != "committed"
           for r in store.audit(thread)), "the refusal left no audit line"
ok("and the attempt is on the audit, because a refusal has to be reviewable")


# ---------------------------------------------------------------------------
# 4. With a pregnancy open: three rows, one per reading, each coded.
# ---------------------------------------------------------------------------

conceive(store, thread)
assert "pregnancy.open" in state.flags(store, thread, WF)
decision = proposals.commit(store, BUNDLE, "phc.op.antenatal-measure",
                            thread=thread, payload=dict(READING),
                            caps=ANM, actor=AN_ANM)
assert decision, decision.reason

rows = store.select("observation", thread=thread,
                    where={"category": "vital-signs"},
                    fields=["code", "code_system", "value", "unit", "created_by"],
                    limit=20)
assert len(rows) == 3, [r.get("code") for r in rows]
by_code = {r["code"]: r for r in rows}
assert set(by_code) == {q["code"] for q in compiled.values()}, sorted(by_code)
for link_id, q in compiled.items():
    row = by_code[q["code"]]
    assert str(row["value"]) == str(READING[link_id]), (link_id, row["value"])
    assert row["unit"] == q["unit"], (link_id, row["unit"])
    assert row["code_system"] == "http://loinc.org", link_id
    assert row["created_by"] == AN_ANM, link_id
ok("one reading is one row, with its own code, its own unit and its author")

# A measurement out of the declared band raises the flag the workflow stores,
# which is how it reaches the doctor ahead of the consultation.
assert "vitals.flagged" in state.flags(store, thread, WF), \
    "a haemoglobin of 9.4 raised nothing"
ok("a reading outside the band raises the flag, so the doctor sees it first")

# And it travels. A row that cannot be projected is a number this centre
# holds and nobody else can read.
doc = fhir.document(store, thread, profile="WellnessRecord",
                    sections_wanted={"VitalSigns": [
                        ("observation", {"category": "vital-signs"})]},
                    now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
observations = [e["resource"] for e in doc["entry"]
                if e["resource"]["resourceType"] == "Observation"]
assert len(observations) == 3, len(observations)
for observation in observations:
    (coding,) = observation["code"]["coding"]
    assert coding["system"] == "http://loinc.org", coding
    quantity = observation["valueQuantity"]
    assert quantity["system"] == "http://unitsofmeasure.org", quantity
    assert quantity["code"] == quantity["unit"], quantity
ok("each one projects to a FHIR Observation with a LOINC code and a UCUM unit")


# ---------------------------------------------------------------------------
# 5. AND THE ONE THAT MATTERS. Measuring is not seeing.
# ---------------------------------------------------------------------------

pregnancy = episode_of(store, thread)
contacts = schedule.contacts(BUNDLE, store, WF, pregnancy)
assert contacts, schedule.why(BUNDLE, store, WF, pregnancy)
assert not [c for c in contacts if c["state"] == schedule.DONE], \
    "a tape measure closed an antenatal contact"
(due,) = [c for c in contacts if c["state"] == schedule.DUE]
assert due["operation"] == "phc.op.antenatal-visit", due["operation"]
assert due["owner"] == "anm", due["owner"]
ok("three readings close no contact: what closes one is the visit, not the numbers")

# The other way round, so this is a statement about the measurement and not
# about the schedule being inert.
seen = proposals.commit(store, BUNDLE, "phc.op.antenatal-visit", thread=thread,
                        payload={"history": "Well.", "examination": "Nil.",
                                 "assessment": "Progressing.", "plan": "Review."},
                        caps=ANM, actor=AN_ANM)
assert seen, seen.reason
after = schedule.contacts(BUNDLE, store, WF, episode_of(store, thread))
done = [c["contact"] for c in after if c["state"] == schedule.DONE]
assert done == ["anc3"], done
ok("and the visit closes exactly one, the contact whose window today is in")

print("\nok   antenatal measurements: %d checks" % checks)
