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
- Vitals are not in the scribe's operations and this module fills no numeric
  field. Eka's own output carries a temperature; it is dropped on purpose.
  A misheard number is silent, plausible and unrecoverable.

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

  templates  `eka_emr_template` decodes to a JSON prescription (symptoms,
           diagnosis with SNOMED and ICD-10 codes, medications with dose
           patterns, advices, followup). `transcript_template` decodes to the
           plain transcript. `clinical_notes_template` is markdown prose and
           is not requested here: everything in it is in the EMR JSON, with
           structure instead of headings to parse.

  There is NO per field recognition confidence anywhere in that response.
  `audio_matrix.quality` is about the audio, and the `confidence: true` inside
  a code linkage is about the code, not about what was heard. So this module
  reports a confidence of 0.0 for every field it fills, which the renderer
  draws as "heard, with no score reported", and it does not invent a number.

Run the check: python3 -m api.scribe
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import tempfile
import uuid

# Reused, not re-written: one definition in this repository of what an Aadhaar
# number, a file path and a recording's filename look like, so the two scribe
# call sites cannot drift apart on it. See care_phc/connectors/scribe/eka.py.
from care_phc.connectors.scribe.eka import _scrub

# The action the SDK's v2rx path takes, and the templates worth asking for.
ACTION = "ekascribe-v2"
TEMPLATES = [{"template_id": "eka_emr_template"},
             {"template_id": "transcript_template"}]

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


