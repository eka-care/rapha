"""Drive care_phc_mcp the way an agent would, and narrate what happens.

Speaks MCP over stdio to the real Go binary, which talks HTTP to a mock CARE
that runs the real guard. Nothing here is stubbed except CARE's resource
writes, so the propose-never-commit property is demonstrated rather than
described.

Run: python3 scripts/agent_demo.py
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
PORT = 8765


class Mcp:
    """The smallest MCP client that works: JSON-RPC 2.0 over newline-delimited stdio."""

    def __init__(self, proc):
        self.proc = proc
        self.n = 0

    def call(self, method, params=None):
        """Returns the result, or raises. Tool errors come back as results with
        isError, not as JSON-RPC errors; an unknown tool is a real error."""
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed the connection")
            reply = json.loads(line)
            if reply.get("id") == self.n:
                if "error" in reply:
                    raise RuntimeError(reply["error"])
                return reply["result"]

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()


def rule(title):
    print(f"\n\033[1m{title}\033[0m\n" + "-" * len(title))


def main():
    binary = ROOT / "care_phc_mcp" / "care_phc_mcp"
    if not binary.exists():
        print("build it first:  cd care_phc_mcp && go build -o care_phc_mcp .")
        return 1

    care = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "mock_care.py"), str(PORT)],
                            stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/phc/whoami/", timeout=0.5)
                break
            except Exception:
                time.sleep(0.1)
        else:
            print("mock CARE did not come up")
            return 1

        server = subprocess.Popen(
            [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
            env={"PATH": "/usr/bin:/bin",
                 "CARE_BASE_URL": f"http://127.0.0.1:{PORT}",
                 "CARE_SERVICE_TOKEN": "demo"},
        )
        mcp = Mcp(server)
        mcp.call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "agent-demo", "version": "0"},
        })
        mcp.notify("notifications/initialized")

        rule("1. What this service account can see")
        tools = mcp.call("tools/list")["tools"]
        for t in tools:
            print(f"  {t['name']}")
        print(f"\n  {len(tools)} tools. Every write is a proposal; there is no confirm verb.")
        assert not any("confirm" in t["name"] for t in tools)

        def propose(name, args, note):
            rule(note)
            if name not in {t["name"] for t in tools}:
                print(f"  {name} is not in this account's tool list. The capability")
                print("  filter is the first gate, before the guard sees anything.")
                return
            out = mcp.call("tools/call", {"name": name, "arguments": args})
            text = out["content"][0]["text"]
            start = text.find("{")
            if start != -1:
                try:
                    # The server wraps the JSON in prose, so parse a prefix
                    # rather than the whole string.
                    body, _ = json.JSONDecoder().raw_decode(text[start:])
                except json.JSONDecodeError:
                    body = None
                if body:
                    if "detail" in body:
                        print(f"  \033[31mrefused\033[0m  {body['detail']}")
                        print("           audited as a denial on surface "
                              f"{body['audit']['surface']}")
                        return
                    flags = body.get("flags_raised") or []
                    print(f"  \033[32mproposed\033[0m {body['proposal_id']}"
                          f"  awaiting {body['awaiting']}")
                    if flags:
                        print(f"           raised {', '.join(flags)}")
                    return
            print("  " + text.replace("\n", "\n  "))

        propose("propose_pharmacy_dispense",
                {"dispenses": {"drug": "Amlodipine 5 mg", "qty": 30}, "partial": False},
                "2. Dispense, whose precondition is met because an Rx is confirmed")

        propose("propose_vitals_record", {"systolic": 400, "diastolic": 80, "pulse": 72},
                "3. A systolic of 400, which is outside physiological range")

        propose("propose_vitals_record", {"systolic": 190, "diastolic": 96, "pulse": 72},
                "4. A systolic of 190: high, but real, so it commits and flags")

        propose("propose_patient_register",
                {"name": "A", "age": 30, "sex": "female", "phone": "9", "village": "Yadiki"},
                "5. Registering someone already registered")

        propose("propose_abha_link", {"method": "create_new", "consent_given": True},
                "6. An irreversible operation, asked for from the machine surface")

        print("\n\033[1mNothing above was committed.\033[0m Each success is a proposal "
              "waiting\non a clinician at the rendered surface.\n")
        server.terminate()
        return 0
    finally:
        care.terminate()


if __name__ == "__main__":
    sys.exit(main())
