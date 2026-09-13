"""One conversational turn, with no I/O in it.

An utterance comes in, a list of proposal cards goes out, and in between this
module does exactly three things: ask a planner what was heard, sort the answer
into the order the KERNEL already put this thread's actions in, and hand each
operation to a propose callable. It never decides anything. It cannot write:
the only callable it is given is propose, and the caller that supplies it
(api/main.py) supplies kernel.proposals.propose, which hard codes the machine
surface where a write can only ever come back "proposed".

Why a separate module from the route: the route is a shell around a store, and
this is the part worth checking without a socket. demo() below runs the whole
turn against a fake planner and a fake propose, so the ordering, the payload
filter and the refusal wording are asserted with no database and no port.

Honest about the confidence map. Nothing here recognises speech. A caller that
dictated the utterance passes the recogniser's per-field confidence along
(packages/voice emits exactly that shape, link_id -> 0..1) and this module
carries it to the card so the renderer can mark those fields unsure. A typed
utterance has no confidences and the map is empty, which is the truth rather
than a 1.0 nobody measured.
"""
from __future__ import annotations

import dataclasses

from agent import planner

UNSURE = ("I do not know which operation that is, and I will not guess: a "
          "wrong proposal in front of a busy clinician is worse than none.")

# What to do next, for a precondition denial. Keyed by catalogue.guard's own
# machine-stable classification (precondition_kind()), never by the clerk
# sentence describe_precondition() writes: those sentences are exactly what
# Task 7's copy pass is about to reword, and a string match on them would
# degrade silently to NEXT_OTHERWISE the moment the wording changed.
PRECONDITION_NEXT = {
    # A separation of duties rule is about WHO, not about the visit, so it
    # gets its own half sentence.
    "actor_negated":
        "Somebody else has to do this one. Whoever did the step it names cannot "
        "also do this, whatever capabilities they hold.",
    "actor_required":
        "Only the person who did the step it names may do this one.",
    "unevaluable":
        "Nobody said who is acting here, and the kernel will not guess on a "
        "rule about who did what.",
    # Both polarities of a plain flag precondition ("Already registered." and
    # "Requires rx confirmed.") get the same half sentence: it must be true of
    # either, so it claims no order of its own.
    "flag_negated":
        "The state of this visit does not satisfy that. "
        "The kernel decides what is open here, not me.",
    "flag_required":
        "The state of this visit does not satisfy that. "
        "The kernel decides what is open here, not me.",
}

# Everything else the guard can deny on: no precondition_kind travels with
# these (only a precondition denial gets one), so they are still keyed by the
# shape of the guard's own reason string. None of these are the clerk-facing
# precondition sentences a copy pass is about to touch.
NEXT = (
    ("payload invalid", "Open the form on screen and fill in the rest. I only "
                        "fill what the words actually said."),
    ("missing capability", "This account does not hold that capability. "
                           "Someone who does has to do it."),
    ("outside scope", "That is outside this account's scope of practice."),
    ("irreversible", "Irreversible work is done on screen with an explicit tap. "
                     "I cannot propose it, and that is deliberate."),
    ("not a step of", "This line has no station that draws it, so it cannot "
                      "happen on this visit at all."),
)
NEXT_OTHERWISE = "Open it on screen if it should still happen."


def next_step(reason: str, kind: str = "") -> str:
    if kind in PRECONDITION_NEXT:
        return PRECONDITION_NEXT[kind]
    for prefix, advice in NEXT:
        if prefix in reason:
            return advice
    return NEXT_OTHERWISE


def heard_with(confidence, payload) -> dict:
    """The recogniser's confidence for answers that actually made the payload.

    A trust boundary: a caller that sends anything other than a map of link_id
    to number gets no confidences rather than a 500, and a confidence for a
    field nobody filled is dropped rather than drawn against nothing.
    """
    if not isinstance(confidence, dict):
        return {}
    return {k: v for k, v in confidence.items()
            if k in payload and isinstance(v, (int, float))
            and not isinstance(v, bool)}


