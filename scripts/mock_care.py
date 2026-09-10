"""A stand-in for CARE, just enough for the MCP server to talk to.

Only the resource writes are fake. The guard is the real one from
catalogue/guard.py and the validator is the real one built from the real
questionnaires, so what this demonstrates is the actual decision path, not a
mime of it.

Run: python3 scripts/mock_care.py [port]
"""
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

from care_phc.thread import Snapshot, derive  # noqa: E402
from catalogue import guard, validate  # noqa: E402

CAT = json.loads((pathlib.Path(__file__).parents[1] / "catalogue" / "catalogue.json").read_text())

# One patient mid-visit: registered with no ABHA, consulted and prescribed, but
# vitals not yet taken. Addendum §D allows a consultation to start with a
# vitals-pending flag, because making the doctor wait on another station is how
# queues jam. It also leaves several different guard outcomes reachable.
SNAPSHOT = Snapshot(patient_exists=True, abha_number=None, vitals_observations=0,
                    consult_notes=1, active_medication_requests=2, prescribed_lines=2)
STATE = derive(SNAPSHOT)

# A real sub-centre configuration, not an edge case: addendum §C notes one
# nurse may hold Nurse plus Pharmacist plus Lab technician. Change these to
# watch the tool list change.
CAPABILITIES = sorted(
    set(CAT["bundles"]["nurse"]) | set(CAT["bundles"]["pharmacist"]) | set(CAT["bundles"]["mo"])
)

PROPOSALS = []


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        blob = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):
        if self.path.rstrip("/") == "/api/v1/phc/whoami":
            return self._send(200, {"capabilities": CAPABILITIES})
        self._send(404, {"detail": "no such endpoint"})

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        if len(parts) < 6 or parts[3] != "operations":
            return self._send(404, {"detail": "no such endpoint"})
        op_id, verb = parts[4], parts[5]
        op = CAT["operations"].get(op_id)
        if not op:
            return self._send(404, {"detail": f"unknown operation {op_id}"})

        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        payload = body.get("payload") or {}

        schema = validate.load(op["input"])
        decision = guard.evaluate(
            op, caps=set(CAPABILITIES), state=STATE, payload=payload,
            surface=guard.MCP if verb == "propose" else guard.RENDERED,
            validate=validate.make_validator(schema),
            actor="service-account:demo",
        )
        if not decision:
            # The guard's reason is the useful thing to hand an agent.
            return self._send(422, {"detail": decision.reason, "audit": decision.audit})

        PROPOSALS.append({"operation": op_id, "payload": payload})
        return self._send(200, {
            "proposal_id": f"prop-{len(PROPOSALS):03d}",
            "status": decision.reason,
            "operation": op_id,
            "awaiting": "clinician review on the rendered surface",
            "flags_raised": sorted(validate.flags(schema, payload)),
        })

    def log_message(self, *a):
        pass  # the demo prints its own narrative


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"mock CARE on :{port}  state={sorted(STATE)}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
