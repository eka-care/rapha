"""Run: python3 scripts/check_rx.py

The repeating group slice, every layer, no socket.

A doctor documents a consultation with two diagnoses and prescribes one
medicine. Each diagnosis row and each medicine row is validated on its own,
coded on its own, stored as its own record row with its own author, and
published as its own FHIR resource inside an ABDM OPConsultRecord.

What this is proving is narrower than it looks, and it is the thing a
repeating group is for: there is no answer on either of these forms that
nothing checks. Both questions were `type: structured` until now, which is
the escape hatch CARE never finished, so a diagnosis was whatever text
arrived and a prescription was one prose string.

  declarations   the group declares its sub questions, with types and bindings
  validate       required, choice and range hold PER ROW, and a stray key is refused
  terminology    every coded answer of every row resolves through one constructor
  mapping        one record row per group row, each with its author
  adapter        flat columns, so a prescription is countable by drug
  projection     one Condition per diagnosis, one MedicationRequest per medicine
  guard          the audit row before the write, on every surface

The failures this is built to catch are at the bottom of the file.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore, TABLES          # noqa: E402
from catalogue import validate, vocab                         # noqa: E402
from kernel import declarations, fhir, mapping, proposals, terminology  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
CONSULT = BUNDLE.operations["phc.op.consult-document"]
RX = BUNDLE.operations["phc.op.rx-prescribe"]
DOCTOR = set(vocab.for_bundle("phc").roles["mo"])
# Getting a patient to the doctor's chair needs the two stations in front of
# it, and a doctor holds neither capability. Borrowed only to build the
# fixture, and the commits under test below use DOCTOR alone.
SETUP = DOCTOR | set(vocab.for_bundle("phc").roles["frontdesk"]) \
        | set(vocab.for_bundle("phc").roles["nurse"])
A_DOCTOR = "user:ravi"
NOW = "2026-10-31T10:05:00+00:00"

# What the doctor keys. Two diagnosis rows, and the second is `refuted`: a
# finding the patient denied, recorded without being asserted. Before this
# change the mapping wrote `verification_status: {const: confirmed}` on every
# row, so this row was unexpressible and would have been published as a
# confirmed diagnosis.
NOTE = {
    "history": "Fever three days, passing more urine at night.",
    "examination": "Hydrated, chest clear.",
    "assessment": "Known type 2 diabetes, intercurrent fever.",
    "diagnosis": [
        {"condition": "44054006", "clinical_status": "active",
         "verification_status": "confirmed", "onset": "2024-03-01"},
        {"condition": "297142003", "clinical_status": "active",
         "verification_status": "refuted"},
    ],
    "plan": "Paracetamol, review in three days.",
}
MEDICINE = {"drug": "777067000", "dose": 500, "dose_unit": "mg",
            "route": "26643006", "frequency": "229798009",
            "duration": 3, "duration_unit": "d"}
SCRIPT = {"medications": [MEDICINE]}


# ---------------------------------------------------------------------------
# 1. Declarations. The group declares its own sub questions, and every coded
#    one binds a value set. This is the whole difference from `structured`.
# ---------------------------------------------------------------------------

GROUPS = {}
for op in (CONSULT, RX):
    schema = validate.load(op["input"])
    for link_id, group in validate.row_groups(schema).items():
        GROUPS[link_id] = group

assert sorted(GROUPS) == ["diagnosis", "medications"], sorted(GROUPS)
for link_id, group in sorted(GROUPS.items()):
    subs = validate.row_questions(group)
    assert subs, "%s declares no sub questions, so it is a group in name only" % link_id
    assert validate.row_label(group) != "row", \
        "%s does not say what one of its rows is called" % link_id
    for sub_id, q in subs.items():
        assert q["type"] in validate.TYPES, (sub_id, q["type"])
        assert q["type"] not in ("group", "structured"), \
            "%s.%s is a %s; a row holds answers, not another shape" % (link_id, sub_id, q["type"])
        if q["type"] == "choice":
            slug = terminology.answer_binding(q)
            assert slug, "%s.%s is a choice that binds nothing, so nothing " \
                         "checks its answer" % (link_id, sub_id)
            assert terminology.LOCAL.concepts(slug), slug
ok("both groups declare their sub questions, and every coded one binds a value set")

assert not [q for op in (CONSULT, RX)
            for q in validate.walk(validate.load(op["input"])["questions"])
            if q["type"] == "structured"], \
    "a consultation or a prescription still carries an unvalidated structured answer"
ok("neither form carries a `structured` answer any more")

# Each value set names where every concept was confirmed. A seeded code and a
# confirmed one are indistinguishable once a row is written.
SLUGS = sorted({terminology.answer_binding(q)
                for group in GROUPS.values()
                for q in validate.row_questions(group).values()
                if terminology.answer_binding(q)})
assert len(SLUGS) == 8, SLUGS
for slug in SLUGS:
    blob = json.loads((ROOT / "terminology" / ("%s.json" % slug)).read_text())
    assert not blob["verified"].startswith("unverified"), (slug, blob["verified"])
    assert blob["source"], slug
    for code, concept in blob["concepts"].items():
        assert not concept["verified"].startswith("unverified"), (slug, code)
        assert concept["display"], (slug, code)
        assert concept.get("why"), "%s/%s does not say why this code" % (slug, code)
ok("all %d value sets name where each concept was confirmed and why that one" % len(SLUGS))

# The two lists that are short because nothing authoritative was reachable say
# so in the file, in words, rather than reading as complete.
for slug, word in (("condition-code", "NOT A PRIMARY HEALTH CENTRE DIAGNOSIS LIST"),
                   ("medication-code", "A STARTER SET, NOT A FORMULARY")):
    blob = json.loads((ROOT / "terminology" / ("%s.json" % slug)).read_text())
    assert word in blob["source"], slug
    assert "SIGN-OFF" in blob["source"], \
        "%s is incomplete and does not name the sign-off it needs" % slug
ok("the diagnosis and medicine lists say they are not complete, and name the sign-off")


# ---------------------------------------------------------------------------
# 2. Validation, per row. Every rule the form has, applied to every row.
# ---------------------------------------------------------------------------

def problems(op, payload):
    schema = validate.load(op["input"])
    return (validate.make_validator(schema)(op, payload)
            + terminology.answer_problems(schema, payload))


assert problems(CONSULT, NOTE) == [], problems(CONSULT, NOTE)
assert problems(RX, SCRIPT) == [], problems(RX, SCRIPT)
ok("a sound consultation and a sound prescription both validate")

# One required sub answer missing from the SECOND row. The sentence has to say
# which row, or a prescriber reads "medications is invalid" and guesses.
half = {"medications": [MEDICINE, {k: v for k, v in MEDICINE.items() if k != "route"}]}
assert problems(RX, half) == ["medications[1].route is required"], problems(RX, half)
ok("a row missing a required answer is refused by row number: %s"
   % problems(RX, half)[0])

# A code the value set does not hold, in one row of several. This is the
# failure that had nowhere to be caught: `structured` had no sub schema, so a
# drug name typed as text became the stored code.
wrong = {"medications": [MEDICINE, dict(MEDICINE, drug="Paracetamol 500mg")]}
assert problems(RX, wrong) == \
    ["medications[1].drug is 'Paracetamol 500mg', which is not a code in medication-code"], \
    problems(RX, wrong)
ok("a drug name typed as text is refused, in the row it was typed in")

# A code from the wrong value set. Both are real SNOMED codes with believable
# displays, which is why the branch matters: 26643006 is a route.
crossed = {"diagnosis": [dict(NOTE["diagnosis"][0], condition="26643006")],
           "assessment": "x"}
assert any("not a code in condition-code" in line for line in problems(CONSULT, crossed)), \
    problems(CONSULT, crossed)
ok("a real code from the wrong value set is refused: a route is not a diagnosis")

# A key the group did not declare. The old mapping read `{item: [medication,
# drug, code]}`, so a renderer sending any of three names was accepted.
stray = {"medications": [dict(MEDICINE, dosage_instruction="1 tab TDS")]}
assert problems(RX, stray) == \
    ["medications[0].dosage_instruction is not a question on this medicine"], \
    problems(RX, stray)
ok("an answer the group did not declare is refused: %s" % problems(RX, stray)[0])

# A row that is not a row.
assert problems(RX, {"medications": ["Paracetamol 500 TDS"]}) == \
    ["medications[0] is not a medicine: a medicine is a set of answers, not a single value"], \
    problems(RX, {"medications": ["Paracetamol 500 TDS"]})
assert problems(RX, {"medications": "Paracetamol 500 TDS"}) == \
    ["medications is a list of rows, one per medicine"]
ok("a prescription written as a sentence is refused, where it used to be stored")

# Required, and empty. An empty list is not an answer.
assert problems(RX, {}) == ["medications is required"]
assert problems(RX, {"medications": []}) == ["medications is required"]
# And the optional group: no diagnosis is no rows, not an empty one.
assert problems(CONSULT, {"assessment": "x"}) == []
assert problems(CONSULT, {"assessment": "x", "diagnosis": []}) == []
ok("a required group with no rows is refused, and an optional one with none is fine")

# A sub question's link_id at the top level has lost the row it belonged to.
assert problems(RX, dict(SCRIPT, drug="777067000")) == \
    ["drug is not a question on this form"]
ok("a sub answer sent at the top level is refused, not read as row zero")


# ---------------------------------------------------------------------------
# 3. Mapping. One record row per group row, each with its author, and never a
#    row standing in for an absent answer.
# ---------------------------------------------------------------------------

(dx_record,) = [r for r in CONSULT["mapping"] if r["resource"] == "condition"]
(rx_record,) = RX["mapping"]
assert dx_record["per_row"] == "diagnosis", dx_record
assert rx_record["per_row"] == "medications", rx_record
for record in (dx_record, rx_record):
    assert any("actor" in s for s in record["fields"].values()), record["resource"]
    for column in record["fields"]:
        assert column in TABLES[record["resource"]], \
            "%s has no column %s" % (record["resource"], column)
ok("each group maps to one record per row, with an author, into columns that exist")

rows = mapping.records(CONSULT, NOTE, actor=A_DOCTOR)
conditions = [row for resource, row in rows if resource == "condition"]
assert len(conditions) == 2, rows
assert [c["code"] for c in conditions] == ["44054006", "297142003"], conditions
assert [c["verification_status"] for c in conditions] == ["confirmed", "refuted"], conditions
assert conditions[0]["code_display"] == "Type 2 diabetes mellitus", conditions[0]
assert conditions[0]["onset"] == "2024-03-01"
assert "onset" not in conditions[1], \
    "a row with no onset must leave the column absent, not hold an empty string"
assert all(c["created_by"] == A_DOCTOR for c in conditions), conditions
ok("two diagnosis rows become two condition rows, in order, each with its author")

# The risk a repeating group multiplies: a row whose coded answer is absent
# must write NOTHING rather than a row with a dose and no drug, and it must
# not borrow the code from the row above it.
blank = dict(NOTE, diagnosis=[NOTE["diagnosis"][0],
                              {"clinical_status": "active",
                               "verification_status": "confirmed"}])
made = [row for resource, row in mapping.records(CONSULT, blank, actor=A_DOCTOR)
        if resource == "condition"]
assert len(made) == 1 and made[0]["code"] == "44054006", made
ok("a row with no coded answer writes no row, and does not inherit the one above it")

(medicine,) = [row for resource, row in mapping.records(RX, SCRIPT, actor=A_DOCTOR)
               if resource == "medication_request"]
assert medicine["medication"] == "777067000", medicine
assert medicine["medication_system"] == "http://snomed.info/sct", medicine
assert medicine["dose"] == 500 and medicine["dose_unit"] == "mg", medicine
assert medicine["route_display"] == "Oral route", medicine
assert medicine["frequency_display"] == "Three times daily", medicine
assert medicine["duration"] == 3 and medicine["duration_unit"] == "d", medicine
assert "dosage_instruction" not in medicine, \
    "the dose is five columns now; a prose column would let them disagree"
ok("a medicine row is a drug, a dose, a route, a frequency and a course length")


# ---------------------------------------------------------------------------
# 4. The guard and the adapter. Commit on the rendered surface, rows read back.
# ---------------------------------------------------------------------------

def fresh():
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="B01", actor=A_DOCTOR)
    for op, payload in (("phc.op.patient-register",
                         {"name": "Sunita Devi", "age": 34, "sex": "female",
                          "phone": "9876500000", "village": "Yadiki",
                          "category": "general"}),
                        ("phc.op.vitals-record",
                         {"systolic": 124, "diastolic": 78, "pulse": 80})):
        decision = proposals.commit(store, BUNDLE, op, thread=thread, payload=payload,
                                    caps=SETUP, actor=A_DOCTOR)
        assert decision, (op, decision.reason)
    return store, thread


store, thread = fresh()
for op, payload in (("phc.op.consult-document", NOTE),
                    ("phc.op.rx-prescribe", SCRIPT)):
    before = len(store.audit(thread))
    decision = proposals.commit(store, BUNDLE, op, thread=thread, payload=payload,
                                caps=DOCTOR, actor=A_DOCTOR)
    assert decision, (op, decision.reason)
    assert len(store.audit(thread)) == before + 1, op
    assert store.audit(thread)[-1].outcome == "allowed", op
ok("the consultation and the prescription commit, and each writes its audit line")

stored = store.select("condition", thread=thread, where={}, fields=[], limit=10)
assert len(stored) == 2, stored
assert {r["code"] for r in stored} == {"44054006", "297142003"}, stored
assert store.count("condition", thread=thread, where={"code": "44054006"}) == 1
assert store.count("condition", thread=None,
                   where={"verification_status": "refuted"}) == 1
ok("a diagnosis is countable by its code and by how sure the clinician was")

(line,) = store.select("medication_request", thread=thread, where={}, fields=[], limit=10)
assert line["medication"] == "777067000" and line["created_by"] == A_DOCTOR, line
assert store.count("medication_request", thread=None,
                   where={"medication": "777067000"}) == 1
ok("a prescription is countable by drug, which is what a stock report needs")

refused = proposals.commit(store, BUNDLE, "phc.op.rx-prescribe", thread=thread,
                           payload=wrong, caps=DOCTOR, actor=A_DOCTOR)
assert not refused and "not a code in medication-code" in refused.reason, refused.reason
assert len(store.select("medication_request", thread=thread, where={},
                        fields=[], limit=10)) == 1, "a refused payload wrote a row"
ok("a prescription carrying an uncoded drug is refused at the guard and writes nothing")


# ---------------------------------------------------------------------------
# 5. The projection. One Condition per diagnosis, one MedicationRequest per
#    medicine, inside an ABDM OPConsultRecord.
# ---------------------------------------------------------------------------

# Which section each kind of row belongs in is the CALLER's declaration, the
# way a view declares its query: kernel/fhir.py may not know that a condition
# is a complaint. These two are the slices NRCeS's own example puts them in.
WANTED = {"ChiefComplaints": [("condition", {})],
          "Medications": [("medication_request", {"status": "active"})]}

doc = fhir.document(store, thread, profile="OPConsultRecord",
                    sections_wanted=WANTED, now=NOW)
kinds = [e["resource"]["resourceType"] for e in doc["entry"]]
assert kinds[0] == "Composition", kinds
assert kinds.count("Condition") == 2, kinds
assert kinds.count("MedicationRequest") == 1, kinds
ok("the visit projects to an OPConsultRecord: %s"
   % ", ".join("%d %s" % (kinds.count(k), k) for k in sorted(set(kinds))))

comp = doc["entry"][0]["resource"]
assert comp["meta"]["profile"] == ["%s/OPConsultRecord" % fhir.NRCES], comp["meta"]
for path in fhir.PROFILES["OPConsultRecord"]["required"]:
    assert comp.get(path), "Composition.%s is required and absent" % path
# Fixed by the profile digest, not chosen here.
assert comp["type"]["coding"] == [{"system": fhir.SNOMED, "code": "371530004",
                                  "display": "Clinical consultation report"}], comp["type"]
titles = {s["title"]: s for s in comp["section"]}
assert set(titles) == {"Chief complaints", "Medications"}, titles
assert titles["Chief complaints"]["code"]["coding"][0] == \
    {"system": fhir.SNOMED, "code": "422843007",
     "display": "Chief complaint section"}, titles["Chief complaints"]
assert titles["Medications"]["code"]["coding"][0]["code"] == "721912009"
ok("its Composition carries the profile's fixed type and the published section codes")

refs = {e["fullUrl"]: e["resource"] for e in doc["entry"]}
for section in comp["section"]:
    for entry in section["entry"]:
        assert entry["reference"] in refs, entry
assert all(a["reference"] in refs for a in comp["author"]), comp["author"]
ok("every reference in the document resolves inside the document")

denied = next(e["resource"] for e in doc["entry"]
              if e["resource"]["resourceType"] == "Condition"
              and e["resource"]["code"]["coding"][0]["code"] == "297142003")
assert denied["verificationStatus"]["coding"][0] == {
    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
    "code": "refuted"}, denied["verificationStatus"]
assert denied["clinicalStatus"]["coding"][0]["code"] == "active", denied
assert "onsetDateTime" not in denied, denied
ok("a finding the patient denied is published as refuted, not as a diagnosis")

known = next(e["resource"] for e in doc["entry"]
             if e["resource"]["resourceType"] == "Condition"
             and e["resource"]["code"]["coding"][0]["code"] == "44054006")
assert known["code"]["coding"][0] == {"system": fhir.SNOMED, "code": "44054006",
                                      "display": "Type 2 diabetes mellitus"}, known["code"]
assert known["onsetDateTime"] == "2024-03-01", known
assert known["recorder"]["reference"] in refs, known
assert known["verificationStatus"]["coding"][0]["code"] == "confirmed", known
ok("a confirmed diagnosis is a SNOMED coded Condition with an onset and a recorder")

mr = next(e["resource"] for e in doc["entry"]
          if e["resource"]["resourceType"] == "MedicationRequest")
assert mr["status"] == "active" and mr["intent"] == "order", mr
assert mr["medicationCodeableConcept"]["coding"][0] == {
    "system": fhir.SNOMED, "code": "777067000",
    "display": "Acetaminophen only product"}, mr["medicationCodeableConcept"]
(dosage,) = mr["dosageInstruction"]
assert dosage["route"]["coding"][0]["code"] == "26643006", dosage
assert dosage["additionalInstruction"][0]["coding"][0] == {
    "system": fhir.SNOMED, "code": "229798009",
    "display": "Three times daily"}, dosage["additionalInstruction"]
assert dosage["doseAndRate"] == [{"doseQuantity": {
    "value": 500, "unit": "mg", "system": fhir.UCUM, "code": "mg"}}], dosage["doseAndRate"]
assert dosage["timing"]["repeat"]["boundsDuration"] == {
    "value": 3, "unit": "d", "system": fhir.UCUM, "code": "d"}, dosage["timing"]
assert isinstance(dosage["doseAndRate"][0]["doseQuantity"]["value"], int), \
    "a quoted number is not a FHIR decimal"
ok("the prescription is a Dosage with a coded route, a UCUM dose and a duration")

# A number with no unit is not a Quantity. Checked directly on the projection
# rather than through the store, because the validator makes a dose unit
# required per row, so no stored row can reach this branch: a mutation proved
# that the rule was unreachable from a real payload and therefore unchecked.
bare = fhir.medication_request(
    {"id": "mr-x", "status": "active", "intent": "order", "dose": 500,
     "duration": 3, "duration_unit": "d",
     "duration_unit_system": fhir.UCUM},
    subject="urn:uuid:p", encounter="urn:uuid:e")
(only,) = bare["dosageInstruction"]
assert "doseAndRate" not in only, \
    "a dose of 500 with no unit was published as if the reader could guess"
assert only["timing"]["repeat"]["boundsDuration"]["unit"] == "d", only
ok("a dose with no unit is not published at all, and the course length still is")

again = fhir.document(store, thread, profile="OPConsultRecord",
                      sections_wanted=WANTED, now=NOW)
assert again == doc, "the same rows projected to a different document"
ok("the same rows project to the same document, so ABDM sees one visit once")

try:
    fhir.document(store, thread, profile="OPConsultRecord",
                  sections_wanted={"PhysicalExamination": [("condition", {})]}, now=NOW)
except KeyError as exc:
    assert "PhysicalExamination" in str(exc), exc
    ok("a slice whose published code nobody could read is refused, not guessed")
else:
    raise AssertionError("a section with no published code was emitted")

try:
    fhir.document(store, thread, profile="OPConsultRecord",
                  sections_wanted={"Medications": [("notes", {})]}, now=NOW)
except KeyError as exc:
    assert "no FHIR projection" in str(exc), exc
    ok("a row with no projection is refused, rather than published as the nearest thing")
else:
    raise AssertionError("a notes row was published as some other resource")


# ---------------------------------------------------------------------------
# 6. The rule the layering exists for: no clinical word in the engine.
# ---------------------------------------------------------------------------

# Only the SNOMED backed value sets, and the questions. The FHIR status sets
# and the UCUM units are left out and the reason is not laziness: their codes
# are ordinary English words and bare symbols, so `active`, `unknown`, `d` and
# `mo` appear in any module's live code for reasons that have nothing to do
# with a patient. A check that failed on those would be renamed into silence
# within a week. What is left is every word that could only be here because
# somebody typed a clinical fact into the engine.
CLINICAL = ("condition-code", "medication-code", "medication-route",
            "medication-frequency")
WORDS = sorted({code for slug in CLINICAL
                for code in terminology.LOCAL.concepts(slug)}
               | {c["display"] for slug in CLINICAL
                  for c in terminology.LOCAL.concepts(slug).values()}
               | set(GROUPS))
assert len(WORDS) >= 44, len(WORDS)

ENGINE = ("kernel/mapping.py", "kernel/fhir.py", "kernel/proposals.py",
          "kernel/state.py", "kernel/terminology.py", "catalogue/validate.py",
          "adapters/local/store.py")
sys.path.insert(0, str(ROOT / "scripts"))
from engine_code import engine_code                            # noqa: E402

for name in ENGINE:
    live = engine_code(ROOT / name)
    assert live.strip() and "\ndef\n" in live, name
    typed = [w for w in WORDS if '"%s"' % w in live or "'%s'" % w in live]
    assert not typed, "%s types the clinical word(s) %r" % (name, typed)
ok("no engine module types a diagnosis, a drug, a route or a frequency: %d words" % len(WORDS))

print("ok   repeating groups: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. Each was run.
# ---------------------------------------------------------------------------
#
# - make `_rows` skip a row that is not the first: a missing required answer in
#   row 1 stops being reported.
# - make `_row` write a row whose coded answer is absent: the blank diagnosis
#   row becomes a condition with a status and no code.
# - resolve a per_row record's bound questions against the whole form instead
#   of the group: the build fails rather than binding the wrong value set.
# - drop the branch check from the SNOMED seeder: a route becomes a storable
#   diagnosis.
# - have `document` call `observation` for every row again: a diagnosis is
#   published as an Observation.
# - put a frequency's number in `timing.repeat.frequency` read off its display:
#   there is nothing in the row to read it from, which is the point.