def card(op, proposed, decision_reason, proposal_id, flags_raised, *,
         actions, station, confidence, decision_kind="") -> dict:
    """Everything the thread needs to draw one proposal, and nothing it has to
    compute. `order` is the kernel's ordering explained, never an opinion."""
    allowed = proposal_id is not None
    offered = [a["id"] for a in actions]
    return {
        "proposal_id": proposal_id,
        "operation": op["id"],
        "title": op["title"],
        "instrument": op.get("instrument"),
        "irreversibility": op["irreversibility"],
        # Keyed by link_id, so the renderer can label each answer with the
        # questionnaire's own question text.
        "payload": proposed.payload,
        "confidence": heard_with(confidence, proposed.payload),
        "heard": proposed.why,
        # What the planner heard and would not resolve. Empty is the usual
        # case; a question here is the alternative to a guess, not to a refusal.
        "ask": list(proposed.ask),
        "verdict": {
            "allowed": allowed,
            # The guard's words, unedited. Paraphrasing a refusal is how an
            # agent starts inventing policy.
            "reason": decision_reason,
            "next": "" if allowed else next_step(decision_reason, decision_kind),
        },
        "flags_raised": flags_raised,
        "station": next((a["station"] for a in actions if a["id"] == op["id"]), None),
        # The kernel does not offer it here: a card the renderer should draw
        # as superseded rather than as work.
        "offered_here": op["id"] in offered,
        "order": planner.explain_order(proposed, actions, station),
    }


def waiting_for(actions) -> str:
    if not actions:
        return "Nothing on this visit is open to you right now."
    return "Open to you here: " + ", ".join(a["title"] for a in actions[:5]) + "."


def say(cards, actions) -> str:
    """The reply, composed from what the guard said. No clinical prose."""
    if not cards:
        return UNSURE + " " + waiting_for(actions)
    lines = []
    for c in cards:
        if c["verdict"]["allowed"]:
            lines.append("Proposed %s for you to confirm." % c["title"])
        else:
            # The guard's reason sometimes ends in a full stop of its own.
            lines.append("%s was refused: %s. %s"
                         % (c["title"], c["verdict"]["reason"].rstrip(". "),
                            c["verdict"]["next"]))
    # A question the planner would not answer for itself, asked out loud.
    for c in cards:
        lines.extend(c.get("ask") or [])
    # No "nothing is recorded until you confirm" line: the card under this
    # sentence carries the confirm control, and it said so the last five times.
    return " ".join(lines)


def take(utterance: str, *, catalogue: dict, view: dict, propose,
         confidence=None, which: str = None) -> dict:
    """Plan, order by the kernel, propose each, and report every verdict.

    propose: callable(operation_id, payload) -> (proposal_id|None, reason, flags, kind)
             kind is catalogue.guard's machine-stable precondition_kind(), or
             "" for a denial that is not a precondition (or for an allow) --
             next_step() dispatches on it before it ever looks at the reason
             string, so a copy pass over the guard's sentences cannot silently
             change the advice. The only thing here that touches a store,
             injected so this runs without one. There is no second callable
             and there must not be: a confirm argument would be a hole a
             sentence could reach.

    Every operation the planner named is sent, including one the kernel does
    not currently offer, because the refusal is the guard's to state and an
    agent that pre-filters is an agent quietly making clinical decisions.
    """
    which = which or planner.backend()
    actions = view.get("actions") or []
    if not str(utterance).strip():
        return {"said": "Say what you want recorded.", "backend": which,
                "understood": False, "proposals": []}
    try:
        plan = planner.plan(utterance, catalogue, caps=set(view.get("held") or []),
                            state=set(view.get("flags") or []), which=which)
    except Exception as broke:  # the SDK, a key, a rate limit, a network
        # Say which planner failed and stop. Falling back to the other backend
        # silently would hide which one produced what.
        return {"said": "The %s planner failed: %s: %s. The router backend needs "
                        "no key and no network." % (which, type(broke).__name__, broke),
                "backend": which, "understood": False, "proposals": []}

    cards = []
    for p in planner.by_kernel_order(plan, actions):
        op = catalogue["operations"][p.operation]
        # The trust boundary, again, at the last moment before the guard: a
        # planner answers the questionnaire's own questions and nothing else,
        # and never override_reason. A model must not grant itself an override.
        # dataclasses.replace, so a new field on Proposed cannot be silently
        # dropped here by a constructor that was not updated with it.
        p = dataclasses.replace(p, payload=planner.typed(op, p.payload))
        proposal_id, reason, flags, kind = propose(p.operation, p.payload)
        cards.append(card(op, p, reason, proposal_id, flags, actions=actions,
                          station=view.get("station"), confidence=confidence,
                          decision_kind=kind))
    return {"said": say(cards, actions), "backend": which,
            "understood": bool(cards), "proposals": cards}


