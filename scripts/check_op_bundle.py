"""Run: python3 scripts/check_op_bundle.py

A visit leaves this building as an NRCeS OPConsultRecord.

What is proved here, in order:

  the consultation this facility publishes is DECLARED, once, on the bundle,
    and no caller types a section heading
  every section code emitted is the one read off NRCeS's own example and
    recorded in the fact sheet, read from that file rather than typed twice
  every slice this build fills takes the resource type NRCeS fixes for it
  the seven honest consultations, each its own case and its own sentence:
    one that coded nothing, one with a finding the patient denied, one with a
    guess, one with a past illness and its onset, one with medicines, one
    with none, and one that also had vitals taken
  every reference in every one of those documents resolves inside it
  the nine slices this build cannot fill are declared nowhere, and a section
    with no published code is refused rather than given the nearest one

Which validator was run, and what it does not prove
---------------------------------------------------
All five bundles this file generates were put through the ABDM catalogue's
tier one structural validator on 2026-10-31, against the pinned NRCeS
profiles (ndhm.in 6.5.0), catalogue version 2026.09.16. Every one came back
with no findings. Four were run with `record_type: OPConsultation`: the
narrative-only consultation, the one carrying three coded findings and no
medicines, the one carrying findings and a prescription, and the one from the
visit that also had vitals taken. The fifth is that visit's WellnessRecord,
run with `record_type: WellnessRecord`.

The exact JSON that was validated is what OP_BUNDLE_DUMP writes at the foot
of this file, from the same rows.

That is a structural check and nothing more. It does not validate
terminology: no SNOMED, LOINC or UCUM code in these bundles was checked
against a code system by it. It does not check nested paths such as
`subject.reference`, and it does not enforce the section slice
discriminators, because every slice is `min: 0`. The official HL7 validator
with `-ig ndhm.in#6.5.0` has NOT been run on any of these bundles, and until
it has, the slice codes are correct because they were read off the
publisher's own example rather than because a validator confirmed them.

Nothing here sends anything anywhere. Generating a document and validating it
locally is not publishing it, and no module in this build has a path to an
ABDM endpoint.

Pure: in memory stores, no socket. Python 3.9.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore                       # noqa: E402
from catalogue import vocab                                        # noqa: E402
from kernel import declarations, fhir, proposals                   # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
CAPS = set(vocab.for_bundle("phc").roles["mo"]) \
    | set(vocab.for_bundle("phc").roles["frontdesk"]) \
    | set(vocab.for_bundle("phc").roles["nurse"])
A_DOCTOR = "user:ravi"
NOW = "2026-10-31T10:05:00+00:00"
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-10-30-nrces-section-codes.md"

VER = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CLIN = "http://terminology.hl7.org/CodeSystem/condition-clinical"


def table(after):
    """The two column markdown table that follows a heading in the fact sheet.

    The codes and the resource types are read out of the file that recorded
    where they came from, rather than typed here as well. A fact typed twice
    is a fact that can disagree with itself, and this one is the difference
    between a record under the right heading and a record under a heading
    that reads as correct everywhere.
    """
    body = SPEC.read_text().split(after, 1)[1]
    rows, past_header = {}, False
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if set("".join(cells)) <= {"-"}:
            past_header = True       # the ---|--- rule under the column names
        elif past_header:
            rows[cells[0]] = cells[1:]
    assert rows, after
    return rows


# ---------------------------------------------------------------------------
# 1. The placement is declared, once, on the bundle.
# ---------------------------------------------------------------------------

CONSULT = BUNDLE.documents["consultation"]
assert CONSULT["profile"] == "OPConsultRecord", CONSULT
DECLARED = CONSULT["sections_wanted"]
assert set(DECLARED) == {"ChiefComplaints", "Medications", "DocumentReference"}, \
    sorted(DECLARED)
assert [r for q in DECLARED.values() for r, _ in q] \
    == ["condition", "medication_request", "notes"], DECLARED
ok("the consultation this facility publishes is declared on the bundle: three "
   "of the profile's twelve slices, and which rows go under each")

# ---------------------------------------------------------------------------
# And that placement SURVIVES BEING COMPILED, in order. The third seam, closed
# 2026-11-01: `documents` is a bundle key now, so a Go process can read where a
# row is filed instead of being handed it by a caller.
#
# THE ORDER IS THE WHOLE OF THIS CHECK. `fhir.document()` walks the declared
# sections in order, and that order is observable three times in what it
# publishes: the order of the sections, the order of the Bundle's entries, and
# the order the authors are discovered in. catalogue.json is written with
# sort_keys=True, so a MAPPING of slice name to queries would arrive
# alphabetically at every engine that reads the file -- and both engines read
# the same file, so the differential check would compare two identically
# reordered documents and pass. Nothing else in the gate looks at this. That
# is why the artifact carries a LIST and why the comparison is against the
# DECLARATION rather than against the other engine.
# ---------------------------------------------------------------------------

COMPILED = json.loads(
    (ROOT / "catalogue" / "catalogue.json").read_text())["documents"]
assert sorted(COMPILED) == sorted(BUNDLE.documents), \
    "the compiled artifact and the loaded bundle declare different documents: " \
    "%s against %s" % (sorted(COMPILED), sorted(BUNDLE.documents))
for did, declared in BUNDLE.documents.items():
    carried = COMPILED[did]
    assert carried["profile"] == declared["profile"], carried
    assert [s["slice"] for s in carried["sections"]] \
        == list(declared["sections_wanted"]), (
            "documents.%s: the compiled section order is %s and the bundle "
            "declares %s. A section order that changes on the way into "
            "catalogue.json publishes every one of this facility's "
            "consultations with its sections the other way round."
            % (did, [s["slice"] for s in carried["sections"]],
               list(declared["sections_wanted"])))
    assert [[q["resource"] for q in s["queries"]] for s in carried["sections"]] \
        == [[r for r, _ in qs] for qs in declared["sections_wanted"].values()], \
        carried
    assert [[q["where"] for q in s["queries"]] for s in carried["sections"]] \
        == [[dict(w or {}) for _, w in qs]
            for qs in declared["sections_wanted"].values()], carried

# And this facility's own declaration is NOT in alphabetical order, so the
# assertion above is not a check that passes whatever the compiler does. If a
# bundle ever declares its sections alphabetically this fails loudly, and the
# answer is to hold a bundle that does not, never to drop the check.
_ORDERED = [s["slice"] for s in COMPILED["consultation"]["sections"]]
assert _ORDERED != sorted(_ORDERED), (
    "bundles/phc declares its sections in alphabetical order, so the order "
    "check above would pass against a compiler that sorted them and proves "
    "nothing: %s" % _ORDERED)
ok("and it survives being compiled into catalogue.json IN ORDER, which is "
   "what a second engine reads instead of being handed a placement")

# And it compiles to the projection's own argument names, so a caller cannot
# retype a placement on the way in. That is the whole point: a diagnosis was
# filed under Chief complaints in one check and under Medical History in
# another, which is one visit recorded two ways.
assert sorted(CONSULT) == ["profile", "sections_wanted"], sorted(CONSULT)
SLICES = sorted(fhir.sections("OPConsultRecord"))


def placements_typed(text):
    """Slice names typed as keys of a `sections_wanted` literal.

    Scoped to that keyword argument on purpose. A slice name appearing
    anywhere in a file is not the defect; a slice name chosen at a call site is, because
    that is the copy that can disagree with the declaration. The scan is
    narrow enough to be wrong in one direction only: it cannot catch a
    placement built up in a variable first, and this file passes its own
    `sections_wanted` a variable in section 5, which is how that limit is
    known rather than assumed.
    """
    typed = []
    for found in re.finditer(r"sections_wanted=", text):
        before = text[max(0, found.start() - 300):found.start()]
        if "WellnessRecord" in before:
            # A wellness record's slices carry no code at all, so this
            # module's reason for declaring a placement does not reach them
            # and nothing declares one. Named rather than silently skipped.
            continue
        ahead = text[found.end():found.end() + 200]
        typed += [s for s in SLICES if '"%s"' % s in ahead]
    return sorted(set(typed))


for name in ("scripts/check_op_bundle.py", "scripts/check_codification.py",
             "scripts/check_verification.py"):
    typed = placements_typed((ROOT / name).read_text())
    assert not typed, "%s chooses the placement of %r at a call site instead " \
                      "of reading the bundle's declaration" % (name, typed)
# The WellnessRecord's placement is still chosen at the call site, in this
# file and in two others, and is NOT declared. Asserted rather than left
# unsaid: that record's slices carry no code at all, so this module's reason
# for declaring a placement does not reach it, and a second declaration
# nobody checks would be worse than one honest gap.
assert "WellnessRecord" not in [d["profile"] for d in BUNDLE.documents.values()]
ok("no caller chooses a consultation section placement: all three read the "
   "one declaration, and only the wellness record is still typed")

# A profile, a slice or a resource the standard or this build does not have is
# a build failure rather than a document a gateway rejects.
MANIFEST = {"operations": ["phc.op.consult-document"], "documents": {}}
OPS = {"phc.op.consult-document": {"writes": ["condition", "notes"]}}


def refused(documents):
    return declarations._lint_documents(dict(MANIFEST, documents=documents), OPS)


assert refused({"d": {"profile": "OPConsultRecord",
                      "sections": {"ChiefComplaints": [{"resource": "condition"}]}}}) == []
for case, says in (
        ({"profile": "DischargeSummaryRecord", "sections": {}},
         "is not a profile this build emits"),
        ({"profile": "OPConsultRecord", "sections": {"FamilyHistory": []}},
         "declares no section 'FamilyHistory'"),
        ({"profile": "OPConsultRecord",
          "sections": {"ChiefComplaints": [{"resource": "diagnostic_report"}]}},
         "no FHIR projection"),
        ({"profile": "OPConsultRecord",
          "sections": {"Medications": [{"resource": "medication_request"}]}},
         "no operation this bundle loads writes"),
        ({"profile": "OPConsultRecord", "sections": {}},
         "declares no section, and every profile requires"),
):
    problems = refused({"d": case})
    assert any(says in p for p in problems), (says, problems)
ok("a declared document is linted against ABDM's own grammar: five ways it is "
   "refused at build time rather than rejected by a gateway")


# ---------------------------------------------------------------------------
# 2. Every code emitted is the one the fact sheet recorded, from a source.
# ---------------------------------------------------------------------------

CODES = table("## OPConsultRecord: eight real codes, all SNOMED CT")
assert len(CODES) == 8, sorted(CODES)
BY_TITLE = {s["title"]: s for s in fhir.sections("OPConsultRecord").values()}
assert sorted(BY_TITLE) == sorted(CODES), (sorted(BY_TITLE), sorted(CODES))
for title, (code, display) in CODES.items():
    live = BY_TITLE[title]
    assert live["code"] == code, (title, live, code)
    assert live["display"] == display, (title, live, display)
ok("all 8 section codes and their displays are the ones read off NRCeS's own "
   "example, held against the file that recorded where they came from")

TYPES = table("## Which resource type each of the twelve slices takes")
assert len(TYPES) == 12, sorted(TYPES)
for slice_name, queries in DECLARED.items():
    (expected,) = TYPES[slice_name]
    for resource, _ in queries:
        assert fhir.RESOURCE_TYPE[resource] == expected, \
            "%s takes a %s and this build files a %s there" \
            % (slice_name, expected, fhir.RESOURCE_TYPE[resource])
ok("every slice this build fills carries the resource type NRCeS's own "
   "slicing fixes for it")


# ---------------------------------------------------------------------------
# 3. The seven honest consultations.
# ---------------------------------------------------------------------------

NARRATIVE = {"history": "Bukhaar teen din se.", "examination": "Chest clear.",
             "assessment": "Likely dengue fever.", "plan": "Review in three days."}
MEDICINE = {"medications": [{"drug": "777067000", "dose": 500, "dose_unit": "mg",
                             "route": "26643006", "frequency": "229798009",
                             "duration": 3, "duration_unit": "d"}]}
# Three codes the value set already holds, three different amounts of
# certainty. Nothing here is recalled and nothing here is invented.
DIAGNOSES = [
    {"condition": "297142003", "clinical_status": "active",
     "verification_status": "refuted"},
    {"condition": "44054006", "clinical_status": "active",
     "verification_status": "unconfirmed"},
    {"condition": "46635009", "clinical_status": "resolved",
     "verification_status": "confirmed", "onset": "2019-04-01"},
]
VITALS = {"systolic": 186, "diastolic": 112, "pulse": 92, "spo2": 97,
          "weight": 61.5, "temperature": 37.1}


def visit(token, consult, *, rx=None, vitals=None):
    """One patient, one visit, through the guard with a person's tap on it."""
    store = SqliteStore(":memory:")
    thread = store.open_thread(token=token, actor=A_DOCTOR)
    for op, payload in (("phc.op.patient-register",
                         {"name": "Sunita Devi", "age": 34, "sex": "female",
                          "phone": "9876500000", "village": "Yadiki",
                          "category": "general"}),
                        ("phc.op.vitals-record", vitals),
                        ("phc.op.consult-document", consult),
                        ("phc.op.rx-prescribe", rx)):
        if payload is None:
            continue
        decision = proposals.commit(store, BUNDLE, op, thread=thread,
                                    payload=payload, caps=CAPS, actor=A_DOCTOR)
        assert decision, (op, decision.reason)
    return store, thread


