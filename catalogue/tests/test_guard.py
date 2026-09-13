"""Run: python3 -m catalogue.tests.test_guard

The checks that matter are the ones that fail loudly if the safety properties
regress: an action visible before its precondition, a capability not enforced,
or an agent finding a way to commit an irreversible write.
"""
import json
import pathlib

from catalogue import guard

CAT = json.loads((pathlib.Path(__file__).parents[1] / "catalogue.json").read_text())
OPS = CAT["operations"]
ok = lambda *a, **k: []  # a validator that passes


def test_dispense_invisible_until_rx_confirmed():
    op = OPS["phc.op.pharmacy-dispense"]
    caps = {"pharmacy.dispense"}
    assert not guard.visible(op, caps, {"registered"}), "dispense shown with no Rx"
    assert guard.visible(op, caps, {"registered", "rx.confirmed"})
    assert not guard.visible(op, caps, {"rx.confirmed", "dispensed.complete"})


def test_capability_is_enforced_not_just_hidden():
    op = OPS["phc.op.pharmacy-dispense"]
    d = guard.evaluate(op, caps={"rx.prescribe"}, state={"rx.confirmed"},
                       payload={"q": 1}, surface=guard.RENDERED, validate=ok)
    assert not d and "missing capability" in d.reason


def test_precondition_denied_even_when_capability_held():
    op = OPS["phc.op.pharmacy-dispense"]
    d = guard.evaluate(op, caps={"pharmacy.dispense"}, state={"registered"},
                       payload={"q": 1}, surface=guard.RENDERED, validate=ok)
    assert not d and d.reason == "Requires rx confirmed.", d.reason


def test_agent_can_never_commit_an_irreversible_write():
    op = OPS["phc.op.abha-link"]
    assert op["irreversibility"] == "irreversible"
    for claimed in (False, True):
        d = guard.evaluate(op, caps={"abha.link"}, state={"registered"},
                           payload={"abha": "x"}, surface=guard.MCP,
                           confirmed=claimed, validate=ok)
        assert not d, "MCP surface committed an irreversible write"
        assert "rendered surface" in d.reason


def test_irreversible_needs_explicit_confirm_on_the_rendered_surface():
    op = OPS["phc.op.abha-link"]
    args = dict(caps={"abha.link"}, state={"registered"}, payload={"abha": "x"},
                surface=guard.RENDERED, validate=ok)
    assert not guard.evaluate(op, confirmed=False, **args)
    assert guard.evaluate(op, confirmed=True, **args)


def test_machine_writes_are_proposals_never_commits():
    op = OPS["phc.op.rx-prescribe"]
    args = dict(caps={"rx.prescribe"}, state={"consult.documented"},
                payload={"drug": "x"}, validate=ok)
    assert guard.evaluate(op, surface=guard.MCP, **args).reason == "proposed"
    assert guard.evaluate(op, surface=guard.RENDERED, **args).reason == "allowed"


def test_missing_validator_fails_closed():
    op = OPS["phc.op.lab-order"]
    d = guard.evaluate(op, caps={"lab.order"}, state={"consult.documented"},
                       payload={}, surface=guard.RENDERED)
    assert not d and "no validator" in d.reason


def test_denials_are_audited_too():
    op = OPS["phc.op.pharmacy-dispense"]
    d = guard.evaluate(op, caps=set(), state=set(), payload={"q": 1},
                       surface=guard.MCP, validate=ok, actor="u5")
    assert d.audit["outcome"].startswith("denied:")
    assert d.audit["actor"] == "u5" and d.audit["surface"] == guard.MCP


