"""Run: python3 -m adapters.local.tests.test_store

The adapter's only cleverness is the thread join and the where clause, so that
is what this pins down. No HTTP, no guard: a store with rows in it.
"""
import os

from adapters.local.store import TABLES, SqliteStore, seed
from kernel import declarations, mapping
from kernel.contracts import AuditRecord, Proposal

# The operations with their declared mapping attached. Nothing in this file
# derives a row any more; it checks that the declared ones fit these tables.
OPERATIONS = declarations.load("phc").operations

# One representative payload per operation, answering the questions the
# questionnaire marks required. Nothing here is clinical advice; it is the
# smallest payload that must not vanish.
PAYLOADS = {
    "phc.op.patient-register": {"name": "Devi Prasad", "age": 41, "sex": "male",
                                "phone": "9800000099", "village": "Sonpur"},
    "phc.op.abha-link": {"method": "link_existing", "consent_given": True,
                         "abha_number": "12-0000-0000-0000"},
    "phc.op.vitals-record": {"systolic": 118, "diastolic": 76, "pulse": 80},
    "phc.op.consult-document": {"assessment": "Viral fever",
                                "diagnosis": [
                                    {"condition": "44054006",
                                     "clinical_status": "active",
                                     "verification_status": "confirmed"}]},
    "phc.op.rx-prescribe": {"medications": [{"drug": "777067000",
                                             "dose": 500, "dose_unit": "mg",
                                             "route": "26643006",
                                             "frequency": "229798009",
                                             "duration": 5,
                                             "duration_unit": "d"}]},
    "phc.op.lab-order": {"investigations": [{"code": "CBC"}]},
    # The analyte is the LOINC code its question binds to, and the unit is the
    # one LOINC reports it in: the free text this used to be is now refused
    # before a row is built. scripts/check_lab.py owns that rule.
    "phc.op.lab-result-enter": {"analyte": "718-7", "value": 9.4, "unit": "g/dL",
                                "note": "repeat on a fresh sample"},
    "phc.op.pharmacy-dispense": {"dispenses": [{"medication": "Paracetamol 500mg",
                                                "quantity": 9}]},
    "phc.op.household-visit": {"visit_type": "routine", "consent_at_door": True,
                               "narrative": "Two children, both immunised."},
}


def fresh():
    store = SqliteStore(":memory:")
    seed(store)
    return store


def test_a_query_is_scoped_to_its_thread_even_across_the_patient_join():
    store = fresh()
    # enc-003 is the patient with a critical blood pressure; three vitals.
    assert store.count("observation", thread="enc-003",
                       where={"category": "vital-signs"}) == 3
    assert store.count("observation", thread="enc-002",
                       where={"category": "vital-signs"}) == 0
    # patient joins through the encounter, which no declaration ever states.
    assert store.count("patient", thread="enc-003", where={}) == 1
    assert store.count("patient", thread="enc-001", where={}) == 0, \
        "the walk in thread has no patient yet"


def test_the_star_condition_means_present_and_not_empty():
    store = fresh()
    assert store.count("patient", thread="enc-003", where={"abha_number": "*"}) == 1
    assert store.count("patient", thread="enc-002", where={"abha_number": "*"}) == 0


def test_gte_compares_and_an_unknown_field_is_refused():
    store = fresh()
    # Against the declared seed, not a number typed here: this test is about
    # the gte clause matching everything, and a literal turns every seed
    # change into a failure in a file that has nothing to do with seeds.
    seeded = len(declarations.load("phc").seed)
    assert seeded >= 2, "the seed is what makes this assertion meaningful"
    assert store.count("encounter", thread=None,
                       where={"created_date": {"gte": "0000-01-01"}}) == seeded
    assert store.count("encounter", thread=None,
                       where={"created_date": {"gte": "9999-01-01"}}) == 0
    try:
        store.count("encounter", thread=None, where={"drop table": 1})
    except ValueError:
        pass
    else:
        raise AssertionError("an undeclared field must not reach SQL")


def test_writing_a_patient_twice_updates_the_one_the_thread_already_has():
    store = fresh()
    store.write("patient", {"abha_number": "12-0000-0000-0000"}, thread="enc-002")
    rows = store.select("patient", thread="enc-002", where={}, fields=["id", "name"],
                        limit=5)
    assert len(rows) == 1, "an update must not become a second patient"
    assert rows[0]["name"] == "Kamala Devi", "the untouched columns survive"
    assert store.count("patient", thread="enc-002", where={"abha_number": "*"}) == 1


def test_every_declared_record_names_columns_this_adapter_has():
    """The adapter's half of the mapping lint. kernel/mapping.py checks a
    record against the questionnaire and against Operation.writes; it must not
    know this schema, so column names are checked here. A mapped column this
    table lacks is a build failure, not a value dropped at three in the
    morning."""
    for op_id, op in sorted(OPERATIONS.items()):
        for record in op["mapping"]:
            missing = sorted(set(record["fields"]) - set(TABLES[record["resource"]]))
            assert not missing, "%s maps %s into %s, which has no such column" % (
                op_id, missing, record["resource"])


