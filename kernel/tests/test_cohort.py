"""Run: python3 -m kernel.tests.test_cohort

What a centre owes between two dates, derived across every open episode.

THE TWO CASES THIS FILE EXISTS FOR are the woman nobody has seen for months,
who is exactly who a screen like this is for and who an implementation that
found episodes through recent visits would never list, and the pregnancy that
has ended, which owes nothing to any day, past or future. The rest is
plumbing for stating those.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from adapters.local.store import SqliteStore
from kernel import cohort, declarations, schedule
from kernel.contracts import AuditRecord

BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
SCHED = BUNDLE.schedules["phc.sched.antenatal"]
ANC = "phc.op.antenatal-visit"
checks = 0
LMP = date(2026, 1, 5)
PREG = ("pregnancy",)


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def noon(d):
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)


def contact(cid):
    return next(c for c in SCHED.contacts if c.id == cid)


def day(offset):
    return LMP + timedelta(days=offset)


def centre():
    store = SqliteStore(":memory:")
    for pid, name in (("p-amina", "Amina Sheikh"), ("p-bilal", "Bilal Khan")):
        store.write("patient", {"id": pid, "name": name, "age": "30"}, thread="t-" + pid)
    return store


def episode_row(store, rid, patient, kind, status, when, *, anchor=LMP,
                basis="last_menstrual_period", outcome=""):
    store.db.execute(
        "INSERT INTO episode_of_care (id, patient, type, status, anchor_date,"
        " anchor_basis, outcome, created_date) VALUES (?,?,?,?,?,?,?,?)",
        [rid, patient, kind, status, anchor.isoformat() if anchor else None,
         basis, outcome, when])


def visit(store, thread, patient, when, *, operation=ANC):
    store.db.execute(
        "INSERT INTO encounter (id, patient, status, token, created_date)"
        " VALUES (?, ?, 'in_progress', ?, ?)",
        [thread, patient, thread[-2:], noon(when).isoformat()])
    if operation:
        store.append_audit(AuditRecord(
            id="aud-" + thread, thread=thread, operation=operation, actor="user:cho",
            surface="rendered", payload={}, outcome="committed",
            at=noon(when).strftime("%Y-%m-%dT%H:%M:%SZ"), proposal=None))


def owed(store, since, until, *, types=PREG, at=None):
    return cohort.owed(BUNDLE, store, WF, types=types, since=since, until=until,
                       at=noon(at or until))


def test_an_open_pregnancy_owes_its_contacts_to_the_window():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    anc1 = contact("anc1")
    rows = owed(store, day(anc1.due), day(anc1.due))
    assert [r["contact"] for r in rows] == ["anc1"], rows
    row = rows[0]
    assert row["subject"] == "p-amina" and row["subject_row"]["name"] == "Amina Sheikh"
    assert row["on"] == [day(anc1.due).isoformat()] and row["state"] == schedule.DUE
    assert row["episode"] == "ep-1"


def test_an_ended_pregnancy_owes_nothing_to_any_day():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    episode_row(store, "ep-2", "p-amina", "pregnancy", "ended", "2026-03-01T09:00:00+00:00",
                anchor=None, basis=None, outcome="miscarriage")
    for since, until, at in ((LMP, day(300), day(100)),            # past and future windows
                             (day(150), day(160), day(155)),
                             (day(400), day(500), day(450))):
        assert owed(store, since, until, at=at) == [], (since, until)
    # Same instant for both rows: the opening still wins the tie.
    same = "2026-03-01T09:00:00+00:00"
    store2 = centre()
    episode_row(store2, "ep-1", "p-amina", "pregnancy", "active", same)
    episode_row(store2, "ep-2", "p-amina", "pregnancy", "ended", same, anchor=None,
                basis=None, outcome="live_birth")
    assert owed(store2, LMP, day(300), at=day(100)) == []


def test_a_miscarriage_owes_no_home_visit_to_any_day():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    episode_row(store, "ep-2", "p-amina", "pregnancy", "ended", "2026-03-01T09:00:00+00:00",
                anchor=None, basis=None, outcome="miscarriage")
    assert owed(store, day(0), day(400), types=("pregnancy", "postnatal"), at=day(60)) == []


def test_a_contact_covers_every_day_of_its_window_and_no_other():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    anc2 = contact("anc2")
    rows = [r for r in owed(store, day(anc2.opens - 10), day(anc2.opens + 2),
                            at=day(anc2.opens)) if r["contact"] == "anc2"]
    assert len(rows) == 1
    assert rows[0]["on"] == [day(anc2.opens + n).isoformat() for n in range(3)], rows[0]["on"]
    # A window that ends the day before it opens does not list it.
    assert [r for r in owed(store, day(anc2.opens - 5), day(anc2.opens - 1),
                            at=day(anc2.opens - 1)) if r["contact"] == "anc2"] == []


def test_a_missed_contact_stays_owed_after_its_window_shuts():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    anc1 = contact("anc1")
    later = day(anc1.closes + 20)
    rows = [r for r in owed(store, later, later, at=later) if r["contact"] == "anc1"]
    assert len(rows) == 1 and rows[0]["state"] == schedule.MISSED, rows
    assert rows[0]["owner"] == anc1.escalates_to
    # but a done one whose window shut is not owed
    visit(store, "e-a1", "p-amina", day(anc1.due))
    rows = [r for r in owed(store, later, later, at=later) if r["contact"] == "anc1"]
    assert rows == [], rows


def test_an_undated_pregnancy_owes_nothing_and_does_not_raise():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00",
                anchor=None, basis=None)
    assert owed(store, LMP, day(300)) == []


def test_a_woman_with_no_visit_for_months_is_still_owed_her_contacts():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    # Her only visit is long before the window; Bilal has no episode at all
    # but visited yesterday.
    visit(store, "e-a1", "p-amina", day(10), operation=None)
    visit(store, "e-b1", "p-bilal", day(200), operation=None)
    anc3 = contact("anc3")
    rows = owed(store, day(anc3.due), day(anc3.due))
    # Her earlier contacts are missed and still owed; the one in the window is due.
    assert {(r["subject"], r["contact"]) for r in rows if r["on"]} == {("p-amina", "anc3")}, rows
    assert {r["subject"] for r in rows} == {"p-amina"}, rows


def test_only_the_named_episode_types_are_swept():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    episode_row(store, "ep-r", "p-bilal", "referral", "active", "2026-02-01T09:00:00+00:00",
                anchor=None, basis="raised")
    anc1 = contact("anc1")
    rows = owed(store, LMP, day(anc1.closes))
    assert {r["subject"] for r in rows} == {"p-amina"}, rows
    assert {r["schedule"] for r in rows} == {"phc.sched.antenatal"}


def test_reaching_the_read_limit_raises_rather_than_truncating():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    episode_row(store, "ep-2", "p-bilal", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    saved = cohort._ALL
    cohort._ALL = 2          # the episode read comes back full: somebody may be missing
    try:
        owed(store, LMP, day(300))
    except RuntimeError:
        pass
    else:
        raise AssertionError("a full read must raise, not return a short list")
    finally:
        cohort._ALL = saved


def test_an_episode_with_no_subject_is_skipped_and_its_neighbours_are_not():
    store = centre()
    episode_row(store, "ep-1", "p-amina", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    episode_row(store, "ep-x", None, "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    episode_row(store, "ep-2", "p-bilal", "pregnancy", "active", "2026-02-01T09:00:00+00:00")
    anc1 = contact("anc1")
    rows = owed(store, day(anc1.due), day(anc1.due))
    assert {r["subject"] for r in rows} == {"p-amina", "p-bilal"}, rows
    assert all(r["subject_row"] for r in rows)


def test_the_womans_own_record_and_the_facilitys_day_pick_the_same_open_pregnancy():
    # `spine.episodes` (her record) and `cohort.owed` (the centre's day) each
    # pair openings with endings, in two places in two files. If their
    # tie-break ever diverged, her record and the facility's day would disagree
    # about whether she is pregnant. One pregnancy opened and ended at the very
    # same instant (a delivery is one commit); a second is open.
    from kernel import spine
    store = centre()
    same = "2026-02-01T09:00:00+00:00"
    episode_row(store, "ep-old-end", "p-amina", "pregnancy", "ended", same, anchor=None,
                basis=None, outcome="live_birth")
    episode_row(store, "ep-old", "p-amina", "pregnancy", "active", same)
    episode_row(store, "ep-new", "p-amina", "pregnancy", "active", "2026-06-01T09:00:00+00:00",
                anchor=day(150))
    mine = [e["id"] for e in spine.episodes(BUNDLE, store, WF, "p-amina", [], at=noon(day(200)))
            if e["status"] == "active"]
    theirs = {r["episode"] for r in owed(store, day(150), day(400), at=day(200))}
    assert mine == ["ep-new"], mine
    assert theirs == {"ep-new"}, theirs


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
