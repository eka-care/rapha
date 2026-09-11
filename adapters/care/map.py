"""Adapter 1's field mapping, declared once, in data.

Why this file is data and not code
----------------------------------
kernel/mapping.py already establishes the rule: a column nobody mapped is a
clinical value silently dropped, so the mapping is declared where it can be
checked instead of re-derived in whatever function happens to need it. That
grammar maps a questionnaire answer to a column. This one maps the other seam:
the query grammar's resource and field names (which adapters/local/store.py
stores verbatim as SQLite columns) to CARE's REST paths and JSON keys.

adapters/care/store.py contains no field name at all. Everything CARE calls
something else is below, once.

How each name here was established
----------------------------------
Every field carries one of three marks, and the mark is the deliverable:

  LIVE      Seen in an actual JSON response body from a public CARE instance
            (https://careapi.ohc.network) on 2026-09-11. Only the endpoints
            that serve unauthenticated reads could give this, which is one:
            /api/v1/govt/organization/. Writing to those instances was not
            done and must not be.

  SCHEMA    Taken from the OpenAPI document that same running instance serves
            at /api/schema/, which drf-spectacular generates from the
            serializers that are actually deployed. Stronger than reading
            models on GitHub (it is the wire contract of a running build, not
            a source file that may not be released), weaker than LIVE (a
            response body can still differ from its declared schema, and one
            already does: see PAGE_ENVELOPE below).

  SOURCE    Read in ohcnetwork/care on the develop branch, in the resource
            spec that builds the response. This is the mark for the fields the
            OpenAPI document flattens to a bare `object`: drf-spectacular
            cannot see through `perform_extra_serialization`, so what is
            inside an embedded patient or encounter is only knowable from the
            spec that serialises it. It resolves what SCHEMA leaves open, and
            it is weaker than LIVE for the same reason SCHEMA is: the deployed
            build may not be this commit.

  INFERRED  A guess. Not in the schema, not in the source, not seen on the
            wire. Nested objects
            that the schema declares as bare `object` are the main source:
            EncounterListSpec.patient is typed `{"additionalProperties": true,
            "type": "object"}`, so that a patient inside an encounter is keyed
            `id` is an inference from every other spec, not a fact.

The file this replaces
----------------------
care_phc/queries.py, deleted. It was written from reading care/emr/models and
had never run. Three of its assumptions are wrong against the schema above and
are recorded here so the next person does not make them again:

  - `Observation.objects.filter(encounter=..., category="vital-signs")`.
    Observation.category is a JSONField holding a Coding, not a string, so it
    never equals a string; the code is `vital_signs` with an underscore
    (ObservationCategoryChoices, SCHEMA); and the list endpoint offers no
    category filter at all, only `codes` and `encounter`.
  - `encounter.notes`. Notes hang off a NoteThread, which hangs off the
    patient and optionally the encounter. There is no encounter.notes.
  - `patient.identifiers` with `config_slug`. The field is
    `instance_identifiers`, each entry is {config: {...}, value: str}, and it
    is absent from PatientListSpec: a list response cannot answer "does this
    person have an ABHA", only a retrieve can.

Pure data. Imports nothing, touches no network. Python 3.9.
"""
from __future__ import annotations

LIVE = "live"
SCHEMA = "schema"
SOURCE = "source"
INFERRED = "inferred"

# The pagination envelope. SCHEMA says {count, next, previous, results}; the
# one LIVE response available says {count, results} and nothing else, on an
# endpoint whose schema declares all four. So the adapter reads `count` and
# `results` and pages with limit/offset, and never follows `next`.
PAGE_ENVELOPE = {"count": LIVE, "results": LIVE, "next": SCHEMA, "previous": SCHEMA}

# Authorization. Both schemes are in the running instance's securitySchemes:
# tokenAuth wants `Authorization: Token <t>` (a service account token, minted
# by POST /api/v1/users/{username}/generate_service_account_token/), jwtAuth
# wants `Authorization: Bearer <jwt>` (POST /api/v1/auth/login/). Which one a
# deployment uses is configuration, so the prefix is a constructor argument.
AUTH_SCHEMES = {"Bearer": SCHEMA, "Token": SCHEMA}


