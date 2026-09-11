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

from catalogue import guard, validate, vocab

from agent import planner

CAT = planner.load()
OPS = CAT["operations"]
ALL_CAPS = set(vocab.CAPABILITIES)
ALL_STATES = set(vocab.STATES)


def verdicts(proposals, catalogue, *, caps, state, actor="agent"):
    """Run the guard over a plan, on the machine surface.

    This lives in the check, not in agent/planner.py, because nothing shipping
    calls it: the kernel runs the guard when a proposal is POSTed, and a second
    copy in the planner was one more place a confirmed argument could appear.
    Note what is not passed here either, and could not be by any utterance.
    """
    out = []
    for p in proposals:
        op = catalogue["operations"][p.operation]
        schema = validate.load(op["input"])
        out.append(guard.evaluate(op, caps=caps, state=state, payload=p.payload,
                                  surface=guard.MCP,
                                  validate=validate.make_validator(schema),
                                  actor=actor, scopes=None))
    return out


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
    for p, d in zip(proposals, verdicts(proposals, CAT, caps=ALL_CAPS, state=ALL_STATES)):
        outcome = d.audit.get("outcome", "")
        seen.add(outcome.split(":")[0])
        assert outcome != "allowed", f"{p.operation} came back committable"
        assert d.audit["surface"] == guard.MCP
    assert "proposed" in seen, "the check proved nothing: no proposal survived"


def test_an_irreversible_operation_is_refused_however_good_the_payload():
    op = OPS["phc.op.abha-link"]
    assert op["irreversibility"] == "irreversible", "this test picked the wrong atom"
    p = planner.Proposed(op["id"], sample_payload(op), "check", "router")
    d = verdicts([p], CAT, caps=ALL_CAPS, state={"registered"})[0]
    assert not d.allowed
    assert "human confirmation" in d.reason


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


def fill(op, utterance):
    payload, _ = planner.extract(op, utterance)
    return payload


def asked(op, utterance):
    return planner.extract(op, utterance)[1]


def test_it_fills_in_only_the_numbers_it_is_sure_about():
    op = OPS["phc.op.vitals-record"]
    got = fill(op, "bp 140/90, pulse 72, spo2 97")
    assert got == {"systolic": 140, "diastolic": 90, "pulse": 72, "spo2": 97}
    assert fill(op, "bp is 140 over 90")["diastolic"] == 90
    # A number with no field named next to it is left for the person to type.
    assert fill(op, "she is about 62 kilos today") == {}
    # And a spoken number is not the router's job at all: packages/voice parses
    # it at the microphone, where it can be read back before anyone commits.
    assert fill(op, "systolic one forty") == {}


def test_the_field_names_are_the_ones_packages_voice_already_knew():
    """One alias list, in packages/voice/src/spoken.json, read by both. Before
    this, "temperature 37.2" parsed here and "temp 37.2" did not, while the
    microphone understood both."""
    op = OPS["phc.op.vitals-record"]
    assert fill(op, "temp 37.2") == {"temperature": 37.2}
    assert fill(op, "temperature 37.2") == {"temperature": 37.2}
    assert fill(op, "sats 97 and hr 88") == {"spo2": 97, "pulse": 88}
    assert planner.SPOKEN_FIELDS["temperature"] == ["temperature", "temp", "fever"]


def test_it_fills_text_answers_from_the_words_that_named_them():
    op = OPS["phc.op.consult-document"]
    got = fill(op, "document the consultation, assessment is hypertension poorly controlled")
    assert got == {"assessment": "hypertension poorly controlled"}, got
    # A colon, and a second labelled clause that ends the first.
    got = fill(op, "history: cough for three days. plan is amlodipine 5mg daily")
    assert got == {"history": "cough for three days",
                   "plan": "amlodipine 5mg daily"}, got
    # The bare form, with no lead-in word at all, several clauses in a row.
    assert fill(op, "examination chest clear")["examination"] == "chest clear"
    assert fill(op, "opd note, history: fever three days, examination chest clear, "
                    "assessment viral fever, plan is paracetamol") == {
        "history": "fever three days", "examination": "chest clear",
        "assessment": "viral fever", "plan": "paracetamol"}
    # A field name inside a clause is not a new label unless it is used as one.
    assert fill(op, "assessment of history of asthma")["assessment"] == "history of asthma"
    # Nothing named, nothing filled. The clinician finishes it on screen.
    assert fill(op, "document the consultation") == {}


def test_a_clause_ends_where_the_form_s_own_next_word_begins():
    """Text, numbers and a choice in one breath, which is how it is said. A
    clause stops at the next word the operation declares, so the phone number
    does not swallow the sex that followed it."""
    got = fill(OPS["phc.op.patient-register"],
               "register her, name is Sunita Devi, age 34, village Yadiki, "
               "phone 9876543210, female")
    assert got == {"name": "Sunita Devi", "age": 34, "village": "Yadiki",
                   "phone": "9876543210", "sex": "female"}, got
    # override_reason can never be answered here, so it does not get to make
    # "value" an ambiguous name for the field that can be.
    lab = fill(OPS["phc.op.lab-result-enter"],
               "bench result, analyte is glucose, value 5.4, unit mmol per litre")
    assert lab == {"analyte": "glucose", "value": 5.4, "unit": "mmol per litre"}, lab


def test_a_choice_is_matched_against_the_declared_options():
    op = OPS["phc.op.household-visit"]
    assert fill(op, "household visit, immunisation")["visit_type"] == "immunisation"
    # The option value is spelled with an underscore and nobody says that.
    assert fill(op, "household visit for tb followup")["visit_type"] == "tb_followup"


def test_an_ambiguous_choice_is_asked_about_rather_than_guessed():
    op = OPS["phc.op.household-visit"]
    payload, ask = planner.extract(op, "household visit for the followup")
    assert "visit_type" not in payload, "it guessed between two options"
    assert len(ask) == 1 and "tb_followup or ncd_followup" in ask[0], ask
    assert ask[0].endswith("?")
    # And the unambiguous form asks nothing.
    assert asked(op, "household visit for tb followup") == ()


def test_it_does_not_invent_the_answers_it_cannot_hear():
    op = OPS["phc.op.patient-register"]
    got = fill(op, "register a new female patient, age 34, from Yadiki")
    assert got["age"] == 34 and got["sex"] == "female"
    assert "name" not in got and "village" not in got, "the router invented an answer"
    # Which is why it is denied, not committed, with the name still missing.
    d = verdicts([planner.Proposed(op["id"], got, "check", "router")],
                 CAT, caps=ALL_CAPS, state=set())[0]
    assert not d.allowed and "name is required" in d.reason


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