def test_every_operation_in_the_bundle_writes_a_row_with_something_in_it():
    """The failure this guards against is silent: an answer nothing maps is
    dropped, and the row lands empty with the state flag never flipping."""
    # what every row gets regardless of payload. Anything else is content,
    # including a status: the encounter row a consultation writes carries only
    # a status, because the row itself is the thread and already exists.
    skeleton = {"id", "encounter", "created_by", "created_date"}
    for op_id, payload in sorted(PAYLOADS.items()):
        rows = mapping.records(OPERATIONS[op_id], payload)
        landed = {resource for resource, _ in rows}
        assert landed == set(OPERATIONS[op_id]["writes"]), \
            "%s declares writes %s and this payload reached %s" % (
                op_id, sorted(OPERATIONS[op_id]["writes"]), sorted(landed))
        for resource, row in rows:
            assert set(row) - skeleton, \
                "%s writes an empty %s row" % (op_id, resource)


def test_a_column_this_table_does_not_have_is_refused_and_not_dropped():
    store = fresh()
    try:
        store.write("observation", {"code": "8480-6", "value": 118,
                                    "override_reason": "on the other arm"},
                    thread="enc-002")
    except ValueError as e:
        assert "no column override_reason" in str(e), e
    else:
        raise AssertionError("a mapped value with nowhere to go was swallowed")


def test_the_vitals_payload_fans_out_into_one_row_per_reading():
    store = fresh()
    for resource, row in mapping.records(OPERATIONS["phc.op.vitals-record"],
                                         PAYLOADS["phc.op.vitals-record"]):
        store.write(resource, row, thread="enc-002")
    rows = store.select("observation", thread="enc-002",
                        where={"category": "vital-signs"},
                        fields=["code", "code_system", "code_display", "value",
                                "unit", "unit_system"], limit=10)
    # The code is the question's bound LOINC concept, which is what makes a
    # row countable in another facility: `WHERE code = '8480-6'` means the
    # same thing everywhere and `WHERE code = 'systolic'` means nothing
    # outside this questionnaire.
    by_code = {r["code"]: r for r in rows}
    assert set(by_code) == {"8480-6", "8462-4", "8867-4"}, sorted(by_code)
    assert by_code["8480-6"] == {
        "code": "8480-6", "code_system": "http://loinc.org",
        "code_display": "Systolic blood pressure", "value": "118",
        "unit": "mm[Hg]", "unit_system": "http://unitsofmeasure.org"}, by_code["8480-6"]


def test_a_flag_raised_twice_is_one_flag():
    store = fresh()
    store.raise_flag("enc-002", "capture.consented")
    store.raise_flag("enc-002", "capture.consented")
    assert store.stored_flags("enc-002") == frozenset({"capture.consented"})
    assert store.count("thread_flag", thread="enc-002", where={}) == 1


def test_proposals_and_audit_round_trip_with_their_json_columns():
    store = fresh()
    proposal = Proposal(id="p1", thread="enc-002", operation="phc.op.vitals-record",
                        payload={"systolic": 120}, proposed_by="agent", surface="mcp",
                        status="pending", created_at="2026-09-10T10:00:00+00:00",
                        flags_raised=["vitals.flagged"])
    store.put_proposal(proposal)
    assert store.proposal("p1").payload == {"systolic": 120}
    assert store.proposals("enc-002", status="pending")[0].flags_raised == ["vitals.flagged"]
    store.put_proposal(Proposal(**dict(proposal.__dict__, status="confirmed")))
    assert store.proposals("enc-002", status="pending") == []

    store.append_audit(AuditRecord(id="a1", thread="enc-002", operation="op",
                                   actor="me", surface="rendered", payload={"a": 1},
                                   outcome="allowed", at="2026-09-10T10:00:00+00:00"))
    assert store.audit("enc-002")[0].payload == {"a": 1}


def test_the_seed_puts_people_at_different_points_in_the_line():
    store = fresh()
    threads = store.threads(workflow="phc.wf.outpatient", scope="today")
    assert len(threads) == 7
    assert {t.subject.get("name") for t in threads} >= {"Ramesh Kumar", "Meera Patel",
                                                        "Lakshmi Devi"}
    # The seed declares enc-003's consent to ambient capture as well, which is
    # what makes the scribe offerable on the demo day. capture.consented is not
    # here because it is composed by the workflow and never stored.
    assert store.stored_flags("enc-003") == frozenset({"vitals.flagged", "capture.agreed"})
    assert store.stored_flags("enc-004") == frozenset({"capture.declined"})
    assert store.count("medication_dispense", thread="enc-006", where={}) == 2
    assert store.count("medication_dispense", thread="enc-005", where={}) == 0


