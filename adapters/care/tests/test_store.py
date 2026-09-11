"""Run: python3 -m adapters.care.tests.test_store

No network. A fake transport holds CARE shaped rows in memory and records
every request, so the adapter's logic is testable exactly as adapters/local is
testable with no server: the thread join, the push down of a where clause into
CARE's query parameters, the client side residue, the projection back into the
query grammar's names, the value translations, and every write body.

What this does NOT prove, and cannot: that CARE answers these paths with these
shapes. The fixture rows below are copied from the OpenAPI document
https://careapi.ohc.network/api/schema/ serves, so this file is a check of the
adapter against the declared contract, not against a running CARE. The one
place a real response was available unauthenticated is the pagination
envelope, and that fixture is the live bytes.
"""
import json

from adapters.care import map as care_map
from adapters.care.store import (CareError, CareStore, CareUnreachable,
                                 open_care)
from kernel.contracts import AuditRecord, Proposal

ENCOUNTER = "11111111-1111-1111-1111-111111111111"
PATIENT = "22222222-2222-2222-2222-222222222222"
FACILITY = "33333333-3333-3333-3333-333333333333"


def page(rows):
    """The envelope as the live instance returns it: count and results, and
    nothing else. The schema also declares next and previous; the one real
    response available carries neither, so nothing here may depend on them."""
    return {"count": len(rows), "results": rows}


class Fake:
    """A transport. `routes` maps (METHOD, path) to a body or a callable."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.seen = []          # [(method, path, params, body)]

    def __call__(self, method, path, params=None, body=None):
        self.seen.append((method, path, dict(params or {}), body))
        handler = self.routes.get((method, path))
        if handler is None:
            return 404, {"detail": "no fake route for %s %s" % (method, path)}
        out = handler(params, body) if callable(handler) else handler
        return (201 if method == "POST" else 200), out

    def params(self, method, path):
        for m, p, params, _ in self.seen:
            if (m, p) == (method, path):
                return params
        raise AssertionError("no %s %s in %s" % (method, path, self.seen))

    def body(self, method, path):
        for m, p, _, body in self.seen:
            if (m, p) == (method, path):
                return body
        raise AssertionError("no %s %s in %s" % (method, path, self.seen))


# Rows shaped as the running instance's OpenAPI document declares them.
ENCOUNTER_ROW = {
    "id": ENCOUNTER, "status": "in_progress", "priority": "routine",
    "encounter_class": "amb", "external_identifier": "A04",
    "created_date": "2026-09-11T04:00:00+00:00",
    "patient": {"id": PATIENT, "name": "Kamala Devi", "gender": "female",
                "phone_number": "9800000001", "address": "Sonpur",
                "year_of_birth": 1985},
    "facility": {"id": FACILITY, "name": "Sonpur PHC"},
}
# ObservationReadSpec: main_code, a Coding category, a value object, and no
# created_date at all. care_phc/queries.py expected code, category="vital-signs".
OBSERVATIONS = [
    {"id": "o1", "encounter": ENCOUNTER, "status": "final",
     "category": {"code": "vital_signs", "display": "Vital signs"},
     "main_code": {"code": "systolic", "display": "Systolic BP"},
     "value": {"value": "118", "unit": {"code": "mm[Hg]"}},
     "effective_datetime": "2026-09-11T04:10:00+00:00",
     "created_by": {"username": "nurse"}},
    {"id": "o2", "encounter": ENCOUNTER, "status": "final",
     "category": {"code": "vital_signs"},
     "main_code": {"code": "pulse"},
     "value": {"value": "80", "unit": {"code": "/min"}},
     "effective_datetime": "2026-09-11T04:10:00+00:00",
     "created_by": {"username": "nurse"}},
    {"id": "o3", "encounter": ENCOUNTER, "status": "final",
     "category": {"code": "laboratory"},
     "main_code": {"code": "Haemoglobin"},
     "value": {"value": "9.4", "unit": {"code": "g/dL"}},
     "effective_datetime": "2026-09-11T06:00:00+00:00",
     "created_by": {"username": "lab"}},
]


def store(routes=None, **kwargs):
    base = {("GET", "/api/v1/encounter/%s/" % ENCOUNTER): ENCOUNTER_ROW}
    base.update(routes or {})
    fake = Fake(base)
    return CareStore(transport=fake, facility=FACILITY, **kwargs), fake


# --------------------------------------------------------------------------

def test_the_thread_join_is_one_request_and_is_cached():
    """Every patient scoped path needs the encounter's patient id. That is the
    whole of this adapter's private knowledge and no declaration states it."""
    s, fake = store({("GET", "/api/v1/patient/%s/observation/" % PATIENT):
                     lambda p, b: page(OBSERVATIONS)})
    s.count("observation", thread=ENCOUNTER, where={})
    s.count("observation", thread=ENCOUNTER, where={})
    joins = [r for r in fake.seen if r[1].endswith("/encounter/%s/" % ENCOUNTER)]
    assert len(joins) == 1, "the encounter was fetched %d times" % len(joins)
    assert s.context(ENCOUNTER)["patient"] == PATIENT
    assert s.context(ENCOUNTER)["facility"] == FACILITY


