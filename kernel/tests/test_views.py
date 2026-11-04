"""Run: python3 -m kernel.tests.test_views

The calendar view: one day as rows, that day's month as counts. What this file
guards is that the two agree: a missed visit is owed every day after its window
shuts, so it must be in the day's rows and in the month's counts alike.
"""
from __future__ import annotations

from datetime import date, timedelta

from kernel import views
from kernel.tests.test_cohort import BUNDLE, LMP, centre, contact, day, episode_row, noon

VIEW = "phc.view.calendar"
OPENED = "2026-02-01T09:00:00+00:00"


def pregnant():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", OPENED)
    return store


def ask(store, on, *, at=None):
    return views.resolve(BUNDLE, VIEW, store, on=on, at=noon(at or date.fromisoformat(on)))


def test_a_calendar_answers_the_day_as_rows_and_the_month_as_groups():
    anc1 = day(contact("anc1").due)
    result = ask(pregnant(), anc1.isoformat())
    assert result.kind == "calendar"
    assert [r["contact"] for r in result.rows] == ["anc1"], result.rows
    assert result.rows[0]["subject_row"]["name"] == "Amina Sheikh"
    month = {g["key"]: g["count"] for g in result.groups}
    assert month[anc1.isoformat()] == 1


def test_the_month_groups_cover_that_date_s_own_month_only():
    result = ask(pregnant(), "2026-10-31")
    keys = [g["key"] for g in result.groups]
    assert keys == ["2026-10-%02d" % n for n in range(1, 32)], keys


def test_a_day_whose_episodes_have_all_ended_answers_no_rows():
    store = pregnant()
    episode_row(store, "ep-2", "p-amina", "pregnancy", "ended", "2026-03-01T09:00:00+00:00",
                anchor=None, basis=None, outcome="miscarriage")
    anc1 = day(contact("anc1").due)
    result = ask(store, anc1.isoformat())
    assert result.rows == [] and all(g["count"] == 0 for g in result.groups)


def test_a_bad_on_date_is_a_400_and_not_a_silent_today():
    try:
        views.resolve(BUNDLE, VIEW, pregnant(), on="31st October")
    except ValueError:
        return
    raise AssertionError("an unparseable date was accepted")


def test_a_missed_contact_is_on_every_day_after_its_window_shuts():
    anc1 = contact("anc1")
    today = day(anc1.due + 30)
    result = ask(pregnant(), today.isoformat())
    assert "anc1" in [r["contact"] for r in result.rows], result.rows
    month = {g["key"]: g["count"] for g in result.groups}
    assert month[today.isoformat()] == len(result.rows)
    # Before the window shuts it is not yet overdue, so an earlier day omits it.
    earlier = ask(pregnant(), day(anc1.opens - 1).isoformat(), at=today)
    assert "anc1" not in [r["contact"] for r in earlier.rows]


def test_the_groups_total_equals_the_sum_of_every_day_s_rows():
    store = pregnant()
    at = day(contact("anc1").due + 30)
    first = at.replace(day=1)
    n = (date(at.year + (at.month == 12), at.month % 12 + 1, 1) - first).days
    total = 0
    for i in range(n):
        d = first + timedelta(days=i)
        total += len(views.resolve(BUNDLE, VIEW, store, on=d.isoformat(), at=noon(at)).rows)
    month = views.resolve(BUNDLE, VIEW, store, on=at.isoformat(), at=noon(at)).groups
    assert sum(g["count"] for g in month) == total > 0, (sum(g["count"] for g in month), total)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok   %s" % fn.__name__)
    print("\n%d checks passed" % len(fns))
