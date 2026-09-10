"""Run: python3 -m agent.tests.test_planner

The one property worth a check here is negative: the planner cannot commit. So
the central test is not "the router understands X", it is "no plan the router
can produce, for any operation in the catalogue, with every capability held and
every precondition met and a payload the validator accepts, comes back allowed".
It comes back proposed, which is a person's job to finish.

No network, no key, no model: the router is deterministic by design and the LLM
backend is not exercised here, which is stated rather than hidden.
"""
import pathlib

from catalogue import validate, vocab

from agent import planner

CAT = planner.load()
OPS = CAT["operations"]
ALL_CAPS = set(vocab.CAPABILITIES)
ALL_STATES = set(vocab.STATES)


def sample_payload(op):
    """The smallest payload the validator accepts, built from the questionnaire
    so it stays right when a form changes."""
    schema = validate.load(op["input"])
    payload = {}
    for q in validate.walk(schema["questions"]):
        if not q.get("required"):
            continue
        phc = (q.get("styling_metadata") or {}).get("phc") or {}
        rng = phc.get("range")
        kind = q["type"]
        if kind == "choice":
            payload[q["link_id"]] = q["answer_option"][0]["value"]
        elif kind == "boolean":
            payload[q["link_id"]] = True
        elif kind in ("integer", "decimal"):
            mid = (rng["low"] + rng["high"]) / 2 if rng else 1
            payload[q["link_id"]] = int(mid) if kind == "integer" else float(mid)
        elif kind == "structured":
            payload[q["link_id"]] = {"item": "one"}
        else:
            payload[q["link_id"]] = "recorded by the check"
    return payload


def test_no_plan_can_ever_commit():
    """Every operation, everything held, everything met, a valid payload."""
    proposals = [planner.Proposed(op_id, sample_payload(op), "check", "router")
                 for op_id, op in OPS.items()]
    seen = set()
    for v in planner.verdicts(proposals, CAT, caps=ALL_CAPS, state=ALL_STATES):
        seen.add(v.outcome.split(":")[0])
        assert v.outcome != "allowed", f"{v.proposed.operation} came back committable"
        assert v.decision.audit["surface"] == planner.guard.MCP
    assert "proposed" in seen, "the check proved nothing: no proposal survived"


def test_an_irreversible_operation_is_refused_however_good_the_payload():
    op = OPS["phc.op.abha-link"]
    assert op["irreversibility"] == "irreversible", "this test picked the wrong atom"
    p = planner.Proposed(op["id"], sample_payload(op), "check", "router")
    v = planner.verdicts([p], CAT, caps=ALL_CAPS, state={"registered"})[0]
    assert not v.decision.allowed
    assert "human confirmation" in v.decision.reason


def test_the_planner_has_no_way_to_confirm_anything():
    """The guard's confirm argument exists. Nothing in this package passes it,
    and a source check is the honest way to say so: a future edit that adds one
    fails here rather than in production."""
    for path in sorted(pathlib.Path(__file__).parents[1].glob("*.py")):
        source = path.read_text()
        for hazard in ('confirmed=', '"confirmed"', "'confirmed'", "RENDERED"):
            assert hazard not in source, f"{path.name} contains {hazard}"


def test_the_router_matches_what_people_actually_say():
    said = {
        "record her bp and pulse": "phc.op.vitals-record",
        "new patient, register her": "phc.op.patient-register",
        "link her abha": "phc.op.abha-link",
        "prescribe amlodipine": "phc.op.rx-prescribe",
        "order a blood sugar test": "phc.op.lab-order",
        "dispense what the doctor wrote": "phc.op.pharmacy-dispense",
        "enter the bench result": "phc.op.lab-result-enter",
        "asha household visit at the door": "phc.op.household-visit",
        "document the consultation": "phc.op.consult-document",
    }
    for utterance, expected in said.items():
        got = [p.operation for p in planner.route(utterance, CAT)]
        assert got and got[0] == expected, f"{utterance!r} routed to {got}"


def test_the_router_refuses_rather_than_guessing():
    for utterance in ("good morning", "", "is the doctor in today", "thanks"):
        assert planner.route(utterance, CAT) == [], f"{utterance!r} produced a plan"


def test_it_fills_in_only_the_numbers_it_is_sure_about():
    op = OPS["phc.op.vitals-record"]
    got = planner.extract(op, "bp 140/90, pulse 72, spo2 97")
    assert got == {"systolic": 140, "diastolic": 90, "pulse": 72, "spo2": 97}
    assert planner.extract(op, "bp is 140 over 90")["diastolic"] == 90
    # A number with no field named next to it is left for the person to type.
    assert planner.extract(op, "she is about 62 kilos today") == {}
    # And a spoken number is not the router's job at all: packages/voice parses
    # it at the microphone, where it can be read back before anyone commits.
    assert planner.extract(op, "systolic one forty") == {}


def test_it_does_not_invent_the_answers_it_cannot_hear():
    op = OPS["phc.op.patient-register"]
    got = planner.extract(op, "register a new female patient, age 34, from Yadiki")
    assert got["age"] == 34 and got["sex"] == "female"
    assert "name" not in got and "village" not in got, "the router invented an answer"
    # Which is why it is denied, not committed, with the name still missing.
    v = planner.verdicts([planner.Proposed(op["id"], got, "check", "router")],
                         CAT, caps=ALL_CAPS, state=set())[0]
    assert not v.decision.allowed and "name is required" in v.decision.reason


class _Block:
    def __init__(self, name, payload):
        self.type, self.name, self.input = "tool_use", name, payload


class _StubClient:
    """Stands in for anthropic.Anthropic. The live call is not exercised here;
    what is exercised is what this package does with an answer."""

    def __init__(self, blocks):
        self.blocks = blocks
        self.messages = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return type("Reply", (), {"content": self.blocks})()


def test_the_llm_backend_drops_what_the_catalogue_does_not_hold():
    stub = _StubClient([_Block("propose_operations", {"operations": [
        {"operation": "phc.op.vitals-record", "payload": {"systolic": 140}, "why": "said so"},
        {"operation": "phc.op.discharge-patient", "payload": {}, "why": "invented"},
        {"operation": "phc.op.rx-prescribe", "payload": "not a dict", "why": "wrong shape"},
    ]})])
    got = planner.llm("her bp is 140", CAT, caps=ALL_CAPS, state={"registered"}, client=stub)
    assert [p.operation for p in got] == ["phc.op.vitals-record", "phc.op.rx-prescribe"]
    assert got[0].payload == {"systolic": 140} and got[1].payload == {}
    assert stub.kwargs["model"] == "claude-opus-5"
    assert "propose" in stub.kwargs["tools"][0]["name"]
    # The prompt carries the catalogue, so the model has ids to pick, not invent.
    assert "phc.op.vitals-record" in stub.kwargs["messages"][0]["content"]


def test_no_tool_call_means_no_plan():
    quiet = _StubClient([type("T", (), {"type": "text", "text": "I am not sure."})()])
    assert planner.llm("mm", CAT, caps=ALL_CAPS, state=set(), client=quiet) == []


def test_the_backend_switch_is_the_key_and_nothing_else():
    import os
    before = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert planner.backend() == "router"
        os.environ["ANTHROPIC_API_KEY"] = "sk-not-a-real-key"
        assert planner.backend() == "llm"
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if before is not None:
            os.environ["ANTHROPIC_API_KEY"] = before


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            ran += 1
    print(f"ok   agent planner: {ran} checks, and no plan can commit")
