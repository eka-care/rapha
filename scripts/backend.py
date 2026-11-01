"""Which backend a socket check launches. One place, not seven.

Why this file exists
--------------------
Six places in this repository started a kernel on a port, each with its own
`[sys.executable, "-m", "uvicorn", "api.main:app", ...]` written out by hand.
They were parameterised by port, by database file, by bundle and by facility
shape, and by nothing else: which LANGUAGE answers was a constant spelled six
times.

The Go port's acceptance test is that those checks pass against Go unmodified
except for which backend they launch (docs/superpowers/plans/
2026-10-31-go-backend-port.md, "The rule that governs the whole port"). So
that one constant becomes one variable, read in one place.

    PHC_BACKEND=python   (the default: nothing changes until asked)
    PHC_BACKEND=go       a real build and a real launch of cmd/api

Both are real sockets. There is no stub and no in-process shortcut here: the
whole value of these checks is that they do not know what is answering.

What this does NOT decide
-------------------------
The in-process halves. `SKIP_E2E=1` paths (scripts/check_live.py's InProcess,
bundles/lab/check.py's import-time half) drive the Python kernel as a library,
not over a socket, so they are not a backend choice and are untouched.

The environment contract is the backend's, not this file's
----------------------------------------------------------
PHC_DB, PHC_BUNDLE and PHC_FACILITY mean the same thing to both backends, and
a caller sets them the same way for either. That is deliberate: a check that
had to know which backend it was configuring would be back where it started.

WHICH IS WHY THE SECOND BUNDLE'S CATALOGUE IS COMPILED HERE
-----------------------------------------------------------
A Go kernel reads catalogue.json from the tree, and the tracked one is
compiled for ONE bundle at a time. So starting the Go backend on a second
bundle needs that bundle's catalogue compiled somewhere and the process
pointed at it, which is exactly the kind of per backend launch detail this
file exists to own: `PHC_BUNDLE=lab` goes on meaning the same thing to a
caller, and what it takes to honour it stops being the caller's problem.

The compile is the PYTHON'S, and that is the architecture rather than a
shortcut. Declarations compile to catalogue.json and an engine reads it; the
Go engine does not recompile anything, and `python3 -m kernel.declarations
<bundle> --out <path>` is the compiler writing its artifact where it is
wanted. Nothing tracked is touched.
"""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]

# The variable, its two values, and the one that is the default. The default
# being `python` is what lets this land with the gate unchanged: every check
# runs exactly as it did until somebody asks for Go.
ENV = "PHC_BACKEND"
PYTHON = "python"
GO = "go"
BACKENDS = (PYTHON, GO)
DEFAULT = PYTHON

# Where the Go API's command lives and what its binary is called. The MCP
# server's binary keeps its own name and its own path, because scripts/e2e.py
# and scripts/agent_demo.py drive it by that path and it is not a backend
# choice: there is one MCP server and it is already Go.
GO_MODULE = ROOT / "care_phc_mcp"
GO_API_PACKAGE = "./cmd/api"
GO_API_BINARY = GO_MODULE / "care_phc_api"

# Built at most once per process. Three servers in one scripts/e2e.py run is
# three launches and one build.
_built = False


