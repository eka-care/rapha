---
id: phc.op.consult-document
type: operation
kind: write
short: Consult
title: Document a consultation
summary: History, findings and assessment.
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
        created_by: {actor: id}
        status: {const: in_progress}
    - resource: notes
      fields:
        created_by: {actor: id}
        text: {note: [history, examination, assessment, plan]}
    # One Condition per diagnosis row, and every coded part of it resolved
    # from the row's own answer through the value set that answer binds to.
    #
    # What this replaces was `per_item: diagnosis` with `code: {item: [code,
    # text]}` and `verification_status: {const: confirmed}`. Two defects, and
    # the second is the dangerous one. The code column held whatever text a
    # renderer put in a free text row, because a structured answer has no
    # declared shape and nothing validated one anywhere. And every diagnosis
    # was stored as CONFIRMED by a literal, which is invariant I6 inverted:
    # "patient denies chest pain" became a confirmed chest pain, and a scribe's
    # guess became a settled fact. Both are now answers the doctor gives, and
    # `refuted` and `unconfirmed` are the codes that say so.
    - resource: condition
      per_row: diagnosis
      fields:
        created_by: {actor: id}
        code: {answer_code: condition}
        code_system: {answer_code_system: condition}
        code_display: {answer_code_display: condition}
        clinical_status: {answer_code: clinical_status}
        clinical_status_system: {answer_code_system: clinical_status}
        verification_status: {answer_code: verification_status}
        verification_status_system: {answer_code_system: verification_status}
        onset: {answer: onset}
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
