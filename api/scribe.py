"""The ambient scribe, server side: audio in, a draft a person still has to tap.

The browser records and posts the audio here. The Eka credentials never leave
this process and the recording never reaches the repository: it is written to
one temporary file, handed to the connector, and deleted in a `finally`.

What comes back is a `Draft` in the sense of kernel/contracts.py, and the
architecture's third rule holds unchanged: a draft is drawn in editable fields
and committed by a tap. Nothing in this module writes, proposes or commits. It
has no Store, and api/main.py's routes hand it nothing that could reach one.

Doctrine this module enforces rather than documents
---------------------------------------------------
- `bundles/phc/phc.inst.consult-scribe.md` says `readback: required`,
  `commit: tap`, and names the operations it may fill. A draft is only built
  for an operation that declaration names, and the link_ids filled are only
  the ones this module understands; anything else is left empty rather than
  guessed at.
- Addendum E.3: capture only where `capture.consented` is on the thread. The
  renderer checks so the button is absent; api/main.py checks again before a
  single byte is uploaded, because that is the trust boundary and the
  renderer's check is a courtesy.
- Eka is asked for the transcript only (`transcript_template`, no EMR JSON).
  Structure is ours: `api/fill.py` and `api/extract.py` fill whatever
  questionnaire the operation names from that transcript, so a field this
  module was never told about is never guessed at from Eka's own parse of it.

What Eka actually answers, seen live against https://api.eka.care on
2026-09-11 (not read from a document):

  upload   client.v2rx.upload([path], txn_id=..., action="ekascribe-v2",
             extra_data={"mode": ..., "model_type": "pro"},
             output_format={"input_language": ["en-IN"],
                            "output_template": [{"template_id": ...}]})
           `output_template` must be a list of objects; a list of strings is
           refused with "Input should be a valid dictionary or object".

  status   GET /voice/api/v3/status/{txn}, through
           client.v2rx.get_session_status(txn, action="ekascribe-v2") ->
           {"data": {"created_at": ..., "output": [{"template_id", "value"
              (base64), "status": success|failure, "errors": [...]}],
              "audio_matrix": {"quality": 0.98},
              "template_results": {"custom": [...], "transcript": [...]}}}
           A job still running answers 202 with "output": [].

  Confidence per field comes from `api/extract.py`'s model call against the
  transcript, not from Eka: there is no per field recognition confidence
  anywhere in Eka's response, only `audio_matrix.quality` about the audio.

Run the check: python3 -m api.scribe
"""
from __future__ import annotations

import base64
import contextlib
import io
import os
import tempfile
import time
import uuid
from datetime import date

# Reused, not re-written: one definition in this repository of what an Aadhaar
# number, a file path and a recording's filename look like, so the two scribe
# call sites cannot drift apart on it. See care_phc/connectors/scribe/eka.py.
from care_phc.connectors.scribe.eka import _scrub

from api import extract as extractor_module
from api import fill as filler

# The action the SDK's v2rx path takes, and the templates worth asking for.
ACTION = "ekascribe-v2"

# The transcript and nothing else. Structure is ours: api/fill.py and
# api/extract.py read whatever questionnaire the template names.
TEMPLATES = [{"template_id": "transcript_template", "codification_needed": False}]

# What a person picks in the bar, to what Eka is told was spoken. Hinglish is
# two languages at once, which is how it is sent.
LANGUAGES = {"en-IN": ["en-IN"], "hinglish": ["en-IN", "hi"], "hi": ["hi"],
             "ta": ["ta"], "te": ["te"]}

TRANSCRIPT_SECONDS = 24 * 3600

