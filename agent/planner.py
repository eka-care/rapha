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
payload right. Nothing in this module runs the guard: a plan is proposed
through the kernel, which runs it on the machine surface, and there is no
argument anywhere on this path that could set confirmed. An irreversible
operation is denied on that surface before the guard even looks at
confirmation, which is the property the CLI demonstrates.

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
    # What the planner heard but would not resolve, in its own words. A
    # question is the honest alternative to a guess; it is not a decision and
    # nothing reads it back as one.
    ask: tuple = ()


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


# Spoken names for a questionnaire field, keyed by link_id. ONE list, and it
# lives in packages/voice because that is where it already existed, where it is
# richest, and where it is data rather than code: grammar.ts imports this same
# JSON. Two lists would drift, and the way you find out is a clinician saying
# "temp 37.2" into a box that only knows "temperature". The better home is the
# questionnaire itself, beside the unit and the range that styling_metadata.phc
# already carries; that is an edit to questionnaires/ and not part of this
# change.
SPOKEN_FIELDS = json.loads(
    (pathlib.Path(__file__).parents[1] / "packages" / "voice" / "src" / "spoken.json")
    .read_text())


def _aliases(f: dict):
    """Spoken names for one field: its link_id, the distinctive words of its
    label, and the spoken names packages/voice already knew. Ambiguous words
    are dropped by the caller, not resolved."""
    return ({f["link_id"].lower()}
            | {a.lower() for a in SPOKEN_FIELDS.get(f["link_id"], ())}
            | {w for w in _words(f["text"]) if len(w) > 2})


# Between a field's name and its answer: "assessment is X", "history: X",
# "assessment of X", and the bare "assessment X". Matches empty, which is the
# last of those.
_LEADIN = re.compile(r"[\s:=,-]*(?:(?:is|was|are|were|of|reads|shows|says)\b)?[\s:=,-]*")
# A later field name only ends the clause when it is being used as a label:
# either it is followed by a lead-in ("plan is amlodipine") or it opens a fresh
# clause ("..., examination chest clear"). "history of hypertension" is neither,
# so it stays inside the answer it was said in.
_LABELLED = re.compile(r"\s*(?:[:=-]|(?:is|was|are|were)\b)")


def _is_label(text: str, start: int, end: int) -> bool:
    before = text[:start].rstrip()
    return bool(_LABELLED.match(text, end)) or before == "" or before[-1] in ",.;"


def _clauses(fields: list, unique: dict, text: str, utterance: str) -> dict:
    """Text answers, sliced out of the utterance by the words themselves.

    A field's own name marks where its answer starts; the answer runs to the
    end of what was said, or to the next word the form owns that is being used
    as a label, whichever comes first. Nothing is invented: every character
    returned was spoken.

    Two vocabularies, deliberately different sizes. Only an unambiguous field
    name may START a clause, because starting one is a claim about which field
    the words belong to. Anything the operation declares may END one: an
    ambiguous field name, a numeric field's name, a declared answer option.
    Ending a clause early only ever gives a person less to correct.

    ponytail: one clause per field, first mention wins, and a declared word
    that opens a clause of its own always ends the one before it, so "history:
    pain, plan to come back" ends the history at "pain". The upgrade path is a
    real chunker, and it is not worth it until a transcript proves it is needed.
    """
    def marks(words):
        found = []
        for word in words:
            for m in re.finditer(r"\b%s\b" % re.escape(word), text):
                found.append((m.start(), m.end()))
        return sorted(found)

    owned = set()
    for f in fields:
        owned |= _aliases(f)
        for option in f["options"] or []:
            owned |= {w for w in re.split(r"[^a-z0-9]+", option.lower()) if w}
    ends = marks(owned)

    starts = sorted((s, e, link_id) for alias, link_id in unique.items()
                    for s, e in marks([alias]))

    out, claimed = {}, []
    for start, end, link_id in starts:
        # A name said inside somebody else's answer is part of that answer, not
        # a label of its own: "assessment of history of asthma" is one clause,
        # and the history in it is not a second.
        if link_id in out or any(b <= start < e for b, e in claimed):
            continue
        begin = _LEADIN.match(text, end).end()
        stop = len(text)
        for other_start, other_end in ends:
            if other_start >= begin and _is_label(text, other_start, other_end):
                stop = other_start
                break
        value = utterance[begin:stop].strip(" \t\n.,;:-")
        if len(value) > 1:
            out[link_id] = value
            claimed.append((begin, stop))
    return out


