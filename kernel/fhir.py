"""The bundle seam: rows in, an ABDM document out.

Why this exists, and why it is a projection rather than a storage format
------------------------------------------------------------------------
We store flat rows and generate the document at the edge. Both halves are
deliberate and they pull in opposite directions, so the reason is written down
once, here:

- flat rows, because a district count is `WHERE code = '8480-6'` and a trend
  is an `ORDER BY`. A document store makes both of those a JSON path
  expression, and the people who need them have a spreadsheet, not a query
  planner.
- a document at the edge, because that is what ABDM consumes. A DocumentBundle
  is an envelope for sending, not a record for keeping: it carries a signature,
  a timestamp and a Composition that exists to say "these resources were
  published together on this date". Keeping it would mean keeping a snapshot
  that goes stale the moment a correction lands.

The mapping already declares which answer becomes which column
(kernel/mapping.py), so this file is mechanical rather than clever: it reads
columns and writes FHIR elements. It has to be, because of the rule below.

The rule this file must not break
---------------------------------
It may not name a clinical concept. There is no `if code == "29463-7"` here
and there must never be one: that would be the renderer's failure mode
(kernel/ARCHITECTURE.md's main one) moved one layer down, where it is harder
to see. What a resource knows about itself comes from the row, and which
section of which profile it lands in is declared on the questionnaire
question. The only clinical vocabulary in this file is ABDM's own profile
table below, which is the standard's and not a facility's, in exactly the way
catalogue/vocab.py CARE_RESOURCES is the adapter's and not a facility's.

What is here and what is not
----------------------------
Here: the WellnessRecord profile, which is the one that carries vital signs,
and the Observation and Patient and Encounter and Practitioner resources a
vitals visit needs. That is the vertical slice.

Also here, 2026-10-31: the OPConsultRecord profile with the Condition and
MedicationRequest projections a consultation needs, which is what the
repeating group work unblocked. Its eight section codes are real, read off
NRCeS's own published example and recorded in
docs/superpowers/specs/2026-10-30-nrces-section-codes.md, which is also why
the WellnessRecord sections above still carry no code: NRCeS's own
WellnessRecord example publishes none, so an absent code there is the
standard's answer rather than a gap.

Not here, deliberately, and each is a named plan step rather than an omission:
the ServiceRequest projection an investigation needs, which waits on the lab
order question becoming a repeating group too; the gateway call that sends a
bundle (care_phc/connectors/abdm/base.py is
where that boundary already lives, and linking a care context is already
declared irreversible); and the ECDH encryption M2 wraps a bundle in.

Pure: takes a Store and returns a dict. No network. Python 3.9.
Run: python3 -m kernel.fhir
"""
from __future__ import annotations

import base64
import hashlib
import uuid

# ---------------------------------------------------------------------------
# ABDM's grammar. Not a facility's words: these come from the NRCeS India
# profiles and a bundle declaring something else is not an ABDM bundle. Kept
# here for the same reason catalogue/vocab.py keeps CARE_RESOURCES: it is the
# standard's list, so there is one copy and no bundle may extend it.
# ---------------------------------------------------------------------------

NRCES = "https://nrces.in/ndhm/fhir/r4/StructureDefinition"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
SNOMED = "http://snomed.info/sct"
HL7_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"

# How a narrative row travels. `text/plain` because what is stored is the
# note's own words and not a rendered document, and a content type that
# promised markup would be a claim about the text. The language is the
# Composition's own, which is the only language this product writes a note in
# today; a note in another script keeps its script inside the text, and a
# per-note language column is the honest fix when there is one.
NARRATIVE_TYPE = "text/plain"
NARRATIVE_LANGUAGE = "en-IN"

