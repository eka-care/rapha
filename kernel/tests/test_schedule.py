"""Run: python3 -m kernel.tests.test_schedule

What is owed on one pregnancy, derived rather than stored.

THE CASE THIS FILE EXISTS FOR is the last one, and everything above it is
scaffolding for being able to state it: a pregnancy that has ended owes
NOTHING, at every instant, for ever, with no cancellation step anywhere. A
woman who has just lost a baby must not be chased for her twenty eight week
visit, and the way to be sure of that is not to remember to cancel.

The second thing it catches is double counting. The windows in
bundles/phc/phc.sched.antenatal.md are drawn to touch, so there are days on
which two contacts could both accept the same visit. One visit is one
contact, and a woman who came once must never be recorded as having come
twice.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from adapters.local.store import SqliteStore
from kernel import declarations, schedule
from kernel.contracts import AuditRecord

BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
SCHED = BUNDLE.schedules["phc.sched.antenatal"]
ANC = "phc.op.antenatal-visit"
checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


LMP = date(2026, 1, 5)


def episode(**over):
    """An open pregnancy dated from a last menstrual period."""
    base = {"id": "ep-1", "type": "pregnancy", "status": "active",
            "opened_at": "2026-02-01T09:00:00+00:00", "ended_at": "",
            "outcome": "", "anchor_date": LMP.isoformat(),
            "anchor_basis": "last_menstrual_period", "encounters": []}
    base.update(over)
    return base


def noon(d):
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)


def store_with(visits):
    """A store whose audit says an antenatal visit committed on each date."""
    store = SqliteStore(":memory:")
    threads = []
    for n, when in enumerate(visits):
        thread = "e-%d" % n
        threads.append(thread)
        store.append_audit(AuditRecord(
            id="aud-%d" % n, thread=thread, operation=ANC, actor="user:cho",
            surface="rendered", payload={}, outcome="committed",
            at=noon(when).strftime("%Y-%m-%dT%H:%M:%SZ"), proposal=None))
    return store, threads


# -- day zero, and what a dating basis means -------------------------------

assert schedule.start_of(SCHED, episode()) == LMP
ok("a pregnancy dated from a last period starts on that date")

# A scan reports an estimated delivery date, which is day 280 of the same
# convention, so the arc began 280 days before it. An implementation that
# treated every date the same would put this woman nine months out.
scan = episode(anchor_date="2026-10-12", anchor_basis="dating_scan")
assert schedule.start_of(SCHED, scan) == date(2026, 10, 12) - timedelta(days=280)
ok("a pregnancy dated from a scan's delivery date starts 280 days before it")

unknown = episode(anchor_basis="asked_her_neighbour")
assert schedule.start_of(SCHED, unknown) is None
assert schedule.contacts(BUNDLE, SqliteStore(":memory:"), WF, unknown) == []
assert "does not know" in schedule.why(BUNDLE, SqliteStore(":memory:"), WF, unknown)
ok("a basis nobody declared is refused rather than assumed to mean zero")

undated = episode(anchor_date="")
assert schedule.contacts(BUNDLE, SqliteStore(":memory:"), WF, undated) == []
assert "dated" in schedule.why(BUNDLE, SqliteStore(":memory:"), WF, undated)
ok("an undated pregnancy owes nothing, and says which kind of nothing it is")


# -- the states move with the clock and with nothing else ------------------

empty = SqliteStore(":memory:")
anc1 = next(c for c in SCHED.contacts if c.id == "anc1")

def state_on(day, store=empty, ep=None):
    rows = schedule.contacts(BUNDLE, store, WF, ep or episode(), at=noon(day))
    return {r["contact"]: r["state"] for r in rows}


before = state_on(LMP + timedelta(days=anc1.closes + 1))
assert before["anc1"] == schedule.MISSED, before
assert before["anc4"] == schedule.UPCOMING, before
ok("the same pregnancy has a missed contact and an upcoming one on the same day")

on_time = state_on(LMP + timedelta(days=anc1.due))
assert on_time["anc1"] == schedule.DUE
ok("a contact on the day it is aimed at is due, not late")

# THE WINDOW IS THE POINT. A visit due at 28 weeks is not late at 28 weeks
# and one day, and an implementation comparing against `due` alone would
# fail here while passing everything above.
assert state_on(LMP + timedelta(days=anc1.due + 1))["anc1"] == schedule.DUE
assert state_on(LMP + timedelta(days=anc1.closes))["anc1"] == schedule.DUE
assert state_on(LMP + timedelta(days=anc1.closes + 1))["anc1"] == schedule.MISSED
ok("a day after the day it was aimed at is still on time; a day after the window is not")


# -- a missed contact changes hands ---------------------------------------

missed = [r for r in schedule.contacts(BUNDLE, empty, WF, episode(),
                                       at=noon(LMP + timedelta(days=anc1.closes + 1)))
          if r["contact"] == "anc1"][0]
assert missed["owner"] == anc1.escalates_to, missed["owner"]
assert [r for r in schedule.contacts(BUNDLE, empty, WF, episode(),
                                     at=noon(LMP + timedelta(days=anc1.due)))
        if r["contact"] == "anc1"][0]["owner"] == anc1.owner
ok("a contact that is merely due belongs to its owner; a missed one belongs to the escalation")


# -- one visit closes one contact -----------------------------------------

anc2 = next(c for c in SCHED.contacts if c.id == "anc2")
# anc1 closes at day 90 and anc2 opens at day 98, so day 95 is in neither.
# Pick a day inside anc2 and check anc1 is NOT also discharged by it.
day = LMP + timedelta(days=anc2.due)
store, threads = store_with([day])
one = schedule.contacts(BUNDLE, store, WF, episode(encounters=threads),
                        at=noon(day + timedelta(days=1)))
done = [r["contact"] for r in one if r["state"] == schedule.DONE]
assert done == ["anc2"], "one visit closed %r" % done
ok("one visit closes one contact, and never the one before it as well")

two = LMP + timedelta(days=anc1.due)
store, threads = store_with([two, day])
both = schedule.contacts(BUNDLE, store, WF, episode(encounters=threads),
                         at=noon(day + timedelta(days=1)))
assert sorted(r["contact"] for r in both if r["state"] == schedule.DONE) == ["anc1", "anc2"]
ok("two visits in two windows close two contacts, so coming twice counts twice")


# -- recorded late, which is the common case ------------------------------

# She was seen elsewhere and brings the card back at thirty weeks. The visit
# must not quietly discharge the twelve week contact nobody attended.
anc3 = next(c for c in SCHED.contacts if c.id == "anc3")
late = LMP + timedelta(days=anc3.due)
store, threads = store_with([late])
rows = schedule.contacts(BUNDLE, store, WF, episode(encounters=threads),
                         at=noon(late + timedelta(days=1)))
by_id = {r["contact"]: r for r in rows}
assert by_id["anc3"]["state"] == schedule.DONE, by_id["anc3"]
assert by_id["anc1"]["state"] == schedule.MISSED, by_id["anc1"]
assert by_id["anc2"]["state"] == schedule.MISSED, by_id["anc2"]
ok("a visit recorded late closes the contact it was for, and the missed ones stay missed")


# -- the date is corrected, and the whole arc moves ------------------------
#
# Nothing was written down when the pregnancy opened, so there is nothing to
# reconcile: the same episode with a different anchor is a different arc.

moved = episode(anchor_date=(LMP + timedelta(days=21)).isoformat())
first = schedule.contacts(BUNDLE, empty, WF, episode())[0]
after = schedule.contacts(BUNDLE, empty, WF, moved)[0]
assert date.fromisoformat(after["due"]) - date.fromisoformat(first["due"]) == timedelta(days=21)
ok("correcting the date moves the whole arc, with nothing to regenerate")


# -- AND THE ONE THAT MATTERS ---------------------------------------------
#
# A pregnancy that has ended owes nothing. Not "owes things marked
# cancelled" -- nothing, at every instant, with no cancellation step
# anywhere that somebody could forget to call.

ended = episode(status="ended", outcome="miscarriage",
                ended_at="2026-04-01T09:00:00+00:00")
for day in (LMP, LMP + timedelta(days=90), LMP + timedelta(days=200),
            LMP + timedelta(days=400)):
    assert schedule.contacts(BUNDLE, empty, WF, ended, at=noon(day)) == [], day
ok("a pregnancy that has ended owes nothing, on every day anybody could ask")

store, threads = store_with([LMP + timedelta(days=anc1.due)])
assert schedule.contacts(BUNDLE, store, WF,
                         dict(ended, encounters=threads)) == []
ok("and that holds even where visits happened, so no history resurrects a schedule")

assert schedule.why(BUNDLE, empty, WF, ended) == "this is over"
assert schedule.why(BUNDLE, empty, WF, episode()) == ""
ok("a screen can say which nothing it is looking at")

# -- a referral is an episode too, measured from when it was raised -------
#
# The whole of the referral feature is this: no second mechanism, no second
# kind of row, and no second idea of what "owed" means.

REFERRAL = BUNDLE.schedules["phc.sched.referral"]
confirm = REFERRAL.contacts[0]

raised = date(2026, 10, 1)
open_referral = {"id": "ep-r", "type": "referral", "status": "active",
                 "opened_at": raised.isoformat() + "T09:00:00+00:00",
                 "ended_at": "", "outcome": "", "anchor_date": "",
                 "anchor_basis": "raised", "encounters": []}

assert schedule.start_of(REFERRAL, open_referral) == raised
ok("a referral is measured from the moment it was raised, not from a date anybody typed")

rows = schedule.contacts(BUNDLE, empty, WF, open_referral,
                         at=noon(raised + timedelta(days=confirm.due)))
assert len(rows) == 1 and rows[0]["state"] == schedule.DUE, rows
ok("so raising one owes somebody an answer about it, without a second mechanism")

# The day after the window shuts it belongs to the escalation, and the day
# it is closed it belongs to nobody.
late = schedule.contacts(BUNDLE, empty, WF, open_referral,
                         at=noon(raised + timedelta(days=confirm.closes + 1)))
assert late[0]["state"] == schedule.MISSED and late[0]["owner"] == confirm.escalates_to
ok("a referral nobody chased changes hands, exactly as a missed contact does")

closed = dict(open_referral, status="ended", outcome="attended")
assert schedule.contacts(BUNDLE, empty, WF, closed) == []
ok("and closing the referral stops the chase, because the chase was derived from it")

# An undated PREGNANCY still says so: `anchor_from` is per schedule and a
# referral's answer must not have changed the other one's.
assert "dated" in schedule.why(BUNDLE, empty, WF, episode(anchor_date=""))
ok("the pregnancy schedule still wants a date, so anchor_from is per schedule")

print("\nok   the schedule: %d checks" % checks)