def _choice(f: dict, text: str):
    """One declared answer_option, or a question. Never a guess.

    Matched against the values the questionnaire declares, so "venous blood"
    finds "venous-blood" and nothing has to be spelled with a hyphen out loud.
    When two options fit the words equally well the pair is named and asked
    about, because picking one of them is exactly the kind of quiet decision
    this whole system exists to refuse.
    """
    words = {o: [w for w in re.split(r"[^a-z0-9]+", o.lower()) if w] for o in f["options"]}
    fits = [o for o, ws in words.items()
            if ws and re.search(r"\b%s\b" % r"\W+".join(re.escape(w) for w in ws), text)]
    if not fits:
        # No whole option was said. A single word of one, and only one, option
        # is still the option; a word two of them share is a question.
        fits = [o for o, ws in words.items()
                if any(w not in STOP and re.search(r"\b%s\b" % re.escape(w), text) for w in ws)]
    if len(fits) == 1:
        return fits[0], None
    if len(fits) > 1:
        return None, ("Which did you mean for %s: %s?"
                      % (f["text"], " or ".join([", ".join(fits[:-1]), fits[-1]])))
    return None, None


def extract(op: dict, utterance: str):
    """Fill in only what is unambiguous. Returns (payload, questions).

    A thin payload is the normal outcome and the correct one: the rest is typed
    at the rendered surface, and the guard denies a proposal that is missing a
    required answer rather than the planner inventing one. Nothing here writes
    a value the utterance did not contain, in any of the four shapes it reads:
    the blood pressure pair, a number beside a field name, a declared choice,
    and a text clause introduced by the field's own name.
    """
    low = str(utterance).lower()
    if len(low) != len(utterance):
        # A case fold that changed the width would misalign every text slice.
        utterance = low
    text = low
    payload, asks = {}, []
    # typed() strips override_reason before the guard ever sees it, so this
    # planner can never answer it. A field it cannot answer should not be
    # taking alias words off the fields it can: "Reason for accepting a value
    # outside the plausible band" was quietly making "value" ambiguous.
    fields = [f for f in op["fields"] if f["link_id"] != "override_reason"]
    ids = {f["link_id"] for f in fields}

    # "140/90" and "140 over 90", the way blood pressure is actually said.
    pair = _PAIR.search(text)
    if pair and {"systolic", "diastolic"} <= ids:
        payload["systolic"] = int(pair.group(1))
        payload["diastolic"] = int(pair.group(2))
        # Blanked in place rather than cut out, so the offsets a text clause is
        # sliced with still line up with the utterance.
        text = text[: pair.start()] + " " * (pair.end() - pair.start()) + text[pair.end():]

    # A word that names more than one field names none of them.
    seen = {}
    for f in fields:
        for alias in _aliases(f):
            seen.setdefault(alias, []).append(f["link_id"])
    unique = {a: names[0] for a, names in seen.items() if len(names) == 1}
    clauses = _clauses(fields, unique, text, utterance)

    for f in fields:
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
            value, ask = _choice(f, text)
            if value is not None:
                payload[f["link_id"]] = value
            elif ask:
                asks.append(ask)
        elif f["type"] in ("text", "string") and f["link_id"] in clauses:
            payload[f["link_id"]] = clauses[f["link_id"]]
    return payload, tuple(asks)


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
        payload, ask = extract(op, utterance)
        scored.append(Proposed(
            operation=op["id"],
            payload=payload,
            why="matched " + ", ".join(hits),
            backend="router",
            score=score,
            ask=ask,
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