# One entry per ABDM hiType we emit. `sections` is that profile's
# Composition.section slices, from the NRCeS digest, with the SNOMED code that
# types each one.
#
# `code: None` is not a placeholder to be tidied away later; it is a gap being
# reported. NRCeS discriminates a section slice by its `code`, and the ABDM
# catalogue's own atom for this profile (shared.fhir.map-wellnessrecord) is a
# stub: it lists the eight slice names and says "which resource type fills
# each slice" is not yet authored, so the section codes are not published
# anywhere we can read. A section is therefore emitted with its title and its
# entries and no code, which is structurally valid (the digest does not
# require Composition.section.code) and will not match the slice until
# somebody supplies the code from the implementation guide. Inventing a SNOMED
# code to fill the hole would be worse than leaving it visible: a wrong
# section code is a record filed under the wrong heading, which reads as
# correct everywhere.
PROFILES = {
    "WellnessRecord": {
        "profile": "%s/WellnessRecord" % NRCES,
        "title": "Wellness Record",
        # Composition.type, which the digest requires (min 1) while fixing
        # no value, unlike OPConsultRecord where it fixes a SNOMED code. The
        # digest requires `Composition.type` and not `Composition.type.coding`
        # for this profile, so a CodeableConcept carrying only `text`
        # satisfies it, and that is what is emitted while `code` is None.
        #
        # The gap is deliberate and visible. A wrong SNOMED code here is a
        # record filed under the wrong heading, which reads as correct
        # everywhere it is read, so the code is left absent until somebody
        # supplies it from the implementation guide rather than guessed.
        "type": {"code": None, "text": "Wellness record"},
        # Every path the NRCeS digest for this profile requires on the
        # Composition, so a check can assert the document fills them instead
        # of asserting a list somebody typed twice. Grows with the table.
        "required": ("status", "type", "subject", "date", "author", "title",
                     "section"),
        "sections": {
            "VitalSigns": {"title": "Vital signs", "code": None},
            "BodyMeasurement": {"title": "Body measurement", "code": None},
            "PhysicalActivity": {"title": "Physical activity", "code": None},
            "GeneralAssessment": {"title": "General assessment", "code": None},
            "WomenHealth": {"title": "Women health", "code": None},
            "Lifestyle": {"title": "Lifestyle", "code": None},
            "OtherObservations": {"title": "Other observations", "code": None},
            "DocumentReference": {"title": "Document reference", "code": None},
        },
    },
    # Read off NRCeS's own Bundle-OPConsultNote-example-05 on 2026-10-30 and
    # again on 2026-10-31, through the abdm-docs server's get_fhir_example,
    # and recorded in docs/superpowers/specs/2026-10-30-nrces-section-codes.md.
    # Unlike WellnessRecord above, every section here HAS a published SNOMED
    # code, and `Composition.type` is fixed by the profile digest to 371530004.
    #
    # Four of the profile's twelve slices are absent, and absent on purpose:
    # PhysicalExamination, FamilyHistory, Referral and OtherObservations are
    # not populated by the example, so no code for them was published anywhere
    # this build could read. They are min 0, so omitting them is valid, and
    # reusing a code from the table below because it looks close is how a
    # record gets filed under the wrong heading.
    "OPConsultRecord": {
        "profile": "%s/OPConsultRecord" % NRCES,
        "title": "OP Consultation Record",
        "type": {"code": "371530004", "text": "Clinical consultation report"},
        "required": ("status", "type", "subject", "encounter", "date", "author",
                     "title", "section"),
        "sections": {
            "ChiefComplaints": {"title": "Chief complaints", "code": "422843007",
                                "display": "Chief complaint section"},
            "Allergies": {"title": "Allergies", "code": "722446000",
                                "display": "Allergy record"},
            "MedicalHistory": {"title": "Medical History", "code": "371529009",
                                "display": "History and physical report"},
            "InvestigationAdvice": {"title": "Investigation Advice", "code": "721963009",
                                "display": "Order document"},
            "Medications": {"title": "Medications", "code": "721912009",
                                "display": "Medication summary document"},
            "Procedure": {"title": "Procedure", "code": "371525003",
                                "display": "Clinical procedure report"},
            "FollowUp": {"title": "Follow Up", "code": "736271009",
                                "display": "Outpatient care plan"},
            # The example publishes the Composition's own type code here. That
            # is what it publishes; it is not a transcription slip.
            "DocumentReference": {"title": "Document Reference", "code": "371530004",
                                  "display": "Clinical consultation report"},
        },
    },
}

DOCUMENT_BUNDLE = "%s/DocumentBundle" % NRCES

