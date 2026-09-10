"""An HTTP client for the kernel that has no verb which could commit.

The agent is a caller like any other, so it gets no privileged in-process
route to the store: it speaks the same JSON over the same socket the browser
and the Go MCP server use, and it holds the same read methods plus exactly one
write method, propose(), which the kernel answers with a proposal id and no
clinical row.

Two things stop this file growing a commit path:

  1. There is no method here that names one, and none may be added.
  2. _call() refuses to build a URL containing any FORBIDDEN fragment, so a
     path assembled from a variable, a catalogue string or a model's output
     fails loudly instead of reaching the kernel. The kernel does expose those
     routes. They belong to a person at the rendered surface. This process is
     not one.

Stdlib urllib, not requests: this makes four kinds of call and one of them is
a POST. `PHC_API` moves the base URL, default the port RUNNING.md starts.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("PHC_API", "http://127.0.0.1:8000")
PREFIX = "/api/v1/phc"

# Path fragments this client will not assemble, whatever it is asked for.
FORBIDDEN = ("/confirm", "/commit")


class Unreachable(Exception):
    """No kernel at that address. Said plainly rather than dressed as a refusal."""


class Refused(Exception):
    """The kernel said no. `reason` is its own words, passed through unedited,
    because the guard's wording is the useful part and paraphrasing it is how
    an agent starts inventing policy."""

    def __init__(self, reason: str, status: int):
        super().__init__(reason)
        self.reason = reason
        self.status = status


class Kernel:
    """Read the catalogue, read a thread, propose. That is the whole surface."""

    def __init__(self, base: str = BASE, role: str = None, actor: str = "agent"):
        self.base = base.rstrip("/")
        self.role = role
        self.actor = actor

    # ------------------------------------------------------------------ wire
    def _call(self, path: str, body=None, timeout: float = 30.0):
        for fragment in FORBIDDEN:
            if fragment in path:
                raise RuntimeError(
                    "agent.client will not call %r. Confirming is a person's job "
                    "at the rendered surface." % path)
        url = self.base + PREFIX + path
        if self.role:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"role": self.role})
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            url, data=data, method="POST" if data is not None else "GET",
            headers={"Content-Type": "application/json", "X-PHC-Actor": self.actor})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                raw = reply.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            detail = ""
            try:
                detail = json.loads(raw).get("detail") or ""
            except Exception:
                detail = raw.decode("utf-8", "replace")[:200]
            raise Refused(str(detail) or "HTTP %s" % e.code, e.code)
        except urllib.error.URLError as e:
            raise Unreachable("no kernel at %s (%s). Start it: sh api/run.sh"
                              % (self.base, e.reason))
        return json.loads(raw) if raw else {}

    # ----------------------------------------------------------------- reads
    def catalogue(self) -> dict:
        """The compiled declarations, from the kernel that will judge them, so
        the agent cannot plan against a catalogue.json the API never loaded."""
        return self._call("/catalogue")

    def queue(self, view: str = None) -> list:
        path = "/queue" + ("?view=" + urllib.parse.quote(view) if view else "")
        return self._call(path).get("rows") or []

    def thread(self, thread_id: str) -> dict:
        """A ThreadView: flags, station, the line, and `actions` in the order
        the kernel puts them. That order is read, never recomputed."""
        return self._call("/threads/" + urllib.parse.quote(thread_id))

    # ----------------------------------------------------------------- write
    def propose(self, operation: str, thread: str, payload: dict) -> dict:
        """The only write. Comes back a pending proposal or raises Refused.

        The kernel runs guard steps 1 to 4 on the machine surface here, so what
        this returns is never a committed row: it is an id a person confirms on
        screen, or nothing at all.
        """
        return self._call("/operations/%s/propose" % urllib.parse.quote(operation),
                          {"thread": thread, "payload": payload})


def demo():
    """Run: python3 -m agent.client   (needs the API up; skipped by check.sh)

    The property worth asserting without a socket is the negative one, so that
    part runs anywhere."""
    k = Kernel()
    for path in ("/proposals/prop-1/confirm", "/operations/x/commit"):
        try:
            k._call(path)
        except RuntimeError as e:
            assert "will not call" in str(e)
        else:
            raise AssertionError("%s was not refused" % path)
    assert not any(hasattr(Kernel, name) for name in ("confirm", "commit", "accept")), \
        "agent.client grew a write verb that is not propose"
    print("ok   agent.client has no path to a commit")


if __name__ == "__main__":
    demo()
