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
    # Only YYYY-MM-DD is a day: not a timestamp, not the compact form, not a
    # week date. The Go engine refuses the same list (care_phc_mcp/views).
    for bad in ("31st October", "2026-11-04T00:00:00", "20261104", "2026-W45-3", "2026-1-4", "",
                "2026-02-30", "2026-13-01", "0000-01-01", "2026-02-29"):
        try:
            views.resolve(BUNDLE, VIEW, pregnant(), on=bad)
        except ValueError:
            continue
        raise AssertionError("%r was accepted as a day" % bad)
    views.resolve(BUNDLE, VIEW, pregnant(), on="2024-02-29")      # a real leap day
    try:
        views.resolve(BUNDLE, VIEW, pregnant(), on="2026-02-30")
    except ValueError as e:
        assert str(e) == "on must be a real calendar day written YYYY-MM-DD, not '2026-02-30'", e


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


def span(store, since, until, *, at):
    return views.resolve(BUNDLE, VIEW, store, since=since, until=until, at=noon(at))


def test_a_range_answers_every_day_in_it_and_not_one_day_more():
    due = day(contact("anc1").due)
    result = span(pregnant(), (due - timedelta(days=3)).isoformat(),
                  (due + timedelta(days=3)).isoformat(), at=due)
    keys = [g["key"] for g in result.groups]
    assert keys == [(due + timedelta(days=n)).isoformat() for n in range(-3, 4)], keys
    assert [r["contact"] for r in result.rows] == ["anc1"], result.rows
    assert [g["count"] for g in result.groups] == [0, 0, 0, 1, 0, 0, 0]
    # One day either side is outside the range and so outside the answer.
    assert span(pregnant(), (due + timedelta(days=1)).isoformat(),
                (due + timedelta(days=3)).isoformat(), at=due).rows == []


def test_on_still_answers_exactly_what_it_did_before():
    due = day(contact("anc1").due)
    result = ask(pregnant(), due.isoformat())
    first = due.replace(day=1)
    assert [g["key"] for g in result.groups][0] == first.isoformat()
    assert len(result.groups) == (date(due.year + (due.month == 12), due.month % 12 + 1, 1) - first).days
    assert [r["contact"] for r in result.rows] == ["anc1"]


def test_a_range_crossing_a_year_boundary_is_whole():
    result = span(pregnant(), "2026-12-28", "2027-01-03", at=date(2026, 12, 28))
    keys = [g["key"] for g in result.groups]
    assert keys == ["2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
                    "2027-01-01", "2027-01-02", "2027-01-03"], keys


def test_a_window_covers_a_day_for_on_but_a_one_day_range_wants_the_due_date():
    anc2 = contact("anc2")
    inside = day(anc2.opens + 5).isoformat()           # in the window, not the due day
    on = ask(pregnant(), inside, at=day(anc2.opens))
    assert "anc2" in [r["contact"] for r in on.rows]
    one = span(pregnant(), inside, inside, at=day(anc2.opens))
    assert "anc2" not in [r["contact"] for r in one.rows], one.rows
    assert all("cell" not in r for r in on.rows)


def test_a_range_counts_each_day_by_the_rows_due_on_it():
    store = pregnant()
    anc2 = contact("anc2")
    result = span(store, day(anc2.opens).isoformat(), day(anc2.closes).isoformat(),
                  at=day(anc2.opens))
    # anc1 is missed by then and stays owed; anc2 is due inside the range.
    assert [r["contact"] for r in result.rows] == ["anc1", "anc2"], result.rows
    keys = [g["key"] for g in result.groups]
    assert all(r["cell"] in keys for r in result.rows), result.rows
    by_cell = {k: sum(1 for r in result.rows if r["cell"] == k) for k in keys}
    assert by_cell == {g["key"]: g["count"] for g in result.groups}
    counts = {g["key"]: g["count"] for g in result.groups if g["count"]}
    assert counts == {day(anc2.opens).isoformat(): 1, day(anc2.due).isoformat(): 1}, counts


