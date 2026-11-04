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
- There is no consent gate. Capture used to be refused unless the visit
  carried `capture.consented`, checked in the renderer so the button was
  absent and again in api/main.py before a byte was uploaded. The owner
  removed the whole mechanism on 4 November 2026; the only thing that
  refuses a recording now is the caller's capability.
- Eka is asked for the transcript AND for a note shaped like the form
  (`transcript_template` plus one template per operation, no EMR JSON).
  Structure is ASKED OF THE SAME SERVICE, in a template built from the
  operation's own questionnaire: `api/shaped.py` writes the template and reads
  the table back with a parser. So a field this kernel was never told about is
  never guessed at, and no second provider ever sees a consultation.

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

  Confidence per field is a column of the table this kernel's own template
  asks for. Eka's response carries no per field recognition confidence of its
  own, only `audio_matrix.quality` about the audio.

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

from api import fill as filler
from api import shaped

# The action the SDK's v2rx path takes, and the templates worth asking for.
ACTION = "ekascribe-v2"

# The transcript, always: it is the record of what was said and the thing every
# value is checked against. The shaped note is asked for beside it, one
# template per operation, and `api/shaped.py` reads it.
TRANSCRIPT = {"template_id": "transcript_template", "codification_needed": False}
TEMPLATES = [TRANSCRIPT]

# The title a shaped template is filed under in the workspace. One per
# operation, named after the declaration, so a person looking at the Eka
# console can see which form each one fills.
TEMPLATE_TITLE = "phc · %s"

# Resolved template ids, by operation. One listing per process, not one per
# consultation.
_templates = {}


def shaped_template(op_id, fields):
    """The workspace template that shapes this operation's note, made if the
    workspace has none and corrected if the declaration has moved since.

    THIS WRITES TO THE EKA WORKSPACE, which is the one outward effect in this
    module that is not a recording. It is idempotent by title: a second
    kernel, a restart or a redeploy finds the template rather than making a
    second one, and a bundle whose questionnaire changed updates the one that
    is there instead of leaving the service filling yesterday's form.
    """
    if op_id in _templates:
        return _templates[op_id]
    title, want = TEMPLATE_TITLE % op_id, shaped.instructions(fields)
    listed = sdk(lambda: client().request("GET", "/voice/api/v1/template"))
    for item in (listed or {}).get("items") or []:
        if item.get("title") != title or item.get("default"):
            continue
        if item.get("desc") != want:
            sdk(lambda: client().request(
                "PATCH", "/voice/api/v1/template/%s" % item["id"], json={"desc": want}))
        _templates[op_id] = item["id"]
        return item["id"]
    made = sdk(lambda: client().request("POST", "/voice/api/v1/template", json={
        "title": title, "section_ids": [], "desc": want, "type": "custom"}))
    new_id = (made or {}).get("template_id")
    if not new_id:
        raise ScribeError(
            "The scribe service would not make a template for this form, so "
            "the recording cannot be structured. Type the note.")
    _templates[op_id] = new_id
    return new_id

# ------------------------------------------------------- Eka's template library
# Eka keeps a library of note templates for the workspace: its own defaults
# (SOAP, a discharge summary, a prescription-only note) and whatever the centre
# has added in the console. A template is the SHAPE OF AN OUTPUT NOTE, which is
# a different thing from the form an operation fills. The recording screen
# offers both: a form to fill, and a note to have written.
#
# The ones this module makes itself (`phc · <operation>`, above) are the
# library's plumbing and not its contents, so they are not offered.

LIBRARY_SECONDS = 300
_library = {"at": 0.0, "items": []}


def library(now=None):
    """[{id, title, desc, default, favorite}] for this workspace, minus ours.

    Cached for five minutes: the library changes when somebody edits it in the
    console, which is not something that happens mid consultation, and this is
    called when a doctor opens a tab.
    """
    now = time.time() if now is None else now
    if _library["items"] and now - _library["at"] < LIBRARY_SECONDS:
        return _library["items"]
    try:
        listed = sdk(lambda: client().request("GET", "/voice/api/v1/template"))
    except ScribeError:
        raise
    except Exception as broke:
        raise ScribeError(
            "Could not reach the scribe service to read its templates (%s). "
            "Type the note." % _scrub(str(broke))[:300]) from None
    mine = TEMPLATE_TITLE % ""
    items = [{"id": str(i["id"]), "title": str(i.get("title") or ""),
              "desc": str(i.get("desc") or ""),
              "default": bool(i.get("default")),
              "favorite": bool(i.get("is_favorite"))}
             for i in (listed or {}).get("items") or []
             if i.get("id") and not str(i.get("title") or "").startswith(mine)]
    # Favourites first, then Eka's own, then the centre's, each by name: the
    # order a person would look for them in.
    items.sort(key=lambda i: (not i["favorite"], not i["default"], i["title"].lower()))
    _library.update(at=now, items=items)
    return items