def test_a_pushable_where_becomes_query_parameters_and_one_request():
    """When CARE can answer the whole query, count() reads the envelope's
    `count` and never pages. `codes` is the filter, not `code`."""
    s, fake = store({("GET", "/api/v1/patient/%s/observation/" % PATIENT):
                     lambda p, b: page([r for r in OBSERVATIONS
                                        if r["main_code"]["code"] == p.get("codes")])})
    assert s.count("observation", thread=ENCOUNTER, where={"code": "pulse"}) == 1
    params = fake.params("GET", "/api/v1/patient/%s/observation/" % PATIENT)
    assert params["codes"] == "pulse", params
    assert params["encounter"] == ENCOUNTER, "the thread scopes the read"
    assert params["limit"] == 1, "a pushed down count asks for one row"


def test_category_has_no_care_filter_so_it_is_applied_here_and_translated():
    """The single most expensive fact in map.py, and the one care_phc/
    queries.py got wrong twice: Observation.category is a Coding, not a
    string, the code is vital_signs with an underscore, and the list endpoint
    offers no category filter at all."""
    s, fake = store({("GET", "/api/v1/patient/%s/observation/" % PATIENT):
                     lambda p, b: page(OBSERVATIONS)})
    assert s.count("observation", thread=ENCOUNTER,
                   where={"category": "vital-signs"}) == 2
    params = fake.params("GET", "/api/v1/patient/%s/observation/" % PATIENT)
    assert "category" not in params, "CARE has no category filter; do not send one"
    assert params["limit"] == 100, "a query CARE cannot answer has to page"


def test_rows_come_back_in_the_query_grammar_s_names_not_care_s():
    s, _ = store({("GET", "/api/v1/patient/%s/observation/" % PATIENT):
                  lambda p, b: page(OBSERVATIONS)})
    rows = s.select("observation", thread=ENCOUNTER,
                    where={"category": "vital-signs"},
                    fields=["code", "value", "unit", "category"], limit=10)
    by_code = {r["code"]: r for r in rows}
    assert set(by_code) == {"systolic", "pulse"}
    assert by_code["systolic"] == {"code": "systolic", "value": "118",
                                   "unit": "mm[Hg]", "category": "vital-signs"}, \
        "the declarations say vital-signs and CARE says vital_signs; the "\
        "translation runs in both directions or the state rules never fire"


def test_an_unmapped_field_is_refused_and_never_reaches_care():
    s, _ = store()
    for call in (lambda: s.count("observation", thread=ENCOUNTER,
                                 where={"drop table": 1}),
                 lambda: s.select("observation", thread=ENCOUNTER, where={},
                                  fields=["nonesuch"], limit=1)):
        try:
            call()
        except ValueError as exc:
            assert "map.py" in str(exc), exc
        else:
            raise AssertionError("an unmapped field reached CARE")


