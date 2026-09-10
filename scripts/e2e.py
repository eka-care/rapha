"""Run: python3 scripts/e2e.py

The whole thing, over a real socket, in one process tree.

api/tests/test_api.py drives FastAPI in process, which is the right place for
the write path's edge cases. This is the other half: it starts uvicorn on a
port, seeds a file on disk, and walks a patient through the line with HTTP,
then reads the SQLite file directly to prove the row is really there. It also
drives the unmodified Go MCP server over stdio, because "the agent surface
still works" is not something the Python tests can answer.

It is slower than every other check and it is the only one that binds a port.
If it fails while the in process tests pass, the fault is in the wiring:
routes, ports, JSON shapes, the MCP client's paths.
"""
from __future__ import annotations

import json
import os
import pathlib
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
PREFIX = "/api/v1/phc"  # the MCP server's prefix; /api is the same router
checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(base, path, body=None, method=None, expect=200):
    """One request. Never follows a redirect: a 307 here is a bug, not a
    detail, because curl and fetch both make it visible in different ways."""
    url = base + PREFIX + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method or ("POST" if data is not None else "GET"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    parsed = json.loads(raw) if raw else {}
    assert status == expect, "%s %s: expected %s, got %s %s" % (
        req.method, path, expect, status, parsed)
    return parsed


def wait_for(base, proc, log):
    for _ in range(100):
        if proc.poll() is not None:
            sys.exit("the API died on startup:\n%s" % pathlib.Path(log).read_text())
        try:
            urllib.request.urlopen(base + "/", timeout=1).read()
            return
        except Exception:
            time.sleep(0.2)
    sys.exit("the API never came up:\n%s" % pathlib.Path(log).read_text())


def rows(db, sql, params=()):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def register(base, name, token):
    """Open a thread and register a patient on it. Returns the thread id."""
    thread = call(base, "/threads/", {"token": token})["id"]
    call(base, "/operations/phc.op.patient-register/commit/",
         {"thread": thread, "payload": {"name": name, "age": 44, "sex": "female",
                                        "phone": "9000000000", "village": "Kolar"}})
    return thread


def mcp(base, thread):
    """Drive the Go MCP server, unmodified, against this API."""
    binary = ROOT / "care_phc_mcp" / "care_phc_mcp"
    if not binary.exists():
        print("skip the Go MCP server: build it with (cd care_phc_mcp && go build .)")
        return
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "e2e", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "propose_vitals_record",
                    "arguments": {"patient": thread, "systolic": 128,
                                  "diastolic": 82, "pulse": 76, "temperature": 36.8,
                                  "spo2": 98, "weight": 61}}},
    ]
    # stdin stays open while the replies are read: the server exits on EOF,
    # and closing it up front loses every answer.
    proc = subprocess.Popen(
        [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True,
        env=dict(os.environ, CARE_BASE_URL=base))
    replies = {}
    try:
        proc.stdin.write("\n".join(json.dumps(x) for x in lines) + "\n")
        proc.stdin.flush()
        for _ in lines:  # one reply per request; the notification answers nothing
            line = proc.stdout.readline()
            if not line:
                break
            if line.startswith("{"):
                reply = json.loads(line)
                if "id" in reply:
                    replies[reply["id"]] = reply
            if 3 in replies:
                break
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    assert 2 in replies and 3 in replies, replies

    tools = [t["name"] for t in replies[2]["result"]["tools"]]
    assert tools and all(t.startswith("propose_") for t in tools), tools
    ok("the Go MCP server offers %d tools and every one of them is a proposal" % len(tools))

    said = replies[3]["result"]["content"][0]["text"]
    assert "Proposed, not committed" in said, said
    assert not replies[3]["result"].get("isError"), said
    ok("an agent's tool call reaches the kernel and comes back as a proposal")


def main():
    db = os.path.join(tempfile.mkdtemp(), "e2e.sqlite3")
    port = free_port()
    base = "http://127.0.0.1:%d" % port
    log = os.path.join(os.path.dirname(db), "api.log")
    handle = open(log, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
        env=dict(os.environ, PHC_DB=db, PHC_BUNDLE="phc"))
    try:
        wait_for(base, proc, log)
        ok("the API starts and seeds %s" % os.path.basename(db))

        # --- both spellings of every path, with no redirect in between
        assert call(base, "/queue")["kind"] == "queue"
        queue = call(base, "/queue/")
        ok("a path with and without its trailing slash both answer 200")

        # --- a queue view, declared, not hand built
        stations = {r["thread"]: r["station"] for r in queue["rows"]}
        assert stations == {"enc-001": "reception", "enc-002": "nurse",
                            "enc-003": "doctor", "enc-004": "lab",
                            "enc-005": "pharmacy", "enc-006": None}, stations
        ok("the queue puts six seeded threads at six stations")

        panel = call(base, "/threads/enc-002/")
        assert panel["station"] == "nurse"
        assert [s["status"] for s in panel["line"]] == ["done", "now", "pending",
                                                        "skipped", "skipped"]
        assert "phc.op.pharmacy-dispense" not in [a["id"] for a in panel["actions"]]
        ok("a thread opens with its line, its flags and only the actions it allows")

        # --- propose, which must not write
        payload = {"systolic": 138, "diastolic": 88, "pulse": 92,
                   "temperature": 37.1, "spo2": 97, "weight": 54}
        proposed = call(base, "/operations/phc.op.vitals-record/propose/",
                        {"patient": "enc-002", "payload": payload})
        pid = proposed["proposal_id"]
        assert rows(db, "SELECT * FROM observation WHERE encounter='enc-002'") == []
        ok("a proposal writes a proposal and no clinical row")

        # --- confirm, which must write
        confirmed = call(base, "/proposals/%s/confirm/" % pid, {"confirmed": True})
        assert confirmed["proposal"]["status"] == "confirmed"
        assert confirmed["thread"]["station"] == "doctor"
        written = rows(db, "SELECT code, value FROM observation WHERE encounter='enc-002'")
        assert dict(written)["systolic"] == "138", written
        ok("confirming writes the row, and the line moves to the next station")

        call(base, "/proposals/%s/confirm/" % pid, {"confirmed": True}, expect=409)
        ok("a proposal is confirmed once; the replay is a 409")

        # --- the three refusals
        denied = call(base, "/operations/phc.op.pharmacy-dispense/commit/",
                      {"thread": "enc-002",
                       "payload": {"dispenses": ["Amlodipine 5mg x 10"]}}, expect=422)
        assert "precondition not met: rx.confirmed" in denied["detail"], denied
        ok("a precondition that is not met refuses the write: %s" % denied["detail"])

        thread = register(base, "Range Test", "T-90")
        out_of_range = dict(payload, systolic=400)
        denied = call(base, "/operations/phc.op.vitals-record/commit/",
                      {"thread": thread, "payload": out_of_range}, expect=422)
        assert "outside 70 to 250" in denied["detail"], denied
        ok("an out of range value refuses the write: %s" % denied["detail"])

        allowed = call(base, "/operations/phc.op.vitals-record/commit/",
                       {"thread": thread,
                        "payload": dict(out_of_range,
                                        override_reason="repeated on the other arm, "
                                                        "recorded as measured")})
        assert "vitals.flagged" in allowed["thread"]["flags"]
        ok("the same value with a reason is allowed, written and flagged")

        denied = call(base, "/operations/phc.op.abha-link/propose/",
                      {"patient": "enc-002",
                       "payload": {"method": "link_existing",
                                   "abha_number": "11-1111-1111-1111",
                                   "consent_given": True}}, expect=422)
        assert "rendered surface" in denied["detail"], denied
        ok("an irreversible operation from a machine surface: %s" % denied["detail"])

        denied = call(base, "/operations/phc.op.abha-link/commit/",
                      {"thread": "enc-002",
                       "payload": {"method": "link_existing",
                                   "abha_number": "11-1111-1111-1111",
                                   "consent_given": True}}, expect=422)
        assert "explicit confirm" in denied["detail"], denied
        ok("the same operation on screen without a tap: %s" % denied["detail"])

        linked = call(base, "/operations/phc.op.abha-link/commit/",
                      {"thread": "enc-002", "confirmed": True,
                       "payload": {"method": "link_existing",
                                   "abha_number": "11-1111-1111-1111",
                                   "consent_given": True}})
        assert "abha.linked" in linked["thread"]["flags"]
        ok("with the tap it goes through and the flag flips to abha.linked")

        # --- a capability the caller does not hold
        call(base, "/operations/phc.op.rx-prescribe/commit/?role=frontdesk",
             {"thread": "enc-002", "payload": {"medications": [{"drug": "x"}]}},
             expect=422)
        ok("a role without the capability is refused the write")

        # --- local analytics over the same declarations
        dash = call(base, "/views/phc.view.facility-dashboard/")
        assert {r["metric"] for r in dash["rows"]} == {
            "phc.metric.visits", "phc.metric.abha-coverage",
            "phc.metric.vitals-flagged-rate"}
        assert dash["rows"][0]["value"] >= 6
        ok("the dashboard evaluates three declared metrics against the same store")

        # --- the audit log saw the refusals too, not only the writes
        outcomes = [r[0] for r in rows(db, "SELECT outcome FROM audit")]
        assert any(o.startswith("denied") for o in outcomes), outcomes
        assert any(o in ("allowed", "confirmed") for o in outcomes), outcomes
        ok("the audit log holds what was refused as well as what was written")

        # A registered patient standing at the nurse, so the agent's proposal
        # is refused by nothing but the surface rule if it is refused at all.
        mcp(base, register(base, "Agent Test", "T-91"))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        handle.close()

    print("ok   end to end: %d checks over a real socket" % checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
