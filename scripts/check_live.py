"""Run: python3 scripts/check_live.py

The screens are live. Proved by running the real renderer over what a real
kernel answered, twice, for two facilities that differ by one declared list.

What this is for
----------------
There is an HTML prototype of this product whose patients are written into its
own JavaScript, and until this step the renderer still had one of those seams
left: `web/src/declarations.ts` compiled the questionnaires and the value sets
into the browser bundle from disk, so what a form asked a clinician was the
only thing on a screen the kernel did not serve. `GET /questionnaires/` serves
them now, and this is the check that the renderer really reads them from there.

What it does NOT prove, and the limits are the point of saying so:

 - It is not a browser. Nothing here lays anything out, resolves a cascade or
   clicks. `web/src/ui.check.ts` says the same about itself and means it.
 - "Live" here means THIS kernel and the threads bundles/phc/seed.yaml
   declares. No call leaves this machine. Nothing is asked of Eka, of CARE, of
   ABDM or of any directory, and no real patient exists anywhere in it.
 - It drives one role, the demo account that holds every capability, because
   that is the only account this kernel hands out. So what differs between the
   two shapes below differs because of the FACILITY and not because of a login.

Two halves, like scripts/e2e.py and bundles/lab/check.py: the capture is taken
over a real socket from a real uvicorn, and SKIP_E2E=1 takes it in process
through the same routes instead. The renderer half runs either way, because it
is the half that would say a screen had gone back to inventing something.

Mutations this is built to fail under are listed at the bottom of the file.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import backend                                                       # noqa: E402

PREFIX = "/api/v1/phc"
SHAPES = ("all-plugins", "no-laboratory")

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


# ---------------------------------------------------------------------------
# asking a kernel
# ---------------------------------------------------------------------------

class OverASocket:
    """A real kernel on a real port, running one facility shape.

    Which backend answers is scripts/backend.py's decision and not this
    file's: PHC_BACKEND picks Python or Go and these screens cannot tell.
    """

    def __init__(self, shape, db):
        self.server = backend.launch(
            db, bundle="phc", facility=shape,
            log=pathlib.Path(db).with_suffix(".log"))
        self.base = self.server.base
        self.port = self.server.port

    def get(self, path, expect=200):
        req = urllib.request.Request(self.base + PREFIX + path, method="GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        assert status == expect, "GET %s: expected %s, got %s %s" % (
            path, expect, status, raw[:300])
        return json.loads(raw) if raw else {}

    def close(self):
        self.server.close()


class InProcess:
    """The same routes, no port. What SKIP_E2E leaves behind.

    api.main resolves its bundle and its facility at import time, exactly as a
    deployed kernel does, so a shape cannot be switched inside one process:
    each one is a child python of its own, which is also what keeps the
    environment honest rather than mutated under a running app. One request
    per line in, one answer per line out, so the child boots once.
    """

    SCRIPT = """
import json, os, sys
sys.path.insert(0, %(root)r)
os.environ["PHC_DB"] = %(db)r
os.environ["PHC_BUNDLE"] = "phc"
os.environ["PHC_FACILITY"] = %(shape)r
from fastapi.testclient import TestClient
from api.main import app
client = TestClient(app)
print("ready", flush=True)
for line in sys.stdin:
    if not line.strip():
        break
    path = json.loads(line)
    r = client.get("/api/v1/phc" + path)
    print(json.dumps({"status": r.status_code,
                      "body": r.json() if r.content else {}}), flush=True)
