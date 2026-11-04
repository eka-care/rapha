"""Run: python3 -m catalogue.tests.test_validate"""
import json
import pathlib

from catalogue import guard, validate

CAT = json.loads((pathlib.Path(__file__).parents[1] / "catalogue.json").read_text())
OPS = CAT["operations"]
VITALS = validate.load("phc.schema.vitals-v1")
V = validate.make_validator(VITALS)
NORMAL = {"systolic": 120, "diastolic": 80, "pulse": 72}


def test_required_answers_are_required():
    assert "systolic is required" in V(None, {"diastolic": 80, "pulse": 72})


def test_a_normal_set_passes():
    assert V(None, NORMAL) == []


def test_out_of_range_blocks_the_commit():
    problems = V(None, {**NORMAL, "systolic": 400})
    assert problems and "outside 70 to 250" in problems[0]


def test_override_with_a_reason_unblocks_it():
    assert V(None, {**NORMAL, "systolic": 400, "override_reason": "device fault, re-checked manually"}) == []


def test_a_blank_override_reason_is_not_an_override():
    assert V(None, {**NORMAL, "systolic": 400, "override_reason": "   "})


def test_critical_value_raises_the_flag_without_blocking():
    assert V(None, {**NORMAL, "systolic": 190}) == []      # in range, so it commits
    assert validate.flags(VITALS, {**NORMAL, "systolic": 190}) == {"vitals.flagged"}
    assert validate.flags(VITALS, NORMAL) == set()


def test_choice_answers_are_constrained():
    reg = validate.make_validator(validate.load("phc.schema.register-v1"))
    base = {"name": "A", "age": 30, "phone": "9", "village": "Yadiki"}
    assert reg(None, {**base, "sex": "Female"})               # wrong case is not a value
    assert reg(None, {**base, "sex": "female"}) == []


def test_answers_to_questions_that_do_not_exist_are_rejected():
    assert "bp is not a question on this form" in V(None, {**NORMAL, "bp": "120/80"})


def test_guard_denies_an_invalid_payload_end_to_end():
    d = guard.evaluate(OPS["phc.op.vitals-record"], caps={"vitals.record"},
                       state={"registered"}, payload={"systolic": 400, "diastolic": 80, "pulse": 72},
                       surface=guard.RENDERED, validate=V)
    assert not d and "payload invalid" in d.reason


def test_every_operation_resolves_to_a_questionnaire():
    for oid, op in OPS.items():
        schema = validate.load(op["input"])
        back = validate._phc(schema)["operation"]
        assert oid in (back if isinstance(back, list) else [back])


def test_a_questionnaire_naming_an_operation_that_is_not_an_atom_fails_the_build():
    from catalogue import build
    atoms = build.load()
    real = validate._phc
    def fake(schema):
        d = dict(real(schema))
        if d.get("operation") == ["phc.op.delivery-record", "phc.op.delivery-record-high-risk"]:
            d["operation"] = list(d["operation"]) + ["phc.op.nonesuch"]
        return d
    validate._phc = fake
    try:
        bad = build.lint(atoms)
    finally:
        validate._phc = real
    assert any("phc.op.nonesuch" in b and "not an atom" in b for b in bad), bad
    assert build.lint(atoms) == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