def consultation(store, thread):
    return fhir.document(store, thread, now=NOW, **CONSULT)


def resources(doc, kind):
    return [e["resource"] for e in doc["entry"]
            if e["resource"]["resourceType"] == kind]


def status_of(resource, element, system):
    (coding,) = resource[element]["coding"]
    assert coding["system"] == system, coding
    return coding["code"]


def section_of(doc, title):
    found = [s for s in doc["entry"][0]["resource"]["section"]
             if s["title"] == title]
    return found[0] if found else None


DOCS = {}

# (a) The consultation that coded nothing. This is most consultations: three
#     conditions and six medicines are all this build can code.
store, thread = visit("D01", dict(NARRATIVE))
assert store.select("condition", thread=thread, where={}, fields=[], limit=5) == []
DOCS["narrative only"] = only_words = consultation(store, thread)
composition = only_words["entry"][0]["resource"]
(section,) = composition["section"]
assert section["title"] == "Document Reference", composition["section"]
assert section["code"]["coding"][0]["code"] == CODES["Document Reference"][0]
(reference,) = resources(only_words, "DocumentReference")
carried = base64.b64decode(reference["content"][0]["attachment"]["data"]).decode()
assert "dengue" in carried.lower() and "Bukhaar" in carried, carried
assert not resources(only_words, "Condition"), only_words
ok("a consultation that coded nothing publishes an OPConsultRecord with one "
   "section: the doctor's own words, under the code NRCeS publishes for it")