class Field:
    """One query grammar field: where it lives in a CARE response, whether
    CARE can filter on it server side, and how the name was established.

    `path` is dotted and read out of the response body. `param` is the query
    parameter that filters on it, or None when there is none and the adapter
    has to filter the rows itself. `values` translates the vocabulary the
    declarations use into CARE's, in that direction; reads translate back.
    """

    __slots__ = ("path", "param", "range_params", "values", "verified", "note")

    def __init__(self, path, param=None, range_params=None, values=None,
                 verified=INFERRED, note=""):
        self.path = path
        self.param = param
        self.range_params = range_params or {}
        self.values = values or {}
        self.verified = verified
        self.note = note

    def read(self, row):
        """This field's value out of a CARE response row, translated back."""
        value = row
        for part in self.path.split("."):
            if part.isdigit():
                if not isinstance(value, list) or len(value) <= int(part):
                    return None
                value = value[int(part)]
                continue
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        back = {v: k for k, v in self.values.items()}
        return back.get(value, value)

    def send(self, value):
        return self.values.get(value, value)


class Resource:
    """One query grammar resource against CARE.

    `path` is a template over the thread context: {patient}, {facility} and
    {thread} are filled from the encounter the read is scoped to, which is
    this adapter's whole cleverness and the same knowledge THREAD_COLUMN holds
    in adapters/local/store.py. A declaration never states it.

    `write` is None when CARE has no endpoint that creates this resource on
    its own; `write_reason` then says why, and store.write() raises it rather
    than posting something that 404s.
    """

    __slots__ = ("path", "thread_param", "fields", "write", "write_reason",
                 "write_defaults", "write_path", "write_side", "verified", "note")

    def __init__(self, path, fields, thread_param=None, write=None,
                 write_reason="", write_defaults=None, write_path=None,
                 write_side=(), verified=SCHEMA, note=""):
        self.path = path
        self.thread_param = thread_param
        self.fields = fields
        self.write = write
        self.write_reason = write_reason
        self.write_defaults = write_defaults or {}
        self.write_path = write_path or path
        # Columns the handler writes with a call of their own rather than a
        # key in the body. abha_number is the whole list: CARE has no such
        # field, only POST update_identifier.
        self.write_side = tuple(write_side)
        self.verified = verified
        self.note = note


# --------------------------------------------------------------------------
# The mapping. Left of the colon is the query grammar (and adapters/local's
# column names); right of it is CARE.
# --------------------------------------------------------------------------

