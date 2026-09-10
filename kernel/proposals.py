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
from kernel.state import flags as thread_flags


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@lru_cache(maxsize=None)
def _schema(questionnaire: str):
    return validate.load(questionnaire)


def validator(op):
    """The same validator every surface uses. Loaded from the questionnaire
    the operation names, so there is one definition of a valid payload."""
    return validate.make_validator(_schema(op["input"]))


def raised(op, payload, workflow):
    """Stored flags this payload raises. A critical but in range value flags;
    an out of range value never gets this far, the validator blocks it."""
    return sorted(validate.flags(_schema(op["input"]), payload) & set(workflow.stored))


def _audit(store, decision_audit, *, thread, at, proposal=None):
    record = c.AuditRecord.from_guard(decision_audit, id=_id("aud"), thread=thread,
                                      at=at, proposal=proposal)
    store.append_audit(record)
    return record


def _decide(store, bundle, op, *, thread, payload, caps, surface, actor,
            confirmed=False, scopes=None, workflow=None):
    workflow = workflow or bundle.workflow()
    return guard.evaluate(
        op, caps=caps, state=thread_flags(store, thread, workflow), payload=payload,
        surface=surface, confirmed=confirmed, scopes=scopes, actor=actor,
        validate=validator(op))


def _write(store, bundle, op, *, thread, payload, workflow):
    """Guard steps 6 and 7: the CARE write, then the state emit.

    Every resource in Operation.writes gets the payload as it stands. Mapping
    a questionnaire link_id onto a resource field is the adapter's knowledge
    and is not written in any declaration tonight; this is honest about that
    rather than pretending a mapping exists.
    """
    ids = [store.write(res, dict(payload), thread=thread) for res in op["writes"]]
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
        _write(store, bundle, op, thread=thread, payload=payload, workflow=workflow)
    return decision


def confirm(store, bundle, proposal, *, caps, actor, payload=None,
            confirmed=False, scopes=None, at=None):
    """Accept a queued write. The second guard pass, on the rendered surface,
    with the payload as the person edited it. Returns (Decision, Proposal)."""
    at = at or now()
    op, workflow = bundle.operations[proposal.operation], bundle.workflow()
    payload = dict(proposal.payload if payload is None else payload)

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
    _write(store, bundle, op, thread=proposal.thread, payload=payload, workflow=workflow)
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
