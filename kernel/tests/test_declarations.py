"""Lint rules for the `calendar` view kind."""
from __future__ import annotations

import json
import pathlib

import yaml

from catalogue.build import parse
from kernel import declarations

ROOT = pathlib.Path(__file__).parents[2]
BUNDLE = ROOT / "bundles" / "phc"
CAT = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
MANIFEST = yaml.safe_load((BUNDLE / "bundle.yaml").read_text())


def _decls():
    return {fm["id"]: (dict(fm), body)
            for fm, body in (parse(p) for p in sorted(BUNDLE.glob("*.md")))}


def _lint(decls):
    return declarations.lint(MANIFEST, decls, CAT["operations"])


def test_the_shipped_bundle_lints_clean():
    assert _lint(_decls()) == []


def test_a_calendar_naming_an_episode_type_no_schedule_covers_is_refused():
    # Drawing an episode no schedule declares gives an empty screen with no
    # error anywhere: the silent failure the tasklist branch also prevents.
    decls = _decls()
    decls["phc.view.calendar"][0]["episodes"] = ["pregnancy", "toddlerhood"]
    bad = _lint(decls)
    assert any("phc.view.calendar" in b and "toddlerhood" in b for b in bad), bad
    assert not any("'pregnancy'" in b for b in bad)


def test_a_calendar_naming_no_episodes_is_refused():
    decls = _decls()
    decls["phc.view.calendar"][0]["episodes"] = []
    assert any("phc.view.calendar" in b and "no episodes" in b for b in _lint(decls))


def test_a_calendar_naming_an_unknown_workflow_is_refused():
    decls = _decls()
    decls["phc.view.calendar"][0]["workflow"] = "phc.wf.nonesuch"
    assert any("phc.view.calendar" in b and "phc.wf.nonesuch" in b for b in _lint(decls))


def test_the_shipped_calendar_declaration_compiles():
    view = CAT["views"]["phc.view.calendar"]
    assert view["kind"] == "calendar"
    assert view["episodes"] == ["pregnancy", "pregnancy_high_risk", "postnatal",
                              "postnatal_high_risk"]


def test_a_contact_carries_both_a_plain_name_and_the_programme_s():
    anc = CAT["schedules"]["phc.sched.antenatal"]["contacts"]
    assert [c["title"] for c in anc] == [
        "First check-up", "Second check-up", "Third check-up", "Fourth check-up"]
    assert [c["programme_title"] for c in anc] == [
        "First antenatal contact", "Second antenatal contact",
        "Third antenatal contact", "Fourth antenatal contact"]
    # The statutory code is a third thing and stays as it was.
    assert [c["reports_as"] for c in anc] == ["ANC1", "ANC2", "ANC3", "ANC4"]


def test_a_schedule_declaring_no_programme_name_still_compiles():
    decls = _decls()
    for c in decls["phc.sched.antenatal"][0]["contacts"]:
        assert c.pop("programme_title", None), "the antenatal contacts do declare one"
    assert _lint(decls) == []
    bundle = declarations.load("phc")
    from kernel.contracts import Contact
    assert Contact.__dataclass_fields__["programme_title"].default is None
    assert bundle.schedules["phc.sched.postnatal"].contacts


def test_the_subject_answer_carries_the_date_it_was_generated():
    import re
    from adapters.local.store import SqliteStore
    from kernel import spine
    b = declarations.load("phc")
    store = SqliteStore(":memory:")
    wf = b.workflow()
    store.write("patient", {"id": "p-x", "name": "X"}, thread="e-x")
    found = spine.of(b, store, wf, "p-x")
    assert found is not None
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", found["generated_at"])


def _hrp():
    return CAT["schedules"]["phc.sched.antenatal-high-risk"]