def test_a_bundle_with_no_seed_starts_empty_and_does_not_crash():
    """Seed is optional. A facility whose demo day nobody has written gets an
    empty queue, not a traceback and not another facility's patients."""
    import tempfile

    empty = SqliteStore(":memory:")
    assert seed(empty, []) == []
    assert empty.threads(workflow="anything", scope="today") == []
    for table in TABLES:
        assert empty.db.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0] == 0
    # A bundle directory with no seed.yaml is what "no seed" looks like on
    # disk, and that is where the default of none is decided.
    assert declarations.load_seed(tempfile.mkdtemp()) == []


def test_a_stale_demo_day_walks_forward_and_real_work_stays_put():
    """A file seeded yesterday used to draw an empty workspace this morning,
    because every queue view is scope: today. The seeded threads move; a
    thread a person opened does not, and nothing lands in the future."""
    import tempfile
    from datetime import datetime, timedelta, timezone

    path = os.path.join(tempfile.mkdtemp(), "stale.sqlite3")
    store = SqliteStore(path)
    seed(store)
    mine = store.open_thread(token="T-9", actor="user:nurse")
    dated = [(t, "created_at" if t == "proposal" else "at" if t == "audit"
              else "created_date") for t in TABLES]
    for table, column in dated:
        store.db.execute(
            "UPDATE %s SET %s = replace(datetime(%s, '-3 days'), ' ', 'T')"
            " || '+00:00'" % (table, column, column))
    assert store.threads(workflow="w", scope="today") == []

    reopened = SqliteStore(path)          # roll_seed_forward runs in __init__
    today = [t.id for t in reopened.threads(workflow="w", scope="today")]
    # 7 since the pregnancy was seeded. The count is the seed's, so it moves
    # when the seed does; what this is checking is that the whole demo day
    # walked forward together and that a real thread did not come with it.
    assert len(today) == 7, today
    assert mine not in today, "a thread a person opened is not the demo day"
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    for table, column in dated:
        late = reopened.db.execute(
            "SELECT COUNT(*) FROM %s WHERE %s >= ?" % (table, column),
            [tomorrow]).fetchone()[0]
        assert late == 0, "%s was pushed into the future" % table
    assert SqliteStore(path).roll_seed_forward() == 0, "rolling twice moves nothing"


def test_two_threads_writing_at_once_do_not_corrupt_the_file():
    """The regression this exists for: FastAPI runs sync endpoints in a thread
    pool, and one sqlite3 connection shared across those threads corrupts the
    database on the second concurrent request. On a file, not in memory, since
    that is where the corruption lands."""
    import tempfile
    import threading

    path = os.path.join(tempfile.mkdtemp(), "concurrent.sqlite3")
    store = SqliteStore(path)
    store.open_thread(token="T-1")
    errors = []

    op = OPERATIONS["phc.op.vitals-record"]

    def hammer(n):
        try:
            for i in range(20):
                for resource, row in mapping.records(
                        op, {"systolic": 100 + i, "diastolic": 70, "pulse": 70,
                             "temperature": 36.6, "spo2": 98, "weight": 50}):
                    store.write(resource, row, thread="enc-001")
                store.count("observation", thread=None, where={})
        except Exception as e:  # noqa: BLE001 - the point is that nothing raises
            errors.append("%s: %s" % (n, e))

    workers = [threading.Thread(target=hammer, args=(n,)) for n in range(4)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert not errors, errors
    assert store.count("observation", thread=None, where={}) == 4 * 20 * 6


def test_every_store_method_the_contract_names_is_here():
    """A missing one is an AttributeError somewhere in the kernel, which is a
    bad place to find out.

    Relocated here when adapters/care was deleted. It was the only assertion in
    the repository that pinned the protocol's method names against a class, and
    the protocol outlived the second adapter, so the check had to outlive it
    too. kernel/contracts.py used to call the protocol "nine methods" while
    declaring ten; the count is asserted from the class rather than from the
    prose, which is how that was found.

    ELEVEN SINCE 2026-11-01. `issue_token` joined it when the token race was
    closed, and it is the first method here that an adapter can satisfy in
    shape and still get wrong: returning a number is easy and returning a
    number nobody else was given is the actual contract. This test holds the
    NAME, which is all a name test can hold. What holds the behaviour is
    scripts/check_tokens_race.py, which runs real parallel processes against a
    real file, and the sequence test below.
    """
    from kernel.contracts import Store

    declared = sorted(n for n in vars(Store) if not n.startswith("_"))
    assert declared == ["append_audit", "audit", "count", "issue_token",
                        "proposals", "put_proposal", "raise_flag", "select",
                        "stored_flags", "threads", "write"], declared
    for name in declared:
        assert callable(getattr(SqliteStore, name, None)), "SqliteStore has no " + name


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok   %s" % name.replace("_", " ")[5:])
    print("ok   adapters/local: %d checks" % sum(
        1 for n in globals() if n.startswith("test_")))