def chosen() -> str:
    """Which backend, refusing a value it cannot launch.

    Refused by name rather than silently falling back to Python: a typo in
    PHC_BACKEND that quietly ran the reference implementation would report a
    green run against Go that never happened, which is the one failure this
    whole file exists to make impossible.
    """
    name = os.environ.get(ENV) or DEFAULT
    if name not in BACKENDS:
        raise SystemExit(
            "\n%s=%r is not a backend. There are two: %s.\n"
            % (ENV, name, ", ".join(BACKENDS)))
    return name


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_go() -> pathlib.Path:
    """Build cmd/api, or fail saying exactly what Go said.

    Loud on purpose. A check that skipped when the binary would not build
    would report "ok" for a backend that does not compile, and the skip would
    read like a pass in the gate's output.
    """
    global _built
    if _built:
        return GO_API_BINARY
    done = subprocess.run(
        ["go", "build", "-o", str(GO_API_BINARY), GO_API_PACKAGE],
        cwd=str(GO_MODULE), capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(
            "\nthe Go backend did not build, so there is nothing to check "
            "against.\n\n  cd %s && go build -o %s %s\n\n%s%s\n"
            % (GO_MODULE, GO_API_BINARY.name, GO_API_PACKAGE,
               done.stdout, done.stderr))
    if not GO_API_BINARY.exists():
        raise SystemExit(
            "\ngo build reported success and wrote no binary at %s.\n"
            % GO_API_BINARY)
    _built = True
    return GO_API_BINARY


# The artifact the compile step writes and a Go kernel reads, and the variable
# that points one process at a different copy of it. Spelled here to match
# care_phc_mcp's CatalogueEnv and CataloguePath.
CATALOGUE = ROOT / "catalogue" / "catalogue.json"
CATALOGUE_ENV = "PHC_CATALOGUE"


def compiled_bundle() -> str:
    """Which bundle the tracked catalogue.json was compiled for."""
    import json
    with open(CATALOGUE) as f:
        return str(json.load(f)["manifest"]["id"])


def catalogue_for(bundle: str, at) -> pathlib.Path:
    """Compile `bundle`'s catalogue to `at`, and say where it is.

    Loud on failure, for the reason build_go is: a check that quietly carried
    on would start the Go kernel on the tracked catalogue, which is a
    DIFFERENT BUNDLE, and the kernel's own refusal would then read as the
    check's failure rather than as this step's.
    """
    at = pathlib.Path(at)
    done = subprocess.run(
        [sys.executable, "-m", "kernel.declarations", bundle, "--out", str(at)],
        cwd=str(ROOT), capture_output=True, text=True)
    if done.returncode != 0 or not at.exists():
        raise SystemExit(
            "\nthe %r bundle's catalogue did not compile, so the Go backend "
            "has nothing to serve it from.\n\n  python3 -m kernel.declarations "
            "%s --out %s\n\n%s%s\n"
            % (bundle, bundle, at, done.stdout, done.stderr))
    return at


def command(port: int) -> list:
    """The argv that starts the chosen backend on `port`."""
    if chosen() == GO:
        return [str(build_go()), "--host", "127.0.0.1", "--port", str(port)]
    return [sys.executable, "-m", "uvicorn", "api.main:app",
            "--host", "127.0.0.1", "--port", str(port)]


class Server:
    """A kernel on a port, whichever language is answering.

    Ready when it returns: the constructor does not come back until the root
    route has answered, or it exits with the server's own log. Every caller
    wanted that and five of them wrote the wait loop out again.
    """

    def __init__(self, db, *, bundle=None, facility=None, log=None,
                 env=None, drop=()):
        self.backend = chosen()
        self.port = free_port()
        self.base = "http://127.0.0.1:%d" % self.port
        self.log = pathlib.Path(log or (str(db) + ".log"))
        self.handle = open(self.log, "w")
        self.db = db

        where = dict(os.environ)
        for key in drop:
            where.pop(key, None)
        where["PHC_DB"] = str(db)
        if bundle is not None:
            where["PHC_BUNDLE"] = bundle
        if facility is not None:
            where["PHC_FACILITY"] = facility

        # A Go kernel reads catalogue.json from the tree, and the tracked one
        # holds ONE bundle's declarations. So a second bundle gets its own
        # compiled copy beside this server's database, and this process alone
        # is pointed at it. Only when it is actually a different bundle: the
        # ordinary case reads the tracked file, which is what every other
        # check already measures.
        if (self.backend == GO and bundle is not None
                and bundle != compiled_bundle()
                and CATALOGUE_ENV not in (env or {})):
            where[CATALOGUE_ENV] = str(catalogue_for(
                bundle, str(db) + ".catalogue.json"))
        where.update(env or {})

        self.proc = subprocess.Popen(
            command(self.port), cwd=str(ROOT), stdout=self.handle,
            stderr=subprocess.STDOUT, env=where)
        self._wait()

    def _wait(self):
        for _ in range(150):
            if self.proc.poll() is not None:
                self.handle.close()
                sys.exit("the %s API died on startup:\n%s"
                         % (self.backend, self.log.read_text()))
            try:
                urllib.request.urlopen(self.base + "/", timeout=1).read()
                return
            except Exception:
                time.sleep(0.2)
        self.close()
        sys.exit("the %s API never came up:\n%s"
                 % (self.backend, self.log.read_text()))

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.handle.close()

    # So a caller can `with backend.launch(...) as server:` as well as call
    # close() in a finally, which is what the existing sites already do.
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def launch(db, **kw) -> Server:
    """Start the chosen backend against `db` and wait until it answers."""
    return Server(db, **kw)