def start(audio, *, suffix=".webm", language="en-IN", mode="consultation"):
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
            output_format={"input_language": [language],
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


def _prop(item, name):
    """One of Eka's `properties` bags, flattened to text. The keys are opaque
    ids (`pg-1541659976`), so the property is found by its own `name`."""
    for prop in ((item or {}).get("properties") or {}).values():
        if str((prop or {}).get("name", "")).lower() != name.lower():
            continue
        parts = []
        for sel in prop.get("selection") or []:
            value = sel.get("value")
            unit = sel.get("unit")
            if value in (None, ""):
                continue
            parts.append("%s %s" % (value, unit) if unit else str(value))
        if parts:
            return ", ".join(parts)
    return ""


def _phrase(item):
    """A finding as one readable clause: the name, then whatever qualified it."""
    name = str((item or {}).get("name") or "").strip()
    extra = [_prop(item, k) for k in ("Since", "Details", "Finding status", "Status")]
    extra = [e for e in extra if e]
    return "%s (%s)" % (name, ", ".join(extra)) if name and extra else name


def _dose(med):
    """The dose as Eka wrote it. `custom` is its own human spelling of the
    pattern ("1-1-1", "SOS") and is preferred over rebuilding one."""
    freq = (med or {}).get("frequency") or {}
    duration = (med or {}).get("duration") or {}
    parts = [freq.get("custom") or "", duration.get("custom") or "",
             (med or {}).get("instruction") or ""]
    return ", ".join(str(p).strip() for p in parts if str(p).strip())


# The link_ids this module knows how to fill. A questionnaire that asks
# anything else gets nothing for it: an unfilled field is a field a doctor
# fills, and a guessed one is a field nobody re-reads.
KNOWN = ("history", "examination", "assessment", "plan", "diagnosis", "medications")


def fill(link_ids, emr):
    """The draft values this scribe can offer one questionnaire.

    `emr` is the decoded eka_emr_template JSON. Returns {link_id: value} with
    every empty answer dropped, so an operation the recording said nothing
    about produces no draft at all rather than a form full of blanks.
    """
    rx = (emr or {}).get("prescription") or {}
    want = set(link_ids)
    out = {}

    if "history" in want:
        out["history"] = ". ".join(
            p for p in (_phrase(s) for s in rx.get("symptoms") or []) if p)

    if "examination" in want:
        lines = []
        for exam in ((rx.get("medicalHistory") or {}).get("examinations") or []):
            name = str(exam.get("name") or "").strip()
            notes = str(exam.get("notes") or "").strip()
            lines.append(": ".join(x for x in (name, notes) if x))
        out["examination"] = ". ".join(x for x in lines if x)

    if "assessment" in want:
        out["assessment"] = ". ".join(
            p for p in (_phrase(d) for d in rx.get("diagnosis") or []) if p)

    if "plan" in want:
        advices = [str(a.get("text") or a.get("parsedText") or "").strip()
                   for a in rx.get("advices") or []]
        follow = (rx.get("followup") or {}).get("notes") or ""
        out["plan"] = ". ".join(x for x in advices + [str(follow).strip()] if x)

    if "diagnosis" in want:
        # Structured, per the questionnaire: one box per row, and the operation
        # mapping reads `code` off it (catalogue/ops/phc.op.consult-document.md
        # says `code: {item: [code, text]}`, so `code` is the one field the
        # renderer draws and the kernel writes).
        #
        # Eka also linked an ICD-10 and a SNOMED code for most of these, and
        # both are DROPPED here. The box holds one value, a doctor can read
        # back a diagnosis and cannot read back "J06.9", and a discrete value
        # nobody can check is exactly what the readback rule exists to stop. A
        # questionnaire that asks for the code in its own field is what would
        # make the code safe to offer; this one does not.
        out["diagnosis"] = [{"code": str(d.get("name") or "")}
                            for d in rx.get("diagnosis") or [] if d.get("name")]

    if "medications" in want:
        # Same rule: `medication` then `dosage_instruction`, which is what
        # phc.op.rx-prescribe's mapping reads off each item. A dose is a
        # discrete value, so it lands unconfirmed like every other one.
        out["medications"] = [
            {"medication": str(m.get("name") or ""), "dosage_instruction": _dose(m)}
            for m in rx.get("medications") or [] if m.get("name")]

    return {k: v for k, v in out.items() if v}


def drafts(status, targets, *, instrument=""):
    """One Draft per operation the instrument declaration named.

    `targets` is {operation_id: [link_id, ...]}, built by the caller from the
    declarations, so nothing here knows a bundle's words. The shape returned
    is kernel.contracts.Draft's, as JSON: values, per field confidence, and
    the transcript for the readback.

    Confidence is 0.0 for every filled field, and that is the honest number:
    the service reports none. The renderer draws anything under 0.9 as
    unconfirmed, which is exactly what a scribe draft is.
    """
    text = decoded(status)
    emr = {}
    raw = text.get("eka_emr_template") or ""
    if raw:
        try:
            emr = json.loads(raw)
        except ValueError:
            emr = {}
    transcript = (text.get("transcript_template") or text.get("transcript") or "").strip()

    out = []
    for operation, link_ids in sorted(targets.items()):
        values = fill(link_ids, emr)
        if not values:
            continue
        out.append({"instrument": instrument, "operation": operation,
                    "values": values,
                    "confidence": {k: 0.0 for k in values},
                    "transcript": transcript})
    return out


# ------------------------------------------------------------------- sessions
# In memory on purpose. A restart loses an in flight job, which costs a doctor
# one re-recording and costs the record nothing: no draft is a write, and the
# audio is already deleted. A table would have to be emptied by something.

SESSIONS = {}


def begin(thread, actor, txn, targets, instrument=""):
    session = {"id": "scr-" + uuid.uuid4().hex[:12], "thread": thread,
               "actor": actor, "txn": txn, "targets": targets,
               "instrument": instrument, "status": "running", "reason": "",
               "drafts": []}
    SESSIONS[session["id"]] = session
    return session


def by_txn(txn):
    for session in SESSIONS.values():
        if session["txn"] == txn:
            return session
    return None


def collect(session):
    """Ask once whether the draft is ready, and keep whatever came back.

    A withdrawn session is never asked again: withdrawal means this visit's
    audio stops being anybody's business, so the result of a job already
    running is dropped rather than drawn.
    """
    if session["status"] in ("ready", "failed", "withdrawn"):
        return session
    try:
        status = poll(session["txn"])
    except ScribeError as broke:
        session.update(status="failed", reason=str(broke))
        return session
    if running(status):
        return session
    session["drafts"] = drafts(status, session["targets"],
                               instrument=session["instrument"])
    if session["drafts"]:
        session.update(status="ready", reason="")
    else:
        said = failures(status)
        session.update(status="failed", reason=(
            "The scribe returned nothing this form can use. %s Type the note."
            % (" ".join(said) if said else
               "It heard no symptoms, diagnosis or medicines in the recording.")))
    return session


def withdraw(session):
    """Consent withdrawn, or the doctor gave up on it. Nothing is fetched
    afterwards and the draft, if one arrives at Eka, is never read."""
    session.update(status="withdrawn", drafts=[],
                   reason="Withdrawn. Nothing from this recording was kept.")
    return session


def public(session):
    """What the browser may see. The transaction id stays here: it is the
    handle on somebody's consultation audio and it is not the browser's."""
    return {"session": session["id"], "status": session["status"],
            "reason": session["reason"], "drafts": session["drafts"]}


# ---------------------------------------------------------------------- check

SAMPLE = {"data": {
    "created_at": "2026-09-11T05:03:14Z",
    "audio_matrix": {"quality": 0.98},
    "output": [{"template_id": "eka_emr_template", "status": "success",
                "errors": [], "value": base64.b64encode(json.dumps({
        "prescription": {
            "symptoms": [
                {"name": "fever", "linked": {"icd10_code": "R50.9"},
                 "properties": {"pg-1": {"name": "Since",
                                         "selection": [{"value": 3, "unit": "Days"}]}}},
                {"name": "cough", "properties": {"pg-5": {
                    "name": "Details", "selection": [{"value": "with yellow sputum"}]}}}],
            "diagnosis": [{"name": "Acute upper respiratory tract infection",
                           "linked": {"snomedct_code": "54398005", "icd10_code": "J06.9"},
                           "properties": {"pg-9": {"name": "Status", "selection": [
                               {"value": "Suspected"}]}}}],
            "advices": [{"text": "Drink plenty of fluids"}],
            "followup": {"notes": "Return in 3 days if fever does not settle"},
            "medications": [
                {"name": "Amoxicillin 500 mg",
                 "duration": {"custom": "5 Days"},
                 "frequency": {"custom": "1-1-1"}},
                {"name": "Paracetamol 650 mg", "frequency": {"custom": "SOS"},
                 "instruction": "For fever"}],
            "medicalHistory": {"examinations": [
                {"name": "Throat examination", "notes": "Abnormal | Inflamed"}]},
            "vitals": [{"name": "Temperature", "value": "38.4"}],
        }}).encode()).decode()},
               {"template_id": "transcript_template", "status": "success", "errors": [],
                "value": base64.b64encode(b"Good morning. Fever for three days.").decode()}],
    "template_results": {"custom": [{"template_id": "clinical_notes_template",
                                     "status": "failure", "value": "", "errors": [
        {"msg": "Something went wrong", "detail": "Template not found"}]}]}}}

CONSULT = ["history", "examination", "assessment", "diagnosis", "plan"]
RX = ["medications"]


def demo():
    """Run: python3 -m api.scribe

    The sample above is the shape of a real answer from api.eka.care on
    2026-09-11, trimmed. No network, no store, no credentials.
    """
    assert running({"data": {"output": [], "template_results": {}}}), "202 is still running"
    assert not running(SAMPLE), "an answer with output is not still running"

    # THE PARTIAL BODY, verbatim from api.eka.care on 2026-09-11: the transcript
    # is already done and the template every field comes from is not. Before
    # this was handled the session went straight to "failed" and stayed there.
    PARTIAL = {"data": {"output": [{"template_id": "eka_emr_template",
                                    "status": "in-progress", "value": "", "errors": []}],
                        "template_results": {"transcript": [
                            {"template_id": "transcript", "status": "success",
                             "value": base64.b64encode(b"Fever for three days.").decode()}]}}}
    assert running(PARTIAL), "a template still being built means keep waiting"
    assert drafts(PARTIAL, {"phc.op.consult-document": CONSULT}) == [], \
        "and nothing is drafted from the half that did arrive"
    # A template that FAILED is finished, not pending: it must not hang the wait.
    FAILED = {"data": {"output": [{"template_id": "eka_emr_template",
                                   "status": "failure", "value": "",
                                   "errors": [{"msg": "Template not found"}]}]}}
    assert not running(FAILED), "a failure is an answer, not a wait"
    assert failures(FAILED) == ["Template not found"], failures(FAILED)

    text = decoded(SAMPLE)
    assert "Fever for three days" in text["transcript_template"], text
    assert failures(SAMPLE) == ["Something went wrong Template not found"], failures(SAMPLE)

    got = drafts(SAMPLE, {"phc.op.consult-document": CONSULT,
                          "phc.op.rx-prescribe": RX}, instrument="phc.inst.consult-scribe")
    by_op = {d["operation"]: d for d in got}
    consult = by_op["phc.op.consult-document"]["values"]
    assert consult["history"] == "fever (3 Days). cough (with yellow sputum)", consult
    assert consult["examination"] == "Throat examination: Abnormal | Inflamed", consult
    assert consult["assessment"].startswith("Acute upper respiratory tract infection (Suspected)"), consult
    assert consult["plan"] == "Drink plenty of fluids. Return in 3 days if fever does not settle", consult
    assert consult["diagnosis"] == [
        {"code": "Acute upper respiratory tract infection"}], consult
    assert "J06.9" not in json.dumps(consult), \
        "a code the reader cannot check is not put in front of them as a value"

    rx = by_op["phc.op.rx-prescribe"]["values"]
    assert rx["medications"] == [
        {"medication": "Amoxicillin 500 mg", "dosage_instruction": "1-1-1, 5 Days"},
        {"medication": "Paracetamol 650 mg", "dosage_instruction": "SOS, For fever"}], rx

    # The doctrine, asserted rather than commented: no numeric field is ever
    # filled from a recording, and every field that is filled is unconfirmed.
    every = {k: v for d in got for k, v in d["values"].items()}
    assert "temperature" not in every and "systolic" not in every, every
    for d in got:
        assert set(d["confidence"]) == set(d["values"]), d
        assert all(c < 0.9 for c in d["confidence"].values()), d
        assert d["transcript"], "the readback needs the transcript"

    # An operation the recording said nothing about gets no draft at all, and
    # a questionnaire asking something this module does not understand gets
    # nothing for it rather than a guess.
    assert drafts(SAMPLE, {"x.op.y": ["blood_group"]}) == []
    silent = {"data": {"output": [{"template_id": "eka_emr_template",
                                   "value": base64.b64encode(b"{}").decode()}]}}
    assert drafts(silent, {"phc.op.consult-document": CONSULT}) == []

    # A withdrawn session is inert, whatever the service later says.
    session = begin("enc-002", "user:demo", "phc-x", {"phc.op.consult-document": CONSULT})
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

    print("ok api.scribe: 30 asserts, no network")


if __name__ == "__main__":
    demo()
