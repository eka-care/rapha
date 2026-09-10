"""Turn an utterance into PROPOSED operations. Two backends, one interface.

The agent is the primary way into this system, which is exactly why it is the
least trusted caller in it. Nothing here decides anything: a planner picks
operations and fills in what it is sure of, and then catalogue.guard.evaluate()
decides, on the machine surface, where a write can only ever come back
"proposed". A person confirms it on the rendered surface, or it does not happen.

There are two backends because tonight has no API key and a demo has to run:

  route()  deterministic. Scores each compiled operation against the words in
           the utterance, using the catalogue itself as the vocabulary. No
           network, no key, no model. Refuses when nothing scores.
  llm()    the anthropic SDK, claude-opus-5, used when ANTHROPIC_API_KEY is
           set. It is handed the same catalogue and can only answer with
           operation ids from it.

Neither backend can bypass the guard, and neither is trusted to have got the
payload right: both produce Proposed, both go through verdicts(), and
verdicts() never passes confirmed. An irreversible operation is denied on this
surface before the guard even looks at confirmation, which is the property the
CLI demonstrates.

Honest about what is unverified: route() is exercised by the check in
agent/tests/test_planner.py. llm() has never been run, because this machine has
no ANTHROPIC_API_KEY. Its request shape follows the current SDK docs; treat the
first live run as the test.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass

from catalogue import guard, validate

CATALOGUE = pathlib.Path(__file__).parents[1] / "catalogue" / "catalogue.json"
MODEL = "claude-opus-5"


@dataclass(frozen=True)
class Proposed:
    """What a planner wants. Not a decision, and not a write."""
    operation: str
    payload: dict
    why: str
    backend: str
    score: float = 0.0


@dataclass(frozen=True)
class Verdict:
    proposed: Proposed
    decision: guard.Decision

    @property
    def outcome(self) -> str:
        return self.decision.audit.get("outcome", "")


def load(path=CATALOGUE) -> dict:
    cat = json.loads(pathlib.Path(path).read_text())
    # catalogue/ops is shared between bundles (bundles/lab has its own atoms
    # there), and the router must plan only over what the kernel loaded, which
    # the manifest names. The API's /catalogue is already narrowed this way.
    listed = (cat.get("manifest") or {}).get("operations")
    if listed:
        cat["operations"] = {k: v for k, v in cat["operations"].items() if k in listed}
    return cat


# --------------------------------------------------------------------------
# The deterministic router.
# --------------------------------------------------------------------------

# Words that carry no signal. Short on purpose: a stopword list that grows is a
# list nobody maintains, and a stray match costs one point out of several.
STOP = frozenset("""
a an and are as at be by for from has have how in into is it its of on or that
the this to was what when where which who will with you your patient patients
their her his please record records new
""".split())

# Spoken words the catalogue does not contain. This is the only hand written
# vocabulary in the router, and every entry is a word a nurse says out loud
# that no frontmatter field would ever hold.
SPOKEN = {
    "phc.op.patient-register": ["register", "enrol", "enroll", "registration", "intake"],
    "phc.op.abha-link": ["abha", "aadhaar", "aadhar", "ayushman", "link"],
    "phc.op.vitals-record": ["bp", "pressure", "sats", "obs", "triage", "vitals"],
    "phc.op.consult-document": ["consult", "consultation", "note", "opd", "seen", "history"],
    "phc.op.rx-prescribe": ["prescribe", "prescription", "medicine", "medicines", "drug",
                            "tablet", "tablets", "rx"],
    "phc.op.lab-order": ["test", "tests", "investigation", "investigations", "cbc", "sugar"],
    "phc.op.lab-result-enter": ["result", "results", "report", "bench", "analyte"],
    "phc.op.pharmacy-dispense": ["dispense", "issue", "pharmacy", "stock", "handout"],
    "phc.op.household-visit": ["household", "home", "visit", "doorstep", "field"],
}

# A keyword from the operation's own identity is worth more than one from its
# prose, because prose is shared between operations and identity is not.
STRONG, WEAK = 2, 1


def _words(text: str):
    return [w for w in re.split(r"[^a-z0-9]+", str(text).lower()) if w and w not in STOP]


def keywords(op: dict) -> dict:
    """The vocabulary of one operation, weighted. Derived from the compiled
    catalogue so a new atom is routable the moment it lints."""
    weights = {}

    def add(text, weight):
        for w in _words(text):
            weights[w] = max(weights.get(w, 0), weight)

    add(op["id"].rsplit(".", 1)[-1], STRONG)
    add(op["capability"].replace(".", " "), STRONG)
    add(op["short"], STRONG)
    for w in SPOKEN.get(op["id"], []):
        weights[w] = STRONG
    add(op["title"], WEAK)
    add(op["summary"], WEAK)
    for f in op["fields"]:
        add(f["link_id"], WEAK)
    return weights


# A number next to a field name. Deliberately narrow: digits only. Spoken
# numbers ("one forty") are parsed at the point of capture by packages/voice,
# where the value can be read back on screen before anyone commits it.
_NUM = r"(\d+(?:\.\d+)?)"
_PAIR = re.compile(r"\b(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b")


def _aliases(f: dict):
    """Spoken names for one field: its link_id and the distinctive words of its
    label. Ambiguous words are dropped by the caller, not resolved."""
    return {f["link_id"].lower()} | {w for w in _words(f["text"]) if len(w) > 2}


def extract(op: dict, utterance: str) -> dict:
    """Fill in only what is unambiguous. A thin payload is the normal outcome:
    the rest is typed at the rendered surface, and the guard denies a proposal
    that is missing a required answer rather than the planner inventing one."""
    text = utterance.lower()
    payload = {}
    ids = {f["link_id"] for f in op["fields"]}

    # "140/90" and "140 over 90", the way blood pressure is actually said.
    pair = _PAIR.search(text)
    if pair and {"systolic", "diastolic"} <= ids:
        payload["systolic"] = int(pair.group(1))
        payload["diastolic"] = int(pair.group(2))
        text = text[: pair.start()] + " " + text[pair.end():]

    # A word that names more than one field names none of them.
    seen = {}
    for f in op["fields"]:
        for alias in _aliases(f):
            seen.setdefault(alias, []).append(f["link_id"])
    unique = {a: ids[0] for a, ids in seen.items() if len(ids) == 1}

    for f in op["fields"]:
        if f["link_id"] in payload:
            continue
        names = sorted(a for a in _aliases(f) if unique.get(a) == f["link_id"])
        if f["type"] in ("integer", "decimal") and names:
            alt = "|".join(re.escape(n) for n in names)
            m = re.search(r"\b(?:%s)\b\D{0,12}%s" % (alt, _NUM), text)
            if m:
                value = float(m.group(1))
                payload[f["link_id"]] = int(value) if f["type"] == "integer" else value
        elif f["type"] == "choice" and f["options"]:
            hits = [o for o in f["options"] if re.search(r"\b%s\b" % re.escape(o.lower()), text)]
            if len(hits) == 1:
                payload[f["link_id"]] = hits[0]
    return payload


def typed(op: dict, payload) -> dict:
    """Keep only answers the operation actually declares.

    The validator ignores a key it does not know, which means an invented key
    rides along into the proposal a person then taps. Two of those are
    dangerous rather than untidy: override_reason waives the physiological
    range check, and any stray key is a value nobody typed. So a planner may
    answer the questions the questionnaire asks and nothing else. A person can
    still override at the rendered surface, by writing the reason themselves.
    """
    if not isinstance(payload, dict):
        return {}
    allowed = {f["link_id"] for f in op["fields"]} - {"override_reason"}
    return {k: v for k, v in payload.items() if k in allowed}


def route(utterance: str, catalogue: dict, *, limit: int = 3) -> list:
    """Match an utterance to operations, using only the compiled catalogue.

    Needs at least two points before it will name an operation, so a single
    incidental word does not conjure a proposal out of small talk.
    """
    said = set(_words(utterance))
    scored = []
    for op in catalogue["operations"].values():
        kws = keywords(op)
        hits = sorted(w for w in said if w in kws)
        score = sum(kws[w] for w in hits)
        if score < STRONG:
            continue
        scored.append(Proposed(
            operation=op["id"],
            payload=extract(op, utterance),
            why="matched " + ", ".join(hits),
            backend="router",
            score=score,
        ))
    scored.sort(key=lambda p: (-p.score, p.operation))
    return scored[:limit]


# --------------------------------------------------------------------------
# The LLM backend.
# --------------------------------------------------------------------------

SYSTEM = """You plan work at an Indian primary health centre.