# Which resource a row of each table becomes. A table name, not a concept:
# this says "an observation row is a FHIR Observation", which is true of every
# bundle, and says nothing about what any particular observation means.
RESOURCE_TYPE = {
    "observation": "Observation",
    "notes": "DocumentReference",
    "patient": "Patient",
    "encounter": "Encounter",
    "condition": "Condition",
    "medication_request": "MedicationRequest",
}

# The columns a coding spans, by prefix. The adapter owns its schema, so these
# are the query grammar's field names (kernel/contracts.py), which the adapter
# stores verbatim. See adapters/local/store.py TABLES["observation"].
CODE, CODE_SYSTEM, CODE_DISPLAY = "code", "code_system", "code_display"
UNIT, UNIT_SYSTEM = "unit", "unit_system"

# Every stored column a projection below copies VERBATIM into a FHIR `code`
# element, and the value set R4 binds that element to.
#
# `code` in the FHIR sense, not a CodeableConcept: a bare token from a fixed
# list, with no system column beside it, so none of the three binding forms in
# kernel/terminology.py applies and nothing validated these. Three of them
# were already being copied through from an operation's `{const: ...}`, which
# is a literal somebody typed; `scripts/check_verification.py` is what now
# holds each one against the cached published list, at build time, before a
# gateway gets the chance.
#
# A column is in this table because a projection copies it, which is why
# `encounter.status` and `diagnostic_report.status` are NOT here: `encounter()`
# translates its stored workflow state into an R4 code rather than copying it,
# and no projection reads a diagnostic_report row at all. Both of those are
# stated as rules with checks on them, because the day a projection starts
# copying one verbatim is the day a workflow word becomes a FHIR code.
#
# Keyed by (table, column) rather than by column, because `status` means a
# different list on each resource and one of the three systems below is in a
# different namespace from the other two.
STATUS_BINDING = {
    ("observation", "status"): "observation-status",
    ("medication_request", "status"): "medicationrequest-status",
    ("medication_request", "intent"): "medicationrequest-intent",
}

# The columns a projection reads from a row and does NOT copy into a FHIR
# `code` element, so that a check can tell "no binding was declared" from
# "this is deliberately not a FHIR code". `encounter.status` is this build's
# own workflow state, translated by `encounter()` below.
TRANSLATED_STATUS = {("encounter", "status")}


def _urn(seed):
    """A stable urn:uuid for a row id.

    Stable, because a bundle regenerated from the same rows must be the same
    bundle: ABDM deduplicates on the bundle identifier and a fresh uuid4 per
    projection would publish the same visit twice under two identities.
    uuid5 over the row id does that with no state to keep.
    """
    return "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, "phc:%s" % seed)


def _number(text):
    """A stored value as a JSON number where it is one, else as given.

    Every column in the SQLite adapter is TEXT (adapters/local/store.py), so a
    systolic of 140 reads back as "140". FHIR's Quantity.value is a decimal and
    a quoted number fails validation, so the cast happens here, at the one
    place that turns a row into FHIR, rather than in the adapter where it would
    have to guess which columns are numeric.
    """
    if isinstance(text, (int, float)):
        return text
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    return int(number) if number.is_integer() else number


def _coding(row, code=CODE, system=CODE_SYSTEM, display=CODE_DISPLAY):
    """A FHIR Coding from the three columns one coding spans, or None.

    No system means no coding. A code without a system is meaningless in FHIR
    R4 and unexportable to ABDM, so an uncoded row is projected without a
    `code.coding` rather than with a bare code nobody can resolve. CARE makes
    `system` optional on its own Coding (care/emr/resources/common/coding.py)
    and stores codings as untyped JSON, which is how a systemless code gets in.
    """
    if not row.get(code) or not row.get(system):
        return None
    out = {"system": row[system], "code": str(row[code])}
    if display and row.get(display):
        out["display"] = row[display]
    return out


def _concept(row, code=CODE, system=CODE_SYSTEM, display=CODE_DISPLAY):
    """A CodeableConcept from those columns, or None.

    A coding where the row has a system, and `{"text": ...}` where it has only
    a code. The second is not a fallback worth being proud of; it is how an
    uncoded row stays readable instead of becoming an unresolvable code, and it
    is the shape a diagnosis this build cannot code would take if one ever
    reached a column.
    """
    found = _coding(row, code, system, display)
    if found:
        out = {"coding": [found]}
        if found.get("display"):
            out["text"] = found["display"]
        return out
    if row.get(code):
        return {"text": str(row[code])}
    return None


