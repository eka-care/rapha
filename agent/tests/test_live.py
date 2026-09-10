"""Run: python3 -m agent.tests.test_live

agent/tests/test_planner.py checks the planner with no socket in sight. This
checks the wiring, which is the part that cannot be proved in process: the
agent really is an HTTP client, the kernel really refuses it, and the words it
prints when refused are the guard's and not a paraphrase.

It starts its own uvicorn on a free port against a throwaway SQLite file, so
the six seeded threads are known and it does not touch the database anyone is
demonstrating with. SKIP_E2E=1 skips the half that binds a port; the half that
does not needs nothing and always runs.
"""
from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from agent import __main__ as cli
from agent import client, planner

ROOT = pathlib.Path(__file__).parents[2]
ran = 0


def ok(what):
    global ran
    ran += 1
    print("ok   %s" % what)


# --------------------------------------------------------------------------
# No socket needed.
# --------------------------------------------------------------------------

class Recorder:
    """A kernel that records what it was asked to do and grants everything.
    Its point is the assertion afterwards: propose was the only verb used."""

    def __init__(self):
        self.calls = []

    def propose(self, operation, thread, payload):
        self.calls.append(("propose", operation, thread, payload))
        return {"proposal_id": "prop-fake", "status": "proposed", "flags_raised": []}

    def __getattr__(self, name):
        raise AssertionError("the CLI reached for kernel.%s" % name)


def test_the_client_will_not_assemble_a_url_that_could_commit():
    k = client.Kernel("http://127.0.0.1:1")  # nothing listens; refusal comes first
    for path in ("/proposals/prop-1/confirm", "/operations/x/commit", "/x/commit?role=mo"):
        try:
            k._call(path)
        except RuntimeError as e:
            assert "will not call" in str(e), e
        else:
            raise AssertionError("%s was not refused" % path)
    ok("the client refuses a commit path before it opens a socket")


def test_the_agent_package_names_no_commit_route():
    """A source check, because the honest way to say "there is no code path"
    is to fail here when someone adds one."""
    for path in sorted((ROOT / "agent").rglob("*.py")):
        for line in path.read_text().splitlines():
            if '"/confirm' in line or '"/commit' in line or "'/confirm" in line:
                assert "FORBIDDEN" in line or path.name.startswith("test_"), \
                    "%s builds a commit path: %s" % (path.name, line.strip())
    assert set(client.FORBIDDEN) == {"/confirm", "/commit"}
    ok("no module under agent/ names a commit route")


def test_one_turn_uses_propose_and_nothing_else():
    catalogue = planner.load()
    view = {"id": "enc-x", "held": sorted(catalogue["capabilities"]),
            "flags": ["registered"], "station": "nurse", "actions": [], "subject": {}}
    out = cli.respond(Recorder(), catalogue, view, "record her bp 140 over 90, pulse 72",
                      which="router")
    assert "prop-fake" in out
    ok("a turn proposes and reaches for no other verb")


def test_an_utterance_it_cannot_map_says_so():
    catalogue = planner.load()
    view = {"id": "enc-x", "held": sorted(catalogue["capabilities"]), "flags": [],
            "station": "nurse", "actions": [], "subject": {}}
    for said in ("is the doctor in today", "good morning", "thanks"):
        out = cli.respond(Recorder(), catalogue, view, said, which="router")
        assert out.startswith("I do not know"), "%r produced %r" % (said, out[:60])
    ok("an unmappable utterance is answered with I do not know, not a guess")


def test_the_order_comes_from_the_kernel_not_from_the_score():
    """The router scores how well an utterance names an operation. The kernel
    orders the work. Given both, the kernel's order is the one that shows."""
    catalogue = planner.load()
    actions = [{"id": "phc.op.consult-document", "station": "doctor"},
               {"id": "phc.op.vitals-record", "station": "nurse"}]
    plan = [planner.Proposed("phc.op.vitals-record", {}, "top score", "router", score=9),
            planner.Proposed("phc.op.consult-document", {}, "lower", "router", score=2)]
    got = [p.operation for p in planner.by_kernel_order(plan, actions)]
    assert got == [a["id"] for a in actions], got
    said = planner.explain_order(plan[0], actions, "nurse")
    assert said == "the kernel lists it 2 of 2 at nurse", said
    assert "does not offer" in planner.explain_order(
        planner.Proposed("phc.op.lab-order", {}, "", "router"), actions, "nurse")
    ok("ordering is read from ThreadView.actions, not computed here")