def test_the_patient_join_goes_through_the_encounter_and_costs_no_extra_request():
    """instance_identifiers, where an ABHA lives, are on PatientRetrieveSpec
    and NOT on PatientListSpec, so a list can never answer abha_number. The
    encounter retrieve embeds PatientRetrieveSpec (SOURCE), so the join
    already has them and a second GET would be waste."""
    row = dict(ENCOUNTER_ROW["patient"],
               instance_identifiers=[{"config": {"id": "cfg-abha"},
                                      "value": "12-0000-0000-0000"}])
    s, fake = store({("GET", "/api/v1/encounter/%s/" % ENCOUNTER):
                     dict(ENCOUNTER_ROW, patient=row)},
                    abha_config="cfg-abha")
    assert s.count("patient", thread=ENCOUNTER, where={}) == 1
    assert s.count("patient", thread=ENCOUNTER, where={"abha_number": "*"}) == 1
    got = s.select("patient", thread=ENCOUNTER, where={},
                   fields=["name", "sex", "phone", "village", "abha_number"],
                   limit=1)[0]
    assert got == {"name": "Kamala Devi", "sex": "female",
                   "phone": "9800000001", "village": "Sonpur",
                   "abha_number": "12-0000-0000-0000"}, got

    assert [r for r in fake.seen if r[1] == "/api/v1/patient/%s/" % PATIENT] == [], \
        "the encounter retrieve already carried the whole person"

    # With no abha_config the key is absent, not invented.
    s2, _ = store({("GET", "/api/v1/encounter/%s/" % ENCOUNTER):
                   dict(ENCOUNTER_ROW, patient=row)})
    assert s2.count("patient", thread=ENCOUNTER, where={"abha_number": "*"}) == 0


def test_a_thread_with_no_patient_counts_zero_rather_than_erroring():
    s, _ = store({("GET", "/api/v1/encounter/%s/" % ENCOUNTER):
                  dict(ENCOUNTER_ROW, patient={})})
    assert s.count("patient", thread=ENCOUNTER, where={}) == 0
    assert s.select("patient", thread=ENCOUNTER, where={}, fields=["name"],
                    limit=1) == []


def test_paging_uses_limit_and_offset_and_never_follows_next():
    """The live envelope carries count and results only, even on an endpoint
    whose schema declares next and previous."""
    many = [dict(OBSERVATIONS[0], id="o%d" % i) for i in range(250)]

    def handler(params, body):
        start = int(params.get("offset") or 0)
        rows = many[start:start + int(params.get("limit") or 100)]
        return {"count": len(many), "results": rows}

    s, fake = store({("GET", "/api/v1/patient/%s/observation/" % PATIENT): handler})
    assert s.count("observation", thread=ENCOUNTER,
                   where={"category": "vital-signs"}) == 250
    offsets = [r[2].get("offset") for r in fake.seen if "observation" in r[1]]
    assert offsets == [0, 100, 200], offsets
    # select stops as soon as it has enough, rather than draining the list.
    fake.seen = []
    assert len(s.select("observation", thread=ENCOUNTER,
                        where={"category": "vital-signs"},
                        fields=["code"], limit=5)) == 5
    assert len([r for r in fake.seen if "observation" in r[1]]) == 1


def test_threads_is_one_request_because_the_encounter_embeds_its_patient():
    s, fake = store({("GET", "/api/v1/encounter/"): page([ENCOUNTER_ROW])})
    threads = s.threads(workflow="phc.wf.outpatient", scope="today")
    assert len(threads) == 1
    t = threads[0]
    assert t.id == ENCOUNTER and t.workflow == "phc.wf.outpatient"
    assert t.subject["name"] == "Kamala Devi"
    assert t.subject["token"] == "A04", "the PHC token rides on external_identifier"
    assert t.subject["encounter"] == ENCOUNTER
    params = fake.params("GET", "/api/v1/encounter/")
    assert params["facility"] == FACILITY
    assert "created_date_after" in params, "scope today is a date filter"
    assert len([r for r in fake.seen if r[1] == "/api/v1/encounter/"]) == 1, \
        "a queue must not be one request per row"