def observation(row, *, subject, encounter, performer=None):
    """One observation row as a FHIR R4 Observation.

    `status` is the row's own answer and never a literal here. It used to be
    `final`, on the argument that there is one path to a stored row and it
    goes through the guard with a person's tap on it. That argument is about
    whether a row EXISTS, and `Observation.status` is about whether its value
    is settled, which is a different question with a different answer.

    The two come apart in the laboratory, where this build already has the
    second pair of eyes: `lab.op.result-enter` writes the values and the
    report it writes with them says `preliminary`, and `lab.op.result-verify`
    is a separate operation a separate person performs. So between those two
    taps every keyed value was published to ABDM as `final` while the report
    carrying them said `preliminary`. R4 has the word for that state and this
    file was overriding it.

    A row with no status is refused rather than given one. R4 makes the
    element required (1..1) and this file may not decide how settled somebody
    else's measurement is; the operation that writes the row declares it, and
    `scripts/check_verification.py` holds every declared literal against the
    published list.
    """
    status = row.get("status")
    if not status:
        raise KeyError(
            "observation row %r carries no status, and R4 requires "
            "Observation.status. The operation that writes the row declares "
            "it; this file may not choose how settled a measurement is."
            % row.get("id"))
    out = {
        "resourceType": "Observation",
        "id": row["id"],
        "status": status,
        "subject": {"reference": subject},
        "encounter": {"reference": encounter},
    }
    if row.get("category"):
        # The row's own column. A bundle choosing `vital-signs` is a bundle
        # declaring it in a mapping's {const: ...}, which is why this file
        # does not have to know what a vital sign is.
        out["category"] = [{"coding": [{"system": HL7_CATEGORY,
                                        "code": row["category"]}]}]
    coding = _coding(row)
    if coding:
        out["code"] = {"coding": [coding]}
        if coding.get("display"):
            out["code"]["text"] = coding["display"]
    elif row.get(CODE):
        out["code"] = {"text": str(row[CODE])}
    if row.get("created_date"):
        out["effectiveDateTime"] = row["created_date"]
    if performer:
        out["performer"] = [{"reference": performer}]

    value = row.get("value")
    if value not in (None, ""):
        if row.get(UNIT) and row.get(UNIT_SYSTEM):
            # Quantity.unit is the printable symbol and Quantity.code is the
            # coded one. For UCUM they are the same string: the symbol IS the
            # code, which is why the adapter keeps one column and not two.
            out["valueQuantity"] = {"value": _number(value), "unit": row[UNIT],
                                    "system": row[UNIT_SYSTEM], "code": row[UNIT]}
        elif row.get(UNIT):
            out["valueQuantity"] = {"value": _number(value), "unit": row[UNIT]}
        else:
            out["valueString"] = str(value)
    return out


# The columns a Condition's three codings span, and the ones a
# MedicationRequest's five span. Query grammar field names, which the adapter
# stores verbatim: see adapters/local/store.py TABLES.
CLINICAL, CLINICAL_SYSTEM = "clinical_status", "clinical_status_system"
VERIFICATION, VERIFICATION_SYSTEM = "verification_status", "verification_status_system"
MEDICATION = ("medication", "medication_system", "medication_display")
ROUTE = ("route", "route_system", "route_display")
FREQUENCY = ("frequency", "frequency_system", "frequency_display")


