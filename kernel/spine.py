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

from kernel import schedule as sched
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
    return {"subject": subject, "spine": link, "encounters": visits,
            "episodes": episodes(bundle, store, workflow, subject_id, visits)}


def episodes(bundle, store, workflow, subject_id, visits, *, at=None):
    """This subject's episodes, newest first, each holding its own visits.

    THE LEVEL BETWEEN A PERSON AND A VISIT. A flat list of visits cannot say
    which of them belong to one pregnancy, cannot carry the date that
    pregnancy is measured from, and cannot END, so nothing derived from it
    can ever stop. A workflow that declares no `episode` gets an empty list
    and nothing else changes.

    AN EPISODE ENDS BY GAINING A ROW rather than by having its first one
    rewritten, because every clinical table here is insert only. So the rows
    come back in pairs: one `active`, and one `ended` carrying the outcome if
    it has ended. They are paired in date order, which is the only pairing
    available and is correct as long as a subject has one episode of a type
    open at a time -- which the preconditions on the operations that write
    them enforce.

    WHICH VISITS BELONG TO AN EPISODE IS DERIVED FROM THE DATES, not stored
    on the encounter. An encounter column saying which episode a visit
    belonged to would have to be written at the moment the visit opened,
    which is before anybody knows, and a column nothing writes is a column
    that lies: `token_booking` has been in this kernel unwritten since the
    beginning and `followup.booked` is still derived from it. A visit that
    happened between an episode's opening and its ending happened during it,
    which is what EpisodeOfCare.period means in the standard too.
    """
    kind = getattr(workflow, "episode", None)
    if not kind:
        return []

    rows = [dict(r) for r in store.select(kind, thread=None,
                                          where={"patient": subject_id},
                                          fields=(), limit=200)]
    rows.sort(key=lambda r: r.get("created_date") or "")

    out, open_of_type = [], {}
    for row in rows:
        of = row.get("type") or ""
        if row.get("status") == "ended":
            started = open_of_type.pop(of, None)
            if started is not None:
                started["ended_at"] = row.get("created_date") or ""
                started["outcome"] = row.get("outcome") or ""
                started["status"] = "ended"
            continue
        episode = {
            "id": row.get("id") or "",
            "type": of,
            "status": "active",
            "opened_at": row.get("created_date") or "",
            "ended_at": "",
            "outcome": "",
            "anchor_date": row.get("anchor_date") or "",
            "anchor_basis": row.get("anchor_basis") or "",
        }
        out.append(episode)
        open_of_type[of] = episode

    for episode in out:
        episode["encounters"] = [
            v["thread"] for v in visits
            if v["opened_at"] >= episode["opened_at"]
            and (not episode["ended_at"] or v["opened_at"] <= episode["ended_at"])]
    # WHAT EACH ONE OWES. Derived here rather than by the caller, so every
    # reader of a person's record gets the arc and not just the list, and so
    # the two engines compose it the same way. kernel/schedule.py is where
    # the rule lives and why nothing is stored.
    for episode in out:
        episode["contacts"] = sched.contacts(bundle, store, workflow, episode, at=at)
        episode["nothing_due"] = sched.why(bundle, store, workflow, episode)

    out.sort(key=lambda e: e["opened_at"], reverse=True)
    return out


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