# .env names api.dev.eka.care, where these credentials are refused with "pwd
# mismatch". They work on api.eka.care, which is where the ABDM connector
# points for the same reason. See care_phc/connectors/abdm/eka.py.
BASE_URL = "https://api.eka.care"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sdk(call):
    """The only place an SDK call is made from, because the SDK leaks twice.

    It PRINTS the audio filename ("Successfully uploaded phc-scribe-x.m4a",
    seen in this kernel's own log on 2026-09-11), and its exceptions are built
    out of the audio PATH (`EkaUploadError(f"Upload failed for {file_name}")`).
    stdout is a log and a route's 503 body is a screen, so neither may carry
    either. The print goes into a sink and the exception text leaves through
    `_scrub`, which is the caller's job below.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        return call()


class ScribeError(RuntimeError):
    """Anything the connector could not do, in words a doctor can act on.

    Every message ends by saying what to do instead, because the answer is
    always the same and it is always available: type it.
    """


# ------------------------------------------------------------------ connector

def credentials(env_file=None):
    """Client id and secret, from the environment or from .env beside it.

    Nothing here logs them and nothing returns them to a caller over HTTP.
    """
    env = dict(os.environ)
    path = env_file or os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env.setdefault(key.strip(), value.strip())
    client_id = env.get("EKA_CLIENT_ID")
    secret = env.get("EKA_CLIENT_SECRET")
    if not client_id or not secret:
        raise ScribeError(
            "No Eka credentials on this machine, so the consultation cannot be "
            "recorded. Set EKA_CLIENT_ID and EKA_CLIENT_SECRET, or type the note.")
    return client_id, secret


_client = None


def client():
    """The authenticated SDK client, made once. Cached because logging in per
    recording would be a login per consultation."""
    global _client
    if _client is None:
        try:
            from ekacare import EkaCareClient
        except ImportError:
            raise ScribeError(
                "The ekacare SDK is not installed here, so the consultation "
                "cannot be recorded: python3 -m pip install --user ekacare. "
                "Type the note meanwhile.")
        client_id, secret = credentials()
        _client = EkaCareClient(client_id=client_id, client_secret=secret,
                                base_url=BASE_URL)
    return _client


def start(audio, *, suffix=".webm", languages=("en-IN",), mode="consultation"):
    """Upload one recording. Returns the transaction id to poll.

    `audio` is bytes and stays bytes: it is written to a temporary file only
    because the SDK takes paths, and that file is removed whatever happens,
    including on an exception. Nothing under this repository ever holds a
    recording, and there is no second copy to forget about.
    """
    if not audio:
        raise ScribeError("The recording was empty, so there is nothing to send.")
    txn = "phc-" + uuid.uuid4().hex[:16]
    handle, path = tempfile.mkstemp(prefix="phc-scribe-", suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(audio)
        sdk(lambda: client().v2rx.upload(
            [path], txn_id=txn, action=ACTION,
            extra_data={"mode": mode, "model_type": "pro"},
            output_format={"input_language": list(languages),
                           "output_template": TEMPLATES}))
    except ScribeError:
        raise
    except Exception as broke:
        raise ScribeError(
            "The scribe service refused the recording (%s). Nothing was "
            "transcribed. Type the note." % _scrub(str(broke))[:300]) from None
    finally:
        # The one copy, gone. Before the error propagates, not after.
        if os.path.exists(path):
            os.remove(path)
    return txn


def poll(txn):
    """The job's status, verbatim, or a ScribeError with a sentence in it."""
    try:
        return sdk(lambda: client().v2rx.get_session_status(txn, action=ACTION))
    except ScribeError:
        raise
    except Exception as broke:
        raise ScribeError(
            "Could not reach the scribe service to collect the draft (%s). "
            "Nothing was transcribed. Type the note." % _scrub(str(broke))[:300]) from None


# ------------------------------------------------------- reading the response
# Pure from here down: no network, no store, no clock. Checked by demo().

def decoded(status):
    """{template_id: text} for every template that came back with a value.

    A template that failed contributes nothing, which is how a partial job
    ends up as a partial draft rather than as an error. `template_results`
    carries the transcript under its own key and is read the same way.
    """
    data = (status or {}).get("data") or {}
    groups = list((data.get("template_results") or {}).values())
    out = {}
    for group in [data.get("output") or []] + [g for g in groups if isinstance(g, list)]:
        for item in group:
            value = (item or {}).get("value")
            if not value:
                continue
            try:
                text = base64.b64decode(value).decode("utf-8")
            except Exception:
                continue
            out.setdefault(str(item.get("template_id") or ""), text)
    return out


# Eka's own word for a template it has started and not finished. Seen live on
# 2026-09-11 in `output[0].status` while `template_results.transcript` was
# already `success` in the same body.
PENDING = ("in-progress", "in_progress", "pending", "running", "processing")


def running(status):
    """True while any template this form needs is still being built.

    NOT "the output list is empty", which is what this used to say and what the
    browser caught: Eka answers with a PARTIAL body, the transcript already
    `success` and `eka_emr_template` still `in-progress` with no value. Every
    field this form fills comes out of the EMR template, so a draft built from
    that half is empty, and an empty draft latched the session to `failed`
    forever. A doctor polling every two seconds hit it and a doctor polling
    every four did not, which is the worst kind of bug to leave in.

    Measured on api.eka.care, 2026-09-11, one 77 second consultation:

        14.4s  HTTP 202  eka_emr_template in-progress, transcript success
        21.4s  HTTP 200  eka_emr_template success,     transcript success

    So the HTTP code does say it, and this module cannot see the code: the
    SDK's `get_session_status` returns the parsed body and throws the status
    line away. `care_phc/connectors/scribe/eka.py` calls the endpoint with
    `raw_response=True` for exactly this reason and is right to. Until these
    two implementations are one, the rule has to be readable off the body, and
    the row's own `status` is where it is written.

    A row that FAILED is finished: it carries `status: failure` and its errors
    are what the caller shows. Only an explicit in-progress keeps the wait
    going, so a template Eka will never deliver cannot hang the screen.
    """
    data = (status or {}).get("data") or {}
    rows = list(data.get("output") or [])
    for group in (data.get("template_results") or {}).values():
        if isinstance(group, list):
            rows.extend(group)
    if not rows:
        return True                       # the 202, with nothing at all yet
    return any(str((row or {}).get("status") or "").lower() in PENDING for row in rows)


