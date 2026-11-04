"""What a centre owes between two dates, across every open episode.

THIS IS `kernel/spine.py`'s EPISODE PAIRING WIDENED FROM ONE SUBJECT TO ALL
OF THEM. `schedule.contacts()` answers for one episode; a facility wants one
day's work. The episode rows are read directly rather than found through
recent visits, because the woman this screen exists to surface is the one
nobody has seen for months, and she has no recent visit to be found by.

NOTHING HERE IS STORED. No table, no cache, no queue. Every call re-derives
the answer from the episode rows and the audit, through
`schedule.contacts()`, which returns nothing for an episode that has ended.
So there is nothing to cancel when a pregnancy ends badly, and a woman whose
pregnancy has ended cannot appear here on any day, past or future. This
module reimplements none of the date or state logic; it only asks.

WHAT THIS COSTS. One audit read per visit of each open episode, on top of
one read per episode type and a few per patient. That is right for a centre
and wrong for a district. The fix when it bites is a store method that
answers for many threads at once -- a bulk read -- and never a stored
contact, because a stored contact is what has to be cancelled.

Pure: takes a Store and returns values. No clinical word appears here;
`pregnancy` and `postnatal` arrive as data in `types`.
"""
from __future__ import annotations

from datetime import date, timedelta

from kernel import schedule, spine

#: A centre's episodes of one type, more than any one centre holds.
_ALL = 100000


def owed(bundle, store, workflow, *, types, since, until, at=None):
    """Every contact due to any open episode of these types, in the window.

    A contact is listed when its `[opens, closes]` intersects
    `[since, until]`, or when it is `missed`, which stays owed after its
    window shuts. Each entry is a `schedule.contacts()` entry plus `subject`,
    `subject_row` and `on`, the ISO dates inside the window it covers (empty
    for a missed contact whose window lies wholly outside it). Sorted by
    `due`, then `subject`.
    """
    link = spine.declared(workflow)
    kind = getattr(workflow, "episode", None)
    if not link or not kind:
        return []

    rows = []
    for of in types:
        rows.extend(dict(r) for r in store.select(kind, thread=None, where={"type": of},
                                                  fields=(), limit=_ALL))
    by_patient = {}
    for row in rows:
        by_patient.setdefault(row.get("patient") or "", []).append(row)

    out = []
    for patient, theirs in by_patient.items():
        # The sort `spine.episodes()` uses, for the reason given there: an
        # opening beats an ending at an equal timestamp.
        theirs.sort(key=lambda r: ((r.get("created_date") or ""),
                                   1 if r.get("status") == "ended" else 0))
        open_of_type = {}
        for row in theirs:
            of = row.get("type") or ""
            if row.get("status") == "ended":
                open_of_type.pop(of, None)
                continue
            open_of_type[of] = row
        if not open_of_type:
            continue

        subject = store.select(link, thread=None, where={"id": patient}, fields=(), limit=1)
        subject_row = dict(subject[0]) if subject else {}
        visits = [dict(r) for r in store.select(workflow.subject, thread=None,
                                                where={link: patient}, fields=(),
                                                limit=_ALL)]
        for row in open_of_type.values():
            opened = row.get("created_date") or ""
            episode = {
                "id": row.get("id") or "", "type": row.get("type") or "",
                "status": "active", "opened_at": opened, "ended_at": "", "outcome": "",
                "anchor_date": row.get("anchor_date") or "",
                "anchor_basis": row.get("anchor_basis") or "",
                "encounters": [v["id"] for v in visits
                               if (v.get("created_date") or "") >= opened],
            }
            for entry in schedule.contacts(bundle, store, workflow, episode, at=at):
                on = _days(entry, since, until)
                if not on and entry["state"] != schedule.MISSED:
                    continue
                out.append(dict(entry, subject=patient, subject_row=subject_row, on=on))

    out.sort(key=lambda e: (e["due"], e["subject"]))
    return out


def _days(entry, since, until):
    """The ISO dates in `[since, until]` that this contact's window covers."""
    first = max(date.fromisoformat(entry["opens"]), since)
    last = min(date.fromisoformat(entry["closes"]), until)
    return [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]
