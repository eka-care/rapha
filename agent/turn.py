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

from agent import planner

UNSURE = ("I do not know which operation that is, and I will not guess: a "
          "wrong proposal in front of a busy clinician is worse than none.")

# What to do next, per kind of refusal. The guard's own reason is passed
# through unedited and is the first half of the sentence; this is only the
# second half. Keyed by the prefix catalogue/guard.py writes.
NEXT = (
    ("payload invalid", "Open the form on screen and fill in the rest. I only "
                        "fill what the words actually said."),
    ("missing capability", "This account does not hold that capability. "
                           "Someone who does has to do it."),
    ("outside scope", "That is outside this account's scope of practice."),
    # A separation of duties rule is about WHO, not about the visit, so it
    # gets its own half sentence. It has to come first: both reasons begin
    # "precondition not met".
    ("precondition not met: not actor of",
     "Somebody else has to do this one. Whoever did the step it names cannot "
     "also do this, whatever capabilities they hold."),
    ("precondition not met: actor of",
     "Only the person who did the step it names may do this one."),
    # Both polarities: "consult.documented" is not done yet, "not
    # vitals.recorded" is already done. The guard's reason names which; this
    # half must be true of either, so it claims no order of its own.
    ("precondition not met", "The state of this visit does not satisfy that. "
                             "The kernel decides what is open here, not me."),
    ("irreversible", "Irreversible work is done on screen with an explicit tap. "
                     "I cannot propose it, and that is deliberate."),
    ("not a step of", "This line has no station that draws it, so it cannot "
                      "happen on this visit at all."),
)
NEXT_OTHERWISE = "Open it on screen if it should still happen."


def next_step(reason: str) -> str:
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
         actions, station, confidence) -> dict:
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
        "verdict": {
            "allowed": allowed,
            # The guard's words, unedited. Paraphrasing a refusal is how an
            # agent starts inventing policy.
            "reason": decision_reason,
            "next": "" if allowed else next_step(decision_reason),
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
    if any(c["verdict"]["allowed"] for c in cards):
        lines.append("Nothing is recorded until you confirm it on screen. "
                     "I have no way to do that.")
    return " ".join(lines)


def take(utterance: str, *, catalogue: dict, view: dict, propose,
         confidence=None, which: str = None) -> dict:
    """Plan, order by the kernel, propose each, and report every verdict.

    propose: callable(operation_id, payload) -> (proposal_id|None, reason, flags)
             The only thing here that touches a store, injected so this runs
             without one. There is no second callable and there must not be:
             a confirm argument would be a hole a sentence could reach.

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
        p = planner.Proposed(p.operation, planner.typed(op, p.payload), p.why,
                             p.backend, p.score)
        proposal_id, reason, flags = propose(p.operation, p.payload)
        cards.append(card(op, p, reason, proposal_id, flags, actions=actions,
                          station=view.get("station"), confidence=confidence))
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

    def field(link_id, type_="integer"):
        return {"link_id": link_id, "type": type_, "text": link_id,
                "required": True, "options": []}

    cat = {"operations": {
        "x.op.vitals": op("x.op.vitals", "Record vitals", "vitals.record",
                          [field("systolic"), field("diastolic"), field("pulse")]),
        "x.op.dispense": op("x.op.dispense", "Dispense", "pharmacy.dispense",
                            [field("medicines", "string")]),
    }}
    view = {"id": "t-1", "station": "nurse", "flags": [], "held": ["vitals.record"],
            "actions": [{"id": "x.op.vitals", "station": "nurse",
                         "title": "Record vitals"}]}

    sent = []

    def propose(operation, payload):
        sent.append((operation, dict(payload)))
        if operation == "x.op.vitals":
            return "prop-1", "proposed", ["vitals.flagged"]
        return None, "precondition not met: rx.prescribed", []

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
    assert "confirm it on screen" in turn["said"]

    # An operation the kernel does not offer here is still sent, and comes back
    # with the guard's own reason and a next step.
    refused = take("dispense the medicines", catalogue=cat, view=view,
                   propose=propose, which="router")["proposals"][0]
    assert refused["proposal_id"] is None
    assert refused["verdict"]["reason"] == "precondition not met: rx.prescribed"
    assert "does not satisfy that" in refused["verdict"]["next"]
    # A separation of duties refusal shares that prefix and must not share
    # that sentence: it is about who is asking, not about the visit.
    assert "Somebody else has to do this one" in next_step(
        "precondition not met: not actor of lab.op.result-enter")
    assert "does not satisfy that" not in next_step(
        "precondition not met: not actor of lab.op.result-enter")
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

    assert [s[0] for s in sent] == ["x.op.vitals", "x.op.vitals", "x.op.dispense"]

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
