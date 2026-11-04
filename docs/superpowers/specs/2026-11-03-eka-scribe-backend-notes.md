# What is actually in the Eka Scribe backend

Read 2026-11-03 from `~/code/voice2rx-be`. This changes three things I told
the owner earlier and hands Hera a capability nobody has costed.

## 1. I was wrong about streaming

I said Eka's streaming mode sends the transcript back while the person is
still talking. It does not.

`WS /voice/v1/stream/sessions/{stream_id}/audio` is **upload only**. Audio
goes in, Silero VAD cuts it into 10–30 second chunks, the chunks go to S3,
and transcription happens afterwards off an SQS queue. Nothing comes back
down that socket.

What streaming actually buys is still worth having: by the time the doctor
stops talking, the audio is already uploaded and already chunked. That is
two of the three costs in the delay gone. It is not a live transcript.

## 2. A live transcript is still possible, by polling, and it needs no SDK swap

Three things exist on the API we can already reach today:

- **`GET /voice/api/v3/transcript/{txn_id}/{file_name}`** returns the
  transcript of **one audio chunk**. Chunks are transcribed as they land in
  S3, so the first chunk's words exist long before the consultation ends.
- **`GET /voice/v1/sessions/{id}?template_id=…`** fetches **one document**
  instead of polling every document in the session.
- The webhooks are **separate and ordered**:
  `scribe.session.transcript.completed`, then
  `scribe.session.document.generated` once per document, then
  `v2rx.completed`.

So the canvas can show words appearing during the consultation, and then
each note as it is finished, rather than one wait for everything. The
mechanism is polling per chunk, not a push, and the design note should say
so plainly rather than promise a stream.

**This is a bigger deal than the TypeScript question.** Changing language
buys nothing. Changing *what we ask for and when* buys all of it.

## 3. We would be moving onto an open protocol, not a vendor SDK

`/voice/v1/...` is the **MedScribeAlliance Protocol v0.1**, with a
`/.well-known` discovery endpoint. That is the protocol the TypeScript SDK
speaks, and Eka open-sourced it. Moving Rapha's scribe onto it is moving
onto a standard with a discovery document, which is a far better argument
than "switch to their SDK" — and it keeps the second-implementation
promise that `connectors/scribe/base.py` exists to protect.

## 4. Hera's Parrotlet claim is already true

Transcription runs Parrotlet (en/hi), Gemini 2.5 Pro (the default) or BDIC,
per chunk, four workers. Structuring runs Bedrock Claude Sonnet 4.6 for
`pro` and Haiku 4.5 for `lite`, with drug k-NN and SNOMED/ICD codification
and translation. The deck's "Parrotlet — speech recognition for Indian
languages" is a thing that exists and is wired, not a thing to build.

There is also a FHIR path already: structuring output goes to
`fhir-parser.orbi` `/ingest_rx_data`, and `medical_record/apis/fhir_api.py`
fetches the composition back by transaction id.

## 5. THE FINDING: an ASHA can phone the visit in

This is the one nobody has costed, and for Hera it may be the whole demo.

The backend has a **provider-agnostic telephony layer** — Vobiz, Exotel and
Plivo behind one `base.py` interface, with webhooks under
`/voice/v1/telephony/...` and a MySQL `telephony_config` table mapping a
**phone number to a workspace**. The streaming WebSocket speaks the
Vobiz/Twilio Media Streams JSON envelope. A telephone call is already a
first-class way to feed a scribe session.

Which means: **an ASHA with a feature phone calls a number and speaks the
visit.** No smartphone, no app, no data connection, no literacy in a form.
That is the Hera "Frontline — no forms" card at its strongest, and it is
the version that works in a village where the deck's version does not.

It also replaces a dependency: the deck names **Twilio** for reminders.
This layer already does provider-agnostic telephony, so reminders should go
through it rather than adding a fourth provider.

### 5.1 One clinic number that any ASHA dials: yes, with one change

Asked 2026-11-03: can every clinic's workspace have a number an ASHA calls,
have the conversation, and have it land in that clinic's account as a
patient with structured records?

**The lookup today goes the other way.** `webhook_router.py` calls
`get_telephony_config_by_phone(event.caller_number)` — it resolves the
workspace from **the number that called**, so every ASHA's personal handset
has to be registered, and an unregistered caller is refused outright with
"Please setup your workspace at console.eka.care". One shared clinic number
is not what it does.