# (b), (c), (d) Three findings, three certainties, one document.
store, thread = visit("D02", dict(NARRATIVE, diagnosis=DIAGNOSES))
DOCS["coded, no medicines"] = plain = consultation(store, thread)
BY_CODE = {c["code"]["coding"][0]["code"]: c for c in resources(plain, "Condition")}
assert len(BY_CODE) == 3, sorted(BY_CODE)

denied = BY_CODE["297142003"]
assert status_of(denied, "verificationStatus", VER) == "refuted", denied
ok("a finding the patient denied travels in the document as refuted: "
   "recorded, and not asserted")

guess = BY_CODE["44054006"]
assert status_of(guess, "verificationStatus", VER) == "unconfirmed", guess
ok("a guess travels as unconfirmed, so a clinician reading this record in "
   "another facility is told it is a guess")

past = BY_CODE["46635009"]
assert status_of(past, "clinicalStatus", CLIN) == "resolved", past
assert past["onsetDateTime"] == "2019-04-01", past
ok("a past illness travels as resolved with the date it started, which is how "
   "it reaches another facility without reading as a current one")

# All three under one heading, which is the declaration's doing. The build
# cannot tell a presenting complaint from a past condition, and the honest
# consequence is that a resolved 2019 finding is filed beside today's.
chief = section_of(plain, "Chief complaints")
assert len(chief["entry"]) == 3, chief
assert chief["code"]["coding"][0]["code"] == CODES["Chief complaints"][0]
# "and under exactly one heading" was asserted here and DELETED for the same
# reason as the loop below: the declaration is the only thing that could file
# a diagnosis twice, and section 1 pins that declaration to three slices and
# three resources, so it fails first. Recorded rather than shipped.
ok("every coded diagnosis is filed under one heading, whatever its "
   "clinical status: this build does not ask which heading it belongs under")