def library_pick(ids):
    """The library templates named, each one a template this workspace really
    has. An id Eka does not list is refused rather than sent: the upload would
    otherwise carry whatever string a browser chose."""
    known = {i["id"]: i for i in library()}
    wanted = list(dict.fromkeys(i for i in (ids or []) if i))
    missing = [i for i in wanted if i not in known]
    if missing:
        raise ScribeError("The scribe service has no template %s." % ", ".join(missing))
    return {i: known[i]["title"] for i in wanted}


def note(session, template, title=""):
    """One library template's note for this session: the one already held, or
    the one the service writes now from the transcript it already has. Returns
    the text, or None when the service has not written it yet.

    Held notes are kept on the session, which is in memory and dropped with it.
    Nothing here writes a record: a note is words for somebody to read.
    """
    held = session["notes"].get(template)
    if held:
        return held["text"]
    text = reshape(session, template)
    if text:
        session["notes"][template] = {"title": title or template, "text": text}
        _kept(session, template, title or template, text)
    return text


# Where a note goes once it exists. Set by the route layer, which knows where
# the visit's notes live; this module has no store and keeps it that way. A
# note that arrives with the recording and one asked for afterwards both pass
# through here, so neither can be forgotten.
KEEP = None


def _kept(session, template, title, text):
    if KEEP and text:
        KEEP(thread=session["thread"], template=template, title=title,
             actor=session["actor"], session=session["id"], text=text)


# What Eka is told was spoken. Hinglish is two languages at once, which is
# how it is sent.
#
# NOBODY PICKS ONE ANY MORE. There was a dropdown on the recording bar and
# it was a question with no good answer: a consultation in a primary health
# centre is not in one language. A doctor asks in Hindi, the patient answers
# in Bhojpuri-inflected Hindi, the drug name is English and the examination
# is narrated in English with Hindi asides. Making somebody choose before
# they speak is making them predict their own consultation, and getting it
# wrong costs them the transcript.
#
# So every language this facility supports goes up on every recording and
# the service decides what it heard, which is what it is for. `auto` is that
# list, and it is the only value the kernel sends.
_SPOKEN = {"en-IN": ["en-IN"], "hinglish": ["en-IN", "hi"], "hi": ["hi"],
           "ta": ["ta"], "te": ["te"]}
LANGUAGES = dict(_SPOKEN, auto=sorted({c for codes in _SPOKEN.values() for c in codes}))

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


def start(audio, *, suffix=".webm", languages=("en-IN",), mode="consultation",
          templates=()):
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
                           "output_template": TEMPLATES + [
                               {"template_id": t, "codification_needed": False}
                               for t in dict.fromkeys(templates)]}))
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


def begin(thread, actor, txn, operations, instrument="", templates=None, want=None):
    """A new session, already carrying its expiry. Set here and not only when a
    transcript arrives, because a session that fails, is withdrawn or is simply
    abandoned never gets a transcript and would otherwise never be dropped."""
    session = {"id": "scr-" + uuid.uuid4().hex[:12], "thread": thread,
               "actor": actor, "txn": txn, "operations": operations,
               "instrument": instrument, "status": "running", "reason": "",
               "templates": dict(templates or {}),
               # Library templates asked for with the recording ({id: title}),
               # and the notes that came back ({id: {title, text}}).
               "want": dict(want or {}), "notes": {},
               "drafts": [], "transcript": "",
               "expires": time.time() + TRANSCRIPT_SECONDS}
    SESSIONS[session["id"]] = session
    return session


def by_txn(txn):
    for session in SESSIONS.values():
        if session["txn"] == txn:
            return session
    return None


