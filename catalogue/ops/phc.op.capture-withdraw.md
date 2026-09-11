---
id: phc.op.capture-withdraw
type: operation
kind: write
short: Stop recording
title: Stop recording this visit
summary: Stop the scribe for the rest of this visit.
capability: encounter.document
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - capture.consented
irreversibility: correctable
input: phc.schema.capture-withdraw-v1
writes: [questionnaire_response]
mapping:
  # The withdrawal itself is the record: who stopped it and when. No clinical
  # resource is touched, because stopping a recording is not a clinical act.
  records:
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.capture-withdraw-v1}
        payload: {json: payload}
emits: [capture.withdrawn]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.consult-document, phc.op.patient-register]
  concepts: []
---

## In plain words

The patient changes their mind. One tick and the scribe is off for the rest
of the visit. This used to ride on the consultation form, where `assessment`
is required, so a consent could not be withdrawn without also writing a note.
Stopping a recording is not a clinical act and must not require one.

## Before you start

Capture consent must be on right now. That is the whole precondition, so the
action is absent on a visit that never consented and absent again once it has
been withdrawn, which is how every other absence here works.

The one question is `required`. It has to be: a withdrawal that answers
nothing used to be allowed, and drew a card saying the recording had stopped
while it went on running. The gate is already open here, so an unanswered form
must be refused rather than fail quietly shut the way a consent question does.

You need `encounter.document`, which is the same capability that runs the
scribe. Whoever may record may stop.

## What happens

`capture.withdrawn` goes true on the thread, and `capture.consented` is
composed with `not capture.withdrawn`, so the gate is off from that moment.
The server re-reads the flag on every path that could bring a draft back, so
a recording still running at the gateway is never collected, by the poll or
by the webhook, and a second one cannot be started.

Nothing clinical is written. The one row is the withdrawal itself, carrying
who stopped it. Records already confirmed are rows, and rows are untouched.

## How you know it worked

The scribe disappears from this thread and the consultation falls back to
typing. The thread's flags show `capture.withdrawn` and no longer show
`capture.consented`. Any note committed before the withdrawal is still there.

## When it goes wrong

- **It was tapped by mistake.** Nothing here raises consent again: the store
  can raise a flag and cannot lower one, so this visit is typed from here on.
  That asymmetry is deliberate and it points the safe way. Ask again at the
  next visit; a thread is one visit and nothing carries over.
- **The recording is still running in the browser.** The Stop button on the
  panel ends that one job. This is the visit wide answer, and it is the one
  the server reads before collecting anything.
- **The patient declined at the desk instead.** Then this action was never
  drawn, because consent was never on. A declined visit is not asked again at
  any station.