# (e) With no medicines, the Medications section is absent rather than empty.
assert section_of(plain, "Medications") is None, plain["entry"][0]["resource"]
assert not resources(plain, "MedicationRequest"), plain
ok("a consultation with no prescription publishes no Medications section, "
   "rather than a heading saying none were given")

# (f) With medicines. One section more, and a Dosage rather than a sentence.
store, thread = visit("D03", dict(NARRATIVE, diagnosis=DIAGNOSES), rx=MEDICINE)
DOCS["coded, with medicines"] = full = consultation(store, thread)
medicines = section_of(full, "Medications")
assert medicines["code"]["coding"][0]["code"] == CODES["Medications"][0]
(request,) = resources(full, "MedicationRequest")
assert medicines["entry"][0]["reference"] in \
    [e["fullUrl"] for e in full["entry"]], medicines
(dosage,) = request["dosageInstruction"]
assert dosage["doseAndRate"][0]["doseQuantity"]["system"] == fhir.UCUM, dosage
assert dosage["route"]["coding"][0]["system"] == fhir.SNOMED, dosage
ok("a prescription adds the Medications section under its published code, "
   "with the dose as a UCUM quantity and the route as a coding")

# (g) The same visit with vitals taken as well. The vitals do NOT go into the
#     consultation: the two OPConsultRecord slices that take an Observation
#     are PhysicalExamination and OtherObservations, NRCeS has published a
#     code for neither, and a section a reader cannot discriminate is worse
#     than a second document. So the visit publishes two, which is what this
#     build already does for a wellness record.
store, thread = visit("D04", dict(NARRATIVE, diagnosis=DIAGNOSES),
                      rx=MEDICINE, vitals=VITALS)
