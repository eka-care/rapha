"""Run: python3 -m care_phc.tests.test_thread

Pure derivation only. No Django, no CARE, no database: that is the point of
keeping the rules apart from the queries that feed them.
"""
import json
import pathlib

from care_phc.thread import LINE, STORED, Snapshot, actions, derive, station

CAT = json.loads((pathlib.Path(__file__).parents[2] / "catalogue" / "catalogue.json").read_text())
REG = Snapshot(patient_exists=True)
SEEN = Snapshot(patient_exists=True, abha_number="12-3456", vitals_observations=3,
                consult_notes=1)


def test_a_registered_patient_without_abha_is_pending_not_broken():
    flags = derive(REG)
    assert flags == {"registered", "abha.pending", "capture.consented"}
    assert "abha.linked" not in flags


def test_linking_an_abha_clears_pending():
    flags = derive(Snapshot(patient_exists=True, abha_number="12-3456"))
    assert flags == {"registered", "abha.linked", "capture.consented"}


def test_capture_is_consented_until_somebody_refuses_it():
    """The owner's decision of 2026-11-01. A visit nobody asked about may be
    recorded; a decline at the desk and a withdrawal at the doctor are the
    two answers that still stop it, and either one alone is enough."""
    assert "capture.consented" in derive(REG)
    for refusal in ("capture.declined", "capture.withdrawn"):
        flags = derive(Snapshot(patient_exists=True, stored=frozenset({refusal})))
        assert "capture.consented" not in flags, refusal


def test_partial_and_complete_dispense_are_a_comparison_not_a_boolean():
    part = derive(Snapshot(patient_exists=True, active_medication_requests=1,
                           prescribed_lines=3, dispensed_lines=2))
    full = derive(Snapshot(patient_exists=True, active_medication_requests=1,
                           prescribed_lines=3, dispensed_lines=3))
    assert "dispensed.partial" in part and "dispensed.complete" not in part
    assert "dispensed.complete" in full and "dispensed.partial" not in full


def test_only_the_three_stored_flags_survive_derivation():
    s = Snapshot(patient_exists=True, stored=frozenset({"vitals.flagged", "rx.confirmed"}))
    flags = derive(s)
    assert "vitals.flagged" in flags
    assert "rx.confirmed" not in flags, "a derived flag was accepted from storage"


def test_station_skips_steps_the_patient_was_never_sent_to():
    assert station(derive(REG)) == "nurse"
    assert station(derive(SEEN)) is None, "consulted with no orders is finished"
    assert station(derive(Snapshot(**{**SEEN.__dict__, "service_requests": 1}))) == "lab"


def test_station_is_pharmacy_only_once_something_is_prescribed():
    rx = Snapshot(**{**SEEN.__dict__, "active_medication_requests": 1, "prescribed_lines": 2})
    assert station(derive(rx)) == "pharmacy"


def test_dispense_is_not_offered_before_a_prescription_exists():
    caps = {"pharmacy.dispense", "patient.find"}
    assert [op["id"] for op in actions(CAT, derive(SEEN), caps)] == []
    rx = Snapshot(**{**SEEN.__dict__, "active_medication_requests": 1, "prescribed_lines": 2})
    assert "phc.op.pharmacy-dispense" in [op["id"] for op in actions(CAT, derive(rx), caps)]


def test_actions_lead_with_the_station_the_patient_is_at():
    caps = set(CAT["capabilities"])
    flags = derive(REG)
    first = actions(CAT, flags, caps)[0]
    assert first["station"] == station(flags) == "nurse"
    assert first["id"] == "phc.op.vitals-record"


def test_every_line_step_names_a_real_state():
    for _, done_when, applies_when in LINE:
        assert done_when in CAT["states"]
        assert applies_when is None or applies_when in CAT["states"]
    for flag in STORED:
        assert flag in CAT["states"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
