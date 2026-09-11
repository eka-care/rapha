"""Run: python3 -m bundles.phc.check

Consent to ambient capture, end to end through the kernel. No network, no
uvicorn, no browser: SqliteStore on :memory: and kernel.proposals.commit, so
what is asserted here is the same write path the API serves.

capture.consented used to be declared, gated on, and raised by nothing, which
made the scribe permanently off and the consent theatre. It is composed now:

    capture.agreed     the consent question on the registration form
    capture.declined   its own answer on the same form, a first class no
    capture.withdrawn  the stop question on the consultation form
    capture.consented  agreed, and neither declined nor withdrawn

The checks below are the four sentences that have to stay true: consenting
offers the scribe, declining is visibly declined, neither leaks to the next
visit, and a withdrawal turns the gate off without touching a record anybody
already confirmed.
"""
from __future__ import annotations

import pathlib

from adapters.local.store import SqliteStore, seed
from catalogue import validate, vocab
from kernel import declarations, proposals, state, views

BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
OPS = BUNDLE.operations
SCRIBE = BUNDLE.instruments["phc.inst.consult-scribe"]
CAPS = set().union(*vocab.for_bundle("phc").roles.values())

REGISTER = {"name": "Test Person", "age": 30, "sex": "female",
            "phone": "9800000000", "village": "Sonpur"}
CONSULT = {"assessment": "Fever three days, no red flags."}

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def fresh(token="T1"):
    """(store, thread) with nothing on it. A thread is one encounter."""
    s = SqliteStore(":memory:")
    return s, s.open_thread(token=token)


def commit(store, thread, op_id, payload, actor="user:frontdesk", **kw):
    return proposals.commit(store, BUNDLE, op_id, thread=thread, payload=payload,
                            caps=CAPS, actor=actor, **kw)


def flags(store, thread):
    return state.flags(store, thread, WF)


def scribe_offerable(store, thread):
    """The renderer's own rule, which is web/src/messages.ts composer(): a
    scribe pill exists when one of the instrument's operations is a visible
    action AND capture.consented is on the thread. Asserted here so a kernel
    side change cannot quietly turn capture on with nobody's consent."""
    known = flags(store, thread)
    live = {op["id"] for op in state.actions(WF, OPS, known, CAPS)}
    return bool(set(SCRIBE.operations) & live) and "capture.consented" in known


def register(payload_extra, token="T1"):
    store, thread = fresh(token)
    decision = commit(store, thread, "phc.op.patient-register",
                      dict(REGISTER, **payload_extra))
    assert decision, decision.reason
    return store, thread


# --------------------------------------------------------------------------


def check_consenting_raises_the_flag_and_offers_the_scribe():
    store, thread = register({"capture_consent": True})
    known = flags(store, thread)
    assert "capture.agreed" in store.stored_flags(thread), sorted(store.stored_flags(thread))
    assert "capture.consented" in known, sorted(known)
    assert scribe_offerable(store, thread), "consented and the scribe is still off"
    ok("a tick on the registration form raises capture.agreed, the workflow "
       "composes capture.consented, and the scribe becomes offerable")


def check_the_flag_comes_from_the_declaration_and_not_from_this_check():
    """The question carries the flag name. Break the link and the demo is back
    to a consent nothing reads."""
    schema = validate.load(OPS["phc.op.patient-register"]["input"])
    asked = {q["link_id"]: (q.get("styling_metadata") or {}).get("phc", {}).get("flags")
             for q in validate.walk(schema["questions"])}
    assert asked.get("capture_consent") == "capture.agreed", asked
    assert asked.get("capture_declined") == "capture.declined", asked
    assert validate.flags(schema, dict(REGISTER, capture_consent=True)) == {"capture.agreed"}
    # Fail closed: the string "yes" is not a yes.
    assert validate.flags(schema, dict(REGISTER, capture_consent="yes")) == set()
    assert set(WF.stored) >= {"capture.agreed", "capture.declined", "capture.withdrawn"}
    assert "capture.consented" not in WF.stored, \
        "the gate is stored again, so no withdrawal can lower it"
    ok("the questionnaire names the flag, only a real yes raises it, and the "
       "gate itself is composed rather than stored")


def check_declining_is_visible_rather_than_absent():
    store, thread = register({"capture_declined": True})
    known = flags(store, thread)
    assert "capture.declined" in known and "capture.consented" not in known, sorted(known)
    assert not scribe_offerable(store, thread)

    row, = [r for r in views.resolve(BUNDLE, "phc.view.station-queue", store).rows
            if r.thread == thread]
    assert row.badges.get("capture.declined") == "mute", row.badges
    ok("a decline raises its own flag and the queue badges the visit declined, "
       "so the next station reads the answer instead of asking again")