def test_a_planner_cannot_smuggle_a_range_override():
    """override_reason waives the physiological range check. A person may write
    one. A model may not, and typed() is where that is enforced."""
    op = planner.load()["operations"]["phc.op.vitals-record"]
    got = planner.typed(op, {"systolic": 300, "override_reason": "seems fine",
                             "note_to_self": "x"})
    assert got == {"systolic": 300}, got
    ok("typed() drops override_reason and every key the operation never asked for")


def llm_over_a_socket():
    """The llm() backend through the real anthropic SDK, against a fake endpoint.

    test_planner.py hands llm() a duck typed stub, which checks what this
    package does with an answer but never touches the SDK. This runs the SDK
    itself: a one request HTTP server stands in for api.anthropic.com, so the
    kwargs, the tool definition and the pydantic reply objects are all real.

    What it still does not prove, and this is the honest limit: whether
    Anthropic accepts this tool schema. Only a live call answers that, and
    there is no ANTHROPIC_API_KEY on this machine.
    """
    try:
        import anthropic
    except ImportError:
        print("warn llm backend not exercised: pip install anthropic")
        return

    import http.server
    import threading

    body = {"id": "msg_1", "type": "message", "role": "assistant",
            "model": planner.MODEL, "stop_reason": "tool_use", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "tool_use", "id": "tu_1", "name": "propose_operations",
                         "input": {"operations": [
                             {"operation": "phc.op.vitals-record",
                              "payload": {"systolic": 140, "diastolic": 90, "pulse": 72,
                                          "override_reason": "smuggled"},
                              "why": "the utterance gave a blood pressure"},
                             {"operation": "phc.op.not-a-real-operation",
                              "payload": {}, "why": "invented"}]}}]}
    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            seen["path"], seen["body"] = self.path, json.loads(raw)
            out = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    sdk = anthropic.Anthropic(api_key="not-a-key", max_retries=0,
                              base_url="http://127.0.0.1:%d" % server.server_port)
    catalogue = planner.load()
    got = planner.llm("her bp is 140 over 90, pulse 72", catalogue,
                      caps=set(catalogue["capabilities"]), state={"registered"}, client=sdk)
    server.server_close()

    assert seen["path"] == "/v1/messages", seen["path"]
    assert seen["body"]["model"] == "claude-opus-5", seen["body"]["model"]
    assert seen["body"]["tools"][0]["name"] == "propose_operations"
    assert "phc.op.vitals-record" in seen["body"]["messages"][0]["content"]
    ok("the llm backend builds a real SDK request to claude-opus-5")

    assert [p.operation for p in got] == ["phc.op.vitals-record"], got
    assert got[0].payload == {"systolic": 140, "diastolic": 90, "pulse": 72}, got[0].payload
    assert got[0].backend == "llm"
    ok("the SDK's reply is filtered: the invented id and the smuggled override are gone")