def failures(status):
    """The service's own words for what it could not do. Shown, not paraphrased."""
    data = (status or {}).get("data") or {}
    groups = [data.get("output") or []]
    groups += [g for g in (data.get("template_results") or {}).values() if isinstance(g, list)]
    said = []
    for group in groups:
        for item in group:
            for err in (item or {}).get("errors") or []:
                text = err.get("msg") if isinstance(err, dict) else str(err)
                detail = err.get("detail") if isinstance(err, dict) else ""
                line = " ".join(str(x) for x in (text, detail) if x)
                if line and line not in said:
                    said.append(line)
    return said


def transcript_of(status):
    text = decoded(status)
    return (text.get("transcript_template") or text.get("transcript") or "").strip()


# ------------------------------------------------------------------- sessions
# In memory on purpose. A restart loses an in flight job, which costs a doctor
# one re-recording and costs the record nothing: no draft is a write, and the
# audio is already deleted. A table would have to be emptied by something.

SESSIONS = {}


def begin(thread, actor, txn, operations, instrument=""):
    session = {"id": "scr-" + uuid.uuid4().hex[:12], "thread": thread,
               "actor": actor, "txn": txn, "operations": operations,
               "instrument": instrument, "status": "running", "reason": "",
               "drafts": [], "transcript": "", "expires": None}
    SESSIONS[session["id"]] = session
    return session


def by_txn(txn):
    for session in SESSIONS.values():
        if session["txn"] == txn:
            return session
    return None


def expire(now=None):
    """Drop every transcript past its 24 hours. Called on every session read,
    so nothing needs a timer; a kernel nobody asks keeps nothing it could have
    dropped either, because a restart empties SESSIONS."""
    now = time.time() if now is None else now
    for sid in [s for s, v in SESSIONS.items() if v["expires"] and v["expires"] <= now]:
        del SESSIONS[sid]


def refill(session, operations, *, extractor=None, today=None):
    """Build drafts for these operations from the transcript already held. The
    template switch: no re-recording, no second upload."""
    extractor = extractor or extractor_module.extract
    today = today or date.today()
    session["operations"] = operations
    session["drafts"] = []
    for op_id, spec in sorted(operations.items()):
        answers = extractor(filler.flatten(spec["schema"]), session["transcript"])
        d = filler.build_draft(op_id, spec["schema"], answers, session["transcript"],
                               instrument=session["instrument"], today=today)
        if d:
            session["drafts"].append(d)
    if session["drafts"]:
        session.update(status="ready", reason="")
    else:
        session.update(status="ready", reason="Nothing in the recording fills this form. "
                       "The transcript is below. Type the note.")
    return session


def collect(session, *, extractor=None):
    if session["status"] in ("ready", "failed", "withdrawn"):
        return session
    try:
        status = poll(session["txn"])
    except ScribeError as broke:
        session.update(status="failed", reason=str(broke))
        return session
    if running(status):
        return session
    session["transcript"] = transcript_of(status)
    if not session["transcript"]:
        said = failures(status)
        session.update(status="failed", reason="No transcript came back. %s Type the note."
                       % " ".join(said))
        return session
    session["expires"] = time.time() + TRANSCRIPT_SECONDS
    return refill(session, session["operations"], extractor=extractor)


def withdraw(session):
    session.update(status="withdrawn", drafts=[], transcript="",
                   reason="Withdrawn. Nothing from this recording was kept.")
    return session


def public(session):
    return {"session": session["id"], "status": session["status"],
            "reason": session["reason"], "drafts": session["drafts"],
            "transcript": session["transcript"],
            "operations": sorted(session["operations"])}


# ---------------------------------------------------------------------- check