RESOURCES = {

    # GET /api/v1/patient/ SCHEMA. The thread join is the encounter's patient,
    # so a patient read is a retrieve of one id, not a list: instance
    # identifiers (where an ABHA lives) are on PatientRetrieveSpec and NOT on
    # PatientListSpec, so a list can never answer abha_number.
    "patient": Resource(
        path="/api/v1/patient/{patient}/",
        write_path="/api/v1/patient/",
        verified=SCHEMA,
        note="retrieve by id; the thread's patient is read off the encounter",
        fields={
            "id": Field("id", verified=SCHEMA),
            "name": Field("name", param="name", verified=SCHEMA),
            # No `age` column on read. PatientCreateSpec accepts `age`
            # (SCHEMA) and the model stores date_of_birth/year_of_birth, so a
            # written age does not read back as one. Declared, not hidden.
            "age": Field("year_of_birth", verified=SCHEMA,
                         note="write-only as `age`; reads back as year_of_birth"),
            "sex": Field("gender", verified=SCHEMA,
                         values={"male": "male", "female": "female",
                                 "other": "non_binary"},
                         note="GenderChoices SCHEMA: male|female|non_binary|transgender"),
            "phone": Field("phone_number", param="phone_number", verified=SCHEMA),
            "village": Field("address", verified=SCHEMA),
            "category": Field("blood_group", verified=INFERRED,
                              note="no CARE field means the PHC's patient category; "
                                   "this is a placeholder and must not be trusted"),
            # instance_identifiers SCHEMA; the entry shape {config, value} is
            # SCHEMA (PatientIdentifierResponse); which config is the ABHA one
            # is deployment data, so store.py takes it as configuration.
            "abha_number": Field("abha_number", verified=INFERRED,
                                 note="synthesised by store.py from "
                                      "instance_identifiers; not a CARE field"),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is typed `object` on "
                                     "PatientRetrieveSpec; `.username` is a guess"),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write={"name": "name", "sex": "gender", "phone": "phone_number",
               "village": "address", "age": "age"},
        write_side=("abha_number",),
        write_defaults={},   # geo_organization is required (SCHEMA) and is
                             # configuration: store.py supplies it or refuses.
    ),

    # GET /api/v1/encounter/ SCHEMA. The thread IS an encounter.
    "encounter": Resource(
        path="/api/v1/encounter/",
        thread_param=None,          # filtered by id, handled in store.py
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "patient": Field("patient.id", verified=SOURCE,
                             note="the schema types it a bare `object`. "
                                  "encounter/spec.py serialises it with "
                                  "PatientListSpec on the list and "
                                  "PatientRetrieveSpec on the retrieve, and "
                                  "both carry `id`. The retrieve one is why "
                                  "store.py reads the ABHA off the encounter "
                                  "and does not fetch the patient twice"),
            "status": Field("status", param="status", verified=SCHEMA,
                            values={"in_progress": "in_progress",
                                    "completed": "completed"},
                            note="StatusChoices SCHEMA: planned|in_progress|"
                                 "on_hold|discharged|completed|cancelled|"
                                 "discontinued|entered_in_error|unknown"),
            # The PHC's queue token. CARE has a whole token queue app; the
            # nearest free text field on the encounter is external_identifier.
            "token": Field("external_identifier", param="external_identifier",
                           verified=SCHEMA,
                           note="CARE's real tokens are "
                                "/facility/{f}/token/queue/; this is the "
                                "cheap seat and is a deliberate simplification"),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="EncounterRetrieveSpec.created_by is typed "
                                     "bare `object`; `.username` is a guess, "
                                     "and it is absent from EncounterListSpec"),
            "created_date": Field("created_date", verified=SCHEMA,
                                  range_params={"gte": "created_date_after",
                                                "lt": "created_date_before"}),
        },
        write={"status": "status", "token": "external_identifier"},
        write_defaults={"encounter_class": "amb", "priority": "routine",
                        "status": "in_progress"},
    ),

    # GET /api/v1/patient/{p}/observation/ SCHEMA. Filters: codes, encounter,
    # ignore_group, limit, offset. There is NO category filter, and category
    # is a JSONField Coding, so {"category": "vital-signs"} is filtered by
    # this adapter after the fetch. That is the single largest cost in here.
    "observation": Resource(
        path="/api/v1/patient/{patient}/observation/",
        thread_param="encounter",
        verified=SCHEMA,
        note="read only over REST; see write_reason",
        fields={
            "id": Field("id", verified=SCHEMA),
            "encounter": Field("encounter", param="encounter", verified=SCHEMA),
            "category": Field("category.code", verified=SCHEMA,
                              values={"vital-signs": "vital_signs",
                                      "laboratory": "laboratory"},
                              note="ObservationCategoryChoices SCHEMA spells it "
                                   "vital_signs with an underscore; the PHC "
                                   "bundle and adapters/local say vital-signs. "
                                   "Translated here, in both directions"),
            "code": Field("main_code.code", param="codes", verified=SCHEMA,
                          note="care_phc/queries.py called this `code`; the "
                               "serializer field is main_code"),
            "value": Field("value.value", verified=SCHEMA),
            "unit": Field("value.unit.code", verified=SCHEMA,
                          note="QuestionnaireSubmitResultValue.unit is a Coding"),
            "status": Field("status", verified=SCHEMA,
                            note="ObservationStatus SCHEMA: final|amended|"
                                 "entered_in_error"),
            "created_by": Field("created_by.username", verified=SCHEMA,
                                note="created_by is UserSpec, which has username"),
            # ObservationReadSpec carries no created_date. effective_datetime
            # is the clinical time and is the only date on the row.
            "created_date": Field("effective_datetime", verified=SCHEMA,
                                  note="no created_date on ObservationReadSpec"),
        },
        write=None,
        write_reason=(
            "CARE exposes no POST that creates an observation. The schema has "
            "GET only under /patient/{p}/observation/. The two real paths are "
            "POST /api/v1/questionnaire/{slug}/submit/, which needs CARE's own "
            "question UUIDs, and POST /patient/{p}/diagnostic_report/{id}/"
            "upsert_observations/, which needs a diagnostic report to hang "
            "them on. Neither is a row write, so neither is guessed at here."),
    ),

    # GET /api/v1/patient/{p}/diagnosis/ SCHEMA. The resource is Condition.
    "condition": Resource(
        path="/api/v1/patient/{patient}/diagnosis/",
        thread_param="encounter",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "encounter": Field("encounter", param="encounter", verified=SCHEMA),
            "code": Field("code.code", verified=SCHEMA,
                          note="Coding; the display goes in code.display"),
            "verification_status": Field("verification_status",
                                         param="verification_status",
                                         verified=SCHEMA),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write={"code": "code.code", "verification_status": "verification_status"},
        write_defaults={"category": "encounter_diagnosis",
                        "verification_status": "confirmed"},
        note="write_defaults.category is INFERRED: the POST body declares "
             "`category` required, and drf-spectacular resolved its enum to "
             "the allergy CategoryChoices, which is a name collision and not "
             "the condition categories. Confirm before writing.",
    ),

    # GET /api/v1/patient/{p}/thread/{t}/note/ SCHEMA. Two levels: a NoteThread
    # per encounter, then messages on it. store.py opens or finds the thread.
    "notes": Resource(
        path="/api/v1/patient/{patient}/thread/{note_thread}/note/",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "text": Field("message", verified=SCHEMA,
                          note="care_phc/queries.py assumed encounter.notes "
                               "with a `text`; it is NoteMessage.message"),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write={"text": "message"},
    ),

    "medication_request": Resource(
        path="/api/v1/patient/{patient}/medication/request/",
        thread_param="encounter",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "encounter": Field("encounter", param="encounter", verified=SOURCE,
                               note="MedicationRequestReadSpec sets it to "
                                    "obj.encounter.external_id, so a plain id "
                                    "string and not an object"),
            "medication": Field("medication.display", verified=SCHEMA,
                                note="medication is a `system-medication` "
                                     "Coding; .display is INFERRED to be the "
                                     "human string"),
            "dosage_instruction": Field("dosage_instruction.0.text",
                                        verified=INFERRED,
                                        note="dosage_instruction is an array; "
                                             "its item schema is not named in "
                                             "the OpenAPI document"),
            "status": Field("status", param="status", verified=SCHEMA,
                            note="MedicationRequestStatus SCHEMA: active|"
                                 "on_hold|ended|stopped|completed|cancelled|"
                                 "entered_in_error|draft|unknown"),
            "created_by": Field("created_by.username", verified=SCHEMA),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write={"medication": "medication.display", "status": "status",
               "dosage_instruction": "dosage_instruction.0.text"},
        write_defaults={"status": "active", "intent": "order",
                        "category": "inpatient", "priority": "routine",
                        "do_not_perform": False},
        note="write_defaults are this adapter's choices for five required "
             "fields the kernel's mapping does not produce. intent, category "
             "and priority values are INFERRED.",
    ),

    # GET /api/v1/medication/dispense/ SCHEMA. Not patient scoped: filters by
    # encounter directly, which makes it the cheapest read in this file.
    "medication_dispense": Resource(
        path="/api/v1/medication/dispense/",
        thread_param="encounter",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "encounter": Field("encounter", param="encounter", verified=SOURCE,
                               note="CONFIRMED ABSENT: `encounter` filters "
                                    "(SCHEMA) but MedicationDispenseReadSpec "
                                    "has no such field; only "
                                    "MedicationDispenseRetrieveSpec does, and "
                                    "as a dict. A list row cannot say which "
                                    "encounter it is on, so nothing may read "
                                    "this back; filter by it instead"),
            "medication": Field("item.name", verified=INFERRED,
                                note="item is typed bare `object` on read and "
                                     "is a product id string on write"),
            "quantity": Field("quantity", verified=SCHEMA,
                              note="a string on the wire, SCHEMA"),
            "status": Field("status", param="status", verified=SCHEMA),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write=None,
        write_reason=(
            "POST /api/v1/medication/dispense/ requires `item` (a CARE product "
            "id) and `location` (a CARE location id), both SCHEMA. A PHC's "
            "dispense payload carries a medication NAME and a quantity, so "
            "both ids would have to be looked up in /facility/{f}/product/ by "
            "a match nothing here has verified. Refused rather than guessed: "
            "a dispense against the wrong product is a stock decrement on the "
            "wrong medicine."),
    ),

    "service_request": Resource(
        path="/api/v1/facility/{facility}/service_request/",
        thread_param="encounter",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "encounter": Field("encounter.id", param="encounter",
                               verified=SOURCE,
                               note="ServiceRequestReadSpec serialises it with "
                                    "EncounterListSpec, which carries `id`"),
            "code": Field("code.code", verified=SCHEMA),
            "status": Field("status", param="status", verified=SCHEMA,
                            note="ServiceRequestStatusChoices SCHEMA: draft|"
                                 "active|on_hold|entered_in_error|ended|"
                                 "completed|revoked"),
            "created_by": Field("requester.username", verified=INFERRED,
                                note="ServiceRequestReadSpec.requester is a "
                                     "bare object; who ordered is the nearest "
                                     "thing to an author on this row"),
            "created_date": Field("created_date", verified=SCHEMA,
                                  range_params={"gte": "created_date_after",
                                                "lt": "created_date_before"}),
        },
        write={"code": "code.code", "status": "status"},
        write_defaults={"status": "active", "intent": "order",
                        "priority": "routine", "category": "laboratory_procedure",
                        "title": "Investigation"},
        note="category is ActivityDefinitionCategoryOptions and the value here "
             "is INFERRED; title is required (SCHEMA) and the PHC's lab order "
             "payload has nothing to put in it.",
    ),

    "diagnostic_report": Resource(
        path="/api/v1/patient/{patient}/diagnostic_report/",
        thread_param="encounter",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "code": Field("code.code", verified=SCHEMA),
            "conclusion": Field("conclusion", verified=SCHEMA),
            "status": Field("status", param="status", verified=SCHEMA,
                            note="DiagnosticReportStatusChoices SCHEMA: "
                                 "registered|partial|preliminary|final"),
            "encounter": Field("encounter", param="encounter", verified=SOURCE,
                               note="CONFIRMED ABSENT from "
                                    "DiagnosticReportListSpec; only the "
                                    "retrieve spec carries it, as a dict. "
                                    "Filter by it, never read it back"),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write={"code": "code.code", "conclusion": "conclusion", "status": "status"},
        write_defaults={"status": "final", "category": "LAB"},
        note="service_request is required on POST (SCHEMA): a report must "
             "point at the order it answers. store.py refuses without one.",
    ),

    "specimen": Resource(
        path="/api/v1/facility/{facility}/specimen/{id}/",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "code": Field("specimen_type.code", verified=SCHEMA),
            "status": Field("status", verified=SCHEMA),
            "created_date": Field("received_time", verified=SCHEMA),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
        },
        write=None,
        write_reason=(
            "A specimen is created from the order it belongs to, POST "
            "/facility/{f}/service_request/{id}/create_specimen/ (SCHEMA), not "
            "as a free standing row."),
        note="There is also no list endpoint: the schema offers retrieve by id "
             "and retrieve_by_accession_identifier only, so count() and "
             "select() over specimens cannot be served and store.py says so.",
    ),

    "questionnaire_response": Resource(
        path="/api/v1/patient/{patient}/questionnaire_response/",
        thread_param="encounter",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "encounter": Field("encounter", param="encounter", verified=SCHEMA),
            "questionnaire": Field("questionnaire.slug", param="questionnaire_slug",
                                   verified=SCHEMA),
            "payload": Field("responses", verified=SCHEMA),
            "created_by": Field("created_by.username", verified=SCHEMA),
            "created_date": Field("created_date", verified=SCHEMA),
        },
        write=None,
        write_reason=(
            "A questionnaire response is made by POST /questionnaire/{slug}/"
            "submit/ (SCHEMA), whose results are keyed by CARE's own question "
            "UUIDs. This repo's questionnaires are its own and carry link_ids, "
            "not those UUIDs, so the submit body cannot be assembled without a "
            "question id map that does not exist yet."),
    ),

    "token_booking": Resource(
        path="/api/v1/facility/{facility}/appointments/",
        verified=INFERRED,
        fields={
            "id": Field("id", verified=SCHEMA),
            "patient": Field("patient.id", verified=INFERRED,
                             note="the appointment read spec was not examined"),
            "status": Field("status", param="status", verified=INFERRED,
                               note="the appointment read spec was not examined"),
            "created_date": Field("created_date", verified=INFERRED,
                                  note="not a declared property of this read spec"),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
        },
        write=None,
        write_reason=(
            "An appointment is created against a slot, POST /facility/{f}/"
            "slots/{id}/create_appointment/ (SCHEMA). No operation in either "
            "bundle writes one."),
        note="vocab.CARE_RESOURCES calls this token_booking after "
             "care/emr/models/scheduling/booking.py TokenBooking; the REST "
             "spelling is appointments, and its read spec was not examined.",
    ),

    "organization": Resource(
        # The only endpoint a live body could be read from, and the only LIVE
        # marks in this file are here.
        path="/api/v1/govt/organization/",
        verified=LIVE,
        fields={
            "id": Field("id", verified=LIVE),
            "name": Field("name", param="name", verified=LIVE),
            "code": Field("org_type", verified=LIVE),
            "status": Field("active", verified=LIVE),
            "parent": Field("parent.id", verified=LIVE),
        },
        write=None,
        write_reason="No operation in either bundle writes an organization.",
        note="/api/v1/organization/ (the non govt one) needs a token; the govt "
             "tree is readable unauthenticated, which is where LIVE came from.",
    ),

    "location": Resource(
        path="/api/v1/facility/{facility}/location/",
        verified=SCHEMA,
        fields={
            "id": Field("id", verified=SCHEMA),
            "name": Field("name", param="name", verified=SCHEMA),
            "status": Field("status", param="status", verified=SCHEMA),
            "created_date": Field("created_date", verified=INFERRED,
                                  note="not a declared property of this read spec"),
            "created_by": Field("created_by.username", verified=INFERRED,
                                note="created_by is not a declared property of "
                                     "this read spec; the UserSpec shape it "
                                     "would have does carry username (SCHEMA)"),
        },
        write=None,
        write_reason="No operation in either bundle writes a location.",
    ),
}