def condition(row, *, subject, encounter, performer=None):
    """One condition row as a FHIR R4 Condition.

    `verificationStatus` is the row's own answer and never a default. That is
    invariant I6 held at the projection as well as at the write: a finding the
    patient denied is published as `refuted`, which records it without
    asserting it, and a row that says nothing about how sure anybody was
    publishes no verificationStatus rather than a confident one.

    NRCeS's own Condition examples carry a clinicalStatus and no
    verificationStatus, so neither is required and both are emitted from what
    the row holds.
    """
    out = {"resourceType": "Condition", "id": row["id"],
           "subject": {"reference": subject},
           "encounter": {"reference": encounter}}
    clinical = _concept(row, CLINICAL, CLINICAL_SYSTEM, None)
    if clinical:
        out["clinicalStatus"] = clinical
    verification = _concept(row, VERIFICATION, VERIFICATION_SYSTEM, None)
    if verification:
        out["verificationStatus"] = verification
    code = _concept(row)
    if code:
        out["code"] = code
    if row.get("onset"):
        out["onsetDateTime"] = row["onset"]
    if row.get("created_date"):
        out["recordedDate"] = row["created_date"]
    if performer:
        out["recorder"] = {"reference": performer}
    return out


def medication_request(row, *, subject, encounter, performer=None):
    """One medicine row as a FHIR R4 MedicationRequest.

    The dosage is a Dosage element rather than a sentence, which is the point
    of the five columns behind it: a dose as a Quantity with its UCUM unit, a
    coded route, and a course length as a Duration. It used to be one
    `dosage_instruction` string, so nothing downstream could read the dose.

    The frequency is published as `dosageInstruction.additionalInstruction`,
    carrying the SNOMED concept the answer named. That is what NRCeS's own
    OPConsultRecord example does, and it is deliberately NOT turned into
    `timing.repeat.frequency`: reading "3" out of the words "Three times
    daily" would be this file inventing structured data from a label, which is
    the one thing it may not do.
    """
    out = {"resourceType": "MedicationRequest", "id": row["id"],
           # Both required by R4, and both the row's own: `intent` is a
           # {const: order} in the operation's mapping rather than a literal
           # here, so this file decides nothing about what a prescription is.
           "status": row.get("status") or "unknown",
           "subject": {"reference": subject},
           "encounter": {"reference": encounter}}
    if row.get("intent"):
        out["intent"] = row["intent"]
    medication = _concept(row, *MEDICATION)
    if medication:
        out["medicationCodeableConcept"] = medication
    if row.get("created_date"):
        out["authoredOn"] = row["created_date"]
    if performer:
        out["requester"] = {"reference": performer}

    dosage = {}
    route = _concept(row, *ROUTE)
    if route:
        dosage["route"] = route
    frequency = _concept(row, *FREQUENCY)
    if frequency:
        dosage["additionalInstruction"] = [frequency]
    dose = _quantity(row, "dose", "dose_unit", "dose_unit_system")
    if dose:
        dosage["doseAndRate"] = [{"doseQuantity": dose}]
    length = _quantity(row, "duration", "duration_unit", "duration_unit_system")
    if length:
        dosage["timing"] = {"repeat": {"boundsDuration": length}}
    if dosage:
        out["dosageInstruction"] = [dosage]
    return out