# --------------------------------------------------------------------------

def demo():
    """Run: python3 -m agent.turn

    A whole turn with no kernel and no key: a fake catalogue, a fake propose.
    What it pins down is the part that is this module's own: ordering read from
    the kernel's actions, the payload filtered to declared link_ids, a refusal
    carrying the guard's words plus a next step, and an unmappable utterance
    admitting it rather than guessing.
    """
    def op(op_id, title, cap, fields):
        return {"id": op_id, "title": title, "capability": cap, "short": title,
                "summary": title, "description": title, "kind": "write",
                "preconditions": [], "irreversibility": "correctable",
                "instrument": None, "input": "q", "fields": fields}

    def field(link_id, type_="integer", options=None):
        return {"link_id": link_id, "type": type_, "text": link_id,
                "required": True, "options": options or []}

    cat = {"operations": {
        "x.op.vitals": op("x.op.vitals", "Record vitals", "vitals.record",
                          [field("systolic"), field("diastolic"), field("pulse")]),
        "x.op.dispense": op("x.op.dispense", "Dispense", "pharmacy.dispense",
                            [field("medicines", "string")]),
        "x.op.visit": op("x.op.visit", "Visit", "household.visit",
                         [field("visit_type", "choice",
                                ["tb_followup", "ncd_followup"]),
                          field("narrative", "text")]),
    }}
    view = {"id": "t-1", "station": "nurse", "flags": [], "held": ["vitals.record"],
            "actions": [{"id": "x.op.vitals", "station": "nurse",
                         "title": "Record vitals"}]}

    sent = []

    def propose(operation, payload):
        sent.append((operation, dict(payload)))
        if operation == "x.op.vitals":
            return "prop-1", "proposed", ["vitals.flagged"], ""
        return None, "Requires rx prescribed.", [], "flag_required"

    turn = take("vitals 140 over 90 and pulse 72", catalogue=cat, view=view,
                propose=propose, confidence={"systolic": 0.8, "invented": 0.9},
                which="router")
    assert turn["understood"] and len(turn["proposals"]) == 1, turn
    got = turn["proposals"][0]
    assert got["proposal_id"] == "prop-1"
    assert got["payload"] == {"systolic": 140, "diastolic": 90, "pulse": 72}, got
    assert got["confidence"] == {"systolic": 0.8}, "a confidence for no field is dropped"
    junk = take("vitals 140 over 90", catalogue=cat, view=view, propose=propose,
                confidence=["not", "a", "map"], which="router")
    assert junk["proposals"][0]["confidence"] == {}, "a malformed map is dropped, not a 500"
    assert got["verdict"] == {"allowed": True, "reason": "proposed", "next": ""}
    assert got["flags_raised"] == ["vitals.flagged"]
    assert got["offered_here"] and "1 of 1 at nurse" in got["order"]
    assert turn["said"] == "Proposed Record vitals for you to confirm.", turn["said"]

    # An operation the kernel does not offer here is still sent, and comes back
    # with the guard's own reason and a next step.
    refused = take("dispense the medicines", catalogue=cat, view=view,
                   propose=propose, which="router")["proposals"][0]
    assert refused["proposal_id"] is None
    assert refused["verdict"]["reason"] == "Requires rx prescribed."
    assert "does not satisfy that" in refused["verdict"]["next"]
    # The advice is keyed on the guard's machine-stable kind, not on the
    # sentence: rewording the sentence must not change it (Task 7 reworks
    # exactly these clerk-facing sentences), and a different kind must give
    # different advice even carrying the very same words.
    assert next_step("Patient is already registered.", "flag_negated") == \
        next_step("Already registered.", "flag_negated"), \
        "the sentence changed; the advice for the same kind must not"
    assert next_step("Already registered.", "flag_negated") != \
        next_step("Already registered.", "actor_negated"), \
        "two different kinds must not collapse to the same advice just because a sentence was reused"
    # A separation of duties refusal must not share the plain-flag advice: it
    # is about who is asking, not about the visit.
    assert "Somebody else has to do this one" in next_step(
        "Already performed lab op result enter.", "actor_negated")
    assert "does not satisfy that" not in next_step(
        "Already performed lab op result enter.", "actor_negated")
    assert refused["offered_here"] is False
    assert "does not offer this" in refused["order"]

    # Nothing recognisable: no proposal, and no invented operation.
    lost = take("what is the weather", catalogue=cat, view=view, propose=propose,
                which="router")
    assert lost["proposals"] == [] and not lost["understood"]
    assert "will not guess" in lost["said"] and "Record vitals" in lost["said"]

    # override_reason never reaches the guard, whatever a planner answers.
    stripped = planner.typed(dict(cat["operations"]["x.op.vitals"],
                                  fields=[field("systolic")]),
                             {"systolic": 120, "override_reason": "because I said so"})
    assert stripped == {"systolic": 120}

    # A choice the words do not settle is asked about, out loud, in the reply,
    # and the field is left empty rather than filled with the likelier of two.
    both = take("visit, the followup went fine", catalogue=cat, view=view,
                propose=propose, which="router")
    card_ = both["proposals"][0]
    assert "visit_type" not in card_["payload"], "it guessed between two options"
    assert card_["ask"] and "tb_followup or ncd_followup" in card_["ask"][0]
    assert card_["ask"][0] in both["said"], "the question never reached the clinician"

    # And an utterance that names an operation but fills nothing still puts the
    # proposal in front of a person, with the guard stating what is missing.
    thin = take("visit", catalogue=cat, view=view, propose=propose, which="router")
    assert thin["understood"] and thin["proposals"][0]["payload"] == {}
    assert thin["proposals"][0]["ask"] == []

    assert [s[0] for s in sent] == ["x.op.vitals", "x.op.vitals", "x.op.dispense",
                                    "x.op.visit", "x.op.visit"]

    # The key is the switch, with nothing to configure, and it reaches here:
    # ANTHROPIC_API_KEY set and no explicit backend takes the llm branch of
    # planner.plan(). Stubbed, because a check must not call Anthropic.
    import os
    held, called = os.environ.pop("ANTHROPIC_API_KEY", None), []
    real = planner.llm
    planner.llm = lambda *a, **kw: called.append("llm") or []
    try:
        assert take("vitals 1 over 2", catalogue=cat, view=view,
                    propose=propose)["backend"] == "router", "no key, no network"
        assert called == []
        os.environ["ANTHROPIC_API_KEY"] = "not-a-key"
        assert take("vitals 1 over 2", catalogue=cat, view=view,
                    propose=propose)["backend"] == "llm"
        assert called == ["llm"], "the llm backend was asked, and it is opus"
        assert planner.MODEL == "claude-opus-5"
    finally:
        planner.llm = real
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if held is not None:
            os.environ["ANTHROPIC_API_KEY"] = held

    print("ok   agent.turn plans, orders by the kernel, and proposes only")


if __name__ == "__main__":
    demo()