**But the dialled number is already there.** `event.called_number` is
parsed and carried into the stream session's `additional_data`. It is
simply not what the lookup uses. So the change is: resolve the workspace
from `called_number`, and keep `caller_number` to identify the worker.
Both are already in the event, and that combination is better than either
alone — one number for a whole centre, and still a record of who recorded
the visit, which a health record needs.

The schema needs one edit with it: `telephony_config` has
`UNIQUE KEY uq_telephony_config_phone_number`, which forbids many workers
sharing a clinic number. The uniqueness belongs on the clinic number in a
separate table, or on the pair.

**Hanging up is already the end of the session.** Telephony sessions are
created with `commit_on_close: bool = True`, so the structuring pass starts
when the call drops. Nothing needs a stop button.

### 5.2 The patient is the hard half, and it is ours

A telephony session is created today with a workspace and a user and
**no patient**. The protocol's session model does carry `patient_details`
with `oid` promoted for indexing, but the telephony path fills none of it,
because when the call connects nobody knows who the patient is.

Taking the name and mobile out of the conversation works. The danger is the
step after it: **matching a spoken name and a spoken number to a patient.**
A wrong match writes one pregnant woman's record into another woman's file.
In a village with repeated names and shared handsets that is not a rare
event, and it is the one failure this product cannot have.

So the call should not silently create or join a patient. It should land as
a visit with a **suggested** match that somebody at the centre confirms or
corrects before it joins the record. Rapha's front desk is already that
screen, and this keeps "no forms" true for the ASHA — she only talks — while
putting the one dangerous judgement in front of a person.

Note also who creates the patient. Eka's scribe produces a structured
document; it does not own a patient register. Our kernel does, with the
ABHA link and the FHIR record. So the patient is created by the kernel off
the webhook, not by Eka.

### 5.3 Consent has nowhere to live on a phone call

An ambient recording of a conversation with a patient needs that patient's
consent, and a phone call has no screen to show it on. The ASHA has to say
it and the patient has to answer, and that answer should be inside the
recording.

Rapha already gates the microphone on a declared consent flag, so there is
a place to put the result. What does not exist is a way to satisfy that
flag by voice. It is a decision, not a detail: without it the phoned-in
visit cannot legally be the demo.

## 6. A precedent for the reminder decision

Eka's own house rule, written into the webhook registry: *"payloads are
intentionally minimal: identifiers only. clients fetch full details from
the GET session / GET document APIs — this keeps PHI out of the webhook
channel."*

That is exactly the position I recommended for Hera's overdue reminders: a
message that says a visit is overdue and nothing about who or what. It is
now not my preference but the platform's existing practice, which is a much
easier argument.

## 7. Two other things worth knowing

- **Doctor memory.** `POST /voice/api/v1/memory/suggest` answers "what does
  this doctor usually do with this medicine", and there is CRUD for a
  doctor's own memory lines. Eka is already solving the personalisation
  problem that Heidi solves with user-authored templates — differently, and
  arguably better, because nobody has to write anything.
- **Data residency is per workspace**, carried on the gateway JWT as `r`,
  IN (ap-south-1) or ZA. Mandatory on every API. Relevant to anything we
  claim about ABDM compliance.

## 8. What changes in the plans

In `2026-11-02-thread-as-channel-design.md`:

- §8a said the transcript arrives "the moment recording ends" on Eka's
  current API and that a streaming mode sends it live. Correct that to:
  per-chunk transcripts are pollable during the consultation; documents
  arrive one at a time after it.
- The scribe canvas can therefore show real words during recording. The
  waveform is no longer the only honest thing on that screen.

In `2026-11-03-hera-and-the-cleaner-shell-design.md`:

- Decision §6.3 (how a reminder reaches an ASHA) gains a recommended
  answer: through the existing telephony layer, identifiers only, per §6
  above.
- Add a candidate that is not yet in the plan: **the phone-in visit**
  (§5). It is the strongest frontline story available and most of the
  machinery exists. It needs the owner's call on whether the hackathon
  demo leads with it.

## 9. FHIR from the scribe, probed 2026-11-04

Owner: "on the scribe voice to rx repo there's a fhir service, which should
help you get the structured note in FHIR." Probed with one synthetic
recording (a computer voice reading an invented consultation, no real person)
through the same SDK path the kernel uses, asking for the Default Prescription
Print template, `7d03dd95-45b2-41e1-a5d3-fba98fee0418`. Nothing was published.