def document_reference(row, *, subject, encounter, performer=None,
                       document_type=None):
    """One narrative row as a FHIR R4 DocumentReference carrying its text.

    THIS IS THE DESIGNED FALLBACK, and until now it was a sentence rather
    than a path. `kernel/terminology.py` says an uncoded diagnosis travels as
    narrative text and the note still reaches ABDM, and the architecture
    document's ceilings say it twice. It was not true: a narrative row had no
    projection, every profile requires at least one section, so a
    consultation whose findings this build cannot code published NOTHING.
    Measured, not assumed: the probe is in scripts/check_codification.py and
    it is the check that would fail if this were removed again.

    The shape is the NRCeS implementation guide's own, read 2026-10-31 from
    the OPConsultRecord example Bundle-OPConsultNote-example-05 through the
    abdm-docs server, where a DocumentReference carries `status`, `docStatus`,
    a `type` with a SNOMED coding, a `subject` and one `content.attachment`
    with a contentType, a language, base64 `data`, a title and a creation
    instant. The example's attachment is a PDF of a laboratory report; this
    one is the note's own text, which is the same element with a different
    content type and needs nothing invented.

    `document_type` is the profile's own document type, passed in by
    `document()` below, because what kind of document this is is the profile's
    fact and not this function's. Nothing here names a document type.

    `encounter` is accepted and unused: R4's DocumentReference has a `context`
    element whose shape (`context.encounter` plus a period) is not in the
    example, so it is left out rather than guessed at from the signature.
    """
    text = str(row.get("text") or "")
    if not text.strip():
        # A narrative row with nothing in it is not a degraded document, it is
        # an empty attachment under a heading claiming there is a note.
        return None
    attachment = {"contentType": NARRATIVE_TYPE, "language": NARRATIVE_LANGUAGE,
                  "data": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    out = {"resourceType": "DocumentReference", "id": row["id"],
           "meta": {"profile": ["%s/DocumentReference" % NRCES]},
           "status": "current", "docStatus": "final",
           "subject": {"reference": subject}}
    if document_type and document_type.get("code"):
        out["type"] = {"coding": [{"system": SNOMED,
                                   "code": document_type["code"],
                                   "display": document_type["text"]}],
                       "text": document_type["text"]}
        attachment["title"] = document_type["text"]
    if row.get("created_date"):
        attachment["creation"] = row["created_date"]
    if performer:
        out["author"] = [{"reference": performer}]
    out["content"] = [{"attachment": attachment}]
    return out


def _quantity(row, value, unit, system):
    """A FHIR Quantity from a value column and its unit columns, or None.

    A value with no unit is not a Quantity: a dose of 500 is a different thing
    in milligrams and in millilitres, so an unmeasured number is dropped here
    rather than published as if the reader could guess. The same rule the
    validator holds at the other end, where a dose unit is required per row.
    """
    if row.get(value) in (None, "") or not row.get(unit):
        return None
    out = {"value": _number(row[value]), "unit": row[unit]}
    if row.get(system):
        # For UCUM the printable symbol IS the code, which is why the adapter
        # keeps one column: see observation() above.
        out["system"] = row[system]
        out["code"] = row[unit]
    return out


def patient(row):
    """A patient row as a FHIR R4 Patient.

    The ABHA number becomes an identifier and not the resource id. A national
    identifier is a fact about a person, not our name for their row, and a
    patient with no ABHA yet is an ordinary patient rather than an unprojectable
    one.
    """
    out = {"resourceType": "Patient", "id": row["id"]}
    if row.get("name"):
        out["name"] = [{"text": row["name"]}]
    if row.get("sex"):
        out["gender"] = row["sex"]
    if row.get("phone"):
        out["telecom"] = [{"system": "phone", "value": row["phone"]}]
    if row.get("abha_number"):
        out["identifier"] = [{
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                                 "code": "MR"}]},
            "system": "https://healthid.ndhm.gov.in",
            "value": row["abha_number"]}]
    return out


def practitioner(actor):
    """An actor string as a FHIR R4 Practitioner.

    Every row carries its author, because a mapping record with no
    `{actor: id}` field fails lint (kernel/mapping.py). So the document always
    has an author to name, which is what Composition.author requires. The id is
    hashed rather than the raw actor string, which may be a login name.
    """
    return {
        "resourceType": "Practitioner",
        "id": "prac-%s" % hashlib.sha256(actor.encode()).hexdigest()[:12],
        "name": [{"text": actor}],
    }


def encounter(row, *, subject):
    out = {"resourceType": "Encounter", "id": row["id"],
           "status": "finished" if row.get("status") == "completed" else "in-progress",
           "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                     "code": "AMB", "display": "ambulatory"},
           "subject": {"reference": subject}}
    if row.get("created_date"):
        out["period"] = {"start": row["created_date"]}
    return out


# Which function turns a row of each table into a resource. A table name, not
# a concept, for the same reason RESOURCE_TYPE is: this says "a condition row
# becomes a FHIR Condition", which is true of every bundle.
#
# `document` used to call `observation()` for every row of every section, so a
# section carrying conditions would have published them as Observations with a
# diagnosis in the code field. Nothing caught it because nothing but vitals
# had a projection to call.
PROJECTIONS = {
    "observation": observation,
    "condition": condition,
    "medication_request": medication_request,
    "notes": document_reference,
}

# The resources whose projection needs to know what kind of document it is
# travelling in. One, and it is the narrative attachment: what a note IS is
# the profile's fact ("Clinical consultation report"), so the projection is
# handed it rather than typing it. Every other projection describes something
# that means the same thing in any document and is given nothing.
TYPED_BY_PROFILE = ("notes",)