def test_an_error_from_care_carries_care_s_own_words():
    """{"detail": "Authentication credentials were not provided."} with a 403
    is a real response from the public instance, and it is what a missing or
    wrong token looks like."""
    fake = Fake()
    fake.routes[("GET", "/api/v1/encounter/%s/" % ENCOUNTER)] = None
    s = CareStore(transport=lambda *a, **k: (403, {"detail":
                  "Authentication credentials were not provided."}),
                  facility=FACILITY)
    try:
        s.context(ENCOUNTER)
    except CareError as exc:
        assert exc.status == 403 and "Authentication" in json.dumps(exc.body)
    else:
        raise AssertionError("a 403 was swallowed")


# ------------------------------------------------------------------ writes

def test_a_write_body_is_care_s_shape_with_the_required_fields_filled():
    s, fake = store({("POST", "/api/v1/patient/%s/diagnosis/" % PATIENT):
                     {"id": "c1"}})
    assert s.write("condition", {"code": "A99", "created_by": "user:mo"},
                   thread=ENCOUNTER) == "c1"
    body = fake.body("POST", "/api/v1/patient/%s/diagnosis/" % PATIENT)
    assert body["code"] == {"code": "A99"}, "ConditionSpec.code is a Coding"
    assert body["encounter"] == ENCOUNTER
    assert body["verification_status"] == "confirmed", "required, from write_defaults"
    assert "created_by" not in body, "CARE stamps the authenticated user"


def test_a_mapped_column_with_no_care_field_is_refused_and_not_dropped():
    """adapters/local raises on a column its table lacks; the same value must
    not vanish quietly here either."""
    s, _ = store()
    try:
        s.write("condition", {"code": "A99", "override_reason": "other arm"},
                thread=ENCOUNTER)
    except ValueError as exc:
        assert "override_reason" in str(exc), exc
    else:
        raise AssertionError("a mapped clinical value was swallowed")


def test_an_array_field_is_written_as_an_array():
    """dosage_instruction is [{...}] on the wire. A dict keyed "0" would be
    silently wrong and CARE would reject it with a message nobody reads."""
    s, fake = store({("POST", "/api/v1/patient/%s/medication/request/" % PATIENT):
                     {"id": "m1"}})
    s.write("medication_request",
            {"medication": "Paracetamol 500mg", "dosage_instruction": "1 tab TDS"},
            thread=ENCOUNTER)
    body = fake.body("POST", "/api/v1/patient/%s/medication/request/" % PATIENT)
    assert body["dosage_instruction"] == [{"text": "1 tab TDS"}], body
    assert body["medication"] == {"code": "Paracetamol 500mg",
                                  "display": "Paracetamol 500mg"}
    assert body["status"] == "active" and body["intent"] == "order"
    assert body["encounter"] == ENCOUNTER and body["authored_on"]


def test_a_note_opens_or_finds_the_note_thread_care_requires():
    """care_phc/queries.py counted `encounter.notes`. There is no such thing:
    a NoteMessage hangs off a NoteThread, which hangs off the patient."""
    posted = []
    s, fake = store({
        ("GET", "/api/v1/patient/%s/thread/" % PATIENT): lambda p, b: page([]),
        ("POST", "/api/v1/patient/%s/thread/" % PATIENT):
            lambda p, b: posted.append(b) or {"id": "nt1"},
        ("POST", "/api/v1/patient/%s/thread/nt1/note/" % PATIENT): {"id": "n1"},
    })
    assert s.write("notes", {"text": "Viral fever"}, thread=ENCOUNTER) == "n1"
    assert posted[0]["encounter"] == ENCOUNTER
    assert fake.body("POST", "/api/v1/patient/%s/thread/nt1/note/" % PATIENT) \
        == {"message": "Viral fever"}, "NoteMessage.message, not text"

    # An existing thread is reused, not duplicated.
    s2, fake2 = store({
        ("GET", "/api/v1/patient/%s/thread/" % PATIENT):
            lambda p, b: page([{"id": "nt0"}]),
        ("POST", "/api/v1/patient/%s/thread/nt0/note/" % PATIENT): {"id": "n2"},
    })
    assert s2.write("notes", {"text": "again"}, thread=ENCOUNTER) == "n2"


