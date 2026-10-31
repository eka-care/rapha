"""Run: python3 -m kernel.tests.test_mapping

Two questions, and they are the two that matter about a mapping.

1. Does a mismatch fail the build? A record naming a link_id the questionnaire
   does not have, or a resource the operation does not write, or a required
   answer that goes nowhere, must stop the compile and not reach a store.
2. Do the same payloads still produce the same rows? adapters/local/shape.py
   derived these rows in code until this change. GOLDEN below is what it
   produced, captured from it before it was deleted, and the declared mapping
   has to reproduce it exactly.

Pure: no store, no HTTP.
"""
from __future__ import annotations

from kernel import declarations, mapping

BUNDLE = declarations.load("phc")
OPERATIONS = BUNDLE.operations

# The payloads adapters/local/tests/test_store.py uses, kept in step with it by
# hand: one representative payload per operation, answering what is required.
PAYLOADS = {
    "phc.op.patient-register": {"name": "Devi Prasad", "age": 41, "sex": "male",
                                "phone": "9800000099", "village": "Sonpur"},
    "phc.op.abha-link": {"method": "link_existing", "consent_given": True,
                         "abha_number": "12-0000-0000-0000"},
    "phc.op.vitals-record": {"systolic": 118, "diastolic": 76, "pulse": 80},
    # Two diagnosis rows, and the second one is the point of the type change.
    # "A99" used to be an acceptable diagnosis here, because `structured` had
    # no sub schema and nothing validated it anywhere. Each row is now four
    # bound answers, and the second row is `refuted`: a finding the patient
    # denied, recorded without being asserted, which is invariant I6 and was
    # unexpressible when the mapping wrote `{const: confirmed}` on every row.
    "phc.op.consult-document": {
        "assessment": "Viral fever",
        "diagnosis": [
            {"condition": "44054006", "clinical_status": "active",
             "verification_status": "confirmed", "onset": "2024-03-01"},
            {"condition": "297142003", "clinical_status": "active",
             "verification_status": "refuted"},
        ]},
    "phc.op.rx-prescribe": {
        "medications": [{"drug": "777067000", "dose": 500, "dose_unit": "mg",
                         "route": "26643006", "frequency": "229798009",
                         "duration": 5, "duration_unit": "d"}]},
    "phc.op.lab-order": {"investigations": [{"code": "CBC"}]},
    # The analyte is a LOINC code now and not the word a technician typed, and
    # the unit must be the one LOINC reports that analyte in. See
    # scripts/check_lab.py for the rule and the reason.
    "phc.op.lab-result-enter": {"analyte": "718-7", "value": 9.4, "unit": "g/dL",
                                "note": "repeat on a fresh sample"},
    "phc.op.pharmacy-dispense": {"dispenses": [{"medication": "Paracetamol 500mg",
                                                "quantity": 9}]},
    "phc.op.household-visit": {"visit_type": "routine", "consent_at_door": True,
                               "narrative": "Two children, both immunised."},
}