def demo():
    """Run: python3 -m api.scribe

    No network, no store, no credentials.
    """
    assert running({"data": {"output": [], "template_results": {}}}), "202 is still running"

    # THE PARTIAL BODY, verbatim from api.eka.care on 2026-09-11: the transcript
    # is already done and the template every field comes from is not. Before
    # this was handled the session went straight to "failed" and stayed there.
    PARTIAL = {"data": {"output": [{"template_id": "eka_emr_template",
                                    "status": "in-progress", "value": "", "errors": []}],
                        "template_results": {"transcript": [
                            {"template_id": "transcript", "status": "success",
                             "value": base64.b64encode(b"Fever for three days.").decode()}]}}}
    assert running(PARTIAL), "a template still being built means keep waiting"
    # A template that FAILED is finished, not pending: it must not hang the wait.
    FAILED = {"data": {"output": [{"template_id": "eka_emr_template",
                                   "status": "failure", "value": "",
                                   "errors": [{"msg": "Template not found"}]}]}}
    assert not running(FAILED), "a failure is an answer, not a wait"
    assert failures(FAILED) == ["Template not found"], failures(FAILED)

    text = decoded(PARTIAL)
    assert "Fever for three days" in text["transcript"], text

    DONE = {"data": {"output": [], "template_results": {"transcript": [
        {"template_id": "transcript", "status": "success",
         "value": base64.b64encode(b"BP is 140 over 90. Fever for three days.").decode()}]}}}
    assert transcript_of(DONE) == "BP is 140 over 90. Fever for three days."

    vitals = {"questions": [{"link_id": "systolic", "text": "Systolic", "type": "integer"}]}
    consult = {"questions": [{"link_id": "history", "text": "History", "type": "text"}]}

    def fake(fields, transcript):
        ids = {f["link_id"] for f in fields}
        said = {"systolic": {"value": 140, "confidence": 0.95, "evidence": "BP is 140"},
                "history": {"value": "Fever for three days", "confidence": 0.9,
                            "evidence": "Fever for three days"}}
        return {k: v for k, v in said.items() if k in ids}

    global poll
    real_poll, poll = poll, lambda txn: DONE
    try:
        s = begin("enc-003", "user:mo", "phc-y", {"v.op": {"schema": vitals}}, instrument="i")
        collect(s, extractor=fake)
    finally:
        poll = real_poll
    assert s["status"] == "ready" and s["drafts"][0]["values"] == {"systolic": 140}, s
    assert s["drafts"][0]["tick"] == ["systolic"]
    assert s["expires"] - time.time() > 24 * 3600 - 5, "the transcript is kept a day"

    refill(s, {"c.op": {"schema": consult}}, extractor=fake)
    assert [d["operation"] for d in s["drafts"]] == ["c.op"], "the switch rebuilds from the transcript"
    assert public(s)["transcript"].startswith("BP is 140")

    expire(now=s["expires"] + 1)
    assert s["id"] not in SESSIONS, "past a day the transcript is gone"

    withdrawn = begin("enc-003", "user:mo", "phc-z", {}, instrument="i")
    withdrawn["transcript"] = "something"
    withdraw(withdrawn)
    assert public(withdrawn)["transcript"] == "", "withdrawal drops the transcript too"

    # A withdrawn session is inert, whatever the service later says.
    session = begin("enc-002", "user:demo", "phc-x", {})
    withdraw(session)
    assert collect(session)["drafts"] == [], "withdrawal survives a collect"
    assert public(session)["status"] == "withdrawn"
    assert "txn" not in public(session), "the transaction id is not the browser's"

    # The two SDK leaks, asserted rather than trusted. Both were real: the
    # path reached a 503 body on screen, and the print reached this kernel's
    # own log on 2026-09-11. Delete either guard and one of these fails.
    class Leaky:
        class v2rx:
            @staticmethod
            def upload(paths, **kw):
                print("Successfully uploaded %s" % os.path.basename(paths[0]))
                raise RuntimeError("Upload failed for %s: 403 Forbidden" % paths[0])

            @staticmethod
            def get_session_status(txn, action=None):
                raise RuntimeError("no such file /var/phc/audio/ramesh-enc-002.wav")

    global _client
    was, _client = _client, Leaky()
    said = io.StringIO()
    try:
        with contextlib.redirect_stdout(said):
            try:
                start(b"x", suffix=".m4a")
                raise AssertionError("a failing upload must raise")
            except ScribeError as broke:
                assert "/var/folders" not in str(broke) and "/T/" not in str(broke), broke
                assert "phc-scribe-" not in str(broke), broke
                assert "403 Forbidden" in str(broke), broke
            try:
                poll("phc-x")
                raise AssertionError("a failing poll must raise")
            except ScribeError as broke:
                assert "ramesh" not in str(broke), broke
                assert "<audio-redacted>" in str(broke), broke
    finally:
        _client = was
    assert said.getvalue() == "", "the SDK's print never reaches stdout: %r" % said.getvalue()

    print("ok api.scribe")


if __name__ == "__main__":
    demo()