You do not perform operations. You propose them. Every proposal is shown to a
clinician who confirms or rejects it, and a guard checks capabilities,
preconditions and payload validity after you, so a wrong proposal is caught and
an invented value is not.

Rules:
- Only propose operations from the catalogue you are given, by exact id.
- Only fill a field when the utterance actually says it. Leave the rest out.
  A missing answer is filled in by the person; an invented one is a clinical
  error with your name on it.
- Never propose an operation whose preconditions the given thread state does
  not meet, and never propose more than the utterance asks for.
- If the utterance names no operation you are sure of, propose nothing.
- Call the propose_operations tool exactly once, even when the list is empty.
"""

TOOL = {
    "name": "propose_operations",
    "description": "Propose operations for a person to confirm. Never commits anything.",
    "input_schema": {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string", "description": "a catalogue operation id"},
                        "payload": {"type": "object", "description": "answers the utterance stated"},
                        "why": {"type": "string", "description": "one short sentence"},
                    },
                    "required": ["operation", "payload", "why"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["operations"],
        "additionalProperties": False,
    },
    # No "strict": true. Strict tool use requires every object in the schema to
    # be closed, and `payload` cannot be: its keys are one operation's link_ids
    # and differ per operation. An untested strict flag that 400s on the first
    # live call would be worse than the check we already do, which is typed():
    # the payload is filtered against the operation's own fields after the
    # model answers, so an unknown key never reaches the guard either way.
}


def _brief(catalogue: dict, caps) -> list:
    """What the model is allowed to see: the operations this account can hold a
    capability for, and nothing about any patient."""
    return [
        {"id": op["id"], "title": op["title"], "does": op["description"],
         "preconditions": op["preconditions"], "irreversibility": op["irreversibility"],
         "fields": [{"link_id": f["link_id"], "type": f["type"], "text": f["text"],
                     "required": f["required"], "options": f["options"]}
                    for f in op["fields"]]}
        for op in catalogue["operations"].values() if op["capability"] in caps
    ]


def llm(utterance: str, catalogue: dict, *, caps, state, model: str = MODEL,
        client=None) -> list:
    """Plan with claude-opus-5. Still unverified against api.anthropic.com:
    there is no key on this machine. What is verified is one step better than
    a stub: agent/tests/test_live.py runs the real SDK against a fake endpoint
    on a loopback port, so the kwargs, the tool definition and the pydantic
    reply objects are exercised. Whether Anthropic accepts this tool schema is
    the open question, and the first live call is its first test.

    Fails closed in three ways. No tool call means no proposals; an operation
    id the catalogue does not hold is dropped rather than repaired; and a
    payload key the operation does not declare is dropped by typed(), so the
    model emits typed proposals or it emits nothing. Free text never executes:
    `why` is printed and nothing reads it back.
    `client` exists so the check can hand in a stub; it is not a config knob.
    """
    if client is None:
        import anthropic  # imported here so the router works without the SDK
        client = anthropic.Anthropic()
    prompt = json.dumps({
        "utterance": utterance,
        "thread_state": sorted(state),
        "capabilities_held": sorted(caps),
        "operations": _brief(catalogue, caps),
    }, indent=2)

    # tool_choice stays "auto" with the instruction in the system prompt: this
    # code has not been run, and auto is the shape that works on every current
    # model. No tool call is a legitimate answer, and it means no proposals.
    message = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM,
        tools=[TOOL],
        messages=[{"role": "user", "content": prompt}],
    )

    out = []
    for block in message.content:
        if getattr(block, "type", None) != "tool_use" or block.name != TOOL["name"]:
            continue
        for item in (block.input or {}).get("operations") or []:
            op_id = item.get("operation")
            if op_id not in catalogue["operations"]:
                continue  # a hallucinated id is dropped, not repaired
            out.append(Proposed(
                operation=op_id,
                # typed() is the trust boundary: the model answers the
                # questionnaire's questions or it answers nothing.
                payload=typed(catalogue["operations"][op_id], item.get("payload")),
                why=str(item.get("why") or "")[:200],
                backend="llm",
            ))
    return out


def backend() -> str:
    """Which planner is live. The key is the switch; there is nothing to config."""
    return "llm" if os.environ.get("ANTHROPIC_API_KEY") else "router"


def plan(utterance: str, catalogue: dict, *, caps, state, which: str = None) -> list:
    """The one interface. Returns Proposed, never a decision and never a write."""
    which = which or backend()
    if which == "llm":
        return llm(utterance, catalogue, caps=caps, state=state)
    return route(utterance, catalogue)


# --------------------------------------------------------------------------
# The guard. Every plan, from either backend, goes through here.
# --------------------------------------------------------------------------

def verdicts(proposals, catalogue: dict, *, caps, state, actor="agent", scopes=None) -> list:
    """Run the guard over a plan on the machine surface.

    Note what is not passed: confirmed. There is no argument to this function
    that could set it, so no planner, prompt or utterance can reach it. A write
    that survives comes back "proposed" and waits for a person.
    """
    out = []
    for p in proposals:
        op = catalogue["operations"][p.operation]
        schema = validate.load(op["input"])
        decision = guard.evaluate(
            op,
            caps=caps,
            state=state,
            payload=p.payload,
            surface=guard.MCP,
            validate=validate.make_validator(schema),
            actor=actor,
            scopes=scopes,
        )
        out.append(Verdict(p, decision))
    return out


# --------------------------------------------------------------------------
# Ordering. Read from the kernel, never computed here.
# --------------------------------------------------------------------------

def by_kernel_order(proposals, actions) -> list:
    """Sort a plan into the order the kernel already put its actions in.

    ThreadView.actions is kernel/state.py actions(): visible operations sorted
    by this thread's current station and then by the declared line. That is the
    ordering, and it is not this package's to have an opinion about. route()
    scores how well an utterance names an operation, which is a different
    question; that score decides what was heard, never what to do next.

    An operation the kernel does not list here sorts last and is still sent, so
    the guard gets to state the refusal rather than the agent guessing it.
    """
    rank = {op["id"]: i for i, op in enumerate(actions)}
    return sorted(proposals, key=lambda p: (rank.get(p.operation, len(rank)), p.operation))


def explain_order(proposal, actions, station=None) -> str:
    """One sentence about where the kernel puts this, sourced from the kernel."""
    ids = [op["id"] for op in actions]
    if proposal.operation not in ids:
        return ("the kernel does not offer this on this thread now"
                + (" (it is standing at %s)" % station if station else ""))
    place = ids.index(proposal.operation) + 1
    where = next(op["station"] for op in actions if op["id"] == proposal.operation)
    return "the kernel lists it %d of %d at %s" % (place, len(ids), where)
