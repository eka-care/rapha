"""Run: python3 -m bundles.lab.check

Does the kernel, unchanged, run a diagnostics laboratory from bundles/lab/?
Two halves. The first is pure: the Fake store from kernel/tests/test_kernel.py
and the kernel's own functions, walking a specimen from accession to release.
The second starts uvicorn with PHC_BUNDLE=lab on a free port, drives it over
HTTP, and reads the SQLite file to prove the rows landed. SKIP_E2E=1 skips
the second half, as check.sh does for scripts/e2e.py.

The checks that matter are the ones a laboratory would fire someone over: a
release reachable from a machine, a result verified by the person who keyed
it, a potassium of 6.8 committed without a flag. All three are refused, and
every station, flag, capability and role below is the laboratory's own,
declared in bundles/lab/bundle.yaml. What the kernel still cannot do is in
bundles/LAB-LOG.md, and the checks that assert those holes say so.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

from catalogue import guard, vocab
from kernel import declarations, mapping, proposals, state, views
from kernel.tests.test_kernel import Fake

ROOT = pathlib.Path(__file__).parents[2]
BUNDLE = declarations.load("lab")
WF = BUNDLE.workflow()
OPS = BUNDLE.operations
T = "enc-1"

ROLES = vocab.for_bundle("lab").roles
PHLEBOTOMIST = set(ROLES["phlebotomist"])
TECHNOLOGIST = set(ROLES["technologist"])
PATHOLOGIST = set(ROLES["pathologist"])
# The role that makes the separation of duties rule necessary: one person who
# may both key and verify. The rule is about the specimen, not the role.
SENIOR = set(ROLES["senior_technologist"])

# Who is doing it. A row's author and the guard's actor rule both read these.
A_PHLEB = "user:meena"
A_TECH = "user:asha"
A_PATH = "user:ravi"
A_SENIOR = "user:sunil"

ACCESSION = {"name": "Referred Person", "age": 40, "sex": "female", "phone": "9",
             "referrer_name": "Dr Outside", "referrer_contact": "9000000000",
             "panel": "bmp"}
SPECIMEN = {"specimen_type": "venous-blood", "container": "lithium heparin"}
RESULT = {"panel": "bmp", "glucose": 96, "creatinine": 0.9, "sodium": 139, "potassium": 4.1}
VERIFY = {"decision": "verified", "comment": "Consistent with the specimen."}
RELEASE = {"channel": "portal", "attest": True}

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def commit(store, op_id, payload, caps, actor="user:somebody", **kw):
    return proposals.commit(store, BUNDLE, op_id, thread=T, payload=payload,
                            caps=caps, actor=actor, **kw)


def drawn(store, caps, actor=None):
    return [op["id"] for op in state.actions(
        WF, OPS, state.flags(store, T, WF), caps, actor=actor,
        performed=state.performers(store, T) if actor else None)]


# --------------------------------------------------------------------------
# pure: the declared line, walked with the kernel's own functions
# --------------------------------------------------------------------------

def check_the_declaration_drives_a_line_the_phc_never_had():
    assert [s.station for s in WF.steps] == \
        ["accession", "phlebotomy", "processing", "verification", "release"]
    phc = vocab.for_bundle("phc")
    # lab.critical is the one name both vocabularies happen to use, and in a
    # laboratory it is not a lie. It keeps the name because the questionnaire
    # that raises it says `flags: lab.critical`, and questionnaires/ is not
    # this bundle's directory to edit.
    assert set(WF.states) & set(phc.states) == {"lab.critical"}, \
        "a lab flag is wearing a primary health centre's name"
    assert not ({op["capability"] for op in OPS.values()} & set(phc.capabilities))
    assert not (set(ROLES) & set(phc.roles)), "a lab role is a PHC role"
    for op_id, op in sorted(OPS.items()):
        for record in op["mapping"]:
            from adapters.local.store import TABLES
            missing = sorted(set(record["fields"]) - set(TABLES[record["resource"]]))
            assert not missing, "%s maps %s which the adapter lacks" % (op_id, missing)
    ok("the lab declares its own vocabulary: 5 stations, 7 flags, 7 capabilities, "
       "4 roles, and not one word of them is the PHC's")


def check_the_loop_derivations_are_the_kernels_not_the_phcs():
    """The loop derivations are kernel behaviour, not the health centre's. This
    bundle's line must resolve a closer for every station it declares, from its
    own done_when flags, with no phc.* anywhere in the answer.
    """
    for step in WF.steps:
        closer = state.loop_closer(WF, OPS, step.station)
        assert closer is not None, f"{step.station} has no operation emitting {step.done_when}"
        assert not closer.startswith("phc."), f"lab station {step.station} closed by {closer}"
    ok("every laboratory station resolves its own closer, and none of them is the PHC's")


def check_the_seed_is_the_laboratorys_own():
    """Leak 10, closed. The seed used to live in adapters/local/store.py and
    ran under whatever bundle was loaded, so a laboratory opened on six
    outpatients with tokens like A01 and a pending Amoxicillin on a specimen
    thread. It is declared data in bundles/<id>/seed.yaml now, and this walks
    every value of every row it wrote looking for a primary health centre.
    """
    from adapters.local.store import TABLES, SqliteStore, seed
    store = SqliteStore(":memory:")
    threads = seed(store, BUNDLE.seed)
    assert threads, "the laboratory declares no seed"

    import re
    phc_bundle = declarations.load("phc")
    phc = vocab.for_bundle("phc")
    lab = vocab.for_bundle("lab")
    # Every word the PHC owns, less the ones the laboratory also declares.
    # lab.critical is the only overlap and it is not a lie here; see the check
    # above.
    banned = ((set(phc.states) | set(phc.capabilities) | set(phc.stations)
               | set(phc.roles) | set(phc_bundle.manifest.operations)
               | {t["patient"]["name"] for t in phc_bundle.seed if t.get("patient")})
              - (set(lab.states) | set(lab.capabilities) | set(lab.stations)
                 | set(lab.roles) | set(OPS)))
    # Whole words: "lab" is a PHC station and "lab-001" is a laboratory thread.
    edge = re.compile("|".join(r"(?<![\w.-])%s(?![\w.-])" % re.escape(w)
                               for w in sorted(banned)))
    for table in TABLES:
        for row in store.db.execute("SELECT * FROM %s" % table).fetchall():
            blob = " ".join(str(v) for v in tuple(row) if v is not None)
            hit = edge.search(blob)
            assert not hit, "%s row carries the PHC's word %r: %s" % (
                table, hit.group(0), blob)

    # And it draws the laboratory's own line, with something at every station.
    caps = set().union(*ROLES.values())
    standing = {}
    for ref in store.threads(workflow=WF.id, scope="today"):
        view = state.thread_view(store, ref, WF, OPS, caps=caps, actor="user:demo")
        standing.setdefault(view.station, []).append(ref.id)
    assert set(standing) == {s.station for s in WF.steps} | {None}, standing
    assert "lab.critical" in state.flags(store, "lab-004", WF)
    assert "result.rejected" in state.flags(store, "lab-005", WF)
    # The one proposal on the demo day is the analyser offering a result the
    # bench has not accepted, and it is an operation this bundle loads.
    pending = [p for t in threads for p in store.proposals(t, status="pending")]
    assert [p.operation for p in pending] == ["lab.op.result-enter"], pending
    ok("the seed is the laboratory's own: %d specimens, one at every station, "
       "and not one PHC word in any row" % len(threads))


def check_a_seeded_result_carries_who_keyed_it():
    """The separation of duties rule reads the thread's audit trail, so a
    seeded thread that claims a result was entered has to say by whom. Without
    it the demo day cannot show the rule that the laboratory exists to prove."""
    from adapters.local.store import SqliteStore, seed
    store = SqliteStore(":memory:")
    seed(store, BUNDLE.seed)
    flags = state.flags(store, "lab-004", WF)
    performed = state.performers(store, "lab-004")
    assert performed.get("lab.op.result-enter") == {"user:technologist"}, performed
    for actor, expect in (("user:technologist", False), ("user:pathologist", True)):
        drawn = [op["id"] for op in state.actions(WF, OPS, flags, SENIOR,
                                                  actor=actor, performed=performed)]
        assert ("lab.op.result-verify" in drawn) is expect, (actor, drawn)
    ok("on the seeded critical specimen the Verify action is absent for the "
       "technologist who keyed it and present for the pathologist")


def check_a_bundle_cannot_borrow_another_bundles_words():
    """The closure that stops leak 2 coming back. Hand the lab manifest a PHC
    operation and every borrowed word has to be a build failure, not a screen
    that says `dispensed.complete` to a laboratory."""
    import json
    import yaml
    from catalogue.build import parse
    path = declarations.BUNDLES / "lab"
    manifest = yaml.safe_load((path / "bundle.yaml").read_text())
    manifest["operations"] = list(manifest["operations"]) + ["phc.op.vitals-record"]
    decls = {fm["id"]: (fm, body)
             for fm, body in (parse(f) for f in sorted(path.glob("*.md")))}
    ops = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())["operations"]
    bad = " | ".join(declarations.lint(manifest, decls, ops))
    for expected in ("capability 'vitals.record' is not this bundle's",
                     "station 'nurse' is not this bundle's line",
                     "precondition names state 'registered'",
                     "emits 'vitals.flagged'"):
        assert expected in bad, bad
    borrowed = dict(manifest, capabilities=list(manifest["capabilities"]) + ["nope"],
                    roles=dict(manifest["roles"], intruder=["vitals.record"]))
    assert any("role 'intruder' holds 'vitals.record'" in line
               for line in declarations.lint(borrowed, decls, ops))
    ok("a PHC operation listed by the lab manifest fails the build on every "
       "borrowed word, and so does a role holding a capability this bundle "
       "does not declare")


def check_an_action_is_absent_before_its_precondition():
    store = Fake()
    assert state.station(WF, state.flags(store, T, WF)) == "accession"
    assert drawn(store, PHLEBOTOMIST) == ["lab.op.referral-accession"]
    assert drawn(store, PATHOLOGIST) == [], "the pathologist has nothing to do yet"
    assert drawn(store, TECHNOLOGIST) == []
    ok("an empty thread stands at accession and only the accession desk sees an action")

    assert commit(store, "lab.op.referral-accession", ACCESSION, PHLEBOTOMIST,
                  actor=A_PHLEB)
    known = state.flags(store, T, WF)
    assert known == {"order.accessioned"}, known
    assert state.station(WF, known) == "phlebotomy"
    assert drawn(store, PHLEBOTOMIST) == ["lab.op.specimen-collect"], \
        "accession is gone, not greyed out"
    assert "Dr Outside" in store.rows["questionnaire_response"][0]["payload"]
    assert {r["created_by"] for r in store.rows["patient"]} == {A_PHLEB}, \
        "a row with no author is what made separation of duties unenforceable"
    ok("accession writes patient, order and the referrer, each row signed; "
       "the specimen moves to phlebotomy")

    assert commit(store, "lab.op.specimen-collect", SPECIMEN, PHLEBOTOMIST, actor=A_PHLEB)
    assert state.station(WF, state.flags(store, T, WF)) == "processing"
    assert drawn(store, TECHNOLOGIST) == ["lab.op.result-enter"]
    assert "lab.op.result-verify" not in drawn(store, PATHOLOGIST)
    ok("a collected specimen stands at processing; verify does not exist yet")


def check_ranges_are_per_analyte():
    store = _at_bench()
    d = commit(store, "lab.op.result-enter", dict(RESULT, potassium=14), TECHNOLOGIST, actor=A_TECH)
    assert not d and "potassium is 14" in d.reason and "outside 1 to 10" in d.reason, d.reason
    assert "observation" not in store.rows, "a blocked value wrote nothing"
    d = commit(store, "lab.op.result-enter", dict(RESULT, glucose=5), TECHNOLOGIST, actor=A_TECH)
    assert not d and "glucose is 5" in d.reason and "outside 10 to 1500" in d.reason
    ok("each analyte blocks on its own band: potassium 14 and glucose 5 refused")

    d = commit(store, "lab.op.result-enter", dict(RESULT, potassium=6.8), TECHNOLOGIST, actor=A_TECH)
    assert d, d.reason
    assert "lab.critical" in store.stored, "6.8 is plausible and critical"
    rows = {r["code"]: r for r in store.rows["observation"]}
    assert rows["potassium"] == {"created_by": A_TECH, "category": "laboratory",
                                 "code": "potassium", "value": 6.8,
                                 "unit": "mmol/L", "_thread": T}
    assert set(rows) == {"glucose", "creatinine", "sodium", "potassium"}, \
        "the unanswered CBC analytes are no row, not an empty row"
    assert store.rows["diagnostic_report"][0]["status"] == "preliminary"
    ok("potassium 6.8 commits with its unit and raises lab.critical; one row per analyte")

    store2 = _at_bench()
    d = commit(store2, "lab.op.result-enter", dict(RESULT, potassium=14), TECHNOLOGIST,
               scopes=None)
    assert not d
    d = commit(store2, "lab.op.result-enter",
               dict(RESULT, potassium=14, override_reason="repeated, analyser agrees"),
               TECHNOLOGIST, actor=A_TECH)
    assert d, d.reason
    assert store2.log[-1].payload["override_reason"], "the reason is on the audit line"
    ok("an override needs a recorded reason, and the reason lands in the audit")

    store3 = _at_bench()
    assert commit(store3, "lab.op.result-enter", dict(RESULT, sodium=133), TECHNOLOGIST,
                  actor=A_TECH)
    assert "lab.critical" not in store3.stored
    ok("sodium 133 is outside the reference interval and raises NOTHING: "
       "the grammar has no abnormal flag, only critical (bundles/LAB-LOG.md, leak 7)")


def _at_bench():
    store = Fake()
    assert commit(store, "lab.op.referral-accession", ACCESSION, PHLEBOTOMIST,
                  actor=A_PHLEB)
    assert commit(store, "lab.op.specimen-collect", SPECIMEN, PHLEBOTOMIST, actor=A_PHLEB)
    return store


def _verified():
    store = _at_bench()
    assert commit(store, "lab.op.result-enter", RESULT, TECHNOLOGIST, actor=A_TECH)
    assert commit(store, "lab.op.result-verify", VERIFY, PATHOLOGIST, actor=A_PATH)
    return store


def _released():
    store = _verified()
    assert commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, actor=A_PATH,
                  confirmed=True)
    return store


def check_separation_of_duties():
    store = _at_bench()
    assert commit(store, "lab.op.result-enter", RESULT, TECHNOLOGIST, actor=A_TECH)
    known = state.flags(store, T, WF)
    assert state.station(WF, known) == "verification"
    assert drawn(store, TECHNOLOGIST) == [], "the technologist cannot verify"
    assert drawn(store, PATHOLOGIST) == ["lab.op.result-verify"], \
        "verify is drawn, release is not: it does not exist until verified"
    d = commit(store, "lab.op.result-verify", VERIFY, TECHNOLOGIST, actor=A_TECH)
    assert not d and "missing capability result.verify" in d.reason
    ok("entered by one capability, verified by another; the technologist is refused")

    assert commit(store, "lab.op.result-verify", VERIFY, PATHOLOGIST, actor=A_PATH)
    assert "result.verified" in state.flags(store, T, WF)
    assert drawn(store, PATHOLOGIST) == ["lab.op.report-release"]
    assert store.rows["notes"][0]["text"].startswith("Comment:")
    assert store.rows["notes"][0]["created_by"] == A_PATH
    ok("verified by a second person: the release action now exists")


def check_the_same_person_cannot_verify_their_own_result():
    """The check the whole exercise was missing. A capability split is a rule
    about roles; this is a rule about the specimen, and it holds even when one
    person holds both capabilities, which in a small laboratory they do."""
    store = _at_bench()
    assert SENIOR >= {"result.enter", "result.verify"}, \
        "this check is meaningless unless one role holds both"
    assert commit(store, "lab.op.result-enter", RESULT, SENIOR, actor=A_SENIOR)

    d = commit(store, "lab.op.result-verify", VERIFY, SENIOR, actor=A_SENIOR)
    assert not d, "the same person verified their own result"
    assert "not actor of lab.op.result-enter" in d.reason, d.reason
    assert "diagnostic_report" in store.rows and \
        all(r["status"] != "verified" for r in store.rows["diagnostic_report"]), \
        "nothing was written by the refused verification"
    assert store.log[-1].outcome.startswith("denied"), "the refusal is on the audit"
    ok("the person who keyed the result is REFUSED verifying it, holding both "
       "capabilities, on the rendered surface")

    _, proposal = proposals.propose(store, BUNDLE, "lab.op.result-verify", thread=T,
                                    payload=VERIFY, caps=SENIOR, actor=A_SENIOR)
    assert proposal is None, "the machine surface let the same actor through"
    ok("and refused on the machine surface too: propose returns no proposal")

    assert "lab.op.result-verify" not in drawn(store, SENIOR, actor=A_SENIOR), \
        "the action a person may not take must be absent, not greyed out"
    assert "lab.op.result-verify" in drawn(store, SENIOR, actor="user:other-senior")
    ok("the button is invisible to the person who entered and present for a colleague")

    assert commit(store, "lab.op.result-verify", VERIFY, SENIOR, actor="user:other-senior")
    assert "result.verified" in state.flags(store, T, WF)
    ok("a second senior technologist verifies the same specimen and it passes")


def check_a_rejection_strands_the_specimen():
    rejected = _at_bench()
    assert commit(rejected, "lab.op.result-enter", RESULT, TECHNOLOGIST, actor=A_TECH)
    assert commit(rejected, "lab.op.result-verify", dict(decision="rejected"),
                  PATHOLOGIST, actor=A_PATH)
    known = state.flags(rejected, T, WF)
    assert "result.verified" not in known and "result.rejected" in known
    assert drawn(rejected, TECHNOLOGIST, actor=A_TECH) == [], \
        "a rejected result strands the thread: no amend loop is declarable"
    ok("a rejection raises result.rejected, does not verify, and strands the "
       "specimen (bundles/LAB-LOG.md, leak 5)")


def check_release_is_irreversible_and_human():
    store = _verified()
    d, prop = proposals.propose(store, BUNDLE, "lab.op.report-release", thread=T,
                                payload=RELEASE, caps=PATHOLOGIST, actor="agent")
    assert not d and prop is None and "rendered surface" in d.reason, d.reason
    d = commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, actor=A_PATH)
    assert not d and "explicit confirm" in d.reason
    assert "questionnaire_response" in store.rows and \
        all(r["questionnaire"] != "lab.schema.release-v1"
            for r in store.rows["questionnaire_response"]), "nothing released yet"
    ok("release: refused over the machine surface, refused on screen without the tap")

    assert commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, actor=A_PATH,
                  confirmed=True)
    known = state.flags(store, T, WF)
    assert "report.released" in known and state.station(WF, known) is None
    assert [s.status for s in state.line(WF, known)] == ["done"] * 5
    d = commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, actor=A_PATH,
               confirmed=True)
    assert not d and "precondition not met: not report.released" in d.reason
    ok("with the tap it releases, the line completes, and a second release is refused")

    outcomes = [r.outcome for r in store.audit(T)]
    assert sum(o.startswith("denied") for o in outcomes) >= 3
    assert "allowed" in outcomes
    ok("the audit holds every refusal on the way")


def check_views_and_metrics():
    store = _released()
    store._threads = [state.c.ThreadRef(id=T, workflow=WF.id, subject={"name": "Referred Person"},
                                        opened_at="2026-09-11T00:00:00Z")]
    q = views.resolve(BUNDLE, "lab.view.worklist", store)
    assert [g["key"] for g in q.groups] == \
        ["accession", "phlebotomy", "processing", "verification", "release", None]
    assert q.rows[0].station is None
    assert q.rows[0].badges == {"report.released": "ok"}
    ok("the worklist groups by station in line order, released under Complete")

    r = views.resolve(BUNDLE, "lab.view.report", store, thread=T, caps=PATHOLOGIST)
    by = {s["title"]: s["rows"] for s in r.rows}
    assert {x["code"] for x in by["Results"]} == {"glucose", "creatinine", "sodium", "potassium"}
    assert "Dr Outside" in by["Referral"][0]["payload"]
    assert by["Release"][0]["payload"] and by["What you can do"] == []
    assert not any("reference" in str(row) for row in by["Results"]), \
        "the report cannot show a reference interval beside a value (bundles/LAB-LOG.md, leak 8)"
    ok("the report view lists the values, the referrer and the release; no reference interval")

    for row in store.rows.get("service_request", []) + store.rows.get("questionnaire_response", []):
        row["created_date"] = "2026-09-11T09:00:00Z"
    d = views.resolve(BUNDLE, "lab.view.turnaround", store, at=None)
    got = {m.metric: m for m in d.rows}
    assert got["lab.metric.accessioned"].numerator == 1
    assert got["lab.metric.released"].numerator == 1
    assert got["lab.metric.release-ratio"].value == 1.0
    ok("four local metrics evaluate; turnaround TIME itself is not declarable (bundles/LAB-LOG.md, leak 3)")


# --------------------------------------------------------------------------
# over a socket, with the SQLite file read back
# --------------------------------------------------------------------------

def e2e():
    sys.path.insert(0, str(ROOT / "scripts"))
    import e2e as h   # reuse: call, free_port, wait_for, rows

    db = os.path.join(tempfile.mkdtemp(), "lab.sqlite3")
    port = h.free_port()
    base = "http://127.0.0.1:%d" % port
    log = os.path.join(os.path.dirname(db), "api.log")
    handle = open(log, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1",
         "--port", str(port)], cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
        env=dict(os.environ, PHC_DB=db, PHC_BUNDLE="lab"))
    try:
        h.wait_for(base, proc, log)
        assert h.call(base, "/facility/")["bundle"]["id"] == "lab"
        ok("the API starts as a laboratory: PHC_BUNDLE=lab, no other change")

        t = h.call(base, "/threads/", {"token": "L-1"})["id"]
        assert h.call(base, "/threads/%s/?role=pathologist" % t)["actions"] == []
        panel = h.call(base, "/threads/%s/?role=phlebotomist" % t)
        assert [a["id"] for a in panel["actions"]] == ["lab.op.referral-accession"]
        assert [s["station"] for s in panel["line"]] == \
            ["accession", "phlebotomy", "processing", "verification", "release"]
        ok("a new thread draws the lab line and only accession, only to the accession desk")

        h.call(base, "/operations/lab.op.referral-accession/commit/?role=phlebotomist",
               {"thread": t, "payload": ACCESSION})
        h.call(base, "/operations/lab.op.specimen-collect/commit/?role=phlebotomist",
               {"thread": t, "payload": SPECIMEN})
        assert h.rows(db, "SELECT created_by FROM specimen WHERE encounter=?", (t,)) == \
            [("user:phlebotomist",)], "the row does not say who drew the specimen"
        assert h.rows(db, "SELECT code, status FROM specimen WHERE encounter=?", (t,)) == \
            [("venous-blood", "available")]
        assert h.rows(db, "SELECT code FROM service_request WHERE encounter=?", (t,)) == [("bmp",)]
        ok("accession and collection land as rows in the file")

        denied = h.call(base, "/operations/lab.op.result-enter/commit/?role=technologist",
                        {"thread": t, "payload": dict(RESULT, potassium=14)}, expect=422)
        assert "potassium is 14" in denied["detail"]
        proposed = h.call(base, "/operations/lab.op.result-enter/propose/?role=technologist",
                          {"thread": t, "payload": dict(RESULT, potassium=6.8)})
        assert proposed["flags_raised"] == ["lab.critical"]
        assert h.rows(db, "SELECT * FROM observation WHERE encounter=?", (t,)) == []
        ok("an implausible potassium is refused; a critical one is proposed, not written")

        confirmed = h.call(base, "/proposals/%s/confirm/?role=technologist"
                           % proposed["proposal_id"], {"confirmed": True})
        assert "lab.critical" in confirmed["thread"]["flags"]
        assert confirmed["thread"]["station"] == "verification"
        landed = dict(h.rows(db, "SELECT code, value FROM observation WHERE encounter=?", (t,)))
        assert landed["potassium"] == "6.8" and len(landed) == 4, landed
        assert h.rows(db, "SELECT DISTINCT created_by FROM observation WHERE encounter=?",
                      (t,)) == [("user:technologist",)]
        ok("confirmed by the technologist: four analyte rows in their name, the flag, "
           "the line at verification")

        denied = h.call(base, "/operations/lab.op.result-verify/commit/?role=technologist",
                        {"thread": t, "payload": VERIFY}, expect=422)
        assert "missing capability result.verify" in denied["detail"]
        h.call(base, "/operations/lab.op.result-verify/commit/?role=pathologist",
               {"thread": t, "payload": VERIFY})
        ok("the technologist role cannot verify over HTTP; the pathologist role can")

        # Separation of duties over the socket, on a second specimen. There is
        # no authentication here, so the actor is "user:<role>": one person
        # keying and verifying is one role doing both, which is exactly what a
        # senior technologist would do at 2am with nobody else in the building.
        t2 = h.call(base, "/threads/", {"token": "L-2"})["id"]
        h.call(base, "/operations/lab.op.referral-accession/commit/?role=phlebotomist",
               {"thread": t2, "payload": ACCESSION})
        h.call(base, "/operations/lab.op.specimen-collect/commit/?role=phlebotomist",
               {"thread": t2, "payload": SPECIMEN})
        h.call(base, "/operations/lab.op.result-enter/commit/?role=senior_technologist",
               {"thread": t2, "payload": RESULT})
        denied = h.call(base, "/operations/lab.op.result-verify/commit/?role=senior_technologist",
                        {"thread": t2, "payload": VERIFY}, expect=422)
        assert "not actor of lab.op.result-enter" in denied["detail"], denied
        denied = h.call(base, "/operations/lab.op.result-verify/propose/?role=senior_technologist",
                        {"thread": t2, "payload": VERIFY}, expect=422)
        assert "not actor of lab.op.result-enter" in denied["detail"], denied
        assert h.rows(db, "SELECT status FROM diagnostic_report WHERE encounter=? "
                          "AND status='verified'", (t2,)) == []
        h.call(base, "/operations/lab.op.result-verify/commit/?role=pathologist",
               {"thread": t2, "payload": VERIFY})
        assert h.rows(db, "SELECT created_by FROM diagnostic_report WHERE encounter=? "
                          "AND status='verified'", (t2,)) == [("user:pathologist",)]
        ok("over HTTP: the account that keyed the result is refused verifying it on "
           "both surfaces, and a second person verifies it")

        denied = h.call(base, "/operations/lab.op.report-release/propose/?role=pathologist",
                        {"thread": t, "payload": RELEASE}, expect=422)
        assert "rendered surface" in denied["detail"]
        denied = h.call(base, "/operations/lab.op.report-release/commit/?role=pathologist",
                        {"thread": t, "payload": RELEASE}, expect=422)
        assert "explicit confirm" in denied["detail"]
        released = h.call(base, "/operations/lab.op.report-release/commit/?role=pathologist",
                          {"thread": t, "payload": RELEASE, "confirmed": True})
        assert released["thread"]["station"] is None
        assert h.rows(db, "SELECT questionnaire FROM questionnaire_response WHERE encounter=? "
                          "AND questionnaire='lab.schema.release-v1'", (t,))
        ok("release: machine surface refused, un-tapped refused, tapped released and in the file")

        report = h.call(base, "/views/lab.view.report/?thread=%s" % t)
        assert {s["title"] for s in report["rows"]} >= {"Results", "Referral", "Release"}
        # The renderer has no role switch, so a view the default account cannot
        # open is a dead nav tab. This board was exactly that until api/main.py
        # stopped building its demo role out of a hand written list of five.
        h.call(base, "/views/lab.view.turnaround/")
        board = h.call(base, "/views/lab.view.turnaround/?role=pathologist")
        got = {m["metric"]: m for m in board["rows"]}
        assert got["lab.metric.accessioned"]["numerator"] >= 1
        assert got["lab.metric.released"]["numerator"] >= 1
        worklist = h.call(base, "/queue/")
        assert {r["thread"]: r["station"] for r in worklist["rows"]}[t] is None
        ok("report, turnaround board and worklist all resolve from the lab "
           "declarations, and the board opens for the account the browser is")

        # Leak 10, closed, over the socket this time: the demo day this
        # kernel seeded into its own file is the laboratory's.
        seeded = [r for r in worklist["rows"] if r["thread"].startswith("lab-")]
        assert len(seeded) == len(BUNDLE.seed), seeded
        phc_threads = {t["id"] for t in declarations.load("phc").seed}
        assert not [r for r in worklist["rows"] if r["thread"] in phc_threads], \
            "a PHC thread is on the laboratory's worklist"
        names = {r["subject"].get("name") for r in worklist["rows"]}
        assert not (names & {"Kamala Devi", "Ramesh Kumar", "Sunita Bai"}), names
        stations = {r["station"] for r in seeded}
        assert stations <= {s.station for s in WF.steps} | {None}, stations
        ok("the worklist the API seeded on its own file is the laboratory's own "
           "demo day, at the laboratory's own stations")

        mcp_tools(base)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        handle.close()


def mcp_tools(base):
    binary = ROOT / "care_phc_mcp" / "care_phc_mcp"
    if not binary.exists():
        print("skip the Go MCP server: build it with (cd care_phc_mcp && go build .)")
        return
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "lab-check", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True,
                            env=dict(os.environ, CARE_BASE_URL=base,
                                     PHC_CAPABILITIES=",".join(sorted(PATHOLOGIST))))
    reply = None
    try:
        proc.stdin.write("\n".join(json.dumps(x) for x in lines) + "\n")
        proc.stdin.flush()
        while reply is None:
            line = proc.stdout.readline()
            if not line:
                break
            if line.startswith("{") and json.loads(line).get("id") == 2:
                reply = json.loads(line)
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    tools = [t["name"] for t in reply["result"]["tools"]]
    assert "propose_result_verify" in tools and "propose_report_release" in tools, tools
    assert all(t.startswith("propose_") for t in tools), tools
    ok("the unmodified Go MCP server offers the lab operations, every one a proposal, "
       "including release, which the kernel then refuses on surface")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_"):
            fn()
    if os.environ.get("SKIP_E2E"):
        print("warn lab e2e skipped: SKIP_E2E is set")
    else:
        e2e()
    print("ok   bundles/lab: %d checks, on its own vocabulary" % checks)
