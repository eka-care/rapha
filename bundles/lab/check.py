"""Run: python3 -m bundles.lab.check

Does the kernel, unchanged, run a diagnostics laboratory from bundles/lab/?
Two halves. The first is pure: the Fake store from kernel/tests/test_kernel.py
and the kernel's own functions, walking a specimen from accession to release.
The second starts uvicorn with PHC_BUNDLE=lab on a free port, drives it over
HTTP, and reads the SQLite file to prove the rows landed. SKIP_E2E=1 skips
the second half, as check.sh does for scripts/e2e.py.

The checks that matter are the ones a laboratory would fire someone over: a
release reachable from a machine, a result verified by the person who keyed
it, a potassium of 6.8 committed without a flag. One of those the kernel
cannot enforce, and the check below says so with an assert rather than a
comment. See bundles/LAB-LOG.md.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

from catalogue import guard, vocab
from catalogue.guard import visible
from kernel import declarations, mapping, proposals, state, views
from kernel.tests.test_kernel import Fake

ROOT = pathlib.Path(__file__).parents[2]
BUNDLE = declarations.load("lab")
WF = BUNDLE.workflow()
OPS = BUNDLE.operations
T = "enc-1"

FRONTDESK = set(vocab.BUNDLES["frontdesk"])
PHLEBOTOMIST = set(vocab.BUNDLES["nurse"])
TECHNOLOGIST = set(vocab.BUNDLES["lab"])
PATHOLOGIST = set(vocab.BUNDLES["lab_incharge"])

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


def commit(store, op_id, payload, caps, **kw):
    return proposals.commit(store, BUNDLE, op_id, thread=T, payload=payload,
                            caps=caps, actor="someone", **kw)


def drawn(store, caps):
    return [op["id"] for op in state.actions(WF, OPS, state.flags(store, T, WF), caps)]


# --------------------------------------------------------------------------
# pure: the declared line, walked with the kernel's own functions
# --------------------------------------------------------------------------

def check_the_declaration_drives_a_line_the_phc_never_had():
    assert [s.station for s in WF.steps] == ["reception", "nurse", "lab", "doctor"]
    assert not any(op["capability"] in ("rx.prescribe", "encounter.document")
                   for op in OPS.values()), "a lab neither consults nor prescribes"
    for op_id, op in sorted(OPS.items()):
        for record in op["mapping"]:
            from adapters.local.store import TABLES
            missing = sorted(set(record["fields"]) - set(TABLES[record["resource"]]))
            assert not missing, "%s maps %s which the adapter lacks" % (op_id, missing)
    ok("lab bundle loads with zero kernel changes; 4 stations, no consult, no rx")


def check_an_action_is_absent_before_its_precondition():
    store = Fake()
    assert state.station(WF, state.flags(store, T, WF)) == "reception"
    assert drawn(store, FRONTDESK) == ["lab.op.referral-accession"]
    assert drawn(store, PATHOLOGIST) == [], "the pathologist has nothing to do yet"
    assert drawn(store, TECHNOLOGIST) == []
    ok("an empty thread stands at accession and only the front desk sees an action")

    assert commit(store, "lab.op.referral-accession", ACCESSION, FRONTDESK)
    known = state.flags(store, T, WF)
    assert {"registered", "lab.ordered", "abha.pending"} <= known
    assert state.station(WF, known) == "nurse"
    assert drawn(store, FRONTDESK) == [], "accession is gone, not greyed out"
    assert drawn(store, PHLEBOTOMIST) == ["lab.op.specimen-collect"]
    assert "Dr Outside" in store.rows["questionnaire_response"][0]["payload"]
    ok("accession writes patient, order and the referrer; the line moves to the draw room")

    assert commit(store, "lab.op.specimen-collect", SPECIMEN, PHLEBOTOMIST)
    assert state.station(WF, state.flags(store, T, WF)) == "lab"
    assert drawn(store, TECHNOLOGIST) == ["lab.op.result-enter"]
    assert "lab.op.result-verify" not in drawn(store, PATHOLOGIST)
    ok("a collected specimen stands at the bench; verify does not exist yet")


def check_ranges_are_per_analyte():
    store = _at_bench()
    d = commit(store, "lab.op.result-enter", dict(RESULT, potassium=14), TECHNOLOGIST)
    assert not d and "potassium is 14" in d.reason and "outside 1 to 10" in d.reason, d.reason
    assert "observation" not in store.rows, "a blocked value wrote nothing"
    d = commit(store, "lab.op.result-enter", dict(RESULT, glucose=5), TECHNOLOGIST)
    assert not d and "glucose is 5" in d.reason and "outside 10 to 1500" in d.reason
    ok("each analyte blocks on its own band: potassium 14 and glucose 5 refused")

    d = commit(store, "lab.op.result-enter", dict(RESULT, potassium=6.8), TECHNOLOGIST)
    assert d, d.reason
    assert "lab.critical" in store.stored, "6.8 is plausible and critical"
    rows = {r["code"]: r for r in store.rows["observation"]}
    assert rows["potassium"] == {"category": "laboratory", "code": "potassium",
                                 "value": 6.8, "unit": "mmol/L", "_thread": T}
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
               TECHNOLOGIST)
    assert d, d.reason
    assert store2.log[-1].payload["override_reason"], "the reason is on the audit line"
    ok("an override needs a recorded reason, and the reason lands in the audit")

    store3 = _at_bench()
    assert commit(store3, "lab.op.result-enter", dict(RESULT, sodium=133), TECHNOLOGIST)
    assert "lab.critical" not in store3.stored
    ok("sodium 133 is outside the reference interval and raises NOTHING: "
       "the grammar has no abnormal flag, only critical (bundles/LAB-LOG.md, leak 7)")


def _at_bench():
    store = Fake()
    assert commit(store, "lab.op.referral-accession", ACCESSION, FRONTDESK)
    assert commit(store, "lab.op.specimen-collect", SPECIMEN, PHLEBOTOMIST)
    return store


def _verified():
    store = _at_bench()
    assert commit(store, "lab.op.result-enter", RESULT, TECHNOLOGIST)
    assert commit(store, "lab.op.result-verify", VERIFY, PATHOLOGIST)
    return store


def _released():
    store = _verified()
    assert commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, confirmed=True)
    return store


def check_separation_of_duties():
    store = _at_bench()
    assert commit(store, "lab.op.result-enter", RESULT, TECHNOLOGIST)
    known = state.flags(store, T, WF)
    assert state.station(WF, known) == "doctor"
    assert drawn(store, TECHNOLOGIST) == [], "the technologist cannot verify"
    assert drawn(store, PATHOLOGIST) == ["lab.op.result-verify"], \
        "verify is drawn, release is not: it does not exist until verified"
    d = commit(store, "lab.op.result-verify", VERIFY, TECHNOLOGIST)
    assert not d and "missing capability lab.result.validate" in d.reason
    ok("entered by one capability, verified by another; the technologist is refused")

    # The honest negative. The pathologist role holds lab.result.enter too, so
    # the kernel would let the same person key and verify. Nothing in the
    # guard compares the actor on the audit line with the actor now. This
    # assert documents the hole; it is not a feature.
    assert visible(OPS["lab.op.result-enter"], PATHOLOGIST, state.flags(_at_bench(), T, WF)), \
        "if this ever fails, the vocabulary changed; update bundles/LAB-LOG.md leak 1"
    ok("KNOWN HOLE: the pathologist role can also enter results; the guard has no "
       "'not the same actor' rule (bundles/LAB-LOG.md, leak 1)")

    rejected = _at_bench()
    assert commit(rejected, "lab.op.result-enter", RESULT, TECHNOLOGIST)
    assert commit(rejected, "lab.op.result-verify", dict(decision="rejected"), PATHOLOGIST)
    assert "lab.validated" not in state.flags(rejected, T, WF)
    assert drawn(rejected, TECHNOLOGIST) == [], \
        "a rejected result strands the thread: no amend loop is declarable"
    ok("a rejection does not verify, and it strands the specimen (bundles/LAB-LOG.md, leak 5)")

    assert commit(store, "lab.op.result-verify", VERIFY, PATHOLOGIST)
    assert "lab.validated" in state.flags(store, T, WF)
    assert drawn(store, PATHOLOGIST) == ["lab.op.report-release"]
    assert store.rows["notes"][0]["text"].startswith("Comment:")
    ok("verified: the release action now exists")


def check_release_is_irreversible_and_human():
    store = _verified()
    d, prop = proposals.propose(store, BUNDLE, "lab.op.report-release", thread=T,
                                payload=RELEASE, caps=PATHOLOGIST, actor="agent")
    assert not d and prop is None and "rendered surface" in d.reason, d.reason
    d = commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST)
    assert not d and "explicit confirm" in d.reason
    assert "questionnaire_response" in store.rows and \
        all(r["questionnaire"] != "lab.schema.release-v1"
            for r in store.rows["questionnaire_response"]), "nothing released yet"
    ok("release: refused over the machine surface, refused on screen without the tap")

    assert commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, confirmed=True)
    known = state.flags(store, T, WF)
    assert "dispensed.complete" in known and state.station(WF, known) is None
    assert [s.status for s in state.line(WF, known)] == ["done"] * 4
    d = commit(store, "lab.op.report-release", RELEASE, PATHOLOGIST, confirmed=True)
    assert not d and "precondition not met: not dispensed.complete" in d.reason
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
    assert [g["key"] for g in q.groups] == ["reception", "nurse", "lab", "doctor", None]
    assert q.rows[0].station is None
    assert q.rows[0].badges == {"abha.pending": "mute", "dispensed.complete": "ok"}
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
        assert h.call(base, "/threads/%s/?role=lab_incharge" % t)["actions"] == []
        panel = h.call(base, "/threads/%s/?role=frontdesk" % t)
        assert [a["id"] for a in panel["actions"]] == ["lab.op.referral-accession"]
        assert [s["station"] for s in panel["line"]] == ["reception", "nurse", "lab", "doctor"]
        ok("a new thread draws the lab line and only accession, only to the front desk")

        h.call(base, "/operations/lab.op.referral-accession/commit/?role=frontdesk",
               {"thread": t, "payload": ACCESSION})
        h.call(base, "/operations/lab.op.specimen-collect/commit/?role=nurse",
               {"thread": t, "payload": SPECIMEN})
        assert h.rows(db, "SELECT code, status FROM specimen WHERE encounter=?", (t,)) == \
            [("venous-blood", "available")]
        assert h.rows(db, "SELECT code FROM service_request WHERE encounter=?", (t,)) == [("bmp",)]
        ok("accession and collection land as rows in the file")

        denied = h.call(base, "/operations/lab.op.result-enter/commit/?role=lab",
                        {"thread": t, "payload": dict(RESULT, potassium=14)}, expect=422)
        assert "potassium is 14" in denied["detail"]
        proposed = h.call(base, "/operations/lab.op.result-enter/propose/?role=lab",
                          {"thread": t, "payload": dict(RESULT, potassium=6.8)})
        assert proposed["flags_raised"] == ["lab.critical"]
        assert h.rows(db, "SELECT * FROM observation WHERE encounter=?", (t,)) == []
        ok("an implausible potassium is refused; a critical one is proposed, not written")

        confirmed = h.call(base, "/proposals/%s/confirm/?role=lab" % proposed["proposal_id"],
                           {"confirmed": True})
        assert "lab.critical" in confirmed["thread"]["flags"]
        assert confirmed["thread"]["station"] == "doctor"
        landed = dict(h.rows(db, "SELECT code, value FROM observation WHERE encounter=?", (t,)))
        assert landed["potassium"] == "6.8" and len(landed) == 4, landed
        ok("confirmed by the technologist: four analyte rows, the flag, the line at the pathologist")

        denied = h.call(base, "/operations/lab.op.result-verify/commit/?role=lab",
                        {"thread": t, "payload": VERIFY}, expect=422)
        assert "missing capability lab.result.validate" in denied["detail"]
        h.call(base, "/operations/lab.op.result-verify/commit/?role=lab_incharge",
               {"thread": t, "payload": VERIFY})
        ok("the technologist role cannot verify over HTTP; the pathologist role can")

        denied = h.call(base, "/operations/lab.op.report-release/propose/?role=lab_incharge",
                        {"thread": t, "payload": RELEASE}, expect=422)
        assert "rendered surface" in denied["detail"]
        denied = h.call(base, "/operations/lab.op.report-release/commit/?role=lab_incharge",
                        {"thread": t, "payload": RELEASE}, expect=422)
        assert "explicit confirm" in denied["detail"]
        released = h.call(base, "/operations/lab.op.report-release/commit/?role=lab_incharge",
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
        board = h.call(base, "/views/lab.view.turnaround/?role=lab_incharge")
        got = {m["metric"]: m for m in board["rows"]}
        assert got["lab.metric.accessioned"]["numerator"] >= 1
        assert got["lab.metric.released"]["numerator"] >= 1
        worklist = h.call(base, "/queue/")
        assert {r["thread"]: r["station"] for r in worklist["rows"]}[t] is None
        ok("report, turnaround board and worklist all resolve from the lab "
           "declarations, and the board opens for the account the browser is")

        # The seed is the adapter's and it is a PHC's. It runs regardless of bundle.
        seeded = [r for r in worklist["rows"] if r["thread"].startswith("enc-00")]
        assert len(seeded) == 6, "the PHC seed still runs under the lab bundle (bundles/LAB-LOG.md, leak 10)"
        ok("KNOWN LEAK: six PHC patients are seeded into the laboratory's worklist")

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
    print("ok   bundles/lab: %d checks, kernel unchanged" % checks)