# --------------------------------------------------------------------------
# Needs the socket.
# --------------------------------------------------------------------------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(db):
    """uvicorn on a free port with its own database. Returns (proc, base)."""
    port = free_port()
    env = dict(os.environ, PHC_DB=db)
    env.pop("ANTHROPIC_API_KEY", None)  # the live half exercises the router
    log = open(db + ".log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port),
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    for _ in range(100):
        if proc.poll() is not None:
            sys.exit("the API died on startup:\n%s" % pathlib.Path(db + ".log").read_text())
        try:
            urllib.request.urlopen(base + "/", timeout=1).read()
            return proc, base
        except Exception:
            time.sleep(0.2)
    proc.kill()
    sys.exit("the API never came up:\n%s" % pathlib.Path(db + ".log").read_text())


def live(base):
    kernel = client.Kernel(base)
    catalogue = kernel.catalogue()
    assert len(catalogue["operations"]) >= 9
    assert "phc.op.vitals-record" in catalogue["operations"]
    ok("the agent plans against the catalogue the running kernel loaded")

    # enc-001 is seeded standing at reception with no flags at all, so vitals
    # has a complete payload and an unmet precondition: the one combination
    # that makes the guard state a precondition rather than a missing answer.
    view = kernel.thread("enc-001")
    assert view["flags"] == [] and view["station"] == "reception", view["flags"]
    out = cli.respond(kernel, catalogue, view, "record her bp 140 over 90 and pulse 72",
                      which="router")
    assert "precondition not met: registered" in out, out
    assert "refused" in out
    ok("an unmet precondition comes back as the guard's own words")

    # And the refusal is really the kernel's: the same sentence over raw HTTP.
    try:
        kernel.propose("phc.op.vitals-record", "enc-001",
                       {"systolic": 140, "diastolic": 90, "pulse": 72})
    except client.Refused as no:
        assert no.reason == "precondition not met: registered", no.reason
        assert no.status == 422
    else:
        raise AssertionError("the kernel allowed vitals on an unregistered thread")
    ok("the refusal is the kernel's, verbatim, not this package's paraphrase")

    # enc-002 is registered and standing at the nurse, so the same sentence is
    # accepted. Accepted means a proposal id and nothing else.
    before = kernel.thread("enc-002")
    out = cli.respond(kernel, catalogue, before, "record her bp 140 over 90 and pulse 72",
                      which="router")
    assert "proposed as prop-" in out.replace("\033[32m", "").replace("\033[0m", ""), out
    proposal_id = out.split("prop-")[1].split()[0].split("\033")[0]
    after = kernel.thread("enc-002")
    assert after["flags"] == before["flags"], "the agent moved the thread's state"
    pending = [p for p in after["proposals"] if p["id"].endswith(proposal_id)]
    assert pending and pending[0]["status"] == "pending", after["proposals"]
    assert pending[0]["surface"] == "mcp"
    assert [a for a in after["audit"] if a["outcome"] == "proposed"]
    assert not [a for a in after["audit"] if a["outcome"] == "allowed"]
    ok("an accepted plan lands a pending proposal, no flag and no clinical row")

    # The kernel does hold the route. This process cannot dial it.
    try:
        kernel._call("/proposals/%s/confirm" % pending[0]["id"], {})
    except RuntimeError:
        pass
    else:
        raise AssertionError("the client dialled confirm")
    assert kernel.thread("enc-002")["proposals"], "the proposal vanished"
    ok("the proposal is still pending: only a person on screen ends it")

    # An utterance the router cannot map does not become a request at all.
    quiet = cli.respond(kernel, catalogue, kernel.thread("enc-002"),
                        "is the doctor in today", which="router")
    assert quiet.startswith("I do not know")
    ok("small talk reaches the kernel as nothing at all")

    # The CLI end to end, as a person would run it.
    env = dict(os.environ, PHC_API=base)
    env.pop("ANTHROPIC_API_KEY", None)
    run = subprocess.run([sys.executable, "-m", "agent",
                          "record her bp 140 over 90 and pulse 72",
                          "--thread", "enc-002", "--role", "nurse"],
                         cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "phc.op.vitals-record" in run.stdout and "prop-" in run.stdout, run.stdout
    assert "confirm it there. I cannot." in run.stdout
    ok("python3 -m agent proposes over a real socket and says who must finish it")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    if os.environ.get("SKIP_E2E"):
        print("warn agent live checks skipped: SKIP_E2E is set")
    else:
        llm_over_a_socket()
        with tempfile.TemporaryDirectory() as tmp:
            proc, base = serve(os.path.join(tmp, "live.sqlite3"))
            try:
                live(base)
            finally:
                proc.terminate()
                proc.wait(timeout=10)
    print("ok   agent live: %d checks, and none of them committed anything" % ran)