**What came back.** A correct transcript and a correct note: patient, age,
complaint, vitals (130/85, 84, 98.6 F, 51 kg), examination, the diagnosis, a
medication row (Nitrofurantoin 100 mg, twice daily, 5 days, after food), a
urine routine, advice and the follow-up. The note is MARKDOWN: headings and
pipe tables. The session names a `document_id` for it.

**What did not.** `GET /voice/api/v1/documents/{id}` answered with
`fhir_data: null`, `ag_ui_data: null` and `publish: {}`. So:

- The structured state (`ag_ui_data`) is saved by a CLIENT, when the Eka
  scribe editor saves or publishes. The SDK path never produces it, so there
  is nothing structured to convert.
- The NRCES (ABDM) bundle is built only by `POST /sessions/{s}/documents/{d}/publish`
  with that state as the JSON body, and only for templates on an allow-list
  that currently holds the Default Prescription Print. Publishing is not a
  conversion: it also pushes the bundle into AWS HealthLake (Eka's patient
  store), uploads the vault PDF and fires the EMR webhook. It is an outward
  write about a real person and is not to be done to try it.
- `GET /voice/medical-record/api/fhir/{txn}` is reachable with the kernel's
  credentials and reads the older `fhir-parser` composition. It answers 408
  "Data unavailable" for this recording: the older path is not run for it.
- The conversion itself (`voice2rx/services/fhir/converter.py`, over the
  `scribe2fhir` SDK) is pure, but it is Eka's code and a dependency.

**What this means for Rapha.** There are three honest ways to have the note in
FHIR, and none is free: (a) build Eka's `ScribeState` ourselves from the forms
a clinician committed and publish it, accepting that publishing writes to
Eka's store; (b) run Eka's converter locally over a state we build, adding
their SDK as a dependency; (c) leave the note as a reading copy and let the
committed forms be the record, which `kernel/fhir.py` already turns into an
ABDM bundle. (c) is what runs today. The choice is the owner's: it decides
which system holds the patient's record.

A synthetic recording, transcript and document (`a17ed378-...`) now sit in the
Eka workspace under txn `phc-a1e6c5605b06459b`. They hold an invented patient.

### 9.1 How Eka's own app gets the structured note, and that we can too

The structured state does not come from the recording call. It comes from a
SECOND call, which Eka's app makes once the transcript exists:
`POST /voice/v1/scribe/agent/runs/{template_id}` with `thread_id` = the session
id, answered as a server-sent stream (AG-UI): `STATE_SNAPSHOT`, then a
`STATE_DELTA` per change as the model writes each section through a tool.
The same SDK credentials reach it. Probed 2026-11-04 against the synthetic
recording: HTTP 200, 28 seconds, 12 sections, nothing published.

What the final state holds (rebuilt from the snapshot and the deltas):

- Twelve sections, each with a `kind`: LIST, PATIENT_MEDICAL_HISTORY,
  VITAL_TABLE, EXAMINATION_FINDINGS, DIAGNOSIS, MEDICATION_TABLE,
  LAB_INVESTIGATIONS, FOLLOW_UP.
- Vitals as rows with a unit each: 130/85 mmHg, 84 /min, 98.6 F, 51 kg.
- The medicine split into name, strength, form, dose, frequency and duration:
  Nitrofurantoin / 100 mg / capsule / 1 capsule / twice daily / 5 days.
- A follow-up with a computed date (2026-11-11) and a plain interval.
- Allergies as a statement of absence (`status: no`), not an empty list.

What to distrust, for the reason `kernel/codification.py` already states: the
service attaches catalogue codes and they are suggestions. "Urine routine" came
back as "Urine Protein (Dipstick)", LOINC 5804-0, `match_type: closest`, which
is a plausible test and not the one asked for. The diagnosis and the medicine
came back with no catalogue match (`locale-...` ids). A coded value from this
is a candidate for a person to confirm, never a value.

What it changes: the markdown note was the only thing we read, and
`api/shaped.py` parses it back into form fields. This is the same information
before it was flattened, so it fills our forms more exactly, and it is the
input Eka's own converter takes. Running the agent also created a new, empty
document on the session; nothing else was written.
