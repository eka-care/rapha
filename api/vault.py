"""The medical records seam, so the browser can hold the SDK and not the key.

The claims portal runs @eka-care/medical-records-ts-sdk in the browser and
lets it talk to Eka directly, because every user of that portal is an Eka
account holder with a session of their own. A health centre workstation is
not that. It is one shared machine, signed in as a facility, serving a line
of people who have never heard of Eka, and the credential it would have to
carry is the facility's, not any patient's.

So the SDK runs in the browser exactly as it does there, and its `baseUrl`
points here instead of at the service. This module forwards each call on,
with the authorisation attached, and nothing in the browser ever sees a
token. The one call that does NOT come through here is the upload itself:
the service hands back a presigned bucket URL and the browser sends the
photograph straight to it, which is the whole reason a ten megabyte picture
never touches this process.

WHAT IT WILL PASS AND WHAT IT WILL NOT. A proxy that forwards anything is a
hole in a kernel that is otherwise careful about what leaves it, so this one
forwards exactly the medical records paths the SDK uses, by prefix, and
refuses everything else with a 404 rather than a redirect. The headers that
go up are the ones the API reads -- the patient's oid and the content type --
and not whatever the browser chose to send.

Run the check: python3 -m api.vault
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

from api.scribe import ScribeError, client, credentials, sdk
from care_phc.connectors.scribe.eka import _scrub

# Exactly what the SDK calls, and nothing else. `/mr/api/v1/docs` covers the
# listing, the upload authorisation and one document; `/cases` is the SDK's
# folders. A path outside these is not proxied, whatever asks for it.
ALLOWED = ("/mr/api/v1/docs", "/mr/api/v1/cases")

# The headers worth forwarding UP. X-Pt-Id is the patient's own Eka oid and is
# how the service scopes a document to a person; the rest of what a browser
# sends is the browser's business.
FORWARD_UP = ("x-pt-id", "content-type", "accept")

# And the ones worth sending back DOWN. Not Set-Cookie, not anything about
# the upstream's own session.
FORWARD_DOWN = ("content-type",)

TIMEOUT = 30


class VaultError(ScribeError):
    """Anything the seam could not do, in words that say what to do instead."""


# What may follow an allowed prefix: one more segment, an identifier. A
# document id is a uuid and a case id is a short key, so letters, digits and
# the three unreserved punctuation marks is the whole of it.
#
# THE REASON THIS IS A WHITELIST AND NOT A BAN ON `..` is that a ban is a
# list of the tricks somebody thought of. This module's own check caught
# "/mr/api/v1/docs/../../profiles/v1/patient/" passing a prefix test, which
# would have reached the patient directory API on the facility's credential
# through a seam that exists to reach medical records.
_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")


def allowed(path):
    """Whether this is a path the SDK is entitled to reach through here."""
    for prefix in ALLOWED:
        if path == prefix:
            return True
        if not path.startswith(prefix + "/"):
            continue
        rest = path[len(prefix) + 1:]
        # One segment, and a real one. Not empty, not a traversal, not a
        # second path smuggled behind a slash.
        return bool(rest) and bool(_SEGMENT.match(rest))
    return False


def forward(method, path, query, body, headers):
    """One call, passed on with the facility's authorisation attached.

    Returns (status, body_bytes, headers). An upstream error is passed back
    as it came rather than translated: the SDK knows this API's own error
    shapes and handles them, and rewriting them here would be inventing a
    third vocabulary for the same failures.
    """
    if not allowed(path):
        raise VaultError("That is not a medical records path.")

    client_id, _ = credentials()
    base = _base()
    url = base + path + (("?" + query) if query else "")

    up = {
        "Authorization": "Bearer %s" % _token(),
        "client-id": client_id,
    }
    for name in FORWARD_UP:
        if headers.get(name):
            up[name] = headers[name]

    request = urllib.request.Request(url, data=body or None, method=method,
                                     headers=up)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return (answer.status, answer.read(),
                    {k: v for k, v in answer.headers.items()
                     if k.lower() in FORWARD_DOWN})
    except urllib.error.HTTPError as refused:
        # The service's own answer, passed through. The SDK reads these.
        return (refused.code, refused.read() or b"",
                {k: v for k, v in (refused.headers or {}).items()
                 if k.lower() in FORWARD_DOWN})
    except Exception as broke:
        raise VaultError(
            "Could not reach the medical records service (%s)."
            % _scrub(str(broke))[:200]) from None


def _base():
    """Where the service lives. The scribe's own base, which is the same
    host, rather than a second environment variable that can disagree."""
    from api import scribe
    return scribe.BASE_URL


_held = None


def _token():
    """A bearer token for the facility, made once and reused.

    It is never returned to a caller and never logged. The only thing that
    leaves this process holding it is a request to the service itself.
    """
    global _held
    if _held is None:
        try:
            answer = sdk(lambda: client().auth.login())
        except Exception as broke:
            raise VaultError(
                "Could not sign in to the medical records service (%s)."
                % _scrub(str(broke))[:200]) from None
        _held = (answer or {}).get("access_token") or client().access_token
        if not _held:
            raise VaultError("The medical records service gave no token.")
    return _held


def token_for_connectors():
    """The facility's bearer token, for another SERVER-SIDE connector.

    Named for the one thing it is for. The rule this module keeps is that no
    route hands the token to a browser; a module in this process asking for
    it is not that, and the alternative -- a second login in every connector
    -- would be a second thing to keep in step and a second set of calls to
    the same service.
    """
    return _token()


def forget():
    """Drop the held token, so the next call signs in again. Called when the
    service answers 401, which is the only thing that means it went stale."""
    global _held
    _held = None


def demo():
    """python3 -m api.vault -- the path gate, which needs no network."""
    checks = 0

    def ok(what):
        nonlocal checks
        checks += 1
        print("ok   %s" % what)

    for path in ("/mr/api/v1/docs", "/mr/api/v1/docs/abc-123",
                 "/mr/api/v1/cases",
                 "/mr/api/v1/cases/c-1"):
        assert allowed(path), path
    ok("every path the SDK calls is passed on")

    # A PROXY THAT FORWARDS ANYTHING IS A HOLE. These are the shapes that
    # would turn this seam into one: another Eka API behind the same
    # credential, a path that merely starts with the right letters, and the
    # usual traversal.
    # The query string arrives separately and is never part of the path, so
    # a path carrying one is a path somebody assembled by hand.
    assert not allowed("/mr/api/v1/docs?u_at__gt=1")

    for path in ("/profiles/v1/patient/", "/voice/api/v3/status/x",
                 "/mr/api/v1", "/mr/api/v2/docs", "/mr/api/v1/docsomething",
                 "/", "", "/mr/api/v1/docs/../../profiles/v1/patient/",
                 "//api.eka.care/mr/api/v1/docs"):
        assert not allowed(path), path
    ok("nothing else is, including a path that only begins the same way")

    # The token is held in this module and there is no accessor that returns
    # it. A route that could hand it to a browser is the one mistake that
    # would undo the whole arrangement.
    import api.vault as me
    # NO ROUTE RETURNS IT. That is the rule, and it is about routes rather
    # than about the word: `token_for_connectors` exists for server-side
    # callers in this process (api/main.py hands it to the patient
    # directory), and a browser can reach none of them. What would undo the
    # arrangement is a ROUTE that answers with the token, so that is what is
    # checked, in the one file that declares them.
    import pathlib
    routes = pathlib.Path(__file__).with_name("main.py").read_text()
    assert "_token()" not in routes and "token_for_connectors()" not in routes, (
        "api/main.py calls for the token itself; it should hand the function "
        "to a connector and never hold the value")
    assert set(FORWARD_DOWN) == {"content-type"}, FORWARD_DOWN
    ok("no route answers with the token, and no upstream header comes back "
       "except the content type")

    print("\n%d vault checks passed" % checks)


if __name__ == "__main__":
    demo()
