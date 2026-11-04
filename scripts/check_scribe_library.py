"""Eka's template library and the note a recording is written up in.

Run: python3 scripts/check_scribe_library.py

No network and no credential: the library listing and the service's
convert-to-template call are replaced, and the routes are driven through the
real app. What it holds is the three refusals a route owes before it spends a
call to the service, and that a note on a session is words and never a write.
"""
import os
import pathlib
import sys
import tempfile

from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Its own database, so importing the app never touches a developer's demo day.
os.environ["PHC_DB"] = str(pathlib.Path(tempfile.mkdtemp(prefix="scribe-library-")) / "phc.sqlite3")

import api.main as m
import api.scribe as scribe

ROLE = {"X-PHC-Role": "mo"}
api = TestClient(m.app)
BASE = "/api/v1/phc/scribe"

LISTING = [{"id": "t-soap", "title": "SOAP Notes", "desc": "x", "default": True, "favorite": False},
           {"id": "t-gp", "title": "General Physician Note", "desc": "y", "default": True,
            "favorite": False}]
asked = []


def fake_reshape(session, template):
    asked.append(template)
    return "S: fever for three days." if template == "t-soap" else None


real = (scribe.library, scribe.reshape)
scribe.library = lambda now=None: LISTING
scribe.reshape = fake_reshape
try:
    # -- the library is a read, and it is the workspace's own ----------------
    got = api.get(BASE + "/library", headers=ROLE)
    assert got.status_code == 200 and [i["id"] for i in got.json()["items"]] == ["t-soap", "t-gp"], got.text

    # -- a session of this caller's, with a transcript ------------------------
    me = "user:mo"                       # what caller() answers for the mo role
    s = scribe.begin("enc-001", me, "phc-t", {}, instrument="i")
    s.update(status="ready", transcript="Fever for three days.")
    url = "%s/sessions/%s/note" % (BASE, s["id"])

    # -- refusals, before any call to the service ---------------------------
    assert api.post(url + "?template=not-a-template", headers=ROLE).status_code == 400, \
        "an id Eka does not list is refused, not sent"
    assert api.post(url, headers=ROLE).status_code == 400, "no template named"
    assert asked == [], "nothing was asked of the service for a refused request: %r" % asked
    s["status"] = "running"
    assert api.post(url + "?template=t-soap", headers=ROLE).status_code == 409, \
        "there is no transcript to write from until the recording is transcribed"
    s["status"] = "withdrawn"
    assert api.post(url + "?template=t-soap", headers=ROLE).status_code == 403, \
        "a withdrawn recording keeps nothing, so nothing is written from it"
    s["status"] = "ready"
    other = scribe.begin("enc-001", "user:somebody-else", "phc-u", {}, instrument="i")
    other.update(status="ready", transcript="x")
    assert api.post("%s/sessions/%s/note?template=t-soap" % (BASE, other["id"]),
                    headers=ROLE).status_code == 404, "another desk's session does not exist to you"

    # -- the note arrives on the session, once ------------------------------
    first = api.post(url + "?template=t-soap", headers=ROLE)
    assert first.status_code == 200, first.text
    assert first.json()["notes"] == [{"template": "t-soap", "title": "SOAP Notes",
                                      "text": "S: fever for three days."}], first.json()
    api.post(url + "?template=t-soap", headers=ROLE)
    assert asked.count("t-soap") == 1, "a note already held is not asked for twice: %r" % asked

    # -- a service that has not written it yet is a sentence, not a crash ----
    late = api.post(url + "?template=t-gp", headers=ROLE)
    assert late.status_code == 503 and "Try again" in late.json()["detail"], late.text
    assert [n["template"] for n in api.get("%s/sessions/%s" % (BASE, s["id"]),
                                           headers=ROLE).json()["notes"]] == ["t-soap"], \
        "the failed note left nothing half written on the session"
finally:
    scribe.library, scribe.reshape = real
    scribe.SESSIONS.clear()

print("ok   scribe library: listed, refused before any call, held once, and a late note is a sentence")
