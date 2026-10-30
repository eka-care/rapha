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

Not here, deliberately, and each is a named plan step rather than an omission:
OPConsultRecord (plan step 7, and it needs Condition, MedicationRequest and
ServiceRequest projections that depend on the repeating group work in step 4);
the gateway call that sends a bundle (care_phc/connectors/abdm/base.py is
where that boundary already lives, and linking a care context is already
declared irreversible); and the ECDH encryption M2 wraps a bundle in.

Pure: takes a Store and returns a dict. No network. Python 3.9.
Run: python3 -m kernel.fhir
"""
from __future__ import annotations

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
}

DOCUMENT_BUNDLE = "%s/DocumentBundle" % NRCES

# Which resource a row of each table becomes. A table name, not a concept:
# this says "an observation row is a FHIR Observation", which is true of every
# bundle, and says nothing about what any particular observation means.
RESOURCE_TYPE = {
    "observation": "Observation",
    "patient": "Patient",
    "encounter": "Encounter",
}

# The columns a coding spans, by prefix. The adapter owns its schema, so these
# are the query grammar's field names (kernel/contracts.py), which the adapter
# stores verbatim. See adapters/local/store.py TABLES["observation"].
CODE, CODE_SYSTEM, CODE_DISPLAY = "code", "code_system", "code_display"
UNIT, UNIT_SYSTEM = "unit", "unit_system"


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
    if row.get(display):
        out["display"] = row[display]
    return out


def observation(row, *, subject, encounter, performer=None):
    """One observation row as a FHIR R4 Observation.

    `status` is `final`, because there is one path to a stored row and it goes
    through the guard with a person's tap on it. A proposal is not a row, so
    there is nothing here that could be `preliminary`: the unconfirmed state
    lives on the proposal, in the kernel, and never reaches the store. That is
    invariant I4 in the shape the standard already has, with nothing invented.
    """
    out = {
        "resourceType": "Observation",
        "id": row["id"],
        "status": "final",
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
                entries.append((observation(row, subject=subject_ref,
                                            encounter=encounter_ref,
                                            performer=performer), ref))
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
            section["code"] = {"coding": [{"system": SNOMED,
                                           "code": declared["code"],
                                           "display": declared["title"]}]}
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
                           "unit": "g/dL"},
                          subject="urn:uuid:p", encounter="urn:uuid:e")
    assert "coding" not in uncoded["code"] and uncoded["code"]["text"] == "Haemoglobin", \
        "a code with no system is text, never a resolvable coding"
    assert uncoded["valueQuantity"] == {"value": 9.4, "unit": "g/dL"}, uncoded

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