DOCS["with vitals"] = both = consultation(store, thread)
assert not resources(both, "Observation"), \
    "a vital sign was published inside the consultation, under a heading " \
    "NRCeS has not published a code for"
DOCS["wellness, same visit"] = wellness = fhir.document(
    store, thread, profile="WellnessRecord",
    sections_wanted={"VitalSigns": [("observation", {"category": "vital-signs"})]},
    now=NOW)
assert len(resources(wellness, "Observation")) == len(VITALS), wellness
assert wellness["entry"][0]["resource"]["meta"]["profile"] \
    == ["%s/WellnessRecord" % fhir.NRCES], wellness["entry"][0]
assert both["entry"][0]["resource"]["subject"] \
    == wellness["entry"][0]["resource"]["subject"], "two documents, two patients"
ok("a visit that also had vitals taken publishes two documents about one "
   "patient: the consultation, and the wellness record the vitals belong in")

# And the same rows give the same document, every time, because ABDM
# deduplicates on the identifier.
assert consultation(store, thread) == both, \
    "the same visit projected to two different documents"
ok("the same rows project to the same document, so ABDM sees one visit once")


# ---------------------------------------------------------------------------
# 4. What is true of every one of those documents.
# ---------------------------------------------------------------------------

REQUIRED = fhir.PROFILES["OPConsultRecord"]["required"]
assert len(REQUIRED) >= 8, REQUIRED
for name, doc in DOCS.items():
    composition = doc["entry"][0]["resource"]
    for path in (REQUIRED if "wellness" not in name
                 else fhir.PROFILES["WellnessRecord"]["required"]):
        assert composition.get(path), "%s: Composition.%s is missing" % (name, path)
    assert doc["meta"]["profile"] == [fhir.DOCUMENT_BUNDLE], (name, doc["meta"])
    assert doc["meta"].get("versionId"), name
    assert doc["type"] == "document" and doc["timestamp"] == NOW, name