def test_registering_a_patient_needs_geo_organization_and_attaches_the_encounter():
    s, fake = store({("GET", "/api/v1/encounter/%s/" % ENCOUNTER):
                     dict(ENCOUNTER_ROW, patient={})})
    try:
        s.write("patient", {"name": "Devi Prasad", "sex": "male"}, thread=ENCOUNTER)
    except ValueError as exc:
        assert "geo_organization" in str(exc), exc
    else:
        raise AssertionError("a patient was posted without a required field")

    s, fake = store({("GET", "/api/v1/encounter/%s/" % ENCOUNTER):
                     dict(ENCOUNTER_ROW, patient={}),
                     ("POST", "/api/v1/patient/"): {"id": "new-p"},
                     ("PUT", "/api/v1/encounter/%s/" % ENCOUNTER): {}},
                    geo_organization="geo-1")
    assert s.write("patient", {"name": "Devi Prasad", "sex": "male",
                               "phone": "9800000099", "village": "Sonpur",
                               "age": 41}, thread=ENCOUNTER) == "new-p"
    body = fake.body("POST", "/api/v1/patient/")
    assert body == {"name": "Devi Prasad", "gender": "male",
                    "phone_number": "9800000099", "address": "Sonpur",
                    "age": 41, "geo_organization": "geo-1"}, body
    assert fake.body("PUT", "/api/v1/encounter/%s/" % ENCOUNTER)["patient"] == "new-p"


def test_linking_an_abha_updates_the_person_the_thread_already_has():
    s, fake = store({("PUT", "/api/v1/patient/%s/" % PATIENT): {},
                     ("POST", "/api/v1/patient/%s/update_identifier/" % PATIENT): {}},
                    abha_config="cfg-abha")
    assert s.write("patient", {"abha_number": "12-0000-0000-0000"},
                   thread=ENCOUNTER) == PATIENT, "an update, not a second person"
    assert fake.body("POST", "/api/v1/patient/%s/update_identifier/" % PATIENT) \
        == {"config": "cfg-abha", "value": "12-0000-0000-0000"}

    # Without the config id there is nothing honest to post.
    s2, _ = store({("PUT", "/api/v1/patient/%s/" % PATIENT): {}})
    try:
        s2.write("patient", {"abha_number": "12-0000-0000-0000"}, thread=ENCOUNTER)
    except ValueError as exc:
        assert "abha_config" in str(exc), exc
    else:
        raise AssertionError("an ABHA was written against a guessed config")


def test_updating_an_encounter_does_not_reset_what_it_already_says():
    s, fake = store({("PUT", "/api/v1/encounter/%s/" % ENCOUNTER): {}})
    s.write("encounter", {"status": "completed"}, thread=ENCOUNTER)
    body = fake.body("PUT", "/api/v1/encounter/%s/" % ENCOUNTER)
    assert body["status"] == "completed"
    assert body["external_identifier"] == "A04", "the token survived the update"
    assert body["patient"] == PATIENT and body["facility"] == FACILITY


def test_a_report_must_point_at_the_order_it_answers():
    orders = [{"id": "sr1", "status": "active", "code": {"code": "CBC"},
               "encounter": {"id": ENCOUNTER},
               "created_date": "2026-09-11T05:00:00+00:00"}]
    s, fake = store({
        ("GET", "/api/v1/facility/%s/service_request/" % FACILITY):
            lambda p, b: page(orders),
        ("POST", "/api/v1/patient/%s/diagnostic_report/" % PATIENT): {"id": "dr1"},
    })
    assert s.write("diagnostic_report", {"conclusion": "Anaemia", "status": "final"},
                   thread=ENCOUNTER) == "dr1"
    body = fake.body("POST", "/api/v1/patient/%s/diagnostic_report/" % PATIENT)
    assert body["service_request"] == "sr1", "required on POST"
    assert body["conclusion"] == "Anaemia" and body["category"] == "LAB"

    s2, _ = store({("GET", "/api/v1/facility/%s/service_request/" % FACILITY):
                   lambda p, b: page([])})
    try:
        s2.write("diagnostic_report", {"conclusion": "x"}, thread=ENCOUNTER)
    except ValueError as exc:
        assert "service_request" in str(exc), exc
    else:
        raise AssertionError("a report was orphaned")


