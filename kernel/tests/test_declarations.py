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


def test_a_high_risk_delivery_opens_both_postnatal_episodes():
    assert _types("phc.op.delivery-record-high-risk") == [
        ("pregnancy", "ended"), ("pregnancy_high_risk", "ended"),
        ("postnatal", "active"), ("postnatal_high_risk", "active")]
    s = CAT["schedules"]["phc.sched.postnatal-high-risk"]
    assert s["episode"] == "postnatal_high_risk" and s["anchor"] == {"delivery": 0}


def test_the_high_risk_tail_carries_only_the_day_45_check_and_the_visits_are_not_copied():
    (last,) = CAT["schedules"]["phc.sched.postnatal-high-risk"]["contacts"]
    assert last["id"] == "hbnc45" and last["owner"] == "anm"
    assert (last["opens"], last["due"], last["closes"]) == (45, 45, 52)
    assert last["operation"] == "phc.op.postnatal-outcome"
    assert len(CAT["schedules"]["phc.sched.postnatal"]["contacts"]) == 7


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


# ---------------------------------------------------------------------------
# Can anyone actually do what a schedule says is owed?
# ---------------------------------------------------------------------------

def _world(episode_type):
    """The state flags true for a registered woman whose ONLY episode is one
    active `episode_type`, computed from the declared rules by the same forms
    the kernel reads, so a precondition nobody could satisfy shows up here as
    a precondition that is false."""
    states = CAT["workflows"]["phc.wf.outpatient"]["states"]
    rows = {(episode_type, "active"): 1}
    known = set()

    def n(q):
        if q["resource"] != "episode_of_care":
            return 1            # a registered patient on a visit: assume present
        w = q.get("where") or {}
        return rows.get((w.get("type"), w.get("status")), 0)

    def item(i):
        if not isinstance(i, str):
            return true(i)
        return (i[4:] not in known) if i.startswith("not ") else (i in known)

    def true(rule):
        (form, arg), = rule.items()
        if form == "stored":
            return False
        if form == "exists":
            return n(arg) > 0
        if form == "gte":
            a, b = n(arg[0]), n(arg[1])
            return b > 0 and a >= b
        if form == "all_of":
            return all(item(i) for i in arg)
        raise AssertionError(form)

    for flag, rule in states.items():
        if true(rule):
            known.add(flag)
    return known


def _reachable(episode_type):
    """Operations a worker can be offered over this episode: some step of the
    line draws it, that step applies, and its preconditions all hold."""
    known = _world(episode_type)
    out = set()
    for step in CAT["workflows"]["phc.wf.outpatient"]["steps"]:
        if step.get("applies_when") and step["applies_when"] not in known:
            continue
        for op in step["operations"]:
            pre = CAT["operations"][op]["preconditions"]
            if all((p[4:] not in known) if p.startswith("not ") else (p in known)
                   for p in pre):
                out.add(op)
    return out


def test_every_contact_in_every_schedule_names_an_operation_reachable_over_its_episode():
    # WHAT THIS PROTECTS: the lint only asks whether SOME step draws a
    # contact's operation, never whether that step applies and the operation's
    # preconditions hold for the very episode that owes the contact. Without
    # this, a schedule can chase a woman for ever with no form to answer it.
    assert CAT["schedules"]
    for sid, s in CAT["schedules"].items():
        reach = _reachable(s["episode"])
        for c in s["contacts"]:
            assert c["operation"] in reach, (sid, c["id"], c["operation"])


def test_every_episode_a_schedule_covers_can_be_ended_by_an_operation_offered_over_it():
    for sid, s in CAT["schedules"].items():
        closers = [op for op in _reachable(s["episode"])
                   if (s["episode"], "ended") in _types_of(CAT["mapping"][op])]
        assert closers, (sid, s["episode"])


def test_the_day_45_check_is_offered_at_the_nurse_and_ends_only_the_high_risk_tail():
    op = CAT["operations"]["phc.op.postnatal-outcome"]
    assert op["preconditions"] == ["postnatal_high_risk.open"]
    assert op["station"] == "nurse" and len(op["short"]) <= 14
    assert _types("phc.op.postnatal-outcome") == [("postnatal_high_risk", "ended")]
    assert "phc.op.postnatal-outcome" in _reachable("postnatal_high_risk")


def test_every_answer_to_the_day_45_check_ends_the_episode_including_a_poor_one():
    form = json.loads((ROOT / "questionnaires" / "phc.schema.postnatal-outcome-v1.json").read_text())
    q = form["questions"][0]
    assert q["link_id"] == "outcome" and q["required"]
    values = {o["value"] for o in q["answer_option"]}
    assert {"both_well", "mother_unwell", "baby_unwell", "both_unwell", "not_found"} <= values
    # One unconditional ending row: no answer leaves the episode open.
    (row,) = CAT["mapping"]["phc.op.postnatal-outcome"]
    assert row["fields"]["status"] == {"const": "ended"}
    assert row["fields"]["outcome"] == {"answer": "outcome"}


def test_the_day_45_check_is_not_offered_to_an_ordinary_mother_and_the_ordinary_forms_not_to_the_tail():
    assert "phc.op.postnatal-outcome" not in _reachable("postnatal")
    assert "phc.op.postnatal-outcome" not in _reachable("pregnancy")
    tail = _reachable("postnatal_high_risk")
    assert not tail & {"phc.op.postnatal-visit", "phc.op.postnatal-close"}