ok("every one of the %d documents fills every path its profile's digest makes "
   "required, and travels in a DocumentBundle with a version" % len(DOCS))

for name, doc in DOCS.items():
    present = {e["fullUrl"] for e in doc["entry"]}
    composition = doc["entry"][0]["resource"]
    pointing = {composition["subject"]["reference"],
                composition["encounter"]["reference"]} \
        | {a["reference"] for a in composition["author"]} \
        | {e["reference"] for s in composition["section"] for e in s["entry"]}
    for resource in [e["resource"] for e in doc["entry"]]:
        for key in ("subject", "encounter", "recorder", "requester"):
            if isinstance(resource.get(key), dict) and "reference" in resource[key]:
                pointing.add(resource[key]["reference"])
        for ref in resource.get("author") or []:
            pointing.add(ref["reference"])
    dangling = sorted(pointing - present)
    assert not dangling, "%s points outside itself: %r" % (name, dangling)
ok("every reference in every one of those documents resolves inside it: a "
   "reader needs nothing this build did not send")

# A cross cutting "no consultation section is emitted without its published
# code, and none empty" was written here and then DELETED, because it could
# not be made to fail first. Every consultation section's code and its
# non-emptiness is already asserted by the cases above: the narrative only
# document unpacks a single section and reads its code, the Chief complaints
# and Medications sections each have their code held against the fact sheet,
# and the absent Medications section is its own case. Every mutation that
# would have broken the loop broke one of those first, so it asserted nothing
# the file did not already prove and is recorded here instead of shipped.


# ---------------------------------------------------------------------------
# 5. The nine slices this build does not fill, and why each is a wall.
# ---------------------------------------------------------------------------

# Four of the twelve have no published code anywhere this build could read, so
# kernel/fhir.py declares them nowhere and document() refuses them by name.
UNPUBLISHED = ("PhysicalExamination", "FamilyHistory", "Referral",
               "OtherObservations")
for slice_name in UNPUBLISHED:
    assert slice_name in TYPES, slice_name
    assert slice_name not in fhir.sections("OPConsultRecord"), slice_name
    try:
        fhir.document(store, thread, profile="OPConsultRecord", now=NOW,
                      sections_wanted={slice_name: [("notes", {})]})
    except KeyError as refusal:
        assert "declares no section" in str(refusal), refusal
    else:
        raise AssertionError(
            "%s was emitted, and NRCeS has published no code for it: a "
            "section under a borrowed code reads as correct everywhere"
            % slice_name)
ok("the 4 slices NRCeS published no code for are declared nowhere and refused "
   "by name, rather than emitted under the nearest code that looks close")

# The other five need a resource this build has no projection for. Checked
# against PROJECTIONS rather than by listing them, so the day one is added the
# declaration can fill the slice and this check stops claiming it cannot.
CANNOT = {"Allergies": "AllergyIntolerance", "InvestigationAdvice": "ServiceRequest",
          "FollowUp": "Appointment", "Procedure": "Procedure"}
