"""Run: python3 -m bundles.phc.check

Consent to ambient capture, end to end through the kernel. No network, no
uvicorn, no browser: SqliteStore on :memory: and kernel.proposals.commit, so
what is asserted here is the same write path the API serves.

capture.consented used to be declared, gated on, and raised by nothing, which
made the scribe permanently off and the consent theatre. It is composed now:

    capture.agreed     the consent question on the registration form
    capture.declined   its own answer on the same form, a first class no
    capture.withdrawn  phc.op.capture-withdraw, one question, its own action
    capture.consented  agreed, and neither declined nor withdrawn

The checks below are the sentences that have to stay true: consenting offers
the scribe, declining is visibly declined, neither leaks to the next visit,
and a withdrawal turns the gate off without writing a note and without
touching a record anybody already confirmed. Withdrawal rode on the
consultation commit until now, where assessment is required, so stopping a
recording meant writing a clinical note as well. It is its own operation.
"""
from __future__ import annotations

import json
import pathlib

from adapters.local.store import SqliteStore, seed
from catalogue import validate, vocab
from catalogue.build import parse
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


def check_withdrawal_is_its_own_operation_and_writes_no_note():
    store, thread = register({"capture_consent": True})
    assert commit(store, thread, "phc.op.consult-document", CONSULT, actor="user:mo")
    before = store.count("notes", thread=thread, where={})
    assert before == 1 and "capture.consented" in flags(store, thread)

    decision = commit(store, thread, "phc.op.capture-withdraw",
                      {"capture_stop": True}, actor="user:mo")
    assert decision, decision.reason
    known = flags(store, thread)
    assert "capture.withdrawn" in known, sorted(known)
    assert "capture.agreed" in known, "the consent that was given is not erased"
    assert "capture.consented" not in known, "withdrawn and still listening"
    assert not scribe_offerable(store, thread)
    assert store.count("notes", thread=thread, where={}) == before, \
        "stopping a recording wrote a clinical note"
    ok("a withdrawal turns the gate off on its own, with no assessment and no "
       "note written, and the note committed before it still stands")


def check_the_consultation_form_no_longer_withdraws():
    """One way to withdraw, not two. The stop question is off the consult form,
    so a consultation cannot raise the flag as a side effect and a withdrawal
    cannot be held hostage by a required assessment."""
    consult = validate.load(OPS["phc.op.consult-document"]["input"])
    asked = [q["link_id"] for q in validate.walk(consult["questions"])
             if q["link_id"].startswith("capture")]
    assert not asked, asked
    assert validate.flags(consult, dict(CONSULT, capture_stop=True)) == set()

    store, thread = register({"capture_consent": True})
    refused = commit(store, thread, "phc.op.consult-document",
                     dict(CONSULT, capture_stop=True), actor="user:mo")
    assert not refused and "not a question on this form" in refused.reason, refused

    # And the withdrawal form asks nothing clinical, so it cannot demand one.
    withdraw = validate.load(OPS["phc.op.capture-withdraw"]["input"])
    assert [q["link_id"] for q in validate.walk(withdraw["questions"])] == ["capture_stop"]
    assert validate.flags(withdraw, {"capture_stop": True}) == {"capture.withdrawn"}
    assert validate.flags(withdraw, {"capture_stop": "yes"}) == set()
    ok("the stop question is on the withdrawal form and nowhere else: the "
       "consultation refuses it, and the withdrawal asks nothing clinical")


def can_withdraw(store, thread):
    """The renderer's rule for whether the action is drawn at all, which is
    kernel/state.actions over the guard's own visible()."""
    live = {op["id"] for op in state.actions(WF, OPS, flags(store, thread), CAPS)}
    return "phc.op.capture-withdraw" in live


def check_the_withdrawal_action_is_invisible_with_nothing_to_withdraw():
    never, thread = register({})
    assert not can_withdraw(never, thread), "offered to a visit nobody asked"

    declined, thread = register({"capture_declined": True})
    assert not can_withdraw(declined, thread), "offered to a visit that said no"

    store, thread = register({"capture_consent": True})
    assert can_withdraw(store, thread), "consented and no way to stop it"
    assert commit(store, thread, "phc.op.capture-withdraw", {"capture_stop": True},
                  actor="user:mo")
    assert not can_withdraw(store, thread), "offered twice on one visit"
    # Absent means absent, on the tap as well as on the screen.
    again = commit(store, thread, "phc.op.capture-withdraw", {"capture_stop": True},
                   actor="user:mo")
    assert not again and "capture.consented" in again.reason, again.reason
    ok("the withdrawal is absent when consent was never given, when it was "
       "declined and once it has already been withdrawn, on both the screen "
       "and the tap")


