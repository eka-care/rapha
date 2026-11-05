"""Run: python3 scripts/check_high_risk.py

High-risk pregnancy: three extra visits, two arcs, and both stop together.

A woman marked high risk keeps her ordinary four check-ups and gains three
more, owned by the doctor, in a SECOND episode. Nothing is stored for either
arc: what is owed is derived each time anybody asks, from the declarations
and the episode's own date. So the danger is never that a schedule is left
behind, it is that an operation which ends the pregnancy forgets to end the
second episode, and a woman who has delivered, or lost her baby, goes on
being asked about check-ups she can no longer attend.

THE CHECKS THIS FILE EXISTS FOR are claims 4 and 5. A delivery or a loss must
leave her owing no antenatal visit of EITHER kind, and a loss must open no
postnatal care of EITHER kind: absent, not cancelled, not empty.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore                  # noqa: E402
from catalogue import vocab                                   # noqa: E402
from kernel import declarations, proposals, schedule, spine, state  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
ANTENATAL = BUNDLE.schedules["phc.sched.antenatal"]
EXTRA = BUNDLE.schedules["phc.sched.antenatal-high-risk"]
POSTNATAL = BUNDLE.schedules["phc.sched.postnatal"]
DAY45 = BUNDLE.schedules["phc.sched.postnatal-high-risk"]
ANM = set(vocab.for_bundle("phc").roles["anm"])
USER = "user:jyothi"

# The kernel decides "today" in UTC, so the check must too. date.today() is
# local and disagrees with the kernel for 5.5 hours after midnight in India.
TODAY = datetime.now(timezone.utc).date()
RISK = "severe_anaemia"


def fresh(weeks=40):
    """A registered woman with an open pregnancy, `weeks` along today."""
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="1", actor=USER)
    lmp = TODAY - timedelta(weeks=weeks)
    for op, payload in (
            ("phc.op.patient-register",
             {"name": "Lakshmi Devi", "age": 27, "sex": "female",
              "phone": "9876500001", "village": "Yadiki", "category": "general"}),
            ("phc.op.pregnancy-open",
             {"dating_basis": "last_menstrual_period",
              "dating_date": lmp.isoformat()})):
        done = proposals.commit(store, BUNDLE, op, thread=thread,
                                payload=payload, caps=ANM, actor=USER)
        assert done, done.reason
    return store, thread


def mark(store, thread, days_ago=0):
    done = proposals.commit(
        store, BUNDLE, "phc.op.risk-mark", thread=thread,
        payload={"risk_factor": RISK,
                 "marked_date": (TODAY - timedelta(days=days_ago)).isoformat()},
        caps=ANM, actor=USER)
    assert done, done.reason


def episodes_of(store, thread):
    (patient,) = store.select("patient", thread=thread, where={},
                              fields=["id"], limit=2)
    whole = spine.of(BUNDLE, store, WF, patient["id"])
    return {e["type"]: e for e in whole["episodes"]}


def owed(store, thread):
    """Every contact of every episode she has, keyed by episode type."""
    return {kind: schedule.contacts(BUNDLE, store, WF, episode)
            for kind, episode in episodes_of(store, thread).items()}


def ids(rows):
    return [c["contact"] for c in rows]


def deliver(store, thread, days_ago=0, kind="delivery-record-high-risk"):
    done = proposals.commit(
        store, BUNDLE, "phc.op.%s" % kind, thread=thread,
        payload={"delivery_date": (TODAY - timedelta(days=days_ago)).isoformat(),
                 "outcome": "live_birth"},
        caps=ANM, actor=USER)
    assert done, done.reason


ORDINARY_IDS = [c.id for c in ANTENATAL.contacts]
EXTRA_IDS = [c.id for c in EXTRA.contacts]
assert ORDINARY_IDS and EXTRA_IDS and not set(ORDINARY_IDS) & set(EXTRA_IDS)


# ---------------------------------------------------------------------------
# 1. Marking adds the extra visits and changes none of the existing ones.
# ---------------------------------------------------------------------------

store, thread = fresh(weeks=12)
before = owed(store, thread)
assert "pregnancy_high_risk" not in before, sorted(before)
assert ids(before["pregnancy"]) == ORDINARY_IDS, ids(before["pregnancy"])
mark(store, thread)
after = owed(store, thread)
assert after["pregnancy"] == before["pregnancy"], \
    "marking her high risk changed her ordinary check-ups"
assert ids(after["pregnancy_high_risk"]) == EXTRA_IDS, ids(after["pregnancy_high_risk"])
assert len(EXTRA_IDS) == 3, EXTRA_IDS
ok("marking her adds the extra visits and leaves every ordinary one exactly as it was")


# ---------------------------------------------------------------------------
# 2. The calendar: all of them, each on its own day, the new ones the doctor's.
# ---------------------------------------------------------------------------

rows = after["pregnancy"] + after["pregnancy_high_risk"]
assert len(rows) == len(ORDINARY_IDS) + len(EXTRA_IDS), len(rows)
days = [c["due"] for c in rows]
assert len(set(days)) == len(days), "two visits fall on one day: %s" % sorted(days)
for contact in after["pregnancy_high_risk"]:
    declared = next(c for c in EXTRA.contacts if c.id == contact["contact"])
    assert contact["owner"] == declared.owner == "mo", contact
    assert contact["due"] == (TODAY + timedelta(days=declared.due)).isoformat(), contact
for contact in after["pregnancy"]:
    assert contact["owner"] != "mo", contact
ok("her calendar shows every visit on its own day, with the new ones the doctor's")


# ---------------------------------------------------------------------------
# 3. A missed extra visit escalates, like any other.
# ---------------------------------------------------------------------------

late, late_thread = fresh(weeks=20)
span = max(c.closes for c in EXTRA.contacts)
mark(late, late_thread, days_ago=span - 2)         # the last window is still open
rows = {c["contact"]: c for c in owed(late, late_thread)["pregnancy_high_risk"]}
first = next(c for c in EXTRA.contacts if c.id == EXTRA_IDS[0])
last = next(c for c in EXTRA.contacts if c.id == EXTRA_IDS[-1])
assert rows[first.id]["state"] == schedule.MISSED, rows[first.id]
assert rows[first.id]["owner"] == first.escalates_to != first.owner, rows[first.id]
assert rows[last.id]["state"] == schedule.DUE, rows[last.id]
assert rows[last.id]["owner"] == last.owner == "mo", rows[last.id]
ok("an extra visit nobody made reads as missed and moves to the officer above the doctor")


# ---------------------------------------------------------------------------
# 4. A high-risk delivery stops BOTH antenatal arcs.
# ---------------------------------------------------------------------------

store, thread = fresh(weeks=39)
mark(store, thread, days_ago=2)
assert owed(store, thread)["pregnancy_high_risk"], "nothing was owed to stop"
deliver(store, thread)
flags = state.flags(store, thread, WF)
assert "pregnancy.open" not in flags and "pregnancy_high_risk.open" not in flags, sorted(flags)
episodes = episodes_of(store, thread)
for kind in ("pregnancy", "pregnancy_high_risk"):
    assert schedule.contacts(BUNDLE, store, WF, episodes[kind]) == [], kind
    assert schedule.why(BUNDLE, store, WF, episodes[kind]) == "this is over", kind
ok("a high-risk delivery leaves her owing no antenatal visit of either kind")


# ---------------------------------------------------------------------------
# 5. AND THE ONE THAT MATTERS. A high-risk loss opens nothing.
# ---------------------------------------------------------------------------

store, thread = fresh(weeks=10)
mark(store, thread, days_ago=2)
ended = proposals.commit(store, BUNDLE, "phc.op.pregnancy-close-high-risk",
                         thread=thread, payload={"outcome": "miscarriage"},
                         caps=ANM, actor=USER)
assert ended, ended.reason
flags = state.flags(store, thread, WF)
for flag in ("pregnancy.open", "pregnancy_high_risk.open",
             "postnatal.open", "postnatal_high_risk.open"):
    assert flag not in flags, "%s after a loss: %s" % (flag, sorted(flags))
kinds = episodes_of(store, thread)
assert "postnatal" not in kinds and "postnatal_high_risk" not in kinds, sorted(kinds)
for kind in ("pregnancy", "pregnancy_high_risk"):
    assert schedule.contacts(BUNDLE, store, WF, kinds[kind]) == [], kind
ok("a high-risk loss ends both arcs and opens no postnatal care of either kind: absent")


# ---------------------------------------------------------------------------
# 6. The day-45 check is hers alone, and the seven home visits are the usual.
# ---------------------------------------------------------------------------

store, thread = fresh(weeks=39)
mark(store, thread, days_ago=2)
deliver(store, thread)
now = owed(store, thread)
assert ids(now["postnatal"]) == [c.id for c in POSTNATAL.contacts], ids(now["postnatal"])
assert ids(now["postnatal_high_risk"]) == [c.id for c in DAY45.contacts], now["postnatal_high_risk"]
assert len(now["postnatal"]) == 7 and len(now["postnatal_high_risk"]) == 1
assert now["postnatal_high_risk"][0]["owner"] == "anm", now["postnatal_high_risk"]
# Counted over everything she has: the antenatal arcs add nothing.
assert sum(len(v) for v in now.values()) == 8, {k: len(v) for k, v in now.items()}

plain, plain_thread = fresh(weeks=39)
deliver(plain, plain_thread, kind="delivery-record")
usual = owed(plain, plain_thread)
assert "postnatal_high_risk" not in usual, sorted(usual)
assert ids(usual["postnatal"]) == ids(now["postnatal"])
assert sum(len(v) for v in usual.values()) == 7, {k: len(v) for k, v in usual.items()}
ok("after a high-risk delivery: seven home visits and one day-45 check; after an ordinary one, seven and none")


# ---------------------------------------------------------------------------
# 7. Marked late, she still gets all three, and they stop when she delivers.
# ---------------------------------------------------------------------------

store, thread = fresh(weeks=34)
mark(store, thread)
rows = owed(store, thread)["pregnancy_high_risk"]
assert ids(rows) == EXTRA_IDS, ids(rows)
assert all(c["state"] == schedule.UPCOMING for c in rows), rows
assert all(c["due"] > TODAY.isoformat() for c in rows), rows
deliver(store, thread)
assert owed(store, thread)["pregnancy_high_risk"] == []
ok("marked at thirty-four weeks she still owes all three, and none once she delivers")

print("\nok   high-risk pregnancy: %d checks" % checks)