def sections(profile):
    """The section slices this profile declares. A caller may not invent one."""
    return PROFILES[profile]["sections"]


def document(store, thread, *, profile, sections_wanted, now,
             identifier_system="http://phc.local"):
    """A thread as an ABDM DocumentBundle for one profile.

    `sections_wanted` maps a section slice name to the resource rows that go in
    it, as [(resource, where)] queries. The caller says which section a kind of
    row belongs in, because that is a declaration and not this file's business:
    see kernel/views.py for the same division, where a view declares a query
    and the kernel runs it.

    Raises KeyError for a profile or a section slice the standard does not
    declare, rather than emitting a section ABDM will reject.
    """
    spec = PROFILES[profile]
    for slice_name in sections_wanted:
        if slice_name not in spec["sections"]:
            raise KeyError("%s declares no section '%s'; it has %s"
                           % (profile, slice_name, sorted(spec["sections"])))

    enc_rows = store.select("encounter", thread=thread, where={}, fields=[], limit=1)
    if not enc_rows:
        raise KeyError("no such thread %r" % thread)
    enc = enc_rows[0]
    pat_rows = store.select("patient", thread=thread, where={}, fields=[], limit=1)
    if not pat_rows:
        # A visit with no person on it cannot be published: every profile makes
        # Composition.subject required, and a document about nobody is not a
        # degraded document, it is a different kind of mistake. Refused here
        # rather than emitted and rejected by the gateway an hour later.
        raise KeyError("thread %r has no subject, so it has no Composition.subject"
                       % thread)
    pat = pat_rows[0]

    subject_ref = _urn(pat["id"])
    encounter_ref = _urn(enc["id"])
    entries = [(patient(pat), subject_ref),
               (encounter(enc, subject=subject_ref), encounter_ref)]

    authors, section_out = [], []
    for slice_name, queries in sections_wanted.items():
        refs = []
        for resource, where in queries:
            for row in store.select(resource, thread=thread, where=dict(where or {}),
                                    fields=[], limit=200):
                ref = _urn(row["id"])
                actor = row.get("created_by")
                performer = None
                if actor:
                    prac = practitioner(actor)
                    performer = _urn(prac["id"])
                    if performer not in [r for _, r in authors]:
                        authors.append((prac, performer))
                project = PROJECTIONS.get(resource)
                if project is None:
                    raise KeyError(
                        "no FHIR projection for a %r row, so a section asking "
                        "for one would publish something else. Add it to "
                        "PROJECTIONS rather than letting the nearest one "
                        "serve." % resource)
                extra = {"document_type": spec["type"]} \
                    if resource in TYPED_BY_PROFILE else {}
                made = project(row, subject=subject_ref,
                               encounter=encounter_ref, performer=performer,
                               **extra)
                if made is None:
                    # A projection that refuses this particular row: an empty
                    # narrative is the only one today. Skipped rather than
                    # published as an entry pointing at nothing.
                    continue
                entries.append((made, ref))
                refs.append({"reference": ref,
                             "display": RESOURCE_TYPE.get(resource, resource)})
        if not refs:
            # An empty section is not a section. Every slice is min 0, so
            # omitting it is correct, and emitting an entryless one would
            # publish a heading claiming nothing was found rather than that
            # nothing was looked for.
            continue
        declared = spec["sections"][slice_name]
        section = {"title": declared["title"], "entry": refs}
        if declared["code"]:
            # The display the standard publishes for that code, which is not
            # the section's title: NRCeS's "Chief complaints" section carries
            # the display "Chief complaint section". Using the title would put
            # a display beside a code that the code system does not give it.
            section["code"] = {"coding": [{"system": SNOMED,
                                           "code": declared["code"],
                                           "display": declared["display"]}]}
        section_out.append(section)

    if not section_out:
        raise KeyError("thread %r has nothing to put in %s, and every profile "
                       "requires at least one section" % (thread, profile))
    entries = list(authors) + entries

    composition = {
        "resourceType": "Composition",
        "id": "comp-%s" % enc["id"],
        "meta": {"profile": [spec["profile"]], "lastUpdated": now},
        "language": "en-IN",
        "identifier": {"system": identifier_system, "value": enc["id"]},
        "status": "final",
        "subject": {"reference": subject_ref},
        "encounter": {"reference": encounter_ref},
        "date": now,
        "author": [{"reference": ref} for _, ref in authors],
        "title": spec["title"],
        "type": {"text": spec["type"]["text"]},
        "section": section_out,
    }
    if spec["type"]["code"]:
        composition["type"]["coding"] = [
            {"system": SNOMED, "code": spec["type"]["code"],
             "display": spec["type"]["text"]}]
    entries.insert(0, (composition, _urn("composition:%s" % enc["id"])))

    return {
        "resourceType": "Bundle",
        "id": "phc-%s-%s" % (profile.lower(), enc["id"]),
        # versionId is required by the DocumentBundle profile, not optional
        # metadata: a bundle without it fails NRCeS validation. "1" because a
        # correction is published as a new bundle that relatesTo this one,
        # which is how ABDM versions a record, rather than as a second
        # version of the same identifier.
        "meta": {"versionId": "1", "profile": [DOCUMENT_BUNDLE],
                 "lastUpdated": now},
        "identifier": {"system": identifier_system, "value": enc["id"]},
        "type": "document",
        "timestamp": now,
        "entry": [{"fullUrl": ref, "resource": res} for res, ref in entries],
    }