def test_a_high_risk_pregnancy_has_its_own_schedule_of_three_visits():
    s = _hrp()
    assert s["episode"] == "pregnancy_high_risk"
    assert s["anchor"] == {"marked": 0}
    cs = s["contacts"]
    assert [c["id"] for c in cs] == ["hrp1", "hrp2", "hrp3"]
    assert [c["due"] for c in cs] == [30, 60, 90]
    assert [c["title"] for c in cs] == [
        "First extra check-up", "Second extra check-up", "Third extra check-up"]
    assert all(c["programme_title"] for c in cs)
    # The programme counts these; it gives them no code. None may be invented.
    assert all(not c.get("reports_as") for c in cs)
    # Additional to the ordinary four, which stay on the pregnancy episode.
    assert len(CAT["schedules"]["phc.sched.antenatal"]["contacts"]) == 4


def test_the_three_visits_are_owned_by_the_doctor_and_escalate():
    for c in _hrp()["contacts"]:
        assert c["owner"] == "mo" and c["escalates_to"] == "cho"
        assert c["operation"] == "phc.op.antenatal-visit"
        assert c["authority"] == "statutory"


def test_no_two_high_risk_windows_share_a_day():
    cs = sorted(_hrp()["contacts"], key=lambda c: c["due"])
    for c in cs:
        assert c["due"] - c["opens"] == 14 and c["closes"] - c["due"] == 14
    for a, b in zip(cs, cs[1:]):
        assert a["closes"] < b["opens"], (a["id"], b["id"])


def test_marking_needs_an_open_pregnancy_and_refuses_a_second_mark():
    op = CAT["operations"]["phc.op.risk-mark"]
    assert op["capability"] == "episode.manage" and op["station"] == "nurse"
    assert "pregnancy.open" in op["preconditions"]
    assert "not pregnancy_high_risk.open" in op["preconditions"]
    assert op["irreversibility"] == "correctable"
    recs = CAT["mapping"]["phc.op.risk-mark"]
    assert len(recs) == 1 and recs[0]["resource"] == "episode_of_care"
    f = recs[0]["fields"]
    assert f["type"] == {"const": "pregnancy_high_risk"}
    assert f["status"] == {"const": "active"}
    assert f["anchor_basis"] == {"const": "marked"}
    assert "anchor_date" in f
    # She cannot be unmarked: no operation closes it.
    assert "phc.op.risk-unmark" not in CAT["operations"]
    wf = CAT["workflows"]["phc.wf.outpatient"]
    nurse = [s for s in wf["steps"] if s["station"] == "nurse"][0]
    assert "phc.op.risk-mark" in nurse["operations"]
    # Offered at the nurse's bench only: the build refuses it elsewhere.
    others = [s for s in wf["steps"] if s["station"] != "nurse"]
    assert not any("phc.op.risk-mark" in s["operations"] for s in others)
    for st in ("open", "ended"):
        assert f"pregnancy_high_risk.{st}" in wf["states"]


def test_the_calendar_sweeps_the_high_risk_type_too():
    assert "pregnancy_high_risk" in CAT["views"]["phc.view.calendar"]["episodes"]


def _ops():
    return CAT["operations"], CAT["mapping"]


def _types(op):
    return [(r["fields"]["type"]["const"], r["fields"]["status"]["const"])
            for r in CAT["mapping"][op]]


def test_an_ordinary_delivery_cannot_be_recorded_for_a_high_risk_woman():
    ops, _ = _ops()
    assert ops["phc.op.delivery-record"]["preconditions"] == ["pregnancy.ordinary"]
    assert ops["phc.op.pregnancy-close"]["preconditions"] == ["pregnancy.ordinary"]
    st = CAT["workflows"]["phc.wf.outpatient"]["states"]["pregnancy.ordinary"]
    assert st == {"all_of": ["pregnancy.open", "not pregnancy_high_risk.open"]}
    for op in ("phc.op.delivery-record-high-risk", "phc.op.pregnancy-close-high-risk"):
        assert ops[op]["preconditions"] == ["pregnancy_high_risk.open"]


