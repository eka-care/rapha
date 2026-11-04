"""Run: python3 scripts/check_calendar_scale.py

A range of days must mean what a day means, be refused when absurd, and be
fast enough for a centre with a queue in front of it.

A contact owed to somebody is never stored (kernel/schedule.py explains why:
a stored schedule has to be cancelled when a pregnancy ends, and the woman
who has just lost a baby is the one who is called when somebody forgets).
That is why the sweep is dear: every answer is derived again from the episode
and the audit. So the cost is measured, here, with 300 open episodes, and if
it is ever over the line the remedy is a bulk read in kernel/cohort.py, never
a cache of derived rows and never a stored contact.

THE CLAIM THAT IS EASY TO GET WRONG: `?on=` and a range are two questions,
not one. `?on=` asks what is owed ON a day, by window, and lists a contact on
every day it can still be acted on. A range asks what FALLS DUE in a span, by
due date, so a grid draws a visit once. Neither is a special case of the
other, so this does not assert that a range equals its days put together.
It asserts the relationship that does hold (claim 1).

Claims 1 and 2 run against an in-memory store through the real resolver. Claim
2's refusal and claim 3's timing go through the real HTTP route against a
scratch database (PHC_DB is always a fresh temporary file here).

The pass line is a judgement, not anybody's requirement: roughly where a nurse
with a queue in front of her starts to wonder whether the screen is broken.
The year view is twelve requests and is judged on when its FIRST month can
draw, not its last.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

# Before api.main is imported: its store opens PHC_DB at import.
# Always its own file, even if the caller exported PHC_DB: this check must
# never read or write a developer's own database.
os.environ["PHC_DB"] = str(pathlib.Path(tempfile.mkdtemp(prefix="calendar-scale-")) / "phc.sqlite3")
os.environ.setdefault("PHC_DIRECTORY", "absent")

from adapters.local.store import SqliteStore                  # noqa: E402
from catalogue import vocab                                   # noqa: E402
from kernel import declarations, proposals, views             # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
CAL = next(v for v in BUNDLE.views.values() if v.kind == "calendar")
ANM = set(vocab.for_bundle("phc").roles["anm"])
AN_ANM = "user:jyothi"

TODAY = date.today()
NOW = datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0, tzinfo=timezone.utc)
#: Under this many seconds, or the screen feels broken.
LINE = 2.0
OPEN_EPISODES = 300
_n = [0]


def woman(store, name, lmp_days_ago):
    """Register somebody and open a pregnancy dated that many days back."""
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


def key(r):
    return (r["subject"], r["contact"])


# ---------------------------------------------------------------------------
# 1. A range and a day relate by due date, and by nothing looser.
# ---------------------------------------------------------------------------

store = SqliteStore(":memory:")
for i, ago in enumerate((15, 60, 100, 150, 200, 260, 280)):
    woman(store, "Woman %d" % i, ago)

FIRST = TODAY - timedelta(days=30)
LAST = TODAY + timedelta(days=60)
ranged = views.resolve(BUNDLE, CAL.id, store, at=NOW,
                       since=FIRST.isoformat(), until=LAST.isoformat())
by_cell = {}
for r in ranged.rows:
    by_cell.setdefault(r["cell"], []).append(r)
assert len({(key(r)) for r in ranged.rows}) == len(ranged.rows), "a contact is drawn twice in one range"
assert ranged.rows, "the range answered nothing; the fixture proves nothing"
# A range draws a contact in the cell of its due day and nowhere else; the one
# exception is a missed contact due before the range, which is a marker on
# today. Anything else in a cell means the range has slid back to windows.
for r in ranged.rows:
    assert r["cell"] == r["due"] or (r["state"] == "missed" and r["cell"] == TODAY.isoformat()), \
        "%s is drawn on %s but falls due on %s" % (key(r), r["cell"], r["due"])
    assert FIRST.isoformat() <= r["cell"] <= LAST.isoformat(), (key(r), r["cell"])

days = 0
due_rows = 0
windowed_only = 0
for n in range((LAST - FIRST).days + 1):
    d = FIRST + timedelta(days=n)
    iso = d.isoformat()
    asked = views.resolve(BUNDLE, CAL.id, store, at=NOW, on=iso)
    # What falls due on d, by either question. `?on=` lists it because its
    # window covers d (the due day is inside its own window).
    due_on_asked = {key(r) for r in asked.rows if r["due"] == iso}
    due_in_range = {key(r) for r in by_cell.get(iso, []) if r["due"] == iso}
    assert due_on_asked == due_in_range, \
        "%s: asking the day says %s falls due, the range says %s" % (
            iso, sorted(due_on_asked ^ due_in_range)[:3], sorted(due_in_range)[:3])
    # The difference between the questions: a contact owed on d whose due day
    # is not d is on the day's list and not in the range's cell for d (the
    # range draws it once, on its due day). Counted, and required to exist.
    still_owed = {key(r) for r in asked.rows if r["due"] != iso}
    drawn_here = {key(r) for r in by_cell.get(iso, [])}
    assert not still_owed & {key(r) for r in by_cell.get(iso, []) if r["due"] == iso}, iso
    windowed_only += len({k for k in still_owed if k not in drawn_here})
    due_rows += len(due_in_range)
    days += 1
assert due_rows, "nothing fell due in the whole range; the equality above compared empty sets"
assert windowed_only, \
    "no day lists a contact the range omits from that day's cell; the two questions are not being told apart"
ok("1. a range draws each contact once, on its due day, and agrees with ?on= on what falls due that day "
   "(%d days, %d contacts); ?on= additionally lists %d window-only appearances the range deliberately does not"
   % (days, due_rows, windowed_only))


# ---------------------------------------------------------------------------
# 2. The cap admits a year and a month grid, and refuses an absurd range.
# ---------------------------------------------------------------------------

empty = SqliteStore(":memory:")


def span_of(n):
    return (TODAY.isoformat(), (TODAY + timedelta(days=n - 1)).isoformat())


admitted = {}
for n in (42, 366, 400):
    a, b = span_of(n)
    result = views.resolve(BUNDLE, CAL.id, empty, at=NOW, since=a, until=b)
    admitted[n] = len(result.groups)
    assert admitted[n] == n, (n, admitted[n])
for n in (401, 5000):
    a, b = span_of(n)
    try:
        views.resolve(BUNDLE, CAL.id, empty, at=NOW, since=a, until=b)
    except ValueError:
        continue
    raise AssertionError("a range of %d days was answered" % n)
ok("2. a range of 42, 366 and 400 days is answered; 401 and 5000 are refused")


# ---------------------------------------------------------------------------
# 3. 300 open episodes, through the real route, under the line.
# ---------------------------------------------------------------------------

try:
    from starlette.testclient import TestClient
except ImportError:                      # pragma: no cover
    print("warn starlette missing: the timing did not run")
    raise SystemExit(1)

from api.main import app, store as route_store                # noqa: E402

for i in range(OPEN_EPISODES):
    # Spread across the whole arc, so most are mid-schedule and some have a
    # lot of missed contacts. 10..290 days.
    woman(route_store, "Crowd %d" % i, 10 + (i * 280) // OPEN_EPISODES)

client = TestClient(app)
URL = "/api/v1/phc/views/%s" % CAL.id
HEAD = {"X-PHC-Role": "anm"}


def timed(query):
    t = time.perf_counter()
    got = client.get(URL + query, headers=HEAD)
    spent = time.perf_counter() - t
    assert got.status_code == 200, (query, got.status_code, got.text[:200])
    return spent, got.json()


def grid(first):
    """The 42 days a month's grid draws: six weeks from the Monday on or
    before the 1st."""
    start = first - timedelta(days=first.weekday())
    return "?from=%s&to=%s" % (start.isoformat(), (start + timedelta(days=41)).isoformat())


home_s, home = timed("?from=%s&to=%s" % (TODAY.isoformat(), (TODAY + timedelta(days=365)).isoformat()))
assert home["rows"], "the home page's range found nothing among %d women" % OPEN_EPISODES
subjects = {r["subject"] for r in home["rows"]}
assert len(subjects) >= OPEN_EPISODES * 0.9, \
    "only %d of %d women are on the home page; the load is not what it claims" % (len(subjects), OPEN_EPISODES)
month_s, month = timed(grid(TODAY.replace(day=1)))
assert month["rows"], "a month with 300 women in it drew nothing"

months = []
for m in range(12):
    y, mm = TODAY.year + (TODAY.month - 1 + m) // 12, (TODAY.month - 1 + m) % 12 + 1
    months.append(date(y, mm, 1))
cumulative, first_month = 0.0, None
for first in months:
    spent, _ = timed(grid(first))
    cumulative += spent
    if first_month is None:
        first_month = spent
year_s = cumulative

assert home_s < LINE, "the home page took %.2fs for %d women (line %.1fs)" % (home_s, OPEN_EPISODES, LINE)
assert month_s < LINE, "a month took %.2fs for %d women (line %.1fs)" % (month_s, OPEN_EPISODES, LINE)
assert first_month < LINE, "the year's first month took %.2fs (line %.1fs)" % (first_month, LINE)
ok("3. %d open episodes: home page %.2fs, a month %.2fs, a year's first month %.2fs "
   "(all twelve %.2fs); line %.1fs"
   % (OPEN_EPISODES, home_s, month_s, first_month, year_s, LINE))

print("\nok   the calendar at scale: %d checks" % checks)
