"""Build a Snapshot from CARE. The only module here that needs a live CARE.

Kept apart from thread.py on purpose: the derivation rules are pure and tested
exhaustively without a database, and this is the thin, boring part that asks
CARE what it knows.

UNVERIFIED. None of these queries have been run against a CARE instance. Field
names are taken from care/emr/models/*.py and are the most likely source of
error in this repo. Treat every one as a hypothesis until it has run.
"""
from care.emr.models import (
    DiagnosticReport,
    MedicationDispense,
    MedicationRequest,
    Observation,
    ServiceRequest,
)

from care_phc.thread import Snapshot


def snapshot_for(encounter, thread=None):
    patient = encounter.patient
    counts = {
        "vitals_observations": Observation.objects.filter(
            encounter=encounter, category="vital-signs").count(),
        "consult_notes": encounter.notes.count(),
        "active_medication_requests": MedicationRequest.objects.filter(
            encounter=encounter, status="active").count(),
        "service_requests": ServiceRequest.objects.filter(encounter=encounter).count(),
        "diagnostic_reports": DiagnosticReport.objects.filter(encounter=encounter).count(),
        "final_diagnostic_reports": DiagnosticReport.objects.filter(
            encounter=encounter, status="final").count(),
    }
    return Snapshot(
        patient_exists=bool(patient),
        abha_number=_abha(patient),
        prescribed_lines=counts["active_medication_requests"],
        dispensed_lines=MedicationDispense.objects.filter(encounter=encounter).count(),
        bookings=patient.appointments.filter(status="booked").count(),
        stored=frozenset(thread.flags if thread else ()),
        **counts,
    )


def _abha(patient):
    """ABHA lives in CARE's patient identifier config, not on a fixed field."""
    for identifier in patient.identifiers or []:
        if identifier.get("config_slug") == "abha":
            return identifier.get("value")
    return None