def test_a_high_risk_delivery_opens_the_tail_that_runs_to_day_45():
    assert _types("phc.op.delivery-record-high-risk") == [
        ("pregnancy", "ended"), ("pregnancy_high_risk", "ended"),
        ("postnatal_high_risk", "active")]
    s = CAT["schedules"]["phc.sched.postnatal-high-risk"]
    assert s["episode"] == "postnatal_high_risk" and s["anchor"] == {"delivery": 0}
    last = s["contacts"][-1]
    assert last["id"] == "hbnc45" and last["due"] == 45 and last["owner"] == "anm"
    assert CAT["schedules"]["phc.sched.postnatal"]["contacts"][-1]["due"] == 42


def test_the_high_risk_postnatal_schedule_keeps_the_seven_home_visits():
    hr = CAT["schedules"]["phc.sched.postnatal-high-risk"]["contacts"]
    ord_ = CAT["schedules"]["phc.sched.postnatal"]["contacts"]
    assert len(hr) == 8 and hr[:6] == ord_[:6]
    # Identical but for the six week window, a day shorter so that day 45
    # belongs to exactly one contact.
    assert ({k: v for k, v in hr[6].items() if k != "closes"}
            == {k: v for k, v in ord_[6].items() if k != "closes"})
    assert (hr[6]["closes"], ord_[6]["closes"]) == (44, 45)
    assert (hr[7]["opens"], hr[7]["due"], hr[7]["closes"]) == (45, 45, 52)
    cs = sorted(hr, key=lambda c: c["due"])
    for a, b in zip(cs, cs[1:]):
        assert a["closes"] < b["opens"], (a["id"], b["id"])


def test_both_delivery_paths_reuse_one_questionnaire():
    ops, _ = _ops()
    assert ops["phc.op.delivery-record"]["input"] == ops["phc.op.delivery-record-high-risk"]["input"]
    assert ops["phc.op.pregnancy-close"]["input"] == ops["phc.op.pregnancy-close-high-risk"]["input"]


def test_a_high_risk_loss_ends_both_episodes():
    assert _types("phc.op.pregnancy-close-high-risk") == [
        ("pregnancy", "ended"), ("pregnancy_high_risk", "ended")]


def test_a_high_risk_loss_opens_no_postnatal_care_of_either_kind():
    for op in ("phc.op.pregnancy-close", "phc.op.pregnancy-close-high-risk"):
        assert not any(t.startswith("postnatal") for t, _ in _types(op)), op
        assert all(s == "ended" for _, s in _types(op)), op


def test_the_nurse_is_offered_every_way_a_pregnancy_ends():
    nurse = [s for s in CAT["workflows"]["phc.wf.outpatient"]["steps"]
             if s["station"] == "nurse"][0]["operations"]
    for op in ("phc.op.delivery-record-high-risk", "phc.op.pregnancy-close-high-risk"):
        assert op in nurse
    assert "postnatal_high_risk" in CAT["views"]["phc.view.calendar"]["episodes"]


def test_every_operation_that_ends_a_pregnancy_ends_the_high_risk_episode_too():
    # The safety property: no path ends a pregnancy and leaves her owed visits.
    # The only legitimate leaver is an ordinary form guarded to a woman with no
    # high-risk episode open.
    for op, rows in CAT["mapping"].items():
        if ("pregnancy", "ended") not in _types_of(rows):
            continue
        pre = CAT["operations"][op]["preconditions"]
        if ("pregnancy_high_risk", "ended") in _types_of(rows):
            continue
        assert pre == ["pregnancy.ordinary"], (op, pre)


def _types_of(rows):
    return [(r["fields"]["type"]["const"], r["fields"]["status"]["const"])
            for r in rows if r["resource"] == "episode_of_care"
            and "const" in r["fields"].get("type", {}) and "const" in r["fields"].get("status", {})]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