def test_a_missed_contact_counts_once_on_its_due_day_or_on_today_or_nowhere():
    anc1 = contact("anc1")
    store = pregnant()
    today = day(anc1.due + 30)
    count = lambda r: {g["key"]: g["count"] for g in r.groups}
    # Due inside the range: on its due day, not on today.
    r = span(store, day(anc1.due - 2).isoformat(), day(anc1.due + 40).isoformat(), at=today)
    assert count(r)[day(anc1.due).isoformat()] == 1 and count(r)[today.isoformat()] == 0
    assert sum(count(r).values()) == 1
    assert [x["cell"] for x in r.rows] == [day(anc1.due).isoformat()]
    # Due before the range, today inside it: a marker on today.
    r = span(store, day(anc1.due + 10).isoformat(), day(anc1.due + 40).isoformat(), at=today)
    assert [x["contact"] for x in r.rows] == ["anc1"] and count(r)[today.isoformat()] == 1
    assert [x["cell"] for x in r.rows] == [today.isoformat()]
    assert sum(count(r).values()) == 1
    # Due before the range, today outside it: no row and no count.
    r = span(store, day(anc1.due + 50).isoformat(), day(anc1.due + 60).isoformat(), at=today)
    assert r.rows == [] and sum(count(r).values()) == 0, r.rows


def test_a_due_contact_past_its_due_day_lands_on_today_and_one_inside_stays_put():
    anc2 = contact("anc2")
    store = pregnant()
    today = day(anc2.due + 2)                      # state is still due: the window runs on
    assert today < day(anc2.closes)
    count = lambda r: {g["key"]: g["count"] for g in r.groups}
    # Due two days before the range, today the first day of it: a marker on today.
    r = span(store, today.isoformat(), (today + timedelta(days=365)).isoformat(), at=today)
    row = next(x for x in r.rows if x["contact"] == "anc2")
    assert row["state"] == "due" and row["cell"] == today.isoformat(), row
    assert count(r)[today.isoformat()] >= 1
    assert sum(count(r).values()) == len(r.rows), "a row was counted twice or not at all"
    assert [x["contact"] for x in r.rows].count("anc2") == 1
    # Due inside the range: on its own day, not on today.
    r = span(store, day(anc2.due - 3).isoformat(), day(anc2.due + 10).isoformat(), at=today)
    row = next(x for x in r.rows if x["contact"] == "anc2")
    assert row["cell"] == day(anc2.due).isoformat(), row
    assert sum(count(r).values()) == len(r.rows)
    # Due before the range and today outside it: no cell.
    r = span(store, (today + timedelta(days=5)).isoformat(),
             (today + timedelta(days=12)).isoformat(), at=today)
    assert "anc2" not in [x["contact"] for x in r.rows]


def refused(**kw):
    try:
        views.resolve(BUNDLE, VIEW, pregnant(), **kw)
    except ValueError as e:
        return str(e)
    raise AssertionError("%r was accepted" % (kw,))


def test_a_range_longer_than_the_cap_is_refused_with_400():
    assert views.resolve(BUNDLE, VIEW, pregnant(), since="2026-01-01", until="2027-02-04")
    said = refused(since="2026-01-01", until="2027-02-05")
    assert said == "a range may span at most 400 days", said


def test_an_inverted_range_is_refused():
    assert refused(since="2026-03-02", until="2026-03-01") == "from must not be after to"


def test_from_without_to_is_refused_rather_than_guessed():
    said = "from and to go together: give both or neither"
    assert refused(since="2026-03-01") == said
    assert refused(until="2026-03-01") == said
    assert "not be combined" in refused(on="2026-03-01", since="2026-03-01", until="2026-03-02")
    assert refused(since="soon", until="2026-03-02").startswith("from must be a real calendar day")


def test_a_contact_due_outside_the_range_is_absent_though_its_window_overlaps():
    anc2 = contact("anc2")
    # The window opens at day 98 but the visit is due at 154: a range that
    # touches only the early part of the window does not draw it.
    since, until = day(anc2.opens), day(anc2.opens + 20)
    result = span(pregnant(), since.isoformat(), until.isoformat(), at=since)
    assert "anc2" not in [r["contact"] for r in result.rows], result.rows
    wide = span(pregnant(), since.isoformat(), day(anc2.due).isoformat(), at=since)
    assert "anc2" in [r["contact"] for r in wide.rows]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok   %s" % fn.__name__)
    print("\n%d checks passed" % len(fns))