def expire(now=None):
    """Drop every session past its 24 hours. Called on every session read,
    so nothing needs a timer; a kernel nobody asks keeps nothing it could have
    dropped either, because a restart empties SESSIONS."""
    now = time.time() if now is None else now
    for sid in [s for s, v in SESSIONS.items() if v["expires"] <= now]:
        del SESSIONS[sid]


def refill(session, operations, *, notes=None, today=None, reader=None):
    """Build drafts for these operations from the notes the service shaped.

    `notes` is {template_id: text}, straight off the job. The template switch
    arrives here with none, because the note it needs was never asked for when
    the recording went up: that case asks the service to shape the transcript
    it already holds, which is another call to the SAME service and not a
    second opinion from a different one.

    The fetch takes seconds and a withdrawal can land in the middle of it. So
    the drafts are built from a local copy into a local list, and written to
    the session only if it is still not withdrawn once they exist. Writing as
    it went, and marking ready at the end, is how a patient's stop used to be
    quietly undone by the reader finishing.
    """
    reader = reader or shaped.answers
    today = today or date.today()
    transcript = session["transcript"]
    held = dict(notes or {})
    drafts, unshaped = [], []
    for op_id, spec in sorted(operations.items()):
        fields = filler.flatten(spec["schema"])
        try:
            template = session["templates"].get(op_id) or shaped_template(op_id, fields)
        except ScribeError as broke:
            unshaped.append(str(broke))
            continue
        session["templates"][op_id] = template
        note = held.get(template)
        if note is None:
            note = reshape(session, template)
        if note is None:
            unshaped.append("The scribe service has not shaped this form yet.")
            continue
        answers = reader(note, fields, transcript)
        d = filler.build_draft(op_id, spec["schema"], answers, transcript,
                               instrument=session["instrument"], today=today)
        if d:
            drafts.append(d)
    if session["status"] == "withdrawn":
        return session
    session.update(operations=operations, drafts=drafts, status="ready",
                   reason=_why(drafts, unshaped, operations))
    return session


def _why(drafts, unshaped, operations):
    """Why there are no drafts, in the words that tell a doctor what to do.

    "The service never shaped this form" and "the consultation did not state
    any of it" lead to different actions, and answering the same sentence for
    both is what made a missing reader look like an off topic recording once
    already. See the 2026-11-01 commit that split them.
    """
    if drafts:
        return ""
    if not operations:
        # Nothing was asked to be filled: a recording with no form chosen is
        # a transcript, and a transcript is a whole answer.
        return ""
    if unshaped:
        return ("%s The transcript is below, and the note has to be typed."
                % " ".join(dict.fromkeys(unshaped)))
    return ("Nothing in the recording fills this form. "
            "The transcript is below. Type the note.")


def reshape(session, template):
    """Ask the service to shape the transcript it already holds into one more
    template, and wait for it. Returns the note, or None.

    This is the template switch. No audio moves: the service keeps the
    transcript for the session and `convert-to-template` is the documented way
    to ask it for another document from it. Bounded, because this runs inside
    a request a doctor is waiting on, and answering "not yet" beats holding
    the screen open.
    """
    try:
        sdk(lambda: client().request(
            "POST", "/voice/api/v1/transaction/%s/convert-to-template" % session["txn"],
            json={"template_id": template}))
    except Exception:                                      # noqa: BLE001
        return None
    for _ in range(RESHAPE_TRIES):
        time.sleep(RESHAPE_WAIT)
        try:
            note = decoded(poll(session["txn"])).get(template)
        except ScribeError:
            return None
        if note:
            return note
    return None


RESHAPE_TRIES = 10
RESHAPE_WAIT = 2.0


def collect(session, *, reader=None):
    if session["status"] in ("ready", "failed", "withdrawn"):
        return session
    try:
        status = poll(session["txn"])
    except ScribeError as broke:
        session.update(status="failed", reason=str(broke))
        return session
    if running(status):
        return session
    if session["status"] == "withdrawn":     # withdrawn while the poll was out
        return session
    transcript = transcript_of(status)
    if not transcript:
        said = failures(status)
        session.update(status="failed", reason="No transcript came back. %s Type the note."
                       % " ".join(said))
        return session
    # The day is counted from when the transcript arrives, not from the upload.
    session.update(transcript=transcript, expires=time.time() + TRANSCRIPT_SECONDS)
    # The shaped notes came back in the same body as the transcript, so the
    # ordinary path needs no second call to anything.
    came = decoded(status)
    for template, title in session["want"].items():
        if came.get(template):
            session["notes"][template] = {"title": title, "text": came[template]}
            _kept(session, template, title, came[template])
    return refill(session, session["operations"], notes=came, reader=reader)


