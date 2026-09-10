"""Canonical vocabularies. One definition, read by lint, compile, guard and tests.

Nothing here may be extended by an atom: an atom naming a capability, state or
resource that is not in these lists is a lint failure, not a new entry. That is
the whole point -- a typo in frontmatter compiles into a permission hole.
"""

# addendum SSC. `handover` is the prototype's; it is a real operation, not a bundle.
CAPABILITIES = frozenset({
    "patient.find", "patient.register", "abha.link",
    "vitals.record", "assessment.record", "encounter.document",
    "rx.prescribe", "lab.order", "lab.result.enter", "lab.result.validate",
    "pharmacy.dispense", "visit.household", "appointment.book",
    "handover", "facility.admin", "reporting.view",
})

# Default bundles ship as CARE roles with is_system=True. A facility's own
# combination is an is_system=False role in the DB, which CARE's
# sync_permissions_roles command deliberately does not touch.
BUNDLES = {
    "frontdesk": ["patient.find", "patient.register", "abha.link", "appointment.book", "handover"],
    "nurse": ["patient.find", "patient.register", "abha.link", "appointment.book",
              "vitals.record", "assessment.record", "handover"],
    "mo": ["patient.find", "encounter.document", "rx.prescribe", "lab.order",
           "assessment.record", "reporting.view", "handover"],
    "lab": ["patient.find", "lab.result.enter", "handover"],
    "lab_incharge": ["patient.find", "lab.result.enter", "lab.result.validate", "handover"],
    "pharmacist": ["patient.find", "pharmacy.dispense", "handover"],
    "asha": ["patient.find", "patient.register", "abha.link", "visit.household",
             "assessment.record", "appointment.book"],
    "anm": ["patient.find", "patient.register", "abha.link", "visit.household",
            "assessment.record", "appointment.book", "vitals.record"],
    "cho": ["patient.find", "patient.register", "abha.link", "visit.household",
            "assessment.record", "appointment.book", "vitals.record",
            "encounter.document", "lab.order", "rx.prescribe"],
}

# Thread state flags. Derived from CARE resources where CARE knows the answer;
# stored on EncounterThread only where it does not. See catalogue/README.md.
STATES = frozenset({
    "registered", "abha.linked", "abha.pending",
    "capture.consented",
    "vitals.recorded", "vitals.flagged",
    "consult.documented",
    "rx.confirmed",
    "lab.ordered", "lab.resulted", "lab.validated", "lab.critical",
    "dispensed.partial", "dispensed.complete",
    "followup.booked",
})

# CARE emr models an operation may write. Names match care/emr/models/*.py.
CARE_RESOURCES = frozenset({
    "patient", "encounter", "observation", "condition", "notes",
    "medication_request", "medication_dispense", "inventory_item",
    "service_request", "specimen", "diagnostic_report",
    "questionnaire_response", "consent", "organization", "location",
    # care/emr/models/scheduling/booking.py TokenBooking. Unverified name;
    # read only, no operation writes it yet.
    "token_booking",
})

# Records the kernel keeps that CARE does not: the stored thread flags. A
# declaration may count them (a metric) but no operation may write them.
KERNEL_RESOURCES = frozenset({"thread_flag"})

IRREVERSIBILITY = ("reversible", "correctable", "irreversible")
INSTRUMENTS = ("form", "device", "constrained-voice", "scribe", "palette")
KINDS = ("read", "write")
STATIONS = ("reception", "nurse", "doctor", "lab", "pharmacy", "community")

BODY_SECTIONS = (
    "In plain words", "Before you start", "What happens",
    "How you know it worked", "When it goes wrong",
)
