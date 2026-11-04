"""Patient thread state: the baton that carries a patient between stations.

CARE has encounters. It has no concept of a patient part-way through an
outpatient line, which is the whole of addendum SSD, so this is ours.

The rule here is one source of truth. Where CARE already knows something we
derive it and store nothing; a stored copy of a fact CARE owns will desync, and
a desynced copy shows a pharmacist a Dispense button that should not exist.
Only three flags are stored, because only three are things CARE cannot answer.

derive() is deliberately pure: a Snapshot in, a set of flags out, no ORM, so
it can be tested exhaustively without a running CARE. The Django querying that
used to build a Snapshot (queries.py) is deleted: every field name it guessed
was wrong. kernel/state.py is what derives a
thread's flags today; this file and its check are what that was proved
against.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# What CARE cannot answer for us, so we keep it. Nothing else belongs here.
# The three capture flags are the halves of one consent: agreed at the desk,
# declined at the desk, withdrawn mid visit. capture.consented is not among
# them because it is composed from all three, below.
STORED = ("capture.agreed", "capture.declined", "capture.withdrawn",
          "vitals.flagged", "lab.critical")

# Station order for the outpatient line. The current station is the first step
# whose work is not done, which is why it is derived and never stored.
#
# The third element is what makes the step apply at all. Lab and pharmacy are
# conditional: a patient nobody ordered a test for is not waiting at the lab,
# they have simply skipped it. Without this a consultation with no
# investigation parks the patient at a station they were never sent to.
LINE = (
    ("reception", "registered", None),
    ("nurse", "vitals.recorded", None),
    ("doctor", "consult.documented", None),
    ("lab", "lab.resulted", "lab.ordered"),
    ("pharmacy", "dispensed.complete", "rx.confirmed"),
    # The house, and it is last because it is not a bench: see the comment on
    # the same step in bundles/phc/phc.wf.outpatient.md, which is the
    # declaration this tuple is held against.
    ("community", "consult.documented", "postnatal.open"),
)


@dataclass(frozen=True)
class Snapshot:
    """Facts CARE can answer about one encounter. Built by a caller; the
    only one left is this module's own check."""
    patient_exists: bool = False
    abha_number: str | None = None
    vitals_observations: int = 0
    consult_notes: int = 0
    active_medication_requests: int = 0
    service_requests: int = 0
    diagnostic_reports: int = 0
    final_diagnostic_reports: int = 0
    prescribed_lines: int = 0
    dispensed_lines: int = 0
    bookings: int = 0
    stored: frozenset = field(default_factory=frozenset)


def derive(s: Snapshot) -> set[str]:
    """The flags true for this encounter right now."""
    flags = set(f for f in s.stored if f in STORED)

    if s.patient_exists:
        flags.add("registered")
    if s.abha_number:
        flags.add("abha.linked")
    elif s.patient_exists:
        # Not an error state. Addendum SSB.3: registered, tokened and seen,
        # with the gap as a worklist item rather than a barrier to care.
        flags.add("abha.pending")

    # Consent to ambient capture is composed rather than stored: the store can
    # raise a flag and cannot lower one, so a withdrawal has to be a flag of
    # its own that turns the gate off. Since the owner's decision of
    # 2026-11-01 it is presumed: a visit nobody refused may be recorded, and
    # only a decline at the desk or a withdrawal at the doctor lowers it.
    # phc.wf.outpatient declares this rule and this is that rule, in code,
    # until thread.py is retired.
    if not ({"capture.declined", "capture.withdrawn"} & flags):
        flags.add("capture.consented")

    if s.vitals_observations:
        flags.add("vitals.recorded")
    if s.consult_notes:
        flags.add("consult.documented")
    if s.active_medication_requests:
        flags.add("rx.confirmed")
    if s.service_requests:
        flags.add("lab.ordered")
    if s.diagnostic_reports:
        flags.add("lab.resulted")
    if s.final_diagnostic_reports:
        flags.add("lab.validated")
    if s.bookings:
        flags.add("followup.booked")

    # Partial dispense is a normal outcome at a primary health centre, so
    # "dispensed" is a comparison and not a boolean.
    if s.dispensed_lines:
        if s.prescribed_lines and s.dispensed_lines >= s.prescribed_lines:
            flags.add("dispensed.complete")
        else:
            flags.add("dispensed.partial")

    return flags


def station(flags) -> str | None:
    """Where this patient is. None once the line is complete."""
    for name, done_when, applies_when in LINE:
        if applies_when and applies_when not in flags:
            continue
        if done_when not in flags:
            return name
    return None


def actions(catalogue, flags, caps, station_filter=None):
    """Quick actions to draw, ordered. Addendum SSD.2: a table, not a model.

    Ordering is by the line, so the next thing to do at this patient's current
    station sorts first. Six visible, per SSD; the rest live behind the palette.
    """
    from catalogue.guard import visible

    order = {name: i for i, (name, *_) in enumerate(LINE)}
    # Inside one station, the order the STEP lists its operations in. That
    # list is the bundle saying which of the things at this bench is the
    # point, and the fallback this replaces was the operation id, which is
    # alphabetical and means nothing: the first atom added at the nurse whose
    # id sorts before "phc.op.vitals-record" became the headline advice at a
    # bench whose job is to take a reading. kernel/state.actions already
    # ordered this way; this copy had not been brought along.
    seat = {}
    for wf in (catalogue.get("workflows") or {}).values():
        for step in wf.get("steps") or ():
            for i, op_id in enumerate(step.get("operations") or ()):
                seat.setdefault(op_id, i)
    here = station(flags)
    picked = [
        op for op in catalogue["operations"].values()
        if visible(op, caps, flags)
        and (station_filter is None or op["station"] == station_filter)
    ]
    picked.sort(key=lambda op: (op["station"] != here, order.get(op["station"], 99),
                                seat.get(op["id"], 99), op["id"]))
    return picked
