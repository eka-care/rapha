"""The write path: propose, confirm, reject, commit. And the audit log.

There is one rule and this module is it. Nothing reaches Store.write without
a catalogue.guard.evaluate() that allowed it, and confirming a proposal is a
second guard pass on the rendered surface with the payload as it stands after
a person edited it. So a proposal is not a stored permission: it is a stored
request, re-judged at the moment it is accepted, against the thread state as
it is then. A proposal made when a precondition held is denied at confirm if
the precondition has since gone.

commit() hard codes the rendered surface rather than taking one, because a
surface argument is a hole: a caller that could pass RENDERED could pass it
from a machine. The MCP server has propose() and nothing else.

Every decision is audited, denials included. An audit line that only appears
when a write succeeded is a log of what worked, not of what was tried.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from catalogue import guard, validate
from kernel import contracts as c
from kernel import mapping, terminology
from kernel.state import drawn_by
from kernel.state import flags as thread_flags
from kernel.state import performers
from kernel.state import station


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@lru_cache(maxsize=None)
def _schema(questionnaire: str):
    return validate.load(questionnaire)


def validator(op):
    """The same validator every surface uses. Loaded from the questionnaire
    the operation names, so there is one definition of a valid payload.

    Two halves, composed here and nowhere else. The schema rules are the
    catalogue's (required, types, choices, the range rule) and the terminology
    rules are the kernel's (an answer is a code its value set holds, and a
    unit is the one its analyte is reported in). They are composed rather than
    merged because the catalogue layer may not import the kernel and the value
    sets are the kernel's, and composing them here keeps the property that
    matters: there is still exactly one validator per operation and every
    surface uses it.

    Both halves run, and the problems are concatenated, so a technician with a
    bad number and a bad unit is told about both at once rather than fixing
    one and discovering the other. That is CARE's all or nothing submission
    rule, which is the right one.
    """
    schema = _schema(op["input"])
    schema_rules = validate.make_validator(schema)

    def both(op, payload):
        return (schema_rules(op, payload)
                + terminology.answer_problems(schema, payload))

    return both


def raised(op, payload, workflow):
    """Stored flags this payload raises. A critical but in range value flags;
    an out of range value never gets this far, the validator blocks it."""
    return sorted(validate.flags(_schema(op["input"]), payload) & set(workflow.stored))


def _audit(store, decision_audit, *, thread, at, proposal=None):
    record = c.AuditRecord.from_guard(decision_audit, id=_id("aud"), thread=thread,
                                      at=at, proposal=proposal)
    store.append_audit(record)
    return record


# Public, because kernel/queues.py writes the queue's own audit rows and there
# must be exactly one builder of an audit record. A second one would be a
# second place for the id prefix, the field order and the guard's dict shape
# to drift, which is the whole reason this helper exists.
audit_row = _audit


def _decide(store, bundle, op, *, thread, payload, caps, surface, actor,
            confirmed=False, scopes=None, workflow=None, correcting=False):
    # Which plugins this facility runs is the bundle's own answer and never a
    # caller's argument: a surface that could pass one could widen it. It
    # changes no decision, only the sentence; see catalogue/guard.evaluate.
    withheld = dict(bundle.withheld or {})
    workflow = workflow or bundle.workflow()
    if not drawn_by(workflow, op["id"]):
        # Before the guard, because this is not a judgement about this thread's
        # state: the operation is not part of this line at all.
        # In the workflow's own words and the operation's own title: the ids
        # are on the audit line below, where an auditor can find them.
        return guard.Decision(False, "%s is not a step of %s: no station in this "
                                     "line draws it" % (op["title"], workflow.title),
                              audit={"operation": op["id"], "actor": actor,
                                     "surface": surface, "payload": dict(payload),
                                     "outcome": "denied: not in this workflow"})
    known = thread_flags(store, thread, workflow)
    if correcting:
        # A CORRECTION IS EVALUATED AS IF ITS OWN RECORD WERE NOT THERE, and
        # nothing less would work: `phc.op.vitals-record` declares
        # `not vitals.recorded`, so a nurse fixing a pulse she keyed as 85
        # and meant as 58 would be told the vitals are already recorded --
        # which is both true and useless. A precondition of that shape says
        # when a step may first be TAKEN; a correction is not taking it
        # again.
        #
        # Only the negative terms are lifted, and only this operation's own.
        # A positive precondition still has to hold: a correction to a
        # consultation on an unregistered patient is as impossible as the
        # consultation was. Nothing else about the guard changes -- the
        # capability, the scope, the separation of duties, the validator and
        # the irreversibility rule all run exactly as they do on a commit.
        known = frozenset(known) - {
            term[4:].strip() for term in (op.get("preconditions") or [])
            if isinstance(term, str) and term.startswith("not ")}
    return guard.evaluate(
        op, caps=caps, state=known, payload=payload,
        surface=surface, confirmed=confirmed, scopes=scopes, actor=actor,
        validate=validator(op), performers=performers(store, thread),
        withheld=withheld)


def _write(store, bundle, op, *, thread, payload, workflow, actor=None, reuse=None):
    """Guard steps 6 and 7: the CARE write, then the state emit.

    Which answer becomes which column is declared on the operation atom and
    compiled by kernel/mapping.py, so the store is handed rows and not the
    payload. Every adapter inherits the one mapping; none of them re-derives
    what a blood pressure is. What an adapter still owns is its own schema:
    how a row joins to the thread, and what its columns are called.

    One record in, one Store.write out. A payload fans out, so three vitals
    are three observation rows and two medicines are two medication_request
    rows, which is what dispensed.complete counts.

    `actor` is what the mapping's {actor: id} source reads, so every row a
    declaration writes carries its author. Rows used to land with created_by
    null, which made "who did this" a question only the audit could answer.
    """
    rows = mapping.records(op, payload, actor=actor)
    # WHICH OPERATION WROTE THIS ROW, stamped here because it is the kernel's
    # fact and not the mapping's: a declaration says what a blood pressure
    # is, not which form it arrived on. Without it a correction could not
    # find its own rows -- a consultation and a nurse's vitals both write
    # `observation` on one thread -- so kernel.proposals.amend reads it.
    # `reuse` is {resource: [ids]}, the rows a correction is replacing, taken
    # in order per resource. Keyed by resource and not by position, because
    # one payload fans out into several kinds at once and a flat list would
    # hand an observation's id to a condition row. Empty on a first commit,
    # which is an insert.
    spare = {res: list(ids) for res, ids in (reuse or {}).items()}
    ids = []
    for res, row in rows:
        row = dict(row, operation=op["id"])
        left = spare.get(res)
        if left:
            row["id"] = left.pop(0)
        ids.append(store.write(res, row, thread=thread))
    for flag in raised(op, payload, workflow):
        store.raise_flag(thread, flag)
    return ids


def propose(store, bundle, op_id, *, thread, payload, caps, actor,
            surface=guard.MCP, scopes=None, at=None):
    """Queue a write for a person to accept. Returns (Decision, Proposal|None).

    Used by the MCP surface and by an instrument that captured a draft. A
    denial writes an audit line and no proposal.
    """
    at = at or now()
    op, workflow = bundle.operations[op_id], bundle.workflow()
    decision = _decide(store, bundle, op, thread=thread, payload=payload, caps=caps,
                       surface=surface, actor=actor, scopes=scopes, workflow=workflow)
    if not decision:
        _audit(store, decision.audit, thread=thread, at=at)
        return decision, None

    proposal = c.Proposal(
        id=_id("prop"), thread=thread, operation=op_id, payload=dict(payload),
        proposed_by=actor, surface=surface, status="pending", created_at=at,
        flags_raised=raised(op, payload, workflow))
    store.put_proposal(proposal)
    _audit(store, decision.audit, thread=thread, at=at, proposal=proposal.id)
    return decision, proposal


def commit(store, bundle, op_id, *, thread, payload, caps, actor,
           confirmed=False, scopes=None, at=None):
    """A person, on the rendered surface, writing directly. The surface is not
    a parameter on purpose."""
    at = at or now()
    op, workflow = bundle.operations[op_id], bundle.workflow()
    decision = _decide(store, bundle, op, thread=thread, payload=payload, caps=caps,
                       surface=guard.RENDERED, actor=actor, confirmed=confirmed,
                       scopes=scopes, workflow=workflow)
    _audit(store, decision.audit, thread=thread, at=at)
    if decision:
        _write(store, bundle, op, thread=thread, payload=payload, workflow=workflow,
               actor=actor)
    return decision


def written_by(store, op, *, thread):
    """The rows this operation already wrote on this visit, {resource: [ids]}.

    Ordered by when each row was opened, so a correction replaces the first
    medicine with the first medicine. `operation` is the column the adapter
    stamps in `_write`; a row written before that column existed has none,
    and comes back in no list, which is why `amend` refuses rather than
    guessing which row a clinician meant.
    """
    found = {}
    for record in op.get("mapping") or []:
        res = record["resource"]
        if res in found:
            continue
        rows = store.select(res, thread=thread, where={"operation": op["id"]},
                            fields=["id", "created_date"], limit=200)
        found[res] = [r["id"] for r in
                      sorted(rows, key=lambda r: (r.get("created_date") or "", r.get("id") or ""))]
    return {res: ids for res, ids in found.items() if ids}


def amend(store, bundle, op_id, *, thread, payload, caps, actor,
          confirmed=False, scopes=None, at=None):
    """Correct what was already recorded, while the visit is still open.

    THE CASE THIS EXISTS FOR. A nurse keys a pulse of 85 and means 58. Until
    today the only answers were to record a second, contradictory reading or
    to leave the wrong one standing, and a clinician who cannot fix an
    obvious slip stops trusting the screen and keeps a paper copy -- which
    is the one outcome this product cannot survive.

    ONLY WHILE THE VISIT IS OPEN, and that is the whole of the rule. A
    workflow that has run out of stations is a visit that is over, its
    document may already have gone to ABDM, and a record changed after it
    was published is a different problem with a different answer: FHIR
    answers it with a new bundle that relatesTo the old one, which is
    written down in kernel/fhir.py and is not this. So this refuses, in
    those words, rather than quietly rewriting history.

    THE GUARD RUNS AGAIN, unchanged. A correction is a write: the same
    capability, the same preconditions, the same validation and the same
    audit line as the commit it replaces. Nothing here is a shortcut past
    the guard, and the trail keeps both payloads, so what was first recorded
    is still on the record.

    Returns the same Decision shape `commit` does.
    """
    at = at or now()
    op, workflow = bundle.operations[op_id], bundle.workflow()

    if station(workflow, thread_flags(store, thread, workflow)) is None:
        decision = guard.Decision(False, "this visit is over, so its records can no "
                                         "longer be edited here", {
            "operation": op_id, "actor": actor, "surface": guard.RENDERED,
            "payload": dict(payload), "outcome": "denied: the visit is over"})
        _audit(store, decision.audit, thread=thread, at=at)
        return decision

    reuse = written_by(store, op, thread=thread)
    if not reuse:
        decision = guard.Decision(False, "nothing recorded by this operation was "
                                         "found on this visit, so there is nothing "
                                         "to edit", {
            "operation": op_id, "actor": actor, "surface": guard.RENDERED,
            "payload": dict(payload), "outcome": "denied: nothing to edit"})
        _audit(store, decision.audit, thread=thread, at=at)
        return decision

    if op["irreversibility"] == "irreversible":
        decision = guard.Decision(False, "this cannot be edited: it was an "
                                         "irreversible action and it has already "
                                         "left this facility", {
            "operation": op_id, "actor": actor, "surface": guard.RENDERED,
            "payload": dict(payload), "outcome": "denied: irreversible"})
        _audit(store, decision.audit, thread=thread, at=at)
        return decision

    decision = _decide(store, bundle, op, thread=thread, payload=payload, caps=caps,
                       surface=guard.RENDERED, actor=actor, confirmed=confirmed,
                       scopes=scopes, workflow=workflow, correcting=True)
    if decision:
        decision.audit["outcome"] = "amended"
    _audit(store, decision.audit, thread=thread, at=at)
    if decision:
        _write(store, bundle, op, thread=thread, payload=payload, workflow=workflow,
               actor=actor, reuse=reuse)
    return decision


def confirm(store, bundle, proposal, *, caps, actor, payload=None,
            confirmed=False, scopes=None, at=None):
    """Accept a queued write. The second guard pass, on the rendered surface,
    with the payload as the person edited it. Returns (Decision, Proposal)."""
    at = at or now()
    payload = dict(proposal.payload if payload is None else payload)
    workflow = bundle.workflow()

    if proposal.operation not in bundle.operations:
        # A proposal outlived the bundle that queued it: one SQLite file opened
        # under PHC_BUNDLE=lab still holds the health centre's rows. Refuse it
        # like any other denial rather than raising KeyError on the tap, which
        # is what this did. Nothing was ever written either way; a 500 on a
        # confirm button is still the wrong answer.
        decision = guard.Decision(False, "that is not an action this facility "
                                         "offers",
                                  {"operation": proposal.operation, "actor": actor,
                                   "surface": guard.RENDERED, "payload": payload,
                                   "outcome": "denied: not in this bundle"})
        _audit(store, decision.audit, thread=proposal.thread, at=at, proposal=proposal.id)
        return decision, proposal
    op = bundle.operations[proposal.operation]

    if proposal.status != "pending":
        decision = guard.Decision(False, f"proposal is already {proposal.status}", {
            "operation": proposal.operation, "actor": actor, "surface": guard.RENDERED,
            "payload": payload, "outcome": f"denied: already {proposal.status}"})
        _audit(store, decision.audit, thread=proposal.thread, at=at, proposal=proposal.id)
        return decision, proposal

    decision = _decide(store, bundle, op, thread=proposal.thread, payload=payload,
                       caps=caps, surface=guard.RENDERED, actor=actor,
                       confirmed=confirmed, scopes=scopes, workflow=workflow)
    if not decision:
        _audit(store, decision.audit, thread=proposal.thread, at=at, proposal=proposal.id)
        return decision, proposal

    decision.audit["outcome"] = "confirmed"
    _audit(store, decision.audit, thread=proposal.thread, at=at, proposal=proposal.id)
    _write(store, bundle, op, thread=proposal.thread, payload=payload,
           workflow=workflow, actor=actor)
    decided = c.Proposal(**{**proposal.__dict__, "status": "confirmed",
                            "decided_by": actor, "decided_at": at,
                            "final_payload": payload,
                            "flags_raised": raised(op, payload, workflow)})
    store.put_proposal(decided)
    return decision, decided


def reject(store, proposal, *, actor, reason="", at=None):
    """Decline a queued write. Nothing is written; the request stays on the
    record, because what was refused is as interesting as what was done."""
    at = at or now()
    decided = c.Proposal(**{**proposal.__dict__, "status": "rejected",
                            "decided_by": actor, "decided_at": at})
    store.put_proposal(decided)
    _audit(store, {"operation": proposal.operation, "actor": actor,
                   "surface": guard.RENDERED, "payload": dict(proposal.payload),
                   "outcome": f"rejected: {reason}" if reason else "rejected"},
           thread=proposal.thread, at=at, proposal=proposal.id)
    return decided


def draft(instrument, op_id, values, confidence=None, transcript=None):
    """What an instrument hands the renderer. Never a write, never a proposal
    on its own. Empty values is the fail closed outcome: show the fallback."""
    return c.Draft(instrument=instrument.id, operation=op_id, values=dict(values or {}),
                   confidence=dict(confidence or {}), transcript=transcript)