def test_what_care_cannot_create_raises_with_the_reason_not_a_guessed_post():
    """The whole point of the exercise. care_phc/queries.py failed because a
    guess was indistinguishable from a fact; here an unsupported write names
    the endpoint that would be needed instead."""
    s, fake = store()
    for resource, word in (("observation", "questionnaire"),
                           ("questionnaire_response", "submit"),
                           ("specimen", "create_specimen"),
                           ("medication_dispense", "product")):
            # An empty row: the refusal must come from the resource having no
            # create endpoint, not from a column that failed to map.
        try:
            s.write(resource, {}, thread=ENCOUNTER)
        except NotImplementedError as exc:
            assert word in str(exc), (resource, exc)
        else:
            raise AssertionError("%s was written against a guessed endpoint"
                                 % resource)
    assert not [r for r in fake.seen if r[0] == "POST"], \
        "a refused write must not have touched CARE"


def test_a_resource_care_has_no_home_for_says_so():
    s, _ = store()
    for resource in care_map.NO_CARE_RESOURCE:
        for call in (lambda: s.write(resource, {}, thread=ENCOUNTER),
                     lambda: s.count(resource, thread=ENCOUNTER, where={})):
            try:
                call()
            except ValueError as exc:
                assert resource in str(exc)
            else:
                raise AssertionError("%s pretended to work" % resource)


# ----------------------------------------------- the kernel's own records

def test_the_kernel_s_own_records_go_to_the_sidecar_and_never_to_care():
    """CARE has no proposal queue, no arbitrary per encounter flag, and its
    audit is its own. Six of the nine methods are therefore the sidecar's,
    which is a statement about CARE and not a shortcut."""
    from adapters.local.store import SqliteStore

    sidecar = SqliteStore(":memory:")
    s, fake = store(sidecar=sidecar)
    s.raise_flag(ENCOUNTER, "vitals.flagged")
    s.raise_flag(ENCOUNTER, "vitals.flagged")
    assert s.stored_flags(ENCOUNTER) == frozenset({"vitals.flagged"})

    s.put_proposal(Proposal(id="p1", thread=ENCOUNTER, operation="phc.op.vitals-record",
                            payload={"systolic": 120}, proposed_by="agent",
                            surface="mcp", status="pending",
                            created_at="2026-09-11T10:00:00+00:00"))
    assert s.proposals(ENCOUNTER, status="pending")[0].payload == {"systolic": 120}
    s.append_audit(AuditRecord(id="a1", thread=ENCOUNTER, operation="op",
                               actor="me", surface="rendered", payload={"a": 1},
                               outcome="allowed", at="2026-09-11T10:00:00+00:00"))
    assert s.audit(ENCOUNTER)[0].payload == {"a": 1}
    assert fake.seen == [], "not one of those six may reach CARE"

    for resource in care_map.KERNEL_RECORDS:
        try:
            s.count(resource, thread=ENCOUNTER, where={})
        except ValueError as exc:
            assert "sidecar" in str(exc), exc
        else:
            raise AssertionError("%s was queried as if CARE had it" % resource)


def test_every_store_method_the_contract_names_is_here():
    """A missing one is an AttributeError somewhere in the kernel, which is a
    bad place to find out.

    kernel/contracts.py calls the protocol "nine methods", in its docstring and
    twice more in the Store docstring. It declares ten: count, select, threads,
    stored_flags, write, raise_flag, put_proposal, proposals, append_audit,
    audit. The count is asserted from the class, not from the prose, and the
    discrepancy is reported rather than patched: kernel/ is not this adapter's
    to edit."""
    from kernel.contracts import Store

    declared = sorted(n for n in vars(Store) if not n.startswith("_"))
    assert declared == ["append_audit", "audit", "count", "proposals",
                        "put_proposal", "raise_flag", "select", "stored_flags",
                        "threads", "write"], declared
    for name in declared:
        assert callable(getattr(CareStore, name, None)), "CareStore has no " + name