def check_a_withdrawal_that_says_nothing_is_refused_rather_than_allowed():
    """The stop question is `required`, and that one word is load bearing.

    It was `required: false`, matching the two consent questions on the
    registration form, and on screen that read as an allowed withdrawal that
    withdrew nothing: the renderer omits an unticked boolean, so the payload
    was `{}`, validate.flags raises only on a real `True`, and the commit was
    recorded, drew a card, accrued a care unit and left `capture.consented`
    standing with the scribe still offered. Tapping Stop and being told it
    worked while the recording continues is the one outcome this whole
    operation exists to prevent.

    Optional is right for a consent, where not answering means nobody asked
    and every gate stays shut. It is wrong for a withdrawal, where the gate is
    already open and the answer is the only thing that shuts it.

    What `required` does NOT close, asserted below so nobody reads this check
    as more than it is: an explicit `false` is an answer. catalogue/validate
    counts `link_id in payload and payload[link_id] not in (None, "")` as
    answered, and `False` passes that, so a caller that sends the key with a
    false value is still allowed and still raises nothing. No rendered surface
    can produce it, because the renderer omits an unticked boolean, but the MCP
    surface and any HTTP client can. Closing it needs a "must be true" rule in
    catalogue/validate.py mirrored in web/src/validate.ts, which is a change to
    shared validation and not this bundle's to make.
    """
    store, thread = register({"capture_consent": True})
    empty = commit(store, thread, "phc.op.capture-withdraw", {}, actor="user:mo")
    assert not empty and "capture_stop is required" in empty.reason, empty.reason
    assert "capture.withdrawn" not in flags(store, thread)
    assert scribe_offerable(store, thread), "refused, so the scribe is untouched"

    # The hole that is still open, written down rather than left to be found.
    unticked = commit(store, thread, "phc.op.capture-withdraw",
                      {"capture_stop": False}, actor="user:mo")
    assert unticked, "an explicit false is refused now: tighten this check"
    assert scribe_offerable(store, thread), \
        "a false withdrawal must at least not stop anything"

    assert commit(store, thread, "phc.op.capture-withdraw", {"capture_stop": True},
                  actor="user:mo")
    assert not scribe_offerable(store, thread)
    ok("a withdrawal that answers nothing is refused on every rendered path; "
       "an explicit false is still allowed and still withdraws nothing")


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
    assert "phc.op.capture-withdraw" not in lab.operations, \
        "the laboratory loaded a withdrawal for a consent it never takes"
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


def check_the_consent_is_spoken_not_read():
    """The clerk used to read fifty-three words off the registration screen to
    every patient, at a counter, with a queue behind them. Nobody reads
    fifty-three words the fortieth time, so the consent became a tick. The
    agent speaks the line now, and the clerk taps what the patient answered.

    Instrument attributes, not dict keys: c.Instrument is a frozen dataclass
    (kernel/contracts.py) and kernel/declarations.py's _plain() builds it from
    the atom's frontmatter, so the compiled instrument is accessed the same
    way SCRIBE is accessed above, by attribute.
    """
    # The agent's line is the consent itself. Dropping any one of the four
    # things it carries, or paraphrasing it, is not a shorter consent, it is a
    # different one, which is why this asserts the sentence and not a summary
    # of it.
    SPOKEN = ("May we record this visit to write your notes? "
              "You can say no, or stop it any time.")

    inst = BUNDLE.instruments["phc.inst.consent-speak"]
    assert inst.kind == "spoken-prompt"
    assert inst.says == SPOKEN, inst.says
    # Four things, and shortening further drops one: that it is a recording,
    # what for, that refusal is free, that it can be stopped.
    for must in ("record", "notes", "say no", "stop"):
        assert must in SPOKEN.lower(), must

    # `spoken` is the facility's off switch: true speaks the line, false
    # renders the same `says` sentence on screen instead (fallback: text).
    # c.Instrument defaults `spoken` to True, which means the compiled value
    # alone cannot tell "declared true" from "not declared, defaulted true":
    # this reads the atom's own frontmatter to prove the key is actually
    # there, not just that the default happens to agree with it, and then
    # separately proves the value survives compilation into catalogue.json
    # rather than being dropped or reset on the way. Losing either check lets
    # someone delete the off switch again while every other assertion here
    # still passes on the default.
    fm, _ = parse(pathlib.Path("bundles/phc/phc.inst.consent-speak.md"))
    assert "spoken" in fm, "the atom does not declare `spoken`: the off switch is gone"
    assert fm["spoken"] is True, fm["spoken"]
    assert inst.spoken is True, inst.spoken
    compiled = json.load(open("catalogue/catalogue.json"))
    assert compiled["instruments"]["phc.inst.consent-speak"]["spoken"] is True, \
        "the off switch did not survive compilation into catalogue.json"

    schema = json.load(open("questionnaires/phc.schema.register-v1.json"))
    consent = [q for q in schema["questions"] if q["link_id"] == "capture_consent"][0]
    assert consent["text"] == "Record this visit?", consent["text"]
    assert "description" not in consent, "the 53 word read-out moved to the spoken line"
    ok("the registration form asks 'Record this visit?' with no read-out "
       "paragraph, the agent's own line carries all four things a recording "
       "consent needs, and its off switch declares and compiles")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_"):
            fn()
    print("ok   bundles/phc: %d consent checks" % checks)
