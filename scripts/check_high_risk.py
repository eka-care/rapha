"""Run: python3 scripts/check_high_risk.py

High-risk pregnancy: three extra visits, two arcs, and both stop together.

A woman marked high risk keeps her ordinary four check-ups and gains three
more, owned by the doctor, in a SECOND episode. Nothing is stored for either
arc: what is owed is derived each time anybody asks, from the declarations
and the episode's own date. So the danger is never that a schedule is left
behind, it is that an operation which ends the pregnancy forgets to end the
second episode, and a woman who has delivered, or lost her baby, goes on
being asked about check-ups she can no longer attend.

THE CHECKS THIS FILE EXISTS FOR are claims 4, 5, 8 and 9. A delivery or a loss must
leave her owing no antenatal visit of EITHER kind, and a loss must open no
postnatal care of EITHER kind: absent, not cancelled, not empty.

Claim 8 is the reverse worry: one recorded visit must close ONE contact, not an
ordinary one and an extra one together. Claim 9 is that no way of ending a
mother's postnatal care, on a death or on not finding her, leaves her owing a
visit on the other episode.
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
    types = [e["type"] for e in whole["episodes"]]
    assert len(types) == len(set(types)), "an episode type appears twice: %s" % types
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
# 2. Her episodes together: each visit on its own day, the new ones the doctor's.
# This reads the contacts of each episode, not the calendar view built on them.
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
ok("across her episodes every owed visit falls on its own day, the extra ones the doctor's and the ordinary ones not")


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
# 7. Marked late, her extra visits run past her due date and stop at delivery.
# ---------------------------------------------------------------------------
# The extra visits count from the day she is marked, not from how far along she
# is. So a woman marked at thirty-four weeks owes visits after her expected
# delivery date, which she will only reach if she goes overdue, and a schedule
# counted back from the due date would have dropped or squeezed them. 280 days
# is the dating convention in the antenatal schedule, a literal on purpose.

store, thread = fresh(weeks=34)
mark(store, thread)
episodes = episodes_of(store, thread)
edd = schedule.start_of(ANTENATAL, episodes["pregnancy"]) + timedelta(days=280)
rows = owed(store, thread)["pregnancy_high_risk"]
assert ids(rows) == EXTRA_IDS, ids(rows)
beyond = [c for c in rows if c["due"] > edd.isoformat()]
assert beyond, "no extra visit falls after her due date %s: %s" % (edd, rows)
assert all(c["state"] == schedule.UPCOMING for c in beyond), beyond
deliver(store, thread)
assert owed(store, thread)["pregnancy_high_risk"] == []
ok("marked at thirty-four weeks, visits fall after her due date and are owed until she delivers")


# ---------------------------------------------------------------------------
# 8. ONE RECORDED VISIT CLOSES EXACTLY ONE CONTACT, and the extra visits are
#    the doctor's own act, not the ordinary check-up counted twice.
# ---------------------------------------------------------------------------
# The defect this guards: both schedules once named the same operation, and
# contacts are discharged per schedule by the operation committed, so a single
# recorded visit closed an ordinary contact and an extra one together. She
# then received fewer visits than the programme requires, and an ANM's visit
# discharged the medical officer's contact.

VISIT = {"history": "Well.", "examination": "BP normal.",
         "assessment": "Progressing.", "plan": "Review next month."}
ORDINARY_OPS = {c.operation for c in ANTENATAL.contacts}
EXTRA_OPS = {c.operation for c in EXTRA.contacts}
assert len(ORDINARY_OPS) == 1 and len(EXTRA_OPS) == 1, (ORDINARY_OPS, EXTRA_OPS)
assert not ORDINARY_OPS & EXTRA_OPS, \
    "both schedules name %s: one visit closes a contact in each" % (ORDINARY_OPS & EXTRA_OPS)
(ORDINARY_OP,), (EXTRA_OP,) = ORDINARY_OPS, EXTRA_OPS


def record(store, thread, op):
    done = proposals.commit(store, BUNDLE, op, thread=thread, payload=dict(VISIT),
                            caps=ANM, actor=USER)
    assert done, (op, done.reason)


def closed(store, thread):
    """{episode type: [contact ids done]} over everything she owes."""
    return {kind: [c["contact"] for c in rows if c["state"] == schedule.DONE]
            for kind, rows in owed(store, thread).items()}


# Marked thirty days ago, twenty weeks along: a window of each kind is open.
store, thread = fresh(weeks=20)
mark(store, thread, days_ago=30)
assert closed(store, thread) == {"pregnancy": [], "pregnancy_high_risk": []}, closed(store, thread)
record(store, thread, ORDINARY_OP)
once = closed(store, thread)
assert len(once["pregnancy"]) == 1 and once["pregnancy_high_risk"] == [], \
    "one ordinary visit: %s" % once
record(store, thread, EXTRA_OP)
twice = closed(store, thread)
assert twice["pregnancy"] == once["pregnancy"], \
    "the extra visit changed her ordinary contacts: %s -> %s" % (once, twice)
assert len(twice["pregnancy_high_risk"]) == 1, "one extra visit: %s" % twice
assert sum(len(v) for v in twice.values()) == 2, twice

# And the extra visit alone, on a woman who has had no ordinary one, closes
# nothing of her ordinary four.
store, thread = fresh(weeks=20)
mark(store, thread, days_ago=30)
record(store, thread, EXTRA_OP)
alone = closed(store, thread)
assert alone["pregnancy"] == [] and len(alone["pregnancy_high_risk"]) == 1, alone
ok("one recorded visit closes exactly one contact: an ordinary visit closes one ordinary contact, an extra visit one extra, neither touches the other")


# ---------------------------------------------------------------------------
# 9. NO PATH LEAVES A DEAD MOTHER OWING A VISIT, and none chases one who
#    cannot be found.
# ---------------------------------------------------------------------------
# A high-risk mother has two postnatal episodes. Every operation that ends
# either of them, with every answer that means she is gone, is tried against
# the state she is in. A refusal is not a path. A commit is, and after it she
# must owe nothing on EITHER episode. The scan is over the whole catalogue, so
# an operation added later is covered without anybody remembering it.

GONE = ("mother_died", "not_found", "unable_to_contact", "moved_away")
POSTNATAL_KINDS = ("postnatal", "postnatal_high_risk")


def endings_of_postnatal():
    out = []
    for op_id, op in BUNDLE.operations.items():
        for record_ in op.get("mapping") or []:
            fields = record_.get("fields") or {}
            if (fields.get("type") == {"const": "postnatal"}
                    or fields.get("type") == {"const": "postnatal_high_risk"}) \
                    and fields.get("status") == {"const": "ended"}:
                out.append(op_id)
                break
    return sorted(set(out))


ENDERS = endings_of_postnatal()
assert {"phc.op.postnatal-close", "phc.op.postnatal-outcome"} <= set(ENDERS), ENDERS


def high_risk_mother():
    store, thread = fresh(weeks=39)
    mark(store, thread, days_ago=2)
    deliver(store, thread, days_ago=2)
    assert set(POSTNATAL_KINDS) <= set(owed(store, thread)), sorted(owed(store, thread))
    return store, thread


def ordinary_mother():
    store, thread = fresh(weeks=39)
    deliver(store, thread, days_ago=2, kind="delivery-record")
    return store, thread


def owes_nothing(store, thread):
    rows = owed(store, thread)
    return sum(len(v) for v in rows.values()) == 0 \
        and not {"postnatal.open", "postnatal_high_risk.open"} & state.flags(store, thread, WF)


def paths(make):
    """[(op, answer)] that a commit accepts for the mother `make` builds."""
    taken = []
    for op_id in ENDERS:
        for answer in GONE:
            store, thread = make()
            done = proposals.commit(store, BUNDLE, op_id, thread=thread,
                                    payload={"outcome": answer}, caps=ANM, actor=USER)
            if not done:
                continue
            taken.append((op_id, answer))
            assert owes_nothing(store, thread), \
                "%s with %r leaves her owing: %s" % (
                    op_id, answer, {k: ids(v) for k, v in owed(store, thread).items() if v})
    return taken


high = paths(high_risk_mother)
assert ("phc.op.postnatal-close-high-risk", "mother_died") in high, \
    "a high-risk mother has no way of being recorded as dead: %s" % high
assert ("phc.op.postnatal-close", "mother_died") not in high, high
assert not [p for p in high if p[0] == "phc.op.postnatal-outcome"], \
    "the day-45 form takes %s, which would end one episode only" % high

ordinary = paths(ordinary_mother)
assert ("phc.op.postnatal-close", "mother_died") in ordinary, ordinary
assert not [p for p in ordinary if "high-risk" in p[0] or p[0] == "phc.op.postnatal-outcome"], ordinary

# The other order: the day-45 check done first, then she is lost.
for outcome in ("both_well", "mother_unwell", "baby_unwell", "both_unwell", "baby_died"):
    store, thread = high_risk_mother()
    done = proposals.commit(store, BUNDLE, "phc.op.postnatal-outcome", thread=thread,
                            payload={"outcome": outcome}, caps=ANM, actor=USER)
    assert done, (outcome, done.reason)
    after = proposals.commit(store, BUNDLE, "phc.op.postnatal-close", thread=thread,
                             payload={"outcome": "mother_died"}, caps=ANM, actor=USER)
    assert after, (outcome, after.reason)
    assert owes_nothing(store, thread), outcome
ok("no way of ending postnatal care on a death or a lost mother leaves a visit owed on either episode: %d accepted paths tried, ordinary mother and high-risk mother" % (len(high) + len(ordinary)))

# ---------------------------------------------------------------------------
# 10-13. A MARK MADE IN ERROR CAN BE UNDONE, and only that: the extra visits
#        stop, everything else about her carries on, and nothing is erased.
# ---------------------------------------------------------------------------
# This is not a clinical reversal. The reasons on the form are about the
# record being wrong. Whether a woman who has recovered stops receiving
# high-risk care is a question nobody has answered, so nothing here answers it.

import time                                                   # noqa: E402


def unmark(store, thread, reason="wrong_patient", actor=USER):
    return proposals.commit(
        store, BUNDLE, "phc.op.risk-unmark", thread=thread,
        payload={"reason": reason}, caps=ANM, actor=actor)


def every_episode(store, thread):
    """All her episodes, ended ones too, a type possibly more than once."""
    (patient,) = store.select("patient", thread=thread, where={},
                              fields=["id"], limit=2)
    return spine.of(BUNDLE, store, WF, patient["id"])["episodes"]


def high_risk_ones(store, thread):
    return [e for e in every_episode(store, thread) if e["type"] == "pregnancy_high_risk"]


# 10. Undoing stops all three extra visits and moves no ordinary one.
store, thread = fresh(weeks=20)
mark(store, thread, days_ago=30)
record(store, thread, ORDINARY_OP)                    # one ordinary visit done
ordinary_before = owed(store, thread)["pregnancy"]
assert any(c["state"] == schedule.DONE for c in ordinary_before), ordinary_before
assert len(owed(store, thread)["pregnancy_high_risk"]) == 3
undone = unmark(store, thread)
assert undone, undone.reason
now_owed = owed(store, thread)
assert now_owed["pregnancy_high_risk"] == [], now_owed["pregnancy_high_risk"]
assert schedule.why(BUNDLE, store, WF, episodes_of(store, thread)["pregnancy_high_risk"]) == "this is over"
assert now_owed["pregnancy"] == ordinary_before, \
    "undoing the mark changed her ordinary check-ups:\n%s\n%s" % (ordinary_before, now_owed["pregnancy"])
assert [(c["contact"], c["due"], c["owner"], c["state"]) for c in now_owed["pregnancy"]] \
    == [(c["contact"], c["due"], c["owner"], c["state"]) for c in ordinary_before]
flags = state.flags(store, thread, WF)
assert "pregnancy.open" in flags and "pregnancy_high_risk.open" not in flags, sorted(flags)
assert "pregnancy.ordinary" in flags, sorted(flags)
ok("undoing a mark leaves her owing none of the three extra visits and her ordinary four exactly as they were")


# 11. Not offered to a woman who was never marked, and not offered twice.
store, thread = fresh(weeks=20)
never = unmark(store, thread)
assert not never, "a woman who was never marked can be unmarked"
mark(store, thread, days_ago=1)
assert unmark(store, thread)
twice = unmark(store, thread)
assert not twice, "the same mark was undone twice"
assert len(high_risk_ones(store, thread)) == 1
ok("the undo is refused for a woman never marked and refused a second time")


# 12. Marked, undone, marked again: the new marking date counts.
store, thread = fresh(weeks=20)
mark(store, thread, days_ago=20)                      # the mistyped date
assert unmark(store, thread, reason="wrong_date")
time.sleep(1.1)       # episodes pair by the second; see the report on this
mark(store, thread, days_ago=0)                       # the right one
again = high_risk_ones(store, thread)
assert len(again) == 2, [(e["opened_at"], e["status"]) for e in again]
live = [e for e in again if e["status"] == "active"]
dead = [e for e in again if e["status"] == "ended"]
assert len(live) == 1 and len(dead) == 1, again
assert dead[0]["contacts"] == [] and dead[0]["outcome"] == "marked_in_error", dead[0]
assert ids(live[0]["contacts"]) == EXTRA_IDS, live[0]["contacts"]
for contact in live[0]["contacts"]:
    declared = next(c for c in EXTRA.contacts if c.id == contact["contact"])
    assert contact["due"] == (TODAY + timedelta(days=declared.due)).isoformat(), \
        "counted from the old marking date: %s" % contact
flags = state.flags(store, thread, WF)
assert "pregnancy_high_risk.open" in flags and "pregnancy.open" in flags, sorted(flags)
assert sum(len(e["contacts"]) for e in every_episode(store, thread)
           if e["type"] == "pregnancy_high_risk") == 3
# And the second mark can itself be undone.
assert unmark(store, thread)
assert all(e["contacts"] == [] for e in high_risk_ones(store, thread))
ok("marked, undone and marked again, her three visits count from the new date and the old mark owes nothing")


# 13. Nothing is erased: both the mark and the undo stay, with who and when.
store, thread = fresh(weeks=20)
mark(store, thread, days_ago=3)
assert unmark(store, thread, reason="wrong_date", actor="user:meena")
(patient,) = store.select("patient", thread=thread, where={}, fields=["id"], limit=2)
rows = [r for r in store.select("episode_of_care", thread=None,
                                where={"patient": patient["id"]}, fields=(), limit=50)
        if r["type"] == "pregnancy_high_risk"]
assert sorted(r["status"] for r in rows) == ["active", "ended"], rows
opened = next(r for r in rows if r["status"] == "active")
ended = next(r for r in rows if r["status"] == "ended")
assert opened["created_by"] == USER and ended["created_by"] == "user:meena", (opened, ended)
assert opened["created_date"] and ended["created_date"], (opened, ended)
assert ended["outcome"] == "marked_in_error", ended
trail = [a for a in store.audit(thread) if a.operation in ("phc.op.risk-mark", "phc.op.risk-unmark")]
assert [a.operation for a in trail] == ["phc.op.risk-mark", "phc.op.risk-unmark"], trail
assert [a.actor for a in trail] == [USER, "user:meena"], trail
assert trail[0].payload.get("risk_factor") == RISK, trail[0].payload
assert trail[1].payload.get("reason") == "wrong_date", trail[1].payload
shown = high_risk_ones(store, thread)
assert len(shown) == 1 and shown[0]["status"] == "ended" and shown[0]["outcome"] == "marked_in_error", shown
ok("after the undo both the mark and the undo are still in her record, each with who did it and when")

print("\nok   high-risk pregnancy: %d checks" % checks)
