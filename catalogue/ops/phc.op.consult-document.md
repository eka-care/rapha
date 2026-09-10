---
id: phc.op.consult-document
type: operation
kind: write
short: Scribe
title: Document a consultation
summary: >
  Write down what the patient said, what was found, and what the doctor
  concluded.
capability: encounter.document
scope_qualifier: null
station: doctor
instrument: scribe
preconditions:
  - registered
irreversibility: correctable
input: phc.schema.consult-v1
writes: [encounter, notes, condition]
mapping:
  records:
    - resource: encounter
      fields:
        status: {const: in_progress}
    - resource: notes
      fields:
        text: {note: [history, examination, assessment, plan]}
    - resource: condition
      per_item: diagnosis
      fields:
        code: {item: [code, text]}
        verification_status: {const: confirmed}
emits: [consult.documented]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.rx-prescribe, phc.op.lab-order]
  concepts: []
---

## In plain words

The doctor's note. This is narrative, and narrative is the one thing ambient
capture is genuinely good at, because context recovers a dropped word and the
clinician catches the rest on review.

## Before you start

The patient must be registered. Vitals are not required: a consultation can
start with a vitals pending flag showing, because making the doctor wait on
another station is how queues jam.

You need `encounter.document`. Capture requires the visit's consent flag,
taken once at registration, and declining it is not a barrier to being seen.

## What happens

Scribe listens and produces a draft. The draft is a payload rendered for edit
and confirm, never a commit. The doctor edits and confirms, and only then is
anything written.

Consent is visible while capture is live, not buried in a setting. Withdrawal
mid visit stops capture and discards audio from that point. Records already
confirmed stand.

## How you know it worked

The note is on the thread, attributed to the doctor rather than to the model,
and the next actions become prescribe, order an investigation, and refer.

## When it goes wrong

- **The patient declined audio.** Everything falls back to form entry and the
  consultation proceeds normally. This has to be true and visible or the
  consent is theatre.
- **The draft is wrong.** Edit it. Confirming an inaccurate draft because it
  is faster is the failure mode the whole review step exists to catch.
- **Two speakers, or the patient speaks another language.** Second language
  speakers generate measurably more recognition errors. Review the draft with
  more care, not less.
