"""Run: python3 -m care_phc.connectors.scribe.check

The compliance guards, the mapping, the poll bound and the retention rule, with
a client double in place of ekacare.EkaCareClient, so no credential, no socket
and no recording are involved.

THE RESPONSE BELOW IS REAL. It was recorded from a live upload to
https://api.eka.care on 2026-09-11: a 92 second synthetic consultation
generated with macOS `say`, submitted through `EkaScribe.submit`, answered 202
while running and 200 at about 25 seconds. The keys, the nesting, the base64,
the `template_results.transcript` bucket and the diagnosis and medication
shapes are verbatim from that body. Only the volume is trimmed, so the fixture
is a page and not a screenful.

The load-bearing checks are the first four. Delete the scrub or the stdout
redirect in eka.py and they fail with a recording's path in the message, which
is the point of them.
"""
import base64
import json

from care_phc.connectors.scribe import draft as to_draft
from care_phc.connectors.scribe.base import (AudioRetention, ScribeError,
                                             transcribe)
from care_phc.connectors.scribe.eka import EkaScribe, _scrub, templates

CONSULT = "phc.op.consult-document"
RX = "phc.op.rx-prescribe"

AADHAAR = "1234 5678 9012"

# Trimmed from the live clinical_notes_template. The `**Heading**` form and the
# `---` rules between sections are exactly what came back.
NOTES = """**Chief Complaint**
- Fever for 3 days
- Dry cough, mostly at night

---

**Vital Signs**
- Temperature: 99.8°F
- Pulse: 88 beats/min

---

**Assessment**
- Acute upper respiratory tract infection (URTI), viral etiology most likely

---

**Sleep Hygiene**
- Rest and fluids
"""

# Trimmed from the live eka_emr_template. `linked.confidence` really is a
# boolean about the code linkage, not a recognition score, which is why nothing
# in draft.py turns it into one.
EMR = {"prescription": {
    "diagnosis": [{"name": "Acute upper respiratory tract infection",
                   "linked": {"snomedct_code": "54398005",
                              "icd10_code": "J06.9", "confidence": True},
                   "id": "locale-2bc4827157f373a5033b868ccc053f59"}],
    "medications": [{"name": "Paracetamol 500 mg tablet",
                     "dose": {"value": 1, "unit": "tablet", "custom": "1 tablet"},
                     "frequency": {"dose": ["1", "1", "1"], "custom": "1-1-1"},
                     "duration": {"value": 5, "unit": "Days", "custom": "5 Days"},
                     "timing": "after food"},
                    {"name": "Cetirizine 10 mg tablet",
                     "frequency": {"custom": "0-0-1"},
                     "duration": {"custom": "3 Days"}}],
    "symptoms": [{"name": "Fever"}],
    "medicalHistory": {"examinations": [{"name": "Throat", "notes": "Erythematous"}]},
    "language": "en"}}

TRANSCRIPT = ("Good morning. Please sit down. I have had fever since three "
              "days. Any vomiting? Loose motions? Number.")


def b64(text):
    return base64.b64encode(text.encode()).decode()


def body(notes=NOTES, emr=EMR, transcript=TRANSCRIPT):
    """The live 200 body, with the same two places a template can appear in."""
    def row(tid, text, kind):
        return {"template_id": tid, "value": b64(text), "type": kind,
                "name": tid, "status": "success", "errors": [], "warnings": []}
    return {"data": {
        "created_at": "2026-09-11T05:21:07Z",
        "output": [row("eka_emr_template", json.dumps(emr), "eka_emr"),
                   row("clinical_notes_template", notes, "custom")],
        "additional_data": {"mode": "consultation", "model_type": "pro"},
        "audio_matrix": {"quality": 1.0},
        "template_results": {
            "integration": [row("eka_emr_template", json.dumps(emr), "json")],
            "custom": [row("clinical_notes_template", notes, "markdown")],
            "transcript": [row("transcript", transcript, "transcript")]}}}


class Response:
    """Only what eka.py reads off a requests.Response."""

    def __init__(self, status=200, payload=None, text=None):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        return self._payload if self._payload is not None else {}


class V2RX:
    """Stands in for ekacare.v2rx.v2rx.V2RX, including its manners: the real
    one prints "Successfully uploaded <basename>" to stdout."""

    def __init__(self, owner):
        self.owner = owner

    def upload(self, file_paths, txn_id=None, action="default", extra_data=None,
               output_format=None):
        print("Successfully uploaded %s" % file_paths[0])   # as the SDK does
        self.owner.uploads.append({"paths": list(file_paths), "txn_id": txn_id,
                                   "action": action, "extra_data": extra_data,
                                   "output_format": output_format})
        out = self.owner.next()
        if isinstance(out, Exception):
            raise out
        return out