def withdraw(session):
    session.update(status="withdrawn", drafts=[], transcript="", notes={},
                   reason="Withdrawn. Nothing from this recording was kept.")
    return session


def public(session):
    return {"session": session["id"], "status": session["status"],
            "reason": session["reason"], "drafts": session["drafts"],
            "transcript": session["transcript"],
            "notes": [{"template": t, "title": n["title"], "text": n["text"]}
                      for t, n in session["notes"].items()],
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

    # A finished job carries the transcript AND the note shaped to the form
    # that was asked for, in the one body. That is the whole point of asking
    # for both at upload: the ordinary path needs no second call to anything.
    DONE = {"data": {"output": [
        {"template_id": "tpl-v", "status": "success",
         "value": base64.b64encode(b"| field | value | row | heard | sure |").decode()}],
        "template_results": {"transcript": [
            {"template_id": "transcript", "status": "success",
             "value": base64.b64encode(
                 b"BP is 140 over 90. Fever for three days.").decode()}]}}}
    assert transcript_of(DONE) == "BP is 140 over 90. Fever for three days."
    assert "tpl-v" in decoded(DONE), "the shaped note rides with the transcript"

    vitals = {"questions": [{"link_id": "systolic", "text": "Systolic", "type": "integer"}]}
    consult = {"questions": [{"link_id": "history", "text": "History", "type": "text"}]}

    def fake(note, fields, transcript):
        ids = {f["link_id"] for f in fields}
        said = {"systolic": {"value": 140, "confidence": 0.95, "evidence": "BP is 140"},
                "history": {"value": "Fever for three days", "confidence": 0.9,
                            "evidence": "Fever for three days"}}
        return {k: v for k, v in said.items() if k in ids}

    global poll
    real_poll, poll = poll, lambda txn: DONE
    try:
        # The template is already resolved on the session, so nothing here
        # reaches the workspace: making one is a network call and a check that
        # opens a socket is not a check.
        s = begin("enc-003", "user:mo", "phc-y", {"v.op": {"schema": vitals}},
                  instrument="i", templates={"v.op": "tpl-v"})
        collect(s, reader=fake)
    finally:
        poll = real_poll
    assert s["status"] == "ready" and s["drafts"][0]["values"] == {"systolic": 140}, s
    assert s["drafts"][0]["tick"] == ["systolic"]
    assert s["expires"] - time.time() > 24 * 3600 - 5, "the transcript is kept a day"

    s["templates"]["c.op"] = "tpl-c"
    refill(s, {"c.op": {"schema": consult}}, notes={"tpl-c": "note"}, reader=fake)
    assert [d["operation"] for d in s["drafts"]] == ["c.op"], "the switch rebuilds from the transcript"
    assert public(s)["transcript"].startswith("BP is 140")

    expire(now=s["expires"] + 1)
    assert s["id"] not in SESSIONS, "past a day the transcript is gone"

    # A session that never reaches ready still ages out: failed, withdrawn and
    # abandoned sessions are dropped on the same day as a transcript would be.
    stuck = begin("enc-003", "user:mo", "phc-stuck", {}, instrument="i")
    assert stuck["expires"] - time.time() > 24 * 3600 - 5, "every session has an expiry"
    expire(now=stuck["expires"] + 1)
    assert stuck["id"] not in SESSIONS, "a never-ready session does not live forever"

    # A withdrawal that lands while the model is still reading is not undone
    # when the model finishes.
    racing = begin("enc-003", "user:mo", "phc-race", {"v.op": {"schema": vitals}},
                   instrument="i")
    racing.update(status="ready", transcript="BP is 140 over 90.")

    racing["templates"]["v.op"] = "tpl-v"

    def withdrawn_midway(note, fields, transcript):
        withdraw(racing)
        return fake(note, fields, transcript)

    refill(racing, racing["operations"], notes={"tpl-v": "note"},
           reader=withdrawn_midway)
    assert racing["status"] == "withdrawn", racing
    assert racing["drafts"] == [] and racing["transcript"] == "", racing

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

    # "The service never shaped this form" and "the consultation did not state
    # any of it" are different facts and they were once the same sentence: a
    # machine that could not read a transcript at all told the doctor their
    # recording did not fit the form. Keep them apart.
    short = begin("enc-x", "who", "phc-x", {"v.op": {"schema": vitals}},
                  instrument="i", templates={"v.op": "tpl-v"})
    short.update(transcript="BP is 140 over 90.")
    none_shaped = public(refill(short, short["operations"], notes={},
                                reader=lambda *a: {}))
    assert none_shaped["status"] == "ready", none_shaped
    assert "has not shaped this form yet" in none_shaped["reason"], none_shaped["reason"]
    assert none_shaped["transcript"] == "BP is 140 over 90.", \
        "the transcript is kept: it is the record of what was said"

    said_nothing = begin("enc-x", "who", "phc-x", {"v.op": {"schema": vitals}},
                         instrument="i", templates={"v.op": "tpl-v"})
    said_nothing.update(transcript="Good morning.")
    empty = public(refill(said_nothing, said_nothing["operations"],
                          notes={"tpl-v": "a note with nothing in it"},
                          reader=lambda *a: {}))
    assert "Nothing in the recording fills this form" in empty["reason"], empty["reason"]
    assert "shaped" not in empty["reason"], empty["reason"]

    # -- Eka's template library ---------------------------------------------
    # The workspace lists its own templates beside the ones this module files
    # for itself. Offering our own plumbing as a choice of note would be
    # offering a form's shape as though it were a note, and a doctor picking
    # "phc . phc.op.consult-document" has no idea what they chose.
    class Listing:
        calls = 0

        def request(self, method, path, **kw):
            Listing.calls += 1
            assert (method, path) == ("GET", "/voice/api/v1/template"), (method, path)
            return {"items": [
                {"id": "t-soap", "title": "SOAP note", "desc": "", "default": True,
                 "is_favorite": False},
                {"id": "t-mine", "title": "Antenatal summary", "desc": "x",
                 "default": False, "is_favorite": True},
                {"id": "t-ours", "title": TEMPLATE_TITLE % "phc.op.consult-document",
                 "desc": "", "default": False, "is_favorite": False},
                {"title": "no id, so not a template"}]}

    was = _client
    try:
        _client = Listing()
        _library.update(at=0.0, items=[])
        listed = library(now=1000.0)
        assert [i["id"] for i in listed] == ["t-mine", "t-soap"], listed
        assert "t-ours" not in [i["id"] for i in listed], "our own templates are not offered"
        assert listed[0]["favorite"] and listed[1]["default"], listed
        library(now=1100.0)
        assert Listing.calls == 1, "five minutes of one listing, not one per tap"
        library(now=1000.0 + LIBRARY_SECONDS + 1)
        assert Listing.calls == 2, "and then it asks again"
        assert library_pick(["t-soap", "t-soap"]) == {"t-soap": "SOAP note"}
        try:
            library_pick(["not-a-template"])
            raise AssertionError("an id Eka does not list must be refused, not sent")
        except ScribeError as broke:
            assert "not-a-template" in str(broke), broke
    finally:
        _client = was
        _library.update(at=0.0, items=[])

    # A library note that rode with the transcript is on the session, in the
    # shape the screen reads, and a withdrawal takes it with everything else.
    WITH_NOTE = {"data": {"output": [
        {"template_id": "t-soap", "status": "success",
         "value": base64.b64encode(b"S: fever. O: BP 140/90.").decode()}],
        "template_results": {"transcript": [
            {"template_id": "transcript", "status": "success",
             "value": base64.b64encode(b"Fever for three days.").decode()}]}}}
    real_poll, poll = poll, lambda txn: WITH_NOTE
    try:
        n = begin("enc-003", "user:mo", "phc-n", {"v.op": {"schema": vitals}},
                  instrument="i", templates={"v.op": "tpl-v"}, want={"t-soap": "SOAP note"})
        collect(n, reader=lambda *a: {})
    finally:
        poll = real_poll
    shown = public(n)
    assert shown["notes"] == [{"template": "t-soap", "title": "SOAP note",
                               "text": "S: fever. O: BP 140/90."}], shown["notes"]
    assert note(n, "t-soap") == "S: fever. O: BP 140/90.", "a held note is not asked for twice"
    assert public(withdraw(n))["notes"] == [], "withdrawn means nothing is kept"

    print("ok api.scribe")


if __name__ == "__main__":
    demo()
