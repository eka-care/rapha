"""Run: python3 scripts/check_go_parity.py

The Go backend's answers against the Python's, field for field, over two real
sockets at once.

Why this is a differential check and not a Go test
--------------------------------------------------
The port's rule is that the Python is right and the Go is wrong where they
disagree (docs/superpowers/plans/2026-10-31-go-backend-port.md). A Go test
asserting a literal shape would be a THIRD opinion: it would pass while both
engines drifted from each other, because the literal would have been copied
from whichever one was read last. So nothing here is written down. Both
kernels are started on the same declarations with the same environment, asked
the same question, and the two answers are compared.

What this does NOT do
---------------------
Replace the socket level checks. scripts/e2e.py and scripts/check_live.py are
the acceptance test and they run against either backend through
PHC_BACKEND; this is the narrower thing they cannot be, which is a
side-by-side diff. A route Go does not serve yet is named here, not skipped in
silence, so the list of what is still owed is in the output of a check rather
than in a commit message.

Also NOT done here: a shape with no PHC_FACILITY at all. bundles/phc declares
`facility: all-plugins`, so the default IS a shape and the empty case is
bundles/lab's, which the Go backend cannot serve yet at all (one bundle; see
cmd/api/main.go).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import backend                                                       # noqa: E402

PREFIX = "/api/v1/phc"
# The shapes bundles/phc declares. Every one of them, rather than a chosen
# two: a shape is one declared line and the whole point is that nothing else
# differs, so there is no reason to leave one out.
SHAPES = ("all-plugins", "no-laboratory", "consulting-room-only")
# The routes both engines serve today. Each is asked under both prefixes,
# because /api and /api/v1/phc are one router in the Python and two mounts in
# the Go, and that is exactly the kind of difference a diff should catch.
SERVED = ("/whoami", "/facility")

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def get(base, path, headers=None, expect=200):
    req = urllib.request.Request(base + path, method="GET",
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    body = json.loads(raw) if raw else {}
    assert status == expect, "GET %s: expected %s, got %s %s" % (
        path, expect, status, str(body)[:400])
    return body


def both(shape, db_dir):
    """One kernel of each language on the same declarations and the same shape.

    PHC_BACKEND is set per launch rather than for the process, because this is
    the one check that wants both at once and scripts/backend.py reads the
    environment when it is asked.
    """
    started = {}
    for name in (backend.PYTHON, backend.GO):
        os.environ[backend.ENV] = name
        started[name] = backend.launch(
            os.path.join(db_dir, "%s-%s.sqlite3" % (name, shape)),
            bundle="phc", facility=shape)
    os.environ.pop(backend.ENV, None)
    return started


def main():
    # The Go binary is built once, loudly, before anything is compared: a
    # build failure here must not read as a route mismatch.
    binary = backend.build_go()
    ok("the Go backend builds: %s" % binary.relative_to(ROOT))

    with tempfile.TemporaryDirectory() as tmp:
        for shape in SHAPES:
            started = both(shape, tmp)
            try:
                compare(shape, started[backend.PYTHON].base,
                        started[backend.GO].base)
            finally:
                for server in started.values():
                    server.close()

    print("\nok   go parity: %d checks, two engines on one set of declarations"
          % checks)
    return 0


def compare(shape, python, go):
    # --- the root. The service name and the bundle are the same fact in both;
    # `routes` is NOT, and saying so is the point of comparing it separately.
    py_root = get(python, "/")
    go_root = get(go, "/")
    assert py_root["service"] == go_root["service"], (py_root, go_root)
    assert py_root["bundle"] == go_root["bundle"], (py_root, go_root)
    assert sorted(py_root) == sorted(go_root), (sorted(py_root), sorted(go_root))
    # The Python's list is FastAPI's own route table, so it also carries
    # /docs, /redoc and /openapi.json, which are FastAPI's and not the
    # kernel's. Every kernel route is held both ways: the Go names no route
    # the Python does not serve, AND the Go names every route the Python
    # serves. The second direction is the one that matters, because a route
    # added to api/main.py and not to the Go's table would otherwise be
    # invisible until somebody noticed it missing.
    kernel_routes = {r for r in go_root["routes"] if r != "/"}
    served_routes = {r for r in py_root["routes"]
                     if r.startswith("/api") and r != "/"}
    assert kernel_routes == served_routes, \
        "only on the Go: %s\nonly on the Python: %s" % (
            sorted(kernel_routes - served_routes),
            sorted(served_routes - kernel_routes))
    ok("%s: the root answers the same service and the same bundle, and the "
       "two engines name the same %d routes" % (shape, len(kernel_routes)))

    # --- the two served routes, under both prefixes, byte for byte.
    for route in SERVED:
        for prefix in ("/api", PREFIX):
            for spelling in (prefix + route, prefix + route + "/"):
                py = get(python, spelling)
                gone = get(go, spelling)
                assert py == gone, "%s\npython: %s\ngo:     %s" % (
                    spelling, json.dumps(py, sort_keys=True),
                    json.dumps(gone, sort_keys=True))
    ok("%s: /whoami and /facility are identical under both prefixes and both "
       "spellings of the trailing slash" % shape)

    # --- and the shape is really doing something, so the line above is not
    # two engines agreeing about nothing.
    facility = get(go, PREFIX + "/facility")
    assert facility["facility"] == shape, facility["facility"]
    withheld = sorted(facility["withheld"])
    if shape == "all-plugins":
        assert withheld == [], withheld
    else:
        assert withheld, "%s withholds nothing, so this shape proves nothing" % shape
        # The declared list stays whole. A facility declines a capability; it
        # does not delete one from the bundle.
        for cap in withheld:
            assert cap in facility["capabilities"], (cap, facility["capabilities"])
        assert set(withheld).isdisjoint(facility["user"]["capabilities"]), facility
    ok("%s: the Go kernel withholds %d capabilities it still declares, and the "
       "caller holds none of them" % (shape, len(withheld)))

    # --- the role header. There is no authentication in either engine and
    # this is what that means: a header picks who you are. Compared rather
    # than asserted, so neither engine can be the one that invented a model.
    for role in ("nurse", "mo", "frontdesk", "demo"):
        header = {"X-PHC-Role": role, "X-PHC-Actor": "user:someone"}
        py = get(python, PREFIX + "/whoami", header)
        gone = get(go, PREFIX + "/whoami", header)
        assert py == gone, (role, py, gone)
    unknown = {"X-PHC-Role": "surgeon"}
    get(python, PREFIX + "/whoami", unknown, expect=400)
    get(go, PREFIX + "/whoami", unknown, expect=400)
    ok("%s: X-PHC-Role narrows both engines identically for 4 roles, and both "
       "refuse a role the bundle does not declare with a 400" % shape)

    # --- what Go does not serve yet, said out loud. 501 and not 404, so the
    # difference between "not ported" and "no such route" is on the wire.
    owed = []
    for route in sorted({r for r in get(python, "/")["routes"]
                         if r.startswith(PREFIX)}):
        # The templated ones cannot be asked without an id; the prefix is
        # enough, because the Go mounts a subtree.
        path = route.split("{")[0].rstrip("/")
        if path.endswith(tuple(SERVED)):
            continue
        body = get(go, path, expect=501)
        assert "does not serve" in body["detail"], body
        owed.append(path[len(PREFIX):] or "/")
    ok("%s: %d routes the Python serves answer 501 on the Go with the slice "
       "that will bring them, rather than 404" % (shape, len(owed)))


if __name__ == "__main__":
    sys.exit(main())