# Resources adapters/local has tables for that CARE has no home for at all.
# Named rather than silently missing, because a KeyError at three in the
# morning is worse than a sentence.
NO_CARE_RESOURCE = {
    "inventory_item": (
        "CARE's nearest concepts are /facility/{f}/product/ and "
        "product_knowledge (SCHEMA), which are a catalogue and a stock ledger, "
        "not the PHC bundle's per encounter inventory row. Mapping one onto "
        "the other is a modelling decision, not an adapter's."),
    "consent": (
        "GET/POST /api/v1/patient/{p}/consent/ exists (SCHEMA) but no "
        "operation in either bundle reads or writes it, so nothing here is "
        "written against an untested shape."),
}

# The kernel's own records. CARE keeps none of them: there is no proposal
# queue in CARE, no arbitrary per encounter flag, and CARE's audit is its own
# and not addressable as this trail. Six of the nine Store methods are
# therefore served from a sidecar store; see adapters/care/store.py.
KERNEL_RECORDS = ("thread_flag", "proposal", "audit")


def verification_report():
    """(verified, inferred) counts per resource. The test asserts on this, so
    a field that loses its mark cannot slip past unnoticed."""
    out = {}
    for name, resource in sorted(RESOURCES.items()):
        marks = [f.verified for f in resource.fields.values()]
        out[name] = {m: marks.count(m) for m in (LIVE, SCHEMA, SOURCE, INFERRED)}
    return out