# What adapters/local/shape.py wrote for those payloads, read back out of
# SQLite, which is why every value is a string: the store keeps TEXT columns.
# Two rows differ from that capture on purpose, and only these two:
#
#   patient      shape.py put the existing patient's id in the row so the
#                write would update rather than insert. That is the thread
#                join, so it moved to adapters/local/store.py write().
#   household    the questionnaire column was always null, because shape.py
#                read a "questionnaire" key no payload can carry: the
#                validator refuses any key the form does not declare. The
#                mapping names the questionnaire, so the column is filled.
GOLDEN = {
    "phc.op.abha-link": [
        ("patient", {"abha_number": "12-0000-0000-0000"}),
    ],
    # One condition row per diagnosis row, each carrying three codings and
    # the system each came from. The second row has no onset, which is a
    # column absent rather than a column holding an empty string.
    "phc.op.consult-document": [
        ("encounter", {"status": "in_progress"}),
        ("notes", {"text": "Assessment: Viral fever"}),
        ("condition", {"code": "44054006", "code_system": "http://snomed.info/sct",
                       "code_display": "Type 2 diabetes mellitus",
                       "clinical_status": "active",
                       "clinical_status_system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                       "verification_status": "confirmed",
                       "verification_status_system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                       "onset": "2024-03-01"}),
        ("condition", {"code": "297142003", "code_system": "http://snomed.info/sct",
                       "code_display": "Foot swelling",
                       "clinical_status": "active",
                       "clinical_status_system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                       "verification_status": "refuted",
                       "verification_status_system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"}),
    ],
    "phc.op.household-visit": [
        ("encounter", {"status": "in_progress"}),
        ("questionnaire_response",
         {"questionnaire": "phc.schema.household-visit-v1",
          "payload": '{"consent_at_door": true, "narrative": "Two children, '
                     'both immunised.", "visit_type": "routine"}'}),
    ],
    "phc.op.lab-order": [
        ("service_request", {"code": "CBC", "status": "active"}),
    ],
    # Three rows where there were two, and the new one is the point: the
    # result is a quantity. It used to be prose in the report's conclusion,
    # "9.4 g/dL", which is why nothing could trend or count it. The report
    # keeps a narrative the technician wrote, and the specimen no longer
    # claims the test name is its type.
    "phc.op.lab-result-enter": [
        ("observation", {"category": "laboratory", "code": "718-7",
                         "code_system": "http://loinc.org",
                         "code_display": "Hemoglobin [Mass/volume] in Blood",
                         "value": "9.4", "unit": "g/dL",
                         "unit_system": "http://unitsofmeasure.org"}),
        ("diagnostic_report", {"code": "718-7",
                               "code_system": "http://loinc.org",
                               "conclusion": "repeat on a fresh sample",
                               "status": "preliminary"}),
        ("specimen", {"status": "available"}),
    ],
    "phc.op.patient-register": [
        ("patient", {"name": "Devi Prasad", "age": "41", "sex": "male",
                     "phone": "9800000099", "village": "Sonpur"}),
    ],
    "phc.op.pharmacy-dispense": [
        ("medication_dispense", {"medication": "Paracetamol 500mg",
                                 "quantity": "9", "status": "completed"}),
        ("inventory_item", {"code": "Paracetamol 500mg", "quantity": "-9",
                            "status": "issued"}),
    ],
    # A prescription line, as five checked answers rather than one sentence.
    "phc.op.rx-prescribe": [
        ("medication_request", {"medication": "777067000",
                                "medication_system": "http://snomed.info/sct",
                                "medication_display": "Acetaminophen only product",
                                "dose": "500", "dose_unit": "mg",
                                "dose_unit_system": "http://unitsofmeasure.org",
                                "route": "26643006", "route_system": "http://snomed.info/sct",
                                "route_display": "Oral route",
                                "frequency": "229798009",
                                "frequency_system": "http://snomed.info/sct",
                                "frequency_display": "Three times daily",
                                "duration": "5", "duration_unit": "d",
                                "duration_unit_system": "http://unitsofmeasure.org",
                                "status": "active",
                                "intent": "order"}),
    ],
    # The code is the question's bound LOINC concept and not its link_id, and
    # each coding spans the three columns a FHIR Coding has. Nothing here can
    # be written by hand into the record: a Coding exists only if the value
    # set its question binds to vouched for it, so these three expected rows
    # are also an assertion that the binding resolved.
    "phc.op.vitals-record": [
        ("observation", {"category": "vital-signs", "code": "8480-6",
                         "code_system": "http://loinc.org",
                         "code_display": "Systolic blood pressure",
                         "value": "118", "unit": "mm[Hg]",
                         "unit_system": "http://unitsofmeasure.org"}),
        ("observation", {"category": "vital-signs", "code": "8462-4",
                         "code_system": "http://loinc.org",
                         "code_display": "Diastolic blood pressure",
                         "value": "76", "unit": "mm[Hg]",
                         "unit_system": "http://unitsofmeasure.org"}),
        ("observation", {"category": "vital-signs", "code": "8867-4",
                         "code_system": "http://loinc.org",
                         "code_display": "Heart rate",
                         "value": "80", "unit": "/min",
                         "unit_system": "http://unitsofmeasure.org"}),
    ],
}


def as_stored(row):
    """Every column in adapter 0 is TEXT, so compare the way it is stored.
    The mapping keeps an answer's own type and the adapter converts it, which
    is the only difference between the two sides of this comparison."""
    return {k: ("true" if v is True else "false" if v is False else str(v))
            for k, v in row.items()}


# --------------------------------------------------------------------------
# the same payload produces the same rows
# --------------------------------------------------------------------------

def test_the_declared_mapping_reproduces_the_rows_the_adapter_derived():
    for op_id, payload in sorted(PAYLOADS.items()):
        got = [(resource, as_stored(row))
               for resource, row in mapping.records(OPERATIONS[op_id], payload)]
        want = [(resource, dict(row)) for resource, row in GOLDEN[op_id]]
        assert got == want, "%s\n  now:    %s\n  before: %s" % (op_id, got, want)


def test_an_unanswered_question_is_no_row_and_not_an_empty_one():
    rows = mapping.records(OPERATIONS["phc.op.consult-document"],
                           {"assessment": "Viral fever"})
    # no diagnosis in the payload, so no condition row; the encounter row is
    # all constants and is written anyway, because it is the thread.
    assert [r for r, _ in rows] == ["encounter", "notes"], rows


def test_the_unit_comes_from_the_questionnaire_and_is_written_nowhere_else():
    (record,) = OPERATIONS["phc.op.vitals-record"]["mapping"]
    assert record["fields"]["unit"] == {"question": "unit"}
    by_link = {q["link_id"]: q for q in record["per_question"]}
    assert by_link["spo2"]["unit"] == "%"
    # The unit is declared once, in styling_metadata.phc.unit, next to the
    # range that validates it. What is new is that the same string is now
    # bound to the UCUM value set at build time, so the symbol that reaches a
    # FHIR Quantity is one UCUM vouched for and the system travels with it.
    assert by_link["spo2"]["unit_system"] == "http://unitsofmeasure.org"
    rows = mapping.records(OPERATIONS["phc.op.vitals-record"], {"spo2": 97})
    assert rows == [("observation", {
        "category": "vital-signs", "code": "2708-6",
        "code_system": "http://loinc.org",
        "code_display": "Oxygen saturation in Arterial blood",
        "value": 97, "unit": "%",
        "unit_system": "http://unitsofmeasure.org"})], rows


def test_every_write_operation_in_the_bundle_declares_a_mapping():
    for op_id, op in sorted(OPERATIONS.items()):
        if op["kind"] != "write":
            continue
        assert op["mapping"], "%s writes and maps nothing" % op_id
        assert {r["resource"] for r in op["mapping"]} == set(op["writes"]), op_id


# --------------------------------------------------------------------------
# a mismatch fails the build
# --------------------------------------------------------------------------

SCHEMA = {"questions": [
    {"link_id": "systolic", "text": "Systolic", "type": "integer", "required": True,
     "styling_metadata": {"phc": {"unit": "mm[Hg]"}}},
    {"link_id": "note", "text": "Note", "type": "text"},
    {"link_id": "drugs", "text": "Drugs", "type": "structured", "repeats": True},
    # A repeating group, with nothing required inside it: a required sub
    # question would have to be mapped or listed under `ignored` by every
    # test below, which would be a fixture about fixtures.
    {"link_id": "medicines", "text": "Medicines", "type": "group",
     "repeats": True, "styling_metadata": {"phc": {"row": "medicine"}},
     "questions": [
         {"link_id": "pick", "text": "Pick", "type": "choice",
          "answer_value_set": "medication-code"},
         {"link_id": "amount", "text": "Amount", "type": "decimal"},
     ]},
]}


def failures(mapping_block, writes=("observation",)):
    _, bad = mapping.compile_records(
        {"writes": list(writes), "mapping": mapping_block}, SCHEMA)
    return " | ".join(bad)


GOOD = {"records": [
    {"resource": "observation",
     "per_question": ["systolic"],
     "fields": {"created_by": {"actor": "id"},
                "code": {"question": "link_id"}, "value": {"question": "answer"},
                "unit": {"question": "unit"}}},
], "ignored": ["note", "drugs"]}


def test_a_sound_mapping_lints_clean():
    assert failures(GOOD) == ""


def test_a_row_with_no_author_fails_the_build():
    """Every row says who wrote it, or the build stops. Until this rule a
    kernel write left created_by null on every table, which is why a
    separation of duties rule had nothing to read."""
    fields = dict(GOOD["records"][0]["fields"])
    fields.pop("created_by")
    bad = {"records": [dict(GOOD["records"][0], fields=fields)],
           "ignored": ["note", "drugs"]}
    assert "no author" in failures(bad), failures(bad)
    worse = {"records": [dict(GOOD["records"][0],
                              fields=dict(fields, created_by={"actor": "name"}))],
             "ignored": ["note", "drugs"]}
    assert "actor takes one of id" in failures(worse), failures(worse)


def test_the_author_lands_on_every_row_and_never_stands_in_for_an_answer():
    op = OPERATIONS["phc.op.vitals-record"]
    rows = mapping.records(op, {"spo2": 97}, actor="user:nurse")
    assert rows == [("observation", {
        "created_by": "user:nurse", "category": "vital-signs",
        "code": "2708-6", "code_system": "http://loinc.org",
        "code_display": "Oxygen saturation in Arterial blood",
        "value": 97, "unit": "%",
        "unit_system": "http://unitsofmeasure.org"})], rows
    # An author is not an answer: a payload that produced nothing is still no
    # row, not a row carrying only its author.
    assert mapping.records(op, {}, actor="user:nurse") == []


def test_a_link_id_the_questionnaire_lacks_fails_the_build():
    bad = {"records": [dict(GOOD["records"][0], fields={"code": {"answer": "sistolic"}})],
           "ignored": ["note", "drugs"]}
    assert "'sistolic' is not a question" in failures(bad)
    bad = {"records": [{"resource": "observation", "per_question": ["pulse"],
                        "fields": {"code": {"question": "link_id"}}}],
           "ignored": ["note", "drugs", "systolic"]}
    assert "per_question 'pulse' is not a question" in failures(bad)
    bad = {"records": [{"resource": "observation", "per_item": "medications",
                        "fields": {"code": {"item": "code"}}}],
           "ignored": ["note", "drugs", "systolic"]}
    assert "per_item 'medications' is not a question" in failures(bad)


def test_a_resource_the_operation_does_not_write_fails_the_build():
    bad = {"records": [dict(GOOD["records"][0], resource="condition")],
           "ignored": ["note", "drugs"]}
    said = failures(bad)
    assert "does not declare in writes" in said, said
    assert "writes 'observation' but no record maps anything into it" in said, said


def test_a_declared_write_with_no_record_fails_the_build():
    assert "writes 'notes' but no record maps anything into it" in \
        failures(GOOD, writes=("observation", "notes"))


def test_a_required_answer_that_goes_nowhere_fails_the_build():
    bad = {"records": [{"resource": "observation",
                        "fields": {"code": {"answer": "note"}}}]}
    said = failures(bad)
    assert "'systolic' is required and goes nowhere" in said, said


def test_a_unit_the_questionnaire_does_not_carry_fails_the_build():
    bad = {"records": [{"resource": "observation", "per_question": ["note"],
                        "fields": {"value": {"question": "answer"},
                                   "unit": {"question": "unit"}}}],
           "ignored": ["drugs", "systolic"]}
    assert "declares no unit" in failures(bad)


def test_a_question_that_binds_no_concept_may_not_write_a_code_column():
    """The companion of the unit rule above, and the sharper half of it.

    A question binds a concept by declaring a `code`, which is then checked
    against the value set it binds to. A record writing {question: code} for
    a question that declares none would fill the code column with nothing,
    and a row whose code is null is a clinical fact that means nothing
    anywhere, including here.
    """
    bad = {"records": [{"resource": "observation", "per_question": ["note"],
                        "fields": {"created_by": {"actor": "id"},
                                   "code": {"question": "code"}}}],
           "ignored": ["drugs", "systolic"]}
    said = failures(bad)
    assert "binds no code" in said, said
    for fact in ("code_system", "code_display"):
        worse = {"records": [{"resource": "observation", "per_question": ["note"],
                              "fields": {"created_by": {"actor": "id"},
                                         fact: {"question": fact}}}],
                 "ignored": ["drugs", "systolic"]}
        assert "binds no code" in failures(worse), (fact, failures(worse))


def test_an_answer_coding_source_needs_a_question_that_binds_its_answer():
    """The third binding form's own closure rule.

    `{answer_code: x}` stores the code an answer names, resolved through the
    value set that question binds. A question that binds nothing has no value
    set to resolve through, so the column would hold whatever was typed: that
    is exactly the defect the laboratory result's code column had, where the
    analyte's free text became the report's code. Refused at build time.
    """
    bad = {"records": [{"resource": "observation", "per_question": ["systolic"],
                        "fields": {"created_by": {"actor": "id"},
                                   "code": {"answer_code": "note"}}}],
           "ignored": ["drugs"]}
    said = failures(bad)
    assert "declares no answer_value_set" in said, said
    assert "answer_code" in said, said
    # And a link_id that is not a question at all is caught the same way.
    worse = {"records": [{"resource": "observation", "per_question": ["systolic"],
                          "fields": {"created_by": {"actor": "id"},
                                     "code": {"answer_code": "nonsense"}}}],
             "ignored": ["drugs", "note"]}
    assert "is not a question on this form" in failures(worse), failures(worse)


def test_per_row_needs_a_question_that_actually_holds_rows():
    """`per_row` reads a repeating group, and only a repeating group.

    A structured answer has no declared sub questions, so a per_row record
    over one would lint every source against nothing and write whatever
    arrived: the exact behaviour per_row exists to replace. A plain group does
    not repeat, so it has no rows at all.
    """
    for link_id, says in (("drugs", "holds no rows"),
                          ("note", "holds no rows"),
                          ("nonsense", "is not a question on this form")):
        bad = {"records": [{"resource": "observation", "per_row": link_id,
                            "fields": {"created_by": {"actor": "id"},
                                       "value": {"const": 1}}}],
               "ignored": ["note", "drugs", "systolic"]}
        said = failures(bad)
        assert says in said, (link_id, said)


def test_a_per_row_record_reads_its_own_row_and_nothing_else():
    """A source in a per_row record names a sub question of that group.

    Naming a top level question would read a key the row does not have, so
    the column lands null and nothing says why. Refused at build time rather
    than discovered as a blank column in a district report.
    """
    bad = {"records": [{"resource": "observation", "per_row": "medicines",
                        "fields": {"created_by": {"actor": "id"},
                                   "value": {"answer": "systolic"}}}],
           "ignored": ["note", "drugs", "systolic"]}
    said = failures(bad)
    assert "'systolic' is not a question on this form" in said, said
    # And the sub question of its own group is accepted.
    good = {"records": [{"resource": "observation", "per_row": "medicines",
                         "fields": {"created_by": {"actor": "id"},
                                    "value": {"answer": "amount"},
                                    "code": {"answer_code": "pick"}}}],
            "ignored": ["note", "drugs", "systolic"]}
    assert failures(good) == "", failures(good)


def test_one_link_id_means_one_question():
    """A name used twice makes every source in this file ambiguous.

    A repeating group's sub questions share the namespace with the rest of the
    form, so `{answer: dose}` could mean the row's or the form's, and the
    lookup would resolve to whichever one `walk` yielded last. There is no
    useful reading of a duplicate, so it is refused rather than disambiguated.
    """
    clash = {"questions": list(SCHEMA["questions"]) + [
        {"link_id": "amount", "text": "Amount again", "type": "decimal"}]}
    _, bad = mapping.compile_records(
        {"writes": ["observation"], "mapping": GOOD}, clash)
    said = " | ".join(bad)
    assert "'amount' is the link_id of more than one question" in said, said


def test_a_source_that_needs_a_context_it_does_not_have_fails_the_build():
    bad = {"records": [{"resource": "observation",
                        "fields": {"code": {"item": "code"}}}],
           "ignored": ["note", "drugs", "systolic"]}
    assert "the record needs per_item" in failures(bad)
    bad = {"records": [{"resource": "observation", "per_item": "drugs",
                        "fields": {"code": {"question": "link_id"}}}],
           "ignored": ["note", "systolic"]}
    assert "needs per_question" in failures(bad)


def test_an_unknown_source_or_key_fails_the_build():
    bad = {"records": [{"resource": "observation", "per_question": ["systolic"],
                        "fields": {"code": {"lookup": "somewhere"}}}],
           "ignored": ["note", "drugs"]}
    assert "unknown source 'lookup'" in failures(bad)
    bad = {"records": [dict(GOOD["records"][0], where={"a": 1})],
           "ignored": ["note", "drugs"]}
    assert "unknown key 'where'" in failures(bad)


def test_a_missing_mapping_fails_the_build():
    _, bad = mapping.compile_records({"writes": ["observation"]}, SCHEMA)
    assert bad and "no mapping" in bad[0], bad


def test_the_shipped_atoms_lint_clean():
    _, bad = mapping.load()
    assert not bad, bad


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok   %s" % name.replace("_", " ")[5:])
    print("ok   kernel mapping: %d checks" % sum(
        1 for n in globals() if n.startswith("test_")))