def check_a_visit_nobody_asked_is_not_a_decline():
    store, thread = register({})
    known = flags(store, thread)
    assert not [f for f in known if f.startswith("capture.")], sorted(known)
    row, = [r for r in views.resolve(BUNDLE, "phc.view.station-queue", store).rows
            if r.thread == thread]
    assert not row.badges.get("capture.declined")
    ok("an unanswered consent question is neither consent nor a decline, and "
       "is not drawn as one")


def check_a_contradiction_fails_closed():
    store, thread = register({"capture_consent": True, "capture_declined": True})
    known = flags(store, thread)
    assert {"capture.agreed", "capture.declined"} <= known, sorted(known)
    assert "capture.consented" not in known, "both ticked and something listened"
    assert not scribe_offerable(store, thread)
    ok("ticking both answers is a contradiction and the safe one wins: "
       "declined beats agreed, nothing listens")


def check_consent_does_not_leak_to_the_next_encounter():
    store, first = register({"capture_consent": True})
    second = store.open_thread(token="T2")
    assert commit(store, second, "phc.op.patient-register", REGISTER)
    assert "capture.consented" in flags(store, first)
    assert "capture.consented" not in flags(store, second), \
        "consent given at one visit followed the patient to the next"
    assert not scribe_offerable(store, second)
    # And it is scoped by the store, not by this check remembering to ask.
    assert store.stored_flags(second) == frozenset()
    ok("consent is scoped to the visit: a second encounter starts with nothing "
       "raised, on the same day and the same store")


def check_withdrawal_stops_capture_and_leaves_confirmed_records_alone():
    store, thread = register({"capture_consent": True})
    assert commit(store, thread, "phc.op.consult-document", CONSULT, actor="user:mo")
    before = store.count("notes", thread=thread, where={})
    assert before == 1 and "capture.consented" in flags(store, thread)

    assert commit(store, thread, "phc.op.consult-document",
                  dict(CONSULT, assessment="Patient asked to stop recording.",
                       capture_stop=True), actor="user:mo")
    known = flags(store, thread)
    assert "capture.withdrawn" in known, sorted(known)
    assert "capture.agreed" in known, "the consent that was given is not erased"
    assert "capture.consented" not in known, "withdrawn and still listening"
    assert not scribe_offerable(store, thread)
    assert store.count("notes", thread=thread, where={}) == before + 1, \
        "a confirmed record went missing at withdrawal"
    ok("withdrawal mid visit turns the gate off for the rest of the visit and "
       "every record already confirmed stands")


def check_the_demo_day_shows_both_answers():
    store = SqliteStore(":memory:")
    seed(store, BUNDLE.seed)
    rows = {r.thread: r for r in
            views.resolve(BUNDLE, "phc.view.station-queue", store).rows}
    assert "capture.consented" in rows["enc-003"].flags, rows["enc-003"].flags
    assert rows["enc-004"].badges.get("capture.declined") == "mute"
    assert not [f for f in rows["enc-005"].flags if f.startswith("capture.")]
    ok("the seeded day has all three: one visit consented and standing at the "
       "doctor, one declined and badged, and one nobody asked")


def check_the_laboratory_is_not_given_a_consent_it_has_no_use_for():
    """The lab bundle does no ambient capture. Nothing added here may reach it:
    not a state, not a questionnaire, not an instrument."""
    lab = declarations.load("lab")
    lab_states = set(vocab.for_bundle("lab").states)
    assert not [f for f in lab_states if f.startswith("capture.")], sorted(lab_states)
    assert not [i for i in lab.instruments.values() if i.kind == "scribe"]
    for op in lab.operations.values():
        schema = validate.load(op["input"])
        asked = [q["link_id"] for q in validate.walk(schema["questions"])
                 if q["link_id"].startswith("capture_")]
        assert not asked, "%s asks %s" % (op["id"], asked)
    # And the consent questions live only on this bundle's own forms.
    for path in sorted(pathlib.Path("questionnaires").glob("lab.*.json")):
        assert "capture" not in path.read_text(), path
    ok("the laboratory has no capture flag, no scribe and no consent question: "
       "a bundle that does not listen is not asked to consent")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_"):
            fn()
    print("ok   bundles/phc: %d consent checks" % checks)