class Client:
    """Stands in for ekacare.EkaCareClient: the three things eka.py touches."""

    def __init__(self, outcomes=(), uploads=()):
        self.outcomes = list(outcomes)
        self.upload_outcomes = list(uploads) or [[{"key": "k"}]]
        self.calls = []
        self.uploads = []
        self.tokens_cleared = 0
        self.base_url = "https://api.eka.care"
        self.v2rx = V2RX(self)

    def next(self):
        pool = self.upload_outcomes if self.uploads and not self.calls else None
        return (pool or self.outcomes).pop(0) if (pool or self.outcomes) else [{"key": "k"}]

    def request(self, method=None, endpoint=None, raw_response=False, **kw):
        self.calls.append((method, endpoint))
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    def set_access_token(self, token):
        self.tokens_cleared += 1


class Files:
    """A filesystem double: rename and remove without touching a disk."""

    def __init__(self, *paths):
        self.live = set(paths)
        self.removed = []

    def rename(self, src, dst):
        self.live.discard(src)
        self.live.add(dst)

    def remove(self, path):
        if path not in self.live:
            raise OSError("no such file")
        self.live.discard(path)
        self.removed.append(path)


def scribe(outcomes=(), uploads=(), files=None, retention=None):
    client = Client(outcomes, uploads)
    eka = EkaScribe(client=client, retention=retention or AudioRetention())
    if files is not None:
        eka._rename = lambda path, session: (      # noqa: E731  the seam, on purpose
            files.rename(path, "/recordings/%s.wav" % session)
            or "/recordings/%s.wav" % session)
    return eka, client


# ---------------------------------------------------------------- compliance

def test_a_failing_upload_never_leaks_the_recording_path():
    """The SDK's own error quotes both the path and the filename. Neither may
    survive the boundary: a recording's filename is an identifier."""
    broke = RuntimeError("Upload failed for ramesh-enc-002.wav: "
                         "/var/phc/audio/ramesh-enc-002.wav not readable (500)")
    eka, _ = scribe(uploads=[broke], files=Files("/tmp/in.wav"))
    try:
        eka.submit("/tmp/in.wav", operation=CONSULT, thread="enc-1")
    except ScribeError as e:
        assert "ramesh" not in str(e), str(e)
        assert "/var/phc/audio" not in str(e), str(e)
        assert ".wav" not in str(e), str(e)
        assert e.status == 500, e.status
    else:
        raise AssertionError("a failing upload must raise, scrubbed")


def test_the_sdk_printing_the_filename_never_reaches_stdout(capture=None):
    """stdout is a log. The real SDK prints the basename on every upload."""
    import io
    import sys
    files = Files("/tmp/in.wav")
    eka, _ = scribe(files=files)
    held, sys.stdout = sys.stdout, io.StringIO()
    try:
        eka.submit("/tmp/in.wav", operation=CONSULT)
        printed = sys.stdout.getvalue()
    finally:
        sys.stdout = held
    assert printed == "", "the SDK's filename line escaped to stdout: %r" % printed


def test_an_aadhaar_and_a_transcript_path_are_scrubbed():
    text = _scrub('{"error":"bad %s at /var/phc/audio/enc-2.m4a"}' % AADHAAR)
    assert AADHAAR not in text and "5678" not in text, text
    assert "enc-2" not in text and "/var/phc" not in text, text


def test_submit_renames_the_recording_and_sends_no_thread_id():
    """The S3 key is the basename, so the name goes first. The thread is kept
    on this side: Eka does not need an encounter id."""
    files = Files("/tmp/ramesh-enc-002.wav")
    eka, client = scribe(files=files)
    session = eka.submit("/tmp/ramesh-enc-002.wav", operation=CONSULT, thread="enc-002")
    sent = json.dumps(client.uploads[0])
    assert "ramesh" not in sent, sent
    assert "enc-002" not in sent.replace(session, ""), sent
    assert client.uploads[0]["txn_id"] == session
    assert client.uploads[0]["action"] == "ekascribe-v2"
    assert eka.retention._held[session]["thread"] == "enc-002"


# --------------------------------------------------------- the real response

