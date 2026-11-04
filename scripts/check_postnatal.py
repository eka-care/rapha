"""Run: python3 scripts/check_postnatal.py

What happens at the end of a pregnancy, and what must not.

A delivery ends the pregnancy and opens postnatal care in ONE commit, so
there is no instant in which a woman is neither pregnant nor postnatal and
nobody owes her anything. From that moment the antenatal contacts stop being
owed and seven home visits start being owed, counted from the day she
delivered rather than the day somebody keyed it in.

THE CHECK THIS FILE EXISTS FOR is the negative one, and it is the same
failure the pregnancy half was built around, pointed the other way. A woman
who miscarried must not acquire a postnatal schedule. Not one marked
cancelled, not one that is empty, NONE: the only operation that can open
postnatal care is recording a delivery, and recording a delivery has no
outcome that means a loss. So there is no path from a miscarriage to a home
visit, and that is checked here rather than asserted in a comment.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

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
POSTNATAL = BUNDLE.schedules["phc.sched.postnatal"]
ANTENATAL = BUNDLE.schedules["phc.sched.antenatal"]
ANM = set(vocab.for_bundle("phc").roles["anm"])
ASHA = set(vocab.for_bundle("phc").roles["asha"])
AN_ANM = "user:jyothi"
AN_ASHA = "user:parvathi"

# The kernel decides "today" in UTC, so the check must too. date.today() is
# local and disagrees with the kernel for 5.5 hours after midnight in India.
TODAY = datetime.now(timezone.utc).date()
LMP = TODAY - timedelta(days=280)


def noon(d):
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)


def fresh():
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="1", actor=AN_ANM)
    done = proposals.commit(
        store, BUNDLE, "phc.op.patient-register", thread=thread,
        payload={"name": "Lakshmi Devi", "age": 27, "sex": "female",
                 "phone": "9876500001", "village": "Yadiki",
                 "category": "general"},
        caps=ANM, actor=AN_ANM)
    assert done, done.reason
    pregnant = proposals.commit(
        store, BUNDLE, "phc.op.pregnancy-open", thread=thread,
        payload={"dating_basis": "last_menstrual_period",
                 "dating_date": LMP.isoformat()},
        caps=ANM, actor=AN_ANM)
    assert pregnant, pregnant.reason
    return store, thread


def episodes_of(store, thread):
    (patient,) = store.select("patient", thread=thread, where={},
                              fields=["id"], limit=2)
    whole = spine.of(BUNDLE, store, WF, patient["id"])
    return {e["type"]: e for e in whole["episodes"]}


# ---------------------------------------------------------------------------
# 1. The declaration. Seven visits, nobody can do one who could not go, and
#    no two windows touch.
# ---------------------------------------------------------------------------

assert POSTNATAL.episode == "postnatal"
assert len(POSTNATAL.contacts) == 7, len(POSTNATAL.contacts)
visit = BUNDLE.operations["phc.op.postnatal-visit"]
for contact in POSTNATAL.contacts:
    assert contact.operation == "phc.op.postnatal-visit", contact.id
    assert contact.owner == "asha" and contact.escalates_to == "anm", contact.id
assert visit["capability"] in ASHA and visit["capability"] in ANM
ok("seven home visits, owned by somebody who can go and escalating to another")

# TOUCHING WINDOWS ARE THE BUG THIS CATCHES. These visits are days apart, and
# two windows sharing a day would let one visit discharge either of two
# contacts depending on the order they were read in. A mother visited once
# would then read as visited twice.
windows = sorted((c.opens, c.closes, c.id) for c in POSTNATAL.contacts)
for (_, closes, first), (opens, _, second) in zip(windows, windows[1:]):
    assert closes < opens, "%s and %s share a day" % (first, second)
ok("and no two windows share a day, so one visit can never close two")


# ---------------------------------------------------------------------------
# 2. A delivery, in one commit: the pregnancy ends and postnatal care opens.
# ---------------------------------------------------------------------------

store, thread = fresh()
before = state.flags(store, thread, WF)
assert "pregnancy.open" in before and "postnatal.open" not in before, sorted(before)

delivered = TODAY - timedelta(days=3)
done = proposals.commit(store, BUNDLE, "phc.op.delivery-record", thread=thread,
                        payload={"delivery_date": delivered.isoformat(),
                                 "outcome": "live_birth"},
                        caps=ANM, actor=AN_ANM)
assert done, done.reason

after = state.flags(store, thread, WF)
assert "pregnancy.open" not in after, sorted(after)
assert "postnatal.open" in after, sorted(after)
ok("one commit ends the pregnancy and opens postnatal care, with no gap between")

episodes = episodes_of(store, thread)
assert schedule.contacts(BUNDLE, store, WF, episodes["pregnancy"]) == []
assert schedule.why(BUNDLE, store, WF, episodes["pregnancy"]) == "this is over"
ok("every antenatal contact stops being owed, with nothing to cancel")


# ---------------------------------------------------------------------------
# 3. Counted from the delivery, not from the record of it.
# ---------------------------------------------------------------------------

postnatal = episodes["postnatal"]
assert postnatal["anchor_basis"] == "delivery"
assert postnatal["anchor_date"][:10] == delivered.isoformat()
assert schedule.start_of(POSTNATAL, postnatal) == delivered
ok("the arc starts the day she delivered, which is the day she was asked for")

rows = {c["contact"]: c for c in schedule.contacts(BUNDLE, store, WF, postnatal)}
assert len(rows) == 7, sorted(rows)
# She delivered three days ago and was recorded today. The first day visit
# was due two days before anybody knew, so it reads as missed, which is the
# truth. A schedule counted from the keystroke would hide it.
assert rows["hbnc1"]["state"] == schedule.MISSED, rows["hbnc1"]
assert rows["hbnc1"]["owner"] == "anm", rows["hbnc1"]["owner"]
assert rows["hbnc2"]["state"] == schedule.DUE, rows["hbnc2"]
assert rows["hbnc7"]["state"] == schedule.UPCOMING, rows["hbnc7"]
ok("a delivery recorded late shows the visit nobody made as missed, and escalated")


# ---------------------------------------------------------------------------
# 4. One household visit closes one contact.
# ---------------------------------------------------------------------------

house = store.open_thread(token="2", actor=AN_ASHA)
registered = proposals.commit(
    store, BUNDLE, "phc.op.patient-register", thread=house,
    payload={"name": "Lakshmi Devi", "age": 27, "sex": "female",
             "phone": "9876500001", "village": "Yadiki", "category": "general"},
    caps=ASHA | {"patient.register"}, actor=AN_ASHA)
assert registered, registered.reason
# She cannot do it on a thread with no postnatal care open, which is what
# keeps a home visit off an ordinary clinic encounter.
refused = proposals.commit(store, BUNDLE, "phc.op.postnatal-visit", thread=house,
                           payload={"seen": "mother_and_baby",
                                    "narrative": "Mother and baby well.",
                                    "followup_needed": False},
                           caps=ASHA, actor=AN_ASHA)
assert not refused, "a postnatal home visit landed on a clinic thread"
ok("a postnatal visit cannot land on somebody with no postnatal care open")

# THE GAP THIS SCHEDULE FOUND. The obvious operation to close these contacts
# with was the general household visit this bundle already declares. It
# cannot be performed by anybody: no step of the line draws it, so the guard
# refuses every attempt with "no station in this line draws it". A schedule
# built on it would have been owed for ever, and the lint in
# kernel/declarations.py now refuses that combination rather than leaving it
# to be discovered at a doorstep.
drawn = {oid for step in WF.steps for oid in step.operations}
assert "phc.op.postnatal-visit" in drawn, sorted(drawn)
assert "phc.op.household-visit" not in drawn, \
    "the household visit is drawn now; the note in the schedule is stale"
for contact in POSTNATAL.contacts:
    assert contact.operation in drawn, contact.id
ok("and every contact names an operation some step actually offers")


# ---------------------------------------------------------------------------
# 5. AND THE ONE THAT MATTERS. A miscarriage opens nothing.
# ---------------------------------------------------------------------------

lost, lost_thread = fresh()
ended = proposals.commit(lost, BUNDLE, "phc.op.pregnancy-close",
                         thread=lost_thread, payload={"outcome": "miscarriage"},
                         caps=ANM, actor=AN_ANM)
assert ended, ended.reason

flags = state.flags(lost, lost_thread, WF)
assert "pregnancy.open" not in flags, sorted(flags)
assert "postnatal.open" not in flags, \
    "a miscarriage opened postnatal care; this is the failure the file is for"
kinds = episodes_of(lost, lost_thread)
assert "postnatal" not in kinds, sorted(kinds)
assert schedule.contacts(BUNDLE, lost, WF, kinds["pregnancy"]) == []
ok("a miscarriage opens no postnatal care: not cancelled, not empty, absent")

# And it is absent BY CONSTRUCTION rather than by this one path behaving. The
# only operation that writes a postnatal row is recording a delivery, and
# recording a delivery offers no outcome that means a loss.
openers = [op_id for op_id, op in BUNDLE.operations.items()
           for record in op["mapping"]
           if record["resource"] == "episode_of_care"
           and (record["fields"].get("type") or {}).get("const") == "postnatal"
           and (record["fields"].get("status") or {}).get("const") == "active"]
assert openers == ["phc.op.delivery-record"], openers
outcomes = {o["value"] for o in next(
    q for q in __import__("catalogue.validate", fromlist=["x"]).load(
        BUNDLE.operations["phc.op.delivery-record"]["input"])["questions"]
    if q["link_id"] == "outcome")["answer_option"]}
assert outcomes == {"live_birth", "stillbirth"}, outcomes
ok("and only one operation can open it, with no outcome in it that means a loss")

# A stillbirth DOES open it. The mother is at the same risk either way, and a
# product that stopped visiting her would be making a judgement nobody asked
# it to make.
still, still_thread = fresh()
born = proposals.commit(still, BUNDLE, "phc.op.delivery-record",
                        thread=still_thread,
                        payload={"delivery_date": TODAY.isoformat(),
                                 "outcome": "stillbirth"},
                        caps=ANM, actor=AN_ANM)
assert born, born.reason
assert "postnatal.open" in state.flags(still, still_thread, WF)
ok("a stillbirth opens it, because the mother is owed the same six weeks")


# ---------------------------------------------------------------------------
# 6. And closing it stops the visits, with nothing to cancel.
# ---------------------------------------------------------------------------

gone = proposals.commit(store, BUNDLE, "phc.op.postnatal-close", thread=thread,
                        payload={"outcome": "moved_away"},
                        caps=ANM, actor=AN_ANM)
assert gone, gone.reason
assert "postnatal.open" not in state.flags(store, thread, WF)
closed = episodes_of(store, thread)["postnatal"]
for day in (0, 1, 7, 42, 400):
    assert schedule.contacts(BUNDLE, store, WF, closed,
                             at=noon(delivered + timedelta(days=day))) == [], day
assert schedule.why(BUNDLE, store, WF, closed) == "this is over"
ok("closing it stops every home visit, on every day anybody could ask")

print("\nok   the postnatal arc: %d checks" % checks)