def test_every_mapped_field_carries_its_verification_mark():
    """The distinction between confirmed and inferred is the deliverable, so
    losing a mark has to break a check rather than be noticed by nobody."""
    marks = (care_map.LIVE, care_map.SCHEMA, care_map.SOURCE,
             care_map.INFERRED)
    for name, resource in care_map.RESOURCES.items():
        assert resource.verified in marks, name
        for field_name, field in resource.fields.items():
            assert field.verified in marks, (name, field_name)
            if field.verified == care_map.INFERRED:
                assert field.note, \
                    "%s.%s is inferred and says nothing about why" % (name, field_name)
        if resource.write is None:
            assert resource.write_reason, "%s refuses writes silently" % name
            for column in resource.fields:
                pass
        else:
            for column in resource.write:
                assert column in resource.fields, (name, column)
    report = care_map.verification_report()
    assert report["observation"][care_map.INFERRED] == 0, \
        "observation is the resource care_phc/queries.py got wrong; every one "\
        "of its fields is confirmed against the published schema"
    assert report["organization"][care_map.LIVE] == 5, \
        "the only fields read off a real response body"


def test_local_and_care_agree_on_the_names_a_declaration_may_use():
    """Both adapters answer the same query grammar. A column adapters/local has
    and this one has no field for is exactly where a bundle stops working when
    it is pointed at CARE, so the list is asserted and not left to be found."""
    from adapters.local.store import TABLES

    gaps = {}
    for resource, columns in TABLES.items():
        if resource in care_map.KERNEL_RECORDS:
            continue
        if resource in care_map.NO_CARE_RESOURCE:
            gaps[resource] = ["no CARE resource at all"]
            continue
        missing = sorted(set(columns) - set(care_map.RESOURCES[resource].fields))
        if missing:
            gaps[resource] = missing
    assert gaps == {
        # No CARE resource at all; map.NO_CARE_RESOURCE says why.
        "inventory_item": ["no CARE resource at all"],
        # A NoteMessage knows its NoteThread, and the thread knows the
        # encounter. So "which encounter is this note on" is one hop away and
        # a note row cannot answer it; store.py resolves the thread on the way
        # in instead, which is why notes has no thread_param.
        "notes": ["encounter"],
        # No list endpoint and no encounter on the read spec: a specimen is
        # reached from the service request that created it.
        "specimen": ["encounter"],
        # An appointment belongs to a patient and a slot, not an encounter.
        "token_booking": ["encounter"],
    }, gaps


def test_a_care_that_cannot_be_reached_is_a_sentence_and_not_a_traceback():
    """PHC_STORE=care with nothing listening is the ordinary mistake here, so
    every way of getting it wrong has to end in words a person can act on.
    The 401 body is the live one careapi.ohc.network returns to a bad token."""

    def sent(env):
        try:
            open_care(env=env, db=":memory:")
        except CareUnreachable as exc:
            return str(exc)
        raise AssertionError("open_care did not refuse %r" % env)

    assert "CARE_BASE_URL and CARE_TOKEN" in sent({})
    assert "CARE_TOKEN" in sent({"CARE_BASE_URL": "https://care.example"})

    def probes(org, facility):
        calls = []

        def transport(method, path, params=None, body=None):
            calls.append(path)
            return org if path.startswith("/api/v1/govt") else facility

        return CareStore(transport=transport).unreachable(), calls

    reason, calls = probes((200, {"count": 0, "results": []}), (200, {"count": 1}))
    assert reason is None and len(calls) == 2, (reason, calls)

    reason, _ = probes((200, {"count": 0}),
                       (401, {"detail": "Invalid Token, please relogin to continue"}))
    assert "refused CARE_TOKEN" in reason and "Invalid Token" in reason

    reason, calls = probes((404, {"detail": "not found"}), (200, {}))
    assert "probably not a CARE" in reason and len(calls) == 1, calls

    reason, _ = probes((502, {"detail": "bad gateway"}), (200, {}))
    assert "failing, not refusing" in reason

    def refuses(method, path, params=None, body=None):
        raise OSError("Connection refused")

    reason = CareStore(transport=refuses).unreachable()
    assert reason.startswith("Nothing answered") and "Connection refused" in reason


def demo():
    run = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            run += 1
            print("ok   %s" % name.replace("test_", "").replace("_", " "))
    print("ok   adapters/care: %d checks, no network" % run)


if __name__ == "__main__":
    demo()