def test_a_high_risk_mothers_home_visits_are_recorded_on_the_ordinary_episode():
    # Delivering opens `postnatal` too, so the unchanged visit and close serve her.
    assert ("postnatal", "active") in _types("phc.op.delivery-record-high-risk")
    assert {"phc.op.postnatal-visit", "phc.op.postnatal-close"} <= _reachable("postnatal")


def test_the_ordinary_postnatal_path_is_unchanged():
    ops = CAT["operations"]
    assert ops["phc.op.postnatal-visit"]["preconditions"] == ["registered", "postnatal.open"]
    assert ops["phc.op.postnatal-close"]["preconditions"] == ["postnatal.open"]
    assert _types("phc.op.postnatal-close") == [("postnatal", "ended")]
    assert _types("phc.op.delivery-record") == [("pregnancy", "ended"), ("postnatal", "active")]
    steps = CAT["workflows"]["phc.wf.outpatient"]["steps"]
    assert [x["station"] for x in steps].count("community") == 1
    assert steps[-1]["applies_when"] == "postnatal.open"
    assert steps[-1]["operations"] == ["phc.op.postnatal-visit"]


def test_the_new_postnatal_states_have_the_same_shape_as_every_other_episode():
    st = CAT["workflows"]["phc.wf.outpatient"]["states"]
    assert st["postnatal_high_risk.ended"] == {"gte": [
        {"resource": "episode_of_care", "where": {"type": "postnatal_high_risk", "status": "ended"}},
        {"resource": "episode_of_care", "where": {"type": "postnatal_high_risk", "status": "active"}}]}
    assert st["postnatal_high_risk.open"] == {"all_of": [
        {"exists": {"resource": "episode_of_care",
                    "where": {"type": "postnatal_high_risk", "status": "active"}}},
        "not postnatal_high_risk.ended"]}


def test_no_engineering_words_reach_a_worker_in_the_day_45_check():
    op = CAT["operations"]["phc.op.postnatal-outcome"]
    form = json.loads((ROOT / "questionnaires" / "phc.schema.postnatal-outcome-v1.json").read_text())
    texts = [op["title"], op["summary"], op["short"], form["title"]]
    for q in form["questions"]:
        texts += [q["text"], q["styling_metadata"]["phc"].get("short", ""),
                  q["styling_metadata"]["phc"].get("help", "")]
    sched = CAT["schedules"]["phc.sched.postnatal-high-risk"]
    texts += [sched["title"], sched["summary"]] + [c["title"] for c in sched["contacts"]]
    for t in texts:
        for bad in ("TODO", "FIXME", "sign-off", "SIGN-OFF", "HRP"):
            assert bad not in t, t


def test_closing_a_high_risk_mothers_two_episodes_leaves_her_owed_nothing():
    from datetime import datetime, timedelta, timezone
    from adapters.local.store import SqliteStore
    from catalogue import vocab
    from kernel import proposals, schedule, spine, state

    bundle = declarations.load("phc")
    wf = bundle.workflow()
    caps = set(vocab.for_bundle("phc").roles["anm"])
    anm = "user:jyothi"
    today = datetime.now(timezone.utc).date()
    store = SqliteStore(":memory:")
    t = store.open_thread(token="1", actor=anm)

    def go(op, payload):
        r = proposals.commit(store, bundle, op, thread=t, payload=payload,
                             caps=caps, actor=anm)
        assert r, (op, r.reason)

    go("phc.op.patient-register", {"name": "Lakshmi Devi", "age": 27, "sex": "female",
        "phone": "9876500001", "village": "Yadiki", "category": "general"})
    go("phc.op.pregnancy-open", {"dating_basis": "last_menstrual_period",
        "dating_date": (today - timedelta(days=280)).isoformat()})
    go("phc.op.risk-mark", {"risk_factor": "severe_anaemia", "marked_date": today.isoformat()})
    go("phc.op.delivery-record-high-risk", {
        "delivery_date": (today - timedelta(days=2)).isoformat(), "outcome": "live_birth"})
    flags = state.flags(store, t, wf)
    assert {"postnatal.open", "postnatal_high_risk.open"} <= flags
    go("phc.op.postnatal-visit", {"seen": "mother_and_baby",
        "narrative": "Well.", "followup_needed": False})

    (patient,) = store.select("patient", thread=t, where={}, fields=["id"], limit=2)

    def episodes():
        return {e["type"]: e for e in spine.of(bundle, store, wf, patient["id"])["episodes"]}

    assert schedule.contacts(bundle, store, wf, episodes()["postnatal_high_risk"])
    go("phc.op.postnatal-outcome", {"outcome": "both_unwell", "narrative": "Fever.",
                                    "followup_needed": True})
    assert "postnatal_high_risk.open" not in state.flags(store, t, wf)
    assert schedule.contacts(bundle, store, wf, episodes()["postnatal_high_risk"]) == []
    # The home visits are a different episode and are still hers.
    assert "postnatal.open" in state.flags(store, t, wf)
    go("phc.op.postnatal-close", {"outcome": "completed"})
    assert schedule.contacts(bundle, store, wf, episodes()["postnatal"]) == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