def demo():
    import json

    row = {"id": "obs-1", "category": "vital-signs", "code": "8480-6",
           "code_system": LOINC, "code_display": "Systolic blood pressure",
           "value": "140", "unit": "mm[Hg]", "unit_system": UCUM,
           "status": "final",
           "created_by": "user:nurse", "created_date": "2026-10-31T09:14:00+00:00"}
    obs = observation(row, subject="urn:uuid:p", encounter="urn:uuid:e",
                      performer="urn:uuid:n")
    assert obs["code"]["coding"] == [{"system": LOINC, "code": "8480-6",
                                      "display": "Systolic blood pressure"}], obs
    assert obs["valueQuantity"] == {"value": 140, "unit": "mm[Hg]",
                                    "system": UCUM, "code": "mm[Hg]"}, obs
    assert obs["valueQuantity"]["value"] == 140 \
        and not isinstance(obs["valueQuantity"]["value"], str), \
        "a quoted number is not a FHIR decimal"
    assert obs["status"] == "final" and obs["category"][0]["coding"][0]["code"] \
        == "vital-signs"


    uncoded = observation({"id": "o2", "code": "Haemoglobin", "value": "9.4",
                           "unit": "g/dL", "status": "preliminary"},
                          subject="urn:uuid:p", encounter="urn:uuid:e")
    assert "coding" not in uncoded["code"] and uncoded["code"]["text"] == "Haemoglobin", \
        "a code with no system is text, never a resolvable coding"
    assert uncoded["valueQuantity"] == {"value": 9.4, "unit": "g/dL"}, uncoded
    # The status is the row's, not this file's. A keyed laboratory value that
    # nobody has verified is `preliminary` and is published as `preliminary`.
    assert uncoded["status"] == "preliminary", uncoded
    try:
        observation({"id": "o3", "code": "x", "value": "1"},
                    subject="urn:uuid:p", encounter="urn:uuid:e")
    except KeyError:
        pass
    else:
        raise AssertionError("an observation with no status was given one here")
    # And the three columns a projection copies verbatim into a FHIR `code`
    # element each name the published list R4 binds that element to.
    assert set(STATUS_BINDING) == {("observation", "status"),
                                   ("medication_request", "status"),
                                   ("medication_request", "intent")}, STATUS_BINDING

    assert _urn("obs-1") == _urn("obs-1") and _urn("obs-1") != _urn("obs-2")
    assert sorted(sections("WellnessRecord"))[:2] == ["BodyMeasurement",
                                                      "DocumentReference"]
    pat = patient({"id": "pat-1", "name": "Sunita Devi", "sex": "female",
                   "abha_number": "12-3456-7890-1234"})
    assert pat["identifier"][0]["value"] == "12-3456-7890-1234"
    assert pat["id"] == "pat-1", "an ABHA number is an identifier, not our row id"
    assert json.dumps(obs)
    print("ok   kernel.fhir")


if __name__ == "__main__":
    demo()