def test_the_live_response_becomes_the_two_drafts_observed():
    eka, _ = scribe([Response(200, body()), Response(200, body())])
    consult = eka.fetch("phc-1", operation=CONSULT)
    rx = eka.fetch("phc-1", operation=RX)

    assert consult.instrument == "phc.inst.consult-scribe"
    assert set(consult.values) == {"history", "examination", "assessment", "diagnosis"}
    assert consult.values["diagnosis"] == [
        {"code": "Acute upper respiratory tract infection",
         "text": "Acute upper respiratory tract infection",
         "icd10_code": "J06.9", "snomedct_code": "54398005"}]
    assert "Fever for 3 days" in consult.values["history"]
    assert "99.8" in consult.values["examination"]
    assert consult.transcript and "Number." in consult.transcript, \
        "the transcript is what the discrete values are read back against"

    assert set(rx.values) == {"medications"}
    assert rx.values["medications"] == [
        {"medication": "Paracetamol 500 mg tablet",
         "dosage_instruction": "1 tablet, 1-1-1, 5 Days, after food"},
        {"medication": "Cetirizine 10 mg tablet",
         "dosage_instruction": "0-0-1, 3 Days"}]


def test_every_discrete_value_is_unconfirmed():
    """A diagnosis or a drug a machine heard is a discrete value a machine
    heard. web/src/Form.tsx marks anything under 0.9 for re-reading."""
    eka, _ = scribe([Response(200, body()), Response(200, body())])
    for op, key in ((CONSULT, "diagnosis"), (RX, "medications")):
        draft = eka.fetch("phc-1", operation=op)
        assert draft.confidence[key] < 0.9, draft.confidence
    assert to_draft.NO_SCORE == 0.0, "a scored-looking number would be invented"


def test_nothing_is_invented():
    """Eka returned a temperature. The scribe's declaration does not name
    vitals, so no numeric field is filled from it; it survives as prose."""
    eka, _ = scribe([Response(200, body())])
    consult = eka.fetch("phc-1", operation=CONSULT)
    assert "temperature" not in consult.values
    assert not [k for k in consult.values if k not in to_draft.SECTIONS.values()
                and k != "diagnosis"], consult.values
    assert "" not in consult.values.values(), "an empty box is not a value"


def test_an_unheard_section_is_absent_and_an_unknown_heading_is_kept():
    eka, _ = scribe([Response(200, body())])
    consult = eka.fetch("phc-1", operation=CONSULT)
    assert "plan" not in consult.values, "nothing was said about a plan here"
    assert "Sleep Hygiene" in consult.values["history"], \
        "an unmapped heading must land somewhere, with its heading"


def test_a_missing_template_fails_closed_to_the_form():
    """Templates are read from `output` and from `template_results`, so a
    fixture with neither is the honest empty case: show the form."""
    empty = {"data": {"output": [], "template_results": {}}}
    eka, _ = scribe([Response(200, empty), Response(200, empty)])
    assert eka.fetch("phc-1", operation=CONSULT).values == {}
    assert eka.fetch("phc-1", operation="phc.op.vitals-record").values == {}


def test_templates_reads_both_places_the_transcript_can_hide_in():
    found = templates(body()["data"])
    assert set(found) == {"eka_emr_template", "clinical_notes_template", "transcript"}, found
    assert "fever" in found["transcript"].lower(), "the transcript is only in template_results"


# ------------------------------------------------------------- the poll bound

def test_a_running_job_answers_none_rather_than_an_empty_draft():
    for code in (202, 206):
        eka, _ = scribe([Response(code, {})])
        assert eka.fetch("phc-1", operation=CONSULT) is None, code


def test_transcribe_gives_up_on_a_clock_and_keeps_the_session():
    """A clinician's screen is never held open forever, and a timeout is not
    reported as silence: the session id rides on the error."""
    slept, now = [], [0.0]
    eka, _ = scribe([Response(202, {})] * 40, files=Files("/tmp/in.wav"))
    try:
        transcribe(eka, "/tmp/in.wav", operation=CONSULT, timeout=30, interval=3,
                   sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
                   clock=lambda: now[0])
    except ScribeError as e:
        assert e.code == "timeout"
        assert e.session and e.session.startswith("phc-"), "no session to come back for"
        assert sum(slept) <= 33, "the bound is not a bound: waited %ss" % sum(slept)
    else:
        raise AssertionError("an unfinished job must time out, not hang")


def test_transcribe_returns_the_draft_when_it_arrives():
    eka, _ = scribe([Response(202, {}), Response(200, body())], files=Files("/tmp/in.wav"))
    draft = transcribe(eka, "/tmp/in.wav", operation=RX, timeout=30,
                       sleep=lambda s: None, clock=lambda: 0.0)
    assert draft.values["medications"][0]["medication"] == "Paracetamol 500 mg tablet"


