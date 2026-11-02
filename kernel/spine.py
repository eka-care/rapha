"""One subject, every visit it has had.

A thread is one encounter. That is the right unit for a guard -- a
precondition is about this visit, not about a life -- but it is the wrong
unit for a person, who arrives more than once and whose second visit is only
meaningful beside the first.

What joins two encounters is not something this module may know. `patient` is
the health centre's word; a laboratory's continuing subject is its own. So the
workflow declares it:

    subject: encounter     # what a thread is about
    spine:   patient       # the field on that resource naming what continues

A workflow that declares no spine has no continuing subject, and the route
that reads this answers 404 rather than guessing one. That is the honest
answer for a bundle whose threads genuinely do not join up.

No Store method was added for this. `select` already takes `thread=None`, and
the subject resource already carries the spine field, so both reads below are
ordinary selects. The Store protocol stays at its nine methods.
"""
from __future__ import annotations

from catalogue import vocab

from kernel import state


def declared(workflow) -> str | None:
    """The spine resource for this workflow, or None if it declares none."""
    return getattr(workflow, "spine", None)


def of(bundle, store, workflow, subject_id, *, limit=200):
    """The subject row, and every thread that shares it, newest first.

    Returns None when the workflow declares no spine or the subject does not
    exist. The caller turns that into a 404; inventing an empty subject here
    would let a typo render as a person with no visits.
    """
    link = declared(workflow)
    if not link:
        return None

    rows = store.select(link, thread=None, where={"id": subject_id},
                        fields=(), limit=1)
    if not rows:
        return None
    subject = dict(rows[0])

    # ponytail: one select for the encounters, then one flags derivation per
    # encounter. That is N+1 reads for N visits, which is right for a person
    # with a handful and wrong for a cohort screen. The fix when it matters is
    # a store method that returns flags for many threads at once, not a cache.
    encounters = store.select(workflow.subject, thread=None,
                              where={link: subject_id}, fields=(), limit=limit)
    visits = []
    for row in encounters:
        thread = row["id"]
        known = state.flags(store, thread, workflow)
        visits.append({
            "thread": thread,
            "opened_at": row.get("created_date") or "",
            "status": row.get("status") or "",
            "token": row.get("token") or "",
            "flags": sorted(known),
            "station": state.station(workflow, known),
            # §26: a timeline entry needs to say what the visit was, not only
            # when it was. The operations that actually committed are the
            # bundle's own words for that, and they are already on the audit.
            "did": _did(store, thread, bundle),
        })
    visits.sort(key=lambda v: v["opened_at"], reverse=True)
    return {"subject": subject, "spine": link, "encounters": visits}


def _did(store, thread, bundle):
    """The distinct operations this visit committed, in the order they landed,
    titled by their own declarations."""
    out, seen = [], set()
    for record in store.audit(thread):
        outcome = getattr(record, "outcome", "") or ""
        if not outcome.startswith(vocab.WROTE):
            continue
        op_id = getattr(record, "operation", "")
        if op_id in seen:
            continue
        seen.add(op_id)
        declaration = bundle.operations.get(op_id)
        out.append({"operation": op_id,
                    "title": declaration.get("title") if isinstance(declaration, dict)
                             else getattr(declaration, "title", op_id) or op_id})
    return out