"""

    def __init__(self, shape, db):
        self.proc = subprocess.Popen(
            [sys.executable, "-c", self.SCRIPT % {
                "root": str(ROOT), "db": db, "shape": shape}],
            cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        if self.proc.stdout.readline().strip() != "ready":
            sys.exit("the in process kernel never came up:\n%s"
                     % self.proc.stderr.read()[-3000:])

    def get(self, path, expect=200):
        self.proc.stdin.write(json.dumps(path) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            sys.exit("the in process kernel died on GET %s:\n%s"
                     % (path, self.proc.stderr.read()[-3000:]))
        answer = json.loads(line)
        assert answer["status"] == expect, "GET %s: expected %s, got %s %s" % (
            path, expect, answer["status"], str(answer["body"])[:300])
        return answer["body"]

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def kernel(shape, db):
    return InProcess(shape, db) if os.environ.get("SKIP_E2E") else OverASocket(shape, db)


# ---------------------------------------------------------------------------
# what the four screens read
# ---------------------------------------------------------------------------

def bound_slugs(questionnaires):
    """Every value set a question binds its answer to. Walked, because a bound
    sub question of a repeating group is where the empty dropdown was."""
    found = set()

    def walk(qs):
        for q in qs or []:
            if q.get("answer_value_set"):
                found.add(q["answer_value_set"])
            walk(q.get("questions"))

    for q in questionnaires.values():
        walk(q.get("questions"))
    return sorted(found)


def capture(shape, db):
    """One facility's answers to exactly what the screens ask for.

    Nothing is composed here. Every key is one route's body, unedited, so the
    renderer half downstream is reading what a browser would have read.
    """
    k = kernel(shape, db)
    try:
        out = {"shape": shape, "facility": k.get("/facility/"),
               "catalogue": k.get("/catalogue/"),
               "questionnaires": k.get("/questionnaires/")["questionnaires"]}
        # The patient list: every view this facility declares whose capability
        # the caller still holds. A view gated by a withheld capability
        # answers 403 by design (scripts/check_plugins.py owns that
        # assertion), so it is asked for as a 403 and kept out of the
        # renderer's hands, which is what the sidebar does too.
        held_back = out["facility"]["withheld"]
        out["views"], out["refused"], later = {}, [], []
        for v in out["facility"]["views"]:
            if v["capability"] in held_back:
                k.get("/views/%s/" % v["id"], expect=403)
                out["refused"].append(v["id"])
            elif v["kind"] == "summary":
                # A summary is a view OF a thread, so it needs one. Asked
                # below, once a thread is known, and refused with a 400 until
                # then -- which is the kernel's answer and not a wrinkle.
                later.append(v["id"])
            else:
                out["views"][v["id"]] = k.get("/views/%s/" % v["id"])

        # A thread, and the subject behind it: every row of every queue,
        # whatever this facility's seed put there.
        rows = [r for view in out["views"].values() if view.get("kind") == "queue"
                for r in (view.get("rows") or [])]
        out["threads"], out["subjects"] = {}, {}
        workflows = out["catalogue"].get("workflows") or {}
        spine = next((w.get("spine") for w in workflows.values() if w.get("spine")), None)
        for row in rows:
            tid = row["thread"]
            out["threads"][tid] = k.get("/threads/%s/" % tid)
            key = (out["threads"][tid].get("subject") or {}).get(spine) if spine else None
            if key and key not in out["subjects"]:
                out["subjects"][key] = k.get("/subjects/%s/" % key)
        first = next(iter(out["threads"]), None)
        for vid in later:
            k.get("/views/%s/" % vid, expect=400)
            if first:
                out["views"][vid] = k.get("/views/%s/?thread=%s" % (vid, first))

        out["valuesets"] = {s: k.get("/valuesets/%s/?limit=200" % s)
                            for s in bound_slugs(out["questionnaires"])}
        return out, k
    except BaseException:
        k.close()
        raise


# ---------------------------------------------------------------------------
# 1. every parameterless read in the contract really answers
# ---------------------------------------------------------------------------

from kernel.contracts import ROUTES                                # noqa: E402


def contract_routes_answer(k):
    """kernel/contracts.py ROUTES is the written down shape of this API, and
    until now nothing read it, so it was free to drift. Every GET in it that
    needs no path parameter is asked here."""
    asked = []
    for name, spelling in sorted(ROUTES.items()):
        method, path = spelling.split()[0], spelling.split()[1]
        if method != "GET" or "{" in path:
            continue
        asked.append(name)
        k.get(path.split("?")[0][len(PREFIX):])
    assert len(asked) >= 4, asked
    ok("every parameterless GET kernel/contracts.py writes down answers: %s"
       % ", ".join(asked))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="live-"))
    captures = {}
    try:
        for shape in SHAPES:
            got, k = capture(shape, str(tmp / ("%s.sqlite3" % shape)))
            try:
                if shape == SHAPES[0]:
                    contract_routes_answer(k)
            finally:
                k.close()
            captures[shape] = got
            (tmp / ("%s.json" % shape)).write_text(json.dumps(got))

        for shape, got in captures.items():
            assert got["facility"]["facility"] == shape, got["facility"]["facility"]
            assert got["questionnaires"], shape
            ok("%s answered over %s: %d views, %d threads, %d forms, %d value sets"
               % (shape, "a real socket" if not os.environ.get("SKIP_E2E")
                  else "the same routes in process",
                  len(got["views"]), len(got["threads"]),
                  len(got["questionnaires"]), len(got["valuesets"])))

        # The seeded day is the facility's own: a centre with no laboratory
        # could not have had a thread that visited one.
        counts = {s: len(c["threads"]) for s, c in captures.items()}
        assert counts[SHAPES[0]] > counts[SHAPES[1]], counts
        ok("and the two demo days differ: %d threads at %s, %d at %s"
           % (counts[SHAPES[0]], SHAPES[0], counts[SHAPES[1]], SHAPES[1]))

        # --- the renderer half, over both captures, same module twice
        node = subprocess.run(
            ["node", "--experimental-strip-types", "src/live.check.ts", str(tmp)],
            cwd=str(ROOT / "web"), capture_output=True, text=True)
        sys.stdout.write(node.stdout)
        if node.returncode:
            sys.stderr.write(node.stderr[-4000:])
            return 1
        global checks
        checks += sum(1 for line in node.stdout.splitlines() if line.startswith("ok"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("ok   live: %d checks, over %d facility shapes of one bundle" % (checks + 1, len(SHAPES)))
    return 0


# ---------------------------------------------------------------------------
# The mutation ledger: 12 applied, 12 caught, with the check that failed FIRST
# ---------------------------------------------------------------------------
#
# Each one was applied, proved applied (the file changed AND the replaced text
# was gone), run through the whole gate, reverted, and the revert proved clean
# against git. The gate stops at the first failure, so "first" below is the
# gate's own order and not this file's.
#
#  1. api/main.py: the questionnaires route returns an empty dict.
#     -> scripts/check_live.py, the capture's own `assert got["questionnaires"]`.
#  2. web/src/declarations.ts: questionnaire() invents an empty form for a slug
#     it was never given, which is what reading a file back would look like.
#     -> web/src/live.check.ts, "an unserved slug has no form".
#  3. web/src/declarations.ts: a value set expands to no concepts.
#     -> web/src/live.check.ts, "condition binds condition-code and has
#        nothing to choose".
#  4. web/src/grants.ts: drop the withheld test from inert().
#     -> web/src/ui.check.ts, "a withheld capability is dead, whatever the
#        workflow draws". Also caught behaviourally on its own by
#        web/src/grants.check.ts, confirmed separately, because a text match is
#        not a proof that the function behaves.
#  5. kernel/plugins.py: absent() returns {}, so no plugin has a title.
#     -> web/src/grants.check.ts, the sentence reads out a plugin id.
#  6. kernel/views.py: a summary section stops sending its `fields`.
#     -> web/src/live.check.ts, "a summary section carries rows and declares
#        no fields".
#  7. web/src/view/View.tsx: lead a row with the old six word list.
#     -> web/src/ui.check.ts, "in the declared order, and from no other list".
#  8. web/src/screens/Patient.tsx: read age, sex and village off the subject.
#     -> web/src/ui.check.ts, the portability check: `view column "village"`.
#  9. web/src/declarations.ts: put the build time glob back.
#     -> web/src/ui.check.ts, "a renderer file reads a declaration off disk
#        instead of from the kernel".
# 10. web/src/app/App.tsx: draw a screen before the forms have arrived.
#     -> web/src/ui.check.ts, "and does not draw a screen until they are there".
# 11. scripts/check_queues.py: put the visit back on the wall clock.
#     -> scripts/check_queues.py itself, which is the point: the fix is load
#        bearing and the check it repairs is what fails without it.
# 12. api/main.py: caller() stops subtracting a withheld plugin.
#     -> scripts/check_plugins.py, which owns that property and runs first.
#        web/src/live.check.ts was then run alone against the same mutation and
#        failed with "phc.op.lab-order is still offered at a centre whose
#        plugin for it is off", so this file is not relying on the earlier one.
#
# Refused before it ran: one. The first spelling of mutation 2 appended its new
# branch above the old return and left the old text in place, so the harness
# refused it. That is the substring trap in the direction that matters: it
# would have run, passed, and been recorded as a mutation that proved nothing.
#
# One assertion was deleted rather than kept. grants.check.ts asserted that an
# inert switch's sentence does not print a plugin id, which cannot be tested
# here: the only withheld plugin's id is `orders` and its title is "Laboratory
# orders and results", so the id is a substring of the title and the assertion
# fails on the one case it has. The equality against the declared title that
# sits beside it is the real test.

if __name__ == "__main__":
    sys.exit(main())