def test_a_404_surfaces_with_the_gateway_code():
    eka, _ = scribe([Response(404, {"error": {"code": "resource_not_found"}})])
    try:
        eka.fetch("phc-nope", operation=CONSULT)
    except ScribeError as e:
        assert e.status == 404 and e.code == "resource_not_found", (e.status, e.code)
    else:
        raise AssertionError("a missing session must surface")


def test_a_401_is_retried_once_and_a_500_is_not():
    eka, client = scribe([Response(401, text="expired"), Response(200, body())])
    assert eka.fetch("phc-1", operation=CONSULT) is not None
    assert client.tokens_cleared == 1 and len(client.calls) == 2

    eka, client = scribe([Response(500, text="upstream down")])
    try:
        eka.fetch("phc-1", operation=CONSULT)
    except ScribeError as e:
        assert e.status == 500
    assert len(client.calls) == 1, "a 500 was retried; only a 401 should be"


# ---------------------------------------------------------- audio retention

def keeper(files, now, **kw):
    return AudioRetention(remove=files.remove, clock=lambda: now[0],
                          scan=lambda d: [(p, 0.0) for p in sorted(files.live)], **kw)


def test_audio_goes_after_the_grace_window_and_not_before():
    files, now = Files("/a.wav"), [0.0]
    hold = keeper(files, now, grace_seconds=900)
    hold.hold("s1", "/a.wav")
    hold.confirmed("s1")

    now[0] = 899
    assert hold.sweep() == 0 and files.removed == [], "deleted inside the grace window"
    now[0] = 900
    assert hold.sweep() == 1 and files.removed == ["/a.wav"]
    assert hold.pending() == 0
    assert hold.sweep() == 0, "a second sweep must not double count"


def test_a_zero_window_deletes_on_confirm():
    """Zero is a supported value, because it may be the one that gets signed."""
    files, now = Files("/a.wav"), [0.0]
    hold = keeper(files, now, grace_seconds=0)
    hold.hold("s1", "/a.wav")
    hold.confirmed("s1")
    assert hold.sweep() == 1


def test_withdrawal_discards_this_visits_audio_at_once():
    """E.3: withdrawal stops capture and discards the audio from that point.
    A visit may have made several recordings, so the thread deletes its own."""
    files, now = Files("/a.wav", "/b.wav", "/c.wav"), [0.0]
    hold = keeper(files, now)
    hold.hold("s1", "/a.wav", thread="enc-1")
    hold.hold("s2", "/b.wav", thread="enc-1")
    hold.hold("s3", "/c.wav", thread="enc-2")
    assert hold.discard(thread="enc-1") == 2
    assert sorted(files.removed) == ["/a.wav", "/b.wav"]
    assert files.live == {"/c.wav"}, "another visit's audio was taken"


def test_audio_nobody_confirmed_still_goes():
    """An abandoned consultation: no confirm ever arrives. The backstop is the
    only thing standing between that and a disk full of consultations."""
    files, now = Files("/a.wav"), [0.0]
    hold = keeper(files, now, max_hold_seconds=3600)
    hold.hold("s1", "/a.wav")
    now[0] = 3599
    assert hold.sweep() == 0
    now[0] = 3600
    assert hold.sweep() == 1


def test_a_restart_does_not_orphan_a_recording_forever():
    """The register is in memory. A directory sweep is what catches what a
    crash left behind, which is the reason `directory` exists."""
    files, now = Files("/recordings/ghost.wav"), [7200.0]
    hold = keeper(files, now, max_hold_seconds=3600, directory="/recordings")
    assert hold.sweep() == 1 and files.removed == ["/recordings/ghost.wav"]


def test_sweeping_reports_counts_and_never_paths():
    """Whatever a caller logs, it cannot log a recording's path from here."""
    files, now = Files("/a.wav"), [0.0]
    hold = keeper(files, now, grace_seconds=0)
    hold.hold("s1", "/a.wav")
    hold.confirmed("s1")
    assert isinstance(hold.sweep(), int)
    assert isinstance(hold.discard(session="s1"), int)


def test_a_file_already_gone_is_not_an_error():
    files, now = Files(), [0.0]
    hold = keeper(files, now, grace_seconds=0)
    hold.hold("s1", "/gone.wav")
    hold.confirmed("s1")
    assert hold.sweep() == 0 and hold.pending() == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok   %s" % fn.__name__)
    print("\n%d checks passed" % len(fns))