for slice_name, kind in CANNOT.items():
    assert TYPES[slice_name] == [kind], (slice_name, TYPES[slice_name])
    assert kind not in fhir.RESOURCE_TYPE.values(), \
        "%s is projectable now, so %s can be filled" % (kind, slice_name)
    assert slice_name not in DECLARED, slice_name
assert "Referral" in UNPUBLISHED and TYPES["Referral"] == ["ServiceRequest"]
ok("4 more wait on a resource this build cannot project: an allergy, an "
   "order, an appointment and a procedure. Referral waits on both")

# And the twelfth, which is the one that is not a missing code and not a
# missing resource. MedicalHistory has a published code and takes a
# Condition, both of which this build has. It is empty because the
# consultation form does not ask whether a diagnosis is today's complaint or
# a past illness, and nothing may infer it: a split on the clinical status
# code would file four of that value set's six statuses under no heading at
# all. This is a question for the form, named in the plan.
UNASKED = "MedicalHistory"
assert TYPES[UNASKED] == ["Condition"], TYPES[UNASKED]
assert fhir.sections("OPConsultRecord")[UNASKED]["code"], "this slice has a code"
assert "condition" in fhir.PROJECTIONS, "and this build projects a Condition"
assert UNASKED not in DECLARED, UNASKED
ok("the 12th slice is empty for neither of those reasons: the code and the "
   "resource both exist, and the form does not ask which heading a diagnosis "
   "belongs under")

assert len(set(DECLARED) | set(UNPUBLISHED) | set(CANNOT) | {UNASKED}) == 12, \
    "the twelve slices are not accounted for"
ok("3 of the profile's 12 slices are filled and 9 are accounted for: this is "
   "the whole table, not the part that was convenient")

# The bundles this file validated, written out on request so that a reader
# can put the same JSON through the validator again rather than taking the
# docstring's word for it:
#     OP_BUNDLE_DUMP=/some/dir python3 scripts/check_op_bundle.py
# Writes nothing and reaches nothing unless that variable is set.
DUMP = os.environ.get("OP_BUNDLE_DUMP")
if DUMP:
    for name, doc in DOCS.items():
        out = pathlib.Path(DUMP) / ("%s.json" % name.replace(", ", "-").replace(" ", "-"))
        out.write_text(json.dumps(doc, indent=2))
        print("ok   wrote %s" % out)

print("ok   op bundle: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. 25 mutations, 25 caught, and every one of the 20
# checks above is the FIRST to fail for at least one of them, so none of them
# is riding on a neighbour. Each mutation was confirmed present in the file
# before its failure was believed, and the file was confirmed restored after.
# ---------------------------------------------------------------------------
#
#  1 drop the Medications slice from the declaration
#  2 make a check type its own placement instead of reading the declaration
#  3 five mutations, one per lint rule: stop refusing an unknown profile, an
#    undeclared slice, an unprojectable resource, a resource nothing writes,
#    and a document with no section at all
#  4 two mutations, one per side: change a section code in kernel/fhir.py, and
#    change the same code in the fact sheet instead
#  5 change a slice's resource type in the fact sheet
#  6 truncate the narrative attachment so the doctor's words are not all there
#  7 store the denied finding as a guess
#  8 store the guess as denied
#  9 drop onsetDateTime from the Condition projection
# 10 publish only a section's first entry
# 11 write a prescription on the visit that had none
# 12 publish a dose without its unit
# 13 never take the vitals on the visit that had them
# 14 give the Composition a fresh id on every projection
# 15 drop Composition.title
# 16 leave the authors out of the bundle entries
# 17 stop refusing an undeclared slice by name in document()
# 18 make an Appointment projectable
# 19 change the 12th slice's resource type in the fact sheet
# 20 drop one unfillable slice from the tally
#
# One mutation was thrown away rather than counted: deleting the two lines
# that give a Quantity its UCUM system left an `if` with no body, so the file
# did not run at all and every check "failed" for the wrong reason. That is
# the shape of a mutation that proves nothing, and it is why the harness
# records which check failed first rather than only that something did.
