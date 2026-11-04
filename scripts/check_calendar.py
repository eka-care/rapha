"""Run: python3 scripts/check_calendar.py

The facility calendar must never chase a woman it has no business chasing.

A contact owed to somebody is never stored. It is derived, every time
somebody asks, from the episode and the audit (kernel/schedule.py explains
why at length). So an episode that has ended owes nothing, on any day, and
there is no generated row that somebody must remember to cancel. Without that
property a woman who has just lost a baby is the one who gets the call asking
why she missed her twenty eight week visit.

THE CHECK THIS FILE EXISTS FOR is the miscarriage: not a cancelled home
visit, not an empty one, NO row of any kind, on any day, in the day's list or
the month's counts. Absence is what is asserted, not emptiness.

Everything runs against an in-memory store through the real resolver, except
the route refusal, which goes through the real HTTP route against a scratch
database (PHC_DB is always set to a fresh temporary file here)
so that no developer's demo day is touched.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

# Before api.main is imported: its store opens PHC_DB at import.
# Always its own file, even if the caller exported PHC_DB: this check must
# never read or write a developer's own database.
os.environ["PHC_DB"] = str(pathlib.Path(tempfile.mkdtemp(prefix="calendar-")) / "phc.sqlite3")
os.environ.setdefault("PHC_DIRECTORY", "absent")

from adapters.local.store import SqliteStore                  # noqa: E402
from catalogue import vocab                                   # noqa: E402
from kernel import declarations, proposals, schedule, views   # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
CAL = next(v for v in BUNDLE.views.values() if v.kind == "calendar")
ANTENATAL = BUNDLE.schedules["phc.sched.antenatal"]
POSTNATAL = BUNDLE.schedules["phc.sched.postnatal"]
ANM = set(vocab.for_bundle("phc").roles["anm"])
AN_ANM = "user:jyothi"

TODAY = date.today()
NOW = datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0, tzinfo=timezone.utc)
#: Far enough either side to cover every window of both arcs.
SPAN = range(-420, 421)
_n = [0]


def woman(store, name, lmp_days_ago):
    """Register somebody and open a pregnancy dated that many days back.
    Returns her thread."""
    _n[0] += 1
    thread = store.open_thread(token=str(_n[0]), actor=AN_ANM)
    for op, payload in (
        ("phc.op.patient-register",
         {"name": name, "age": 27, "sex": "female", "phone": "9876500001",
          "village": "Yadiki", "category": "general"}),
        ("phc.op.pregnancy-open",
         {"dating_basis": "last_menstrual_period",
          "dating_date": (TODAY - timedelta(days=lmp_days_ago)).isoformat()}),
    ):
        done = proposals.commit(store, BUNDLE, op, thread=thread, payload=payload,
                                caps=ANM, actor=AN_ANM)
        assert done, done.reason
    return thread


def patient_of(store, thread):
    (row,) = store.select("patient", thread=thread, where={}, fields=["id"], limit=2)
    return row["id"]


def day(store, d):
    return views.resolve(BUNDLE, CAL.id, store, at=NOW, on=d.isoformat())


def appearances(store, patient):
    """Every (day, row) on which this patient is owed anything."""
    seen = []
    for n in SPAN:
        d = TODAY + timedelta(days=n)
        seen.extend((d, r) for r in day(store, d).rows if r["subject"] == patient)
    return seen


# ---------------------------------------------------------------------------
# 1 and 2. What ended owes nothing. Three women, one store.
# ---------------------------------------------------------------------------

store = SqliteStore(":memory:")
open_t = woman(store, "Open Pregnancy", 150)
born_t = woman(store, "Delivered", 270)
lost_t = woman(store, "Miscarried", 100)
open_p, born_p, lost_p = (patient_of(store, t) for t in (open_t, born_t, lost_t))

# Control: before anything ends, the miscarrying woman IS owed antenatal
# contacts. Without this the absences below could be an empty fixture.
assert any(r["subject"] == lost_p for r in day(store, TODAY).rows), \
    "the control woman is not on today before her pregnancy ends; the fixture proves nothing"

done = proposals.commit(store, BUNDLE, "phc.op.delivery-record", thread=born_t,
                        payload={"delivery_date": (TODAY - timedelta(days=3)).isoformat(),
                                 "outcome": "live_birth"},
                        caps=ANM, actor=AN_ANM)
assert done, done.reason
done = proposals.commit(store, BUNDLE, "phc.op.pregnancy-close", thread=lost_t,
                        payload={"outcome": "miscarriage"}, caps=ANM, actor=AN_ANM)
assert done, done.reason

ante_ids = {c.id for c in ANTENATAL.contacts}
post_ids = {c.id for c in POSTNATAL.contacts}
assert not ante_ids & post_ids, "the two arcs share a contact id; the split below is meaningless"
seen = appearances(store, born_p)
assert seen, "the delivered woman is owed nothing at all; the fixture proves nothing"
stale = [(d.isoformat(), r["contact"]) for d, r in seen
         if r["schedule"] == ANTENATAL.id]
assert not stale, "a pregnancy that ended is still owed on: %s" % stale[:3]
assert {r["schedule"] for _, r in seen} == {POSTNATAL.id}, {r["schedule"] for _, r in seen}
ok("1. a pregnancy that ended contributes nothing to any day, %d days either side"
   % max(SPAN))

seen = appearances(store, lost_p)
assert seen == [], \
    "a miscarriage is owed something: %s" % [(d.isoformat(), r["contact"]) for d, r in seen[:3]]
# And in the month's counts: every day's count equals the rows of the OTHER
# women, so a count that still carried her would exceed it.
others = {open_p, born_p}
for n in SPAN[::7]:
    d = TODAY + timedelta(days=n)
    result = day(store, d)
    assert all(r["subject"] in others for r in result.rows), d
    for g in result.groups:
        gd = date.fromisoformat(g["key"])
        assert g["count"] == len([r for r in day(store, gd).rows if r["subject"] in others]), g
ok("2. a miscarriage contributes no home visit, and no other row, to any day: absent, not empty")


# ---------------------------------------------------------------------------
# 3. A contact is on exactly the days its window covers.
# ---------------------------------------------------------------------------

store = SqliteStore(":memory:")
thread = woman(store, "Windowed", 100)
patient = patient_of(store, thread)
start = TODAY - timedelta(days=100)
by_day = {}
for d, r in appearances(store, patient):
    by_day.setdefault(r["contact"], set()).add(d)
for contact in ANTENATAL.contacts:
    opens = start + timedelta(days=contact.opens)
    closes = start + timedelta(days=contact.closes)
    want = {opens + timedelta(days=n) for n in range((closes - opens).days + 1)}
    got = by_day.get(contact.id, set())
    if closes < TODAY:
        # Missed: stays owed on every day after the window shuts, which is
        # the point of the screen. Never before it opens.
        want |= {TODAY + timedelta(days=n) for n in SPAN if TODAY + timedelta(days=n) > closes}
    assert got == want, "%s: extra %s, missing %s" % (
        contact.id, sorted(x.isoformat() for x in got - want)[:3],
        sorted(x.isoformat() for x in want - got)[:3])
assert len(by_day) == len(ANTENATAL.contacts), sorted(by_day)
ok("3. each of %d contacts is on exactly its window's days, and the missed ones on every day after"
   % len(by_day))


# ---------------------------------------------------------------------------
# 5. Without the capability, the route refuses. It does not answer empty.
# ---------------------------------------------------------------------------

try:
    from starlette.testclient import TestClient
except ImportError:                      # pragma: no cover
    print("warn starlette missing: the route refusal did not run")
    raise SystemExit(1)

from api.main import ROLES, app                               # noqa: E402

# No real role can exercise this: every one holds the capability (patient.find).
# So a caller that holds nothing is made up, and the route's own guard is
# what is proved.
assert all(CAL.capability in caps for caps in vocab.BUNDLES.values()), \
    "a real role now lacks the calendar's capability; use it here instead of a synthetic one"
ROLES["nobody"] = []
client = TestClient(app)
URL = "/api/v1/phc/views/%s" % CAL.id
refused = client.get(URL, headers={"X-PHC-Role": "nobody"})
assert refused.status_code == 403, (refused.status_code, refused.text)
assert "rows" not in refused.json(), refused.json()
allowed = client.get(URL, headers={"X-PHC-Role": "anm"})
assert allowed.status_code == 200, allowed.text
bad = client.get(URL + "?on=2026-02-30", headers={"X-PHC-Role": "anm"})
assert bad.status_code == 400, bad.status_code
ok("5. a caller holding nothing is refused with 403, not shown an empty screen; a nurse is let in")


# ---------------------------------------------------------------------------
# 4 and 6. The day's total, its piles, and the month's count for it.
# ---------------------------------------------------------------------------

store = SqliteStore(":memory:")
for i, ago in enumerate((20, 100, 150, 200, 260)):
    woman(store, "Woman %d" % i, ago)
for n in range(-45, 46, 1):
    d = TODAY + timedelta(days=n)
    result = day(store, d)
    piles = {}
    for r in result.rows:
        piles.setdefault(r["state"], []).append(r)
    month = {g["key"]: g["count"] for g in result.groups}
    # The month's count is a number the engine computed on its own, not from
    # these rows, so the piles' total is held to it.
    assert sum(len(p) for p in piles.values()) == month[d.isoformat()], \
        "%s: piles hold %d and the month counts %d" % (
            d, sum(len(p) for p in piles.values()), month[d.isoformat()])
    keys = [(r["subject"], r["contact"]) for r in result.rows]
    assert len(set(keys)) == len(keys), "%s: a contact is listed twice" % d
    assert month[d.isoformat()] == len(result.rows), \
        "%s: the month says %d and the day lists %d" % (d, month[d.isoformat()], len(result.rows))
    assert len(month) == (date(d.year + (d.month == 12), d.month % 12 + 1, 1)
                          - date(d.year, d.month, 1)).days, d
assert any(day(store, TODAY + timedelta(days=n)).rows for n in range(-45, 46)), "empty fixture"
ok("4. every day's piles add up to the month's own count for it, and no contact is listed twice")
ok("6. the month's count for a date equals the length of that date's list, 91 days running")


# ---------------------------------------------------------------------------
# 7. The woman nobody has seen for months is still on today.
# ---------------------------------------------------------------------------

store = SqliteStore(":memory:")
thread = woman(store, "Unseen", 190)
patient = patient_of(store, thread)
rows = [r for r in day(store, TODAY).rows if r["subject"] == patient]
assert rows, "an open pregnancy with no visit for five months is not on today"
# The first contact's window shut a hundred days ago with nothing against
# it. That is the woman this screen exists to surface, and she is on today
# by the missed rule, not because anything recent happened to her.
first = {r["contact"]: r["state"] for r in rows}
assert first.get("anc1") == "missed", first
assert all(r["state"] != "done" for r in rows), rows
ok("7. a woman 190 days into a pregnancy with no visit is on today (%d contacts)" % len(rows))

print("\nok   the calendar: %d checks" % checks)
