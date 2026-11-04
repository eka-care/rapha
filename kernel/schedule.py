"""What is owed on one episode, and whether it has been done.

NOTHING HERE IS STORED, AND THAT IS THE SAFETY PROPERTY. A contact is
computed, every time somebody asks, from three things: the schedule
declaration, the episode's own anchor date, and what the audit says was
committed. No row is generated when a pregnancy opens and no row is
cancelled when it ends.

The alternative -- generating a set of rows up front -- is what most
trackers do and it has one failure mode that this product cannot survive. A
generated schedule has to be CANCELLED when the pregnancy ends, which means
somebody has to remember to cancel it, in every path that could end one,
including the ones added later. Miss one and a woman who has just lost a
baby gets the call asking why she missed her twenty eight week visit. That
is not a bug report. Deriving makes it impossible rather than unlikely:
`contacts()` returns nothing for an episode that has ended, because the
thing that produced the chasing has stopped, and there is no queue to
drain, no rows to cancel and no outbox holding something queued a minute
ago.

It also makes the hard case in the design note dissolve. An estimated
delivery date corrected at fourteen weeks moves the whole arc, with no
regeneration, no reconciliation and no orphan rows, because nothing was
ever written down.

WHAT THIS COSTS. One audit read per visit in the episode, so N+1 for N
visits. That is right for a woman with a handful of contacts and wrong for
a district's cohort screen. The fix when it matters is a store method that
answers for many threads at once, not a cache. `kernel/spine.py` already
carries the same note about the same shape.

Pure: takes a Store and returns values. No clinical word appears here --
`pregnancy` is the bundle's word for an episode type and reaches this
module as data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from catalogue import vocab

#: A contact that has not been done and whose window has not opened.
UPCOMING = "upcoming"
#: The window is open and nothing has closed it.
DUE = "due"
#: Something closed it, inside the window or after it.
DONE = "done"
#: The window shut with nothing against it.
MISSED = "missed"


def _day(text):
    """A stored date, as a date. Both `YYYY-MM-DD` and a full timestamp are
    accepted because the first is what a date question answers and the
    second is what `created_date` holds."""
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def for_episode(bundle, workflow, episode):
    """The schedule that applies to this episode, or None.

    Matched on the episode's TYPE, which is the bundle's own word. A bundle
    with two schedules for one type is a declaration problem and the first
    one wins here rather than this module choosing a policy.
    """
    if not episode:
        return None
    for schedule in (getattr(bundle, "schedules", None) or {}).values():
        if schedule.episode == (episode.get("type") or ""):
            return schedule
    return None


def start_of(schedule, episode):
    """Day zero of the arc: the date everything else is measured from.

    The episode records WHAT WAS OBSERVED -- a date and how it was arrived
    at -- and the schedule declares what each basis means in days. A
    pregnancy dated from a last menstrual period starts on that date; one
    dated from a scan's estimated delivery date started 280 days before it.
    Doing that subtraction here rather than at the point of recording is
    what lets a centre correct the convention without rewriting records.

    None when the episode carries no date, or carries a basis the schedule
    does not know. The second case is deliberately not a guess: a basis
    nobody declared is a basis nobody has agreed the meaning of, and
    assuming zero would silently date a pregnancy from a scan's delivery
    date as though it were a period.
    """
    basis = episode.get("anchor_basis") or ""
    if basis not in schedule.anchor:
        return None
    # WHERE THE DATE COMES FROM IS THE SCHEDULE'S TO SAY. A pregnancy is
    # measured from a date somebody recorded, because the event it is
    # measured from happened before the record of it. A referral is
    # measured from the moment it was raised, which IS the record, and
    # asking a clinician to type today's date on every referral is friction
    # that will be wrong a fair share of the time.
    if getattr(schedule, "anchor_from", "recorded") == "opened":
        anchored = _day(episode.get("opened_at"))
    else:
        anchored = _day(episode.get("anchor_date"))
    if anchored is None:
        return None
    return anchored + timedelta(days=int(schedule.anchor[basis]))


def contacts(bundle, store, workflow, episode, *, at=None):
    """Every contact this episode owes, with its dates and its state.

    Returns [] for an episode that has ended, for one with no schedule, and
    for one whose date nobody has recorded. All three are the same answer
    for the caller -- there is nothing to chase -- and the reasons differ,
    which is why `why()` exists beside this.
    """
    schedule = for_episode(bundle, workflow, episode)
    if schedule is None or episode.get("status") == "ended":
        return []
    start = start_of(schedule, episode)
    if start is None:
        return []

    today = (at or datetime.now(timezone.utc)).date()
    closed = _closures(bundle, store, workflow, episode, schedule, start)

    out = []
    for contact in schedule.contacts:
        opens = start + timedelta(days=contact.opens)
        due = start + timedelta(days=contact.due)
        shuts = start + timedelta(days=contact.closes)
        done = closed.get(contact.id)
        if done:
            state = DONE
        elif today < opens:
            state = UPCOMING
        elif today > shuts:
            state = MISSED
        else:
            state = DUE
        out.append({
            "contact": contact.id,
            "title": contact.title,
            "schedule": schedule.id,
            "episode": episode.get("id") or "",
            "opens": opens.isoformat(),
            "due": due.isoformat(),
            "closes": shuts.isoformat(),
            "state": state,
            # Who is answerable now. A missed contact is the escalation's,
            # which is the whole of what escalation means here: the row
            # changes hands rather than turning red at the same person.
            "owner": (contact.escalates_to or contact.owner) if state == MISSED
                     else contact.owner,
            "operation": contact.operation,
            "authority": contact.authority,
            "reports_as": contact.reports_as or "",
            "programme_title": contact.programme_title or "",
            "done_at": done or "",
            # How the date this is all measured from was arrived at, carried
            # on every contact so a screen can say it. A contact "due in
            # nine days" computed from a half remembered period is a false
            # precision, and a false precision teaches people to ignore the
            # tracker.
            "basis": episode.get("anchor_basis") or "",
        })
    return out


def why(bundle, store, workflow, episode):
    """Why an episode has no contacts, in words, or "" when it has some.

    An empty list is three different situations and a screen that cannot
    tell them apart says "nothing due" to a woman nobody has dated.
    """
    if not episode:
        return "there is no episode"
    if episode.get("status") == "ended":
        return "this is over"
    schedule = for_episode(bundle, workflow, episode)
    if schedule is None:
        return "nothing is scheduled for this kind of episode"
    source = ("opened_at" if getattr(schedule, "anchor_from", "recorded") == "opened"
              else "anchor_date")
    if _day(episode.get(source)) is None:
        return "nobody has dated this yet"
    if start_of(schedule, episode) is None:
        return "it is dated in a way this schedule does not know"
    return ""


def _closures(bundle, store, workflow, episode, schedule, start):
    """{contact id: when it was closed}, from the audit of this episode's
    visits.

    ONE VISIT CLOSES ONE CONTACT. A committed operation discharges the
    EARLIEST contact that is still open and whose window contains the day it
    was committed. Without that rule a single visit falling where two
    windows overlap would close both, and a woman who came once would be
    marked as having come twice, which is the direction of error this
    product must not make.

    A contact can be closed LATE, by a commit after its window shut. That is
    not a leniency, it is the common case: the Mother and Child Protection
    card is paper, is the household's, is frequently more complete than
    anything the centre holds, and a woman seen elsewhere brings it back
    with her. A tracker that can only record what happens in front of it is
    wrong about most women in this programme. A late commit closes the
    contact whose window it is nearest to having been in -- the latest one
    whose window has already opened -- so a visit recorded at thirty weeks
    does not quietly discharge the twelve week contact nobody attended.
    """
    by_operation = {}
    for contact in schedule.contacts:
        by_operation.setdefault(contact.operation, []).append(contact)

    events = []
    for thread in episode.get("encounters") or []:
        for record in store.audit(thread):
            outcome = getattr(record, "outcome", "") or ""
            if not outcome.startswith(vocab.WROTE):
                continue
            operation = getattr(record, "operation", "")
            if operation not in by_operation:
                continue
            when = _day(getattr(record, "at", ""))
            if when is not None:
                events.append((when, operation))
    events.sort()

    closed = {}
    for when, operation in events:
        inside = [c for c in by_operation[operation]
                  if c.id not in closed
                  and start + timedelta(days=c.opens) <= when <= start + timedelta(days=c.closes)]
        if inside:
            closed[min(inside, key=lambda c: c.due).id] = when.isoformat()
            continue
        # Late. The latest contact whose window has already opened and which
        # nothing has closed; see the docstring.
        opened = [c for c in by_operation[operation]
                  if c.id not in closed and start + timedelta(days=c.opens) <= when]
        if opened:
            closed[max(opened, key=lambda c: c.due).id] = when.isoformat()
    return closed
