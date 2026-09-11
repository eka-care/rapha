"""Thread state, declared instead of coded.

This is care_phc/thread.py with the rules taken out of the module and put in
the workflow declaration. derive() becomes states(): the same flags, computed
from the same records, but by walking Workflow.states over Store.count rather
than by reading a hard coded Snapshot. station() and actions() keep their
behaviour exactly; only where the line comes from has changed.

Pure in the sense that matters: everything here takes a Store and returns
values. The tests run against a dict backed fake, no database and no network.
"""
from __future__ import annotations

from typing import Optional

from catalogue import vocab
from catalogue.guard import visible
from kernel import contracts as c


def count(store, thread, query):
    return store.count(query["resource"], thread=thread,
                       where=dict(query.get("where") or {}))


def _true(store, thread, rule, known, stored, flag):
    (form, arg), = rule.items()
    if form == "stored":
        return flag in stored
    if form == "exists":
        return count(store, thread, arg) > 0
    if form == "gte":
        a, b = (count(store, thread, q) for q in arg)
        # Partial dispense is a normal outcome, so this is a comparison and
        # not a boolean, and an empty denominator is never "complete".
        return b > 0 and a >= b
    if form == "all_of":
        for item in arg:
            if isinstance(item, str):
                if item.startswith("not "):
                    if item[4:] in known:
                        return False
                elif item not in known:
                    return False
            elif not _true(store, thread, item, known, stored, flag):
                return False
        return True
    raise ValueError(f"unknown state rule form '{form}'")


def flags(store, thread, workflow):
    """The flags true for this thread right now, in declaration order.

    A stored flag the workflow does not declare stored is dropped, the way
    derive() drops one today: a stored copy of a derived fact desyncs, and a
    desynced copy shows a pharmacist a Dispense button that should not exist.
    """
    stored = frozenset(store.stored_flags(thread)) & frozenset(workflow.stored)
    known = set()
    for flag, rule in workflow.states.items():
        if _true(store, thread, rule, known, stored, flag):
            known.add(flag)
    return known


# Outcomes on an audit line that mean "this actor performed this operation on
# this thread". A proposal is a request and not a performance; a denial is the
# opposite of one.
PERFORMED = ("allowed", "confirmed")


def performers(store, thread):
    """{operation id: set of actors who have performed it on this thread}.

    Read from the audit trail, which is the only record that carries an actor
    per decision. The rows an operation wrote carry an author too (the
    {actor: id} mapping source fills created_by), but a row is per resource and
    a separation of duties rule is per operation, so the audit is the honest
    source: it is written for denials and proposals as well, and this filters
    to the two outcomes that mean the work was actually done.
    """
    out = {}
    for record in store.audit(thread):
        if record.outcome in PERFORMED and record.actor:
            out.setdefault(record.operation, set()).add(record.actor)
    return out


def station(workflow, known) -> Optional[str]:
    """Where this thread is. None once the line is complete.

    A step whose applies_when is false is skipped, not pending: a patient
    nobody ordered a test for is not waiting at the lab.
    """
    for step in workflow.steps:
        if step.applies_when and step.applies_when not in known:
            continue
        if step.done_when not in known:
            return step.station
    return None


def line(workflow, known):
    """The workflow's steps as StepStatus, for the renderer to draw."""
    here = station(workflow, known)
    out, current_taken = [], False
    for step in workflow.steps:
        if step.applies_when and step.applies_when not in known:
            status = "skipped"
        elif step.done_when in known:
            status = "done"
        elif not current_taken and step.station == here:
            status, current_taken = "now", True
        else:
            status = "pending"
        out.append(c.StepStatus(station=step.station, label=step.done_when, status=status))
    return out


def drawn_by(workflow, op_id):
    """Does any step of this workflow put this operation on a thread?

    catalogue/ops is shared between bundles, and a manifest may list an atom no
    step draws. phc.op.household-visit is one: it stands at `community`, which
    the outpatient line has no station for. Nothing stopped it, so once the
    demo account held visit.household it appeared as a button on every clinic
    encounter and wrote a household questionnaire onto it. A thread belongs to
    a workflow, so an operation that workflow never draws has no place on that
    thread, from any surface. kernel/proposals._decide refuses the write with
    the same predicate.
    """
    return any(op_id in (step.operations or []) for step in workflow.steps)


def actions(workflow, operations, known, caps, station_filter=None,
            actor=None, performed=None):
    """Quick actions to draw, ordered. Addendum SSD.2: a table, not a model.

    Ordering is by the declared line, so the next thing to do at this
    thread's current station sorts first.

    `actor` and `performed` (from performers() above) are what make an
    `actor of` precondition invisible rather than refused on tap. Without
    them such an action is still drawn and the guard refuses it: see
    catalogue/guard.visible.
    """
    order = {step.station: i for i, step in enumerate(workflow.steps)}
    here = station(workflow, known)
    # Only what this workflow's steps actually draw. A manifest may list an
    # atom from catalogue/ops that no station of this line has a place for;
    # kernel/proposals refuses to write it with the same predicate, so it must
    # not be a button either.
    picked = [op for op in operations.values()
              if drawn_by(workflow, op["id"])
              and visible(op, caps, known, actor, performed)
              and (station_filter is None or op["station"] == station_filter)]
    picked.sort(key=lambda op: (op["station"] != here, order.get(op["station"], 99), op["id"]))
    return picked


def thread_view(store, ref, workflow, operations, *, caps, nudge="", actor=None):
    """contracts.ThreadView for one thread. One read pass, no writes.

    Pass `actor` and an action whose precondition names an actor is absent for
    the person it excludes. api/main.py passes `caller(request)["id"]`. Without
    one such an action is still drawn and the guard refuses the tap with the
    reason, which is the fail-safe, not the intended shape.
    """
    known = flags(store, ref.id, workflow)
    return c.ThreadView(
        id=ref.id, workflow=workflow.id, subject=dict(ref.subject),
        flags=sorted(known), station=station(workflow, known),
        line=line(workflow, known),
        actions=actions(workflow, operations, known, caps, actor=actor,
                        performed=performers(store, ref.id) if actor else None),
        proposals=store.proposals(ref.id, status="pending"),
        audit=store.audit(ref.id),
        capabilities=sorted(vocab.CAPABILITIES), held=sorted(caps), nudge=nudge)