def test_an_agent_inherits_the_exclusions_of_the_person_it_acts_for():
    """The hole this closes: api/main.py proposes as `agent:<caller id>`, so
    without stripping the prefix the account that keyed a result could get the
    verify proposed for itself by dictating the sentence instead of tapping
    the button. It was refused on the confirm, but a card it could never
    accept was put in front of it, which is the greyed out button the
    invisibility rule exists to forbid."""
    op = OPS["lab.op.result-verify"]
    state = {"result.entered", "specimen.collected", "order.accessioned"}
    caps = {"result.verify"}
    performed = {"lab.op.result-enter": {"user:senior_technologist"}}

    for who in ("user:senior_technologist", "agent:user:senior_technologist"):
        assert not guard.visible(op, caps, state, who, performed), who
        d = guard.evaluate(op, caps=caps, state=state, payload={}, validate=ok,
                           surface=guard.MCP, actor=who, performers=performed)
        assert not d and d.reason == "Already performed lab op result enter.", who

    for who in ("user:pathologist", "agent:user:pathologist"):
        assert guard.visible(op, caps, state, who, performed), who


def test_registered_patient_denied_registration_reads_as_already_done():
    """The bug the product owner saw: `not registered` unmet means the flag
    IS present, so the message must say the patient already is one, not
    something a clerk reads as the opposite."""
    op = OPS["phc.op.patient-register"]
    d = guard.evaluate(op, caps={"patient.register"}, state={"registered"},
                       payload={}, surface=guard.RENDERED, validate=ok)
    assert not d
    assert d.reason == "Already registered.", d.reason


def test_no_denial_message_echoes_the_raw_precondition_in_either_bundle():
    """Would this still pass if the renderer ignored the precondition and
    printed the literal? No: every denial below is checked against the exact
    literal(s) that produced it, for both PHC and the laboratory, so a
    regression back to f"precondition not met: {pre}" fails here immediately."""
    cases = [
        # (op id, caps, state, actor, performers) -> raw precondition literals
        # that must never appear verbatim in the denial.
        ("phc.op.patient-register", {"patient.register"}, {"registered"}, None, None,
         ["not registered"]),
        ("phc.op.pharmacy-dispense", {"pharmacy.dispense"}, {"registered"}, None, None,
         ["rx.confirmed"]),
        ("lab.op.referral-accession", {"referral.accession"}, {"order.accessioned"}, None, None,
         ["not order.accessioned"]),
        ("lab.op.specimen-collect", {"specimen.collect"}, set(), None, None,
         ["order.accessioned"]),
    ]
    for oid, caps, state, actor, performers, literals in cases:
        d = guard.evaluate(OPS[oid], caps=caps, state=state, payload={},
                           surface=guard.RENDERED, validate=ok, actor=actor, performers=performers)
        assert not d, oid
        for literal in literals:
            assert literal not in d.reason, (oid, literal, d.reason)

    # The separation-of-duties case: `actor of` also gets a sentence, and the
    # unevaluable case (no actor supplied at all) never leaks the raw pre either.
    op = OPS["lab.op.result-verify"]
    state = {"result.entered", "specimen.collected", "order.accessioned"}
    d = guard.evaluate(op, caps={"result.verify"}, state=state, payload={},
                       surface=guard.RENDERED, validate=ok)  # no actor, no performers
    assert not d
    assert "actor of" not in d.reason and "lab.op.result-enter" not in d.reason, d.reason


def test_describe_precondition_is_derived_from_the_flag_never_a_lookup_table():
    """The three kinds, and that a made-up flag this table has never seen
    still reads as a sentence, which is the proof there is no lookup table of
    PHC strings hiding behind the renderer."""
    assert guard.describe_precondition("not registered") == "Already registered."
    assert guard.describe_precondition("rx.confirmed") == "Requires rx confirmed."
    assert guard.describe_precondition("not actor of lab.op.result-enter") == \
        "Already performed lab op result enter."
    assert guard.describe_precondition("actor of lab.op.result-enter") == \
        "Must be the person who performed lab op result enter."
    assert guard.describe_precondition("lab.op.result-enter", unevaluable=True) == \
        "Needs to know who is acting, to check whether they performed lab op result enter."
    # A flag this codebase has never named, proving there is no table of
    # known PHC strings behind the sentence.
    assert guard.describe_precondition("not something.brand-new") == "Already something brand new."


def test_every_write_operation_is_a_proposal_on_mcp():
    for oid, op in OPS.items():
        if op["kind"] == "write":
            assert op["tool"].startswith("propose_"), f"{oid} exposes a commit verb"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
