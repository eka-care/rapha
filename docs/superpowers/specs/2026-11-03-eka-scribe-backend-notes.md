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
