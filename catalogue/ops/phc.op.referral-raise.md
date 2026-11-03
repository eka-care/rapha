---
id: phc.op.referral-raise
type: operation
kind: write
short: Refer onward
title: Refer this patient onward
summary: Send her somewhere else, and keep the referral open until somebody closes it.
capability: handover
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - registered
  - not referral.open
irreversibility: correctable
input: phc.schema.referral-raise-v1
writes: [episode_of_care, questionnaire_response]
mapping:
  records:
    # A REFERRAL IS AN EPISODE, and that is the design rather than a
    # convenience. It has a start, an owner, an end and an outcome; it
    # outlives the visit that raised it; and it belongs to the person
    # rather than to the encounter. Those are the four properties
    # `episode_of_care` has and a `service_request` on a thread does not.
    # See the body.
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: referral}
        status: {const: active}
        anchor_basis: {const: raised}
    # Where and why, kept whole. The episode table is generic and has no
    # column for a destination, and it should not grow one: which facility
    # and for what reason are this bundle's words about this bundle's
    # referral, and the same row shape already carries a handover's.
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.referral-raise-v1}
        payload: {json: payload}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.referral-close, phc.op.handover]
  concepts: []
---

## In plain words

The centre cannot do what this woman needs, so she is sent on. The
referral stays open from that moment until somebody records what happened
to her, and while it is open it is something this centre owes.

Hera's line is "every voice heard, every referral closed", and this is the
first half of the second clause.

## Why this is an episode and not a request

The obvious shape is a `service_request`, which is what FHIR calls the
clinical ask and what `phc.op.lab-order` already writes. It is the wrong
shape here, for two reasons and the second is the one that matters.

First, `lab.ordered` is derived from `exists: {resource: service_request}`
with no discriminator, so a referral written that way would send the
patient to the laboratory bench. That is the same trap `phc.op.handover`
documents: it wrote `notes`, and `consult.documented` is derived from
`notes`, so a nurse's handover closed the doctor's step.

Second, and this is the real argument: a `service_request` row belongs to
an encounter. A referral raised today and attended next month must be open
at every visit in between, and a row scoped to one visit is invisible at
the next. "A referral that stays open" is precisely a thing that outlives
the visit that raised it, which is the definition of an episode.

So a referral is an `episode_of_care` of type `referral`, exactly as a
pregnancy is one of type `pregnancy`. It is patient scoped, it opens and
closes by the same two row pattern, it appears on the same part of the
record, and a schedule can hang off it -- which is what turns "keep it
open" into "chase it on the seventh day" without a line of new machinery.

**What this does NOT do yet is publish.** A referral should reach ABDM as a
ServiceRequest with a Task pointing at it, which is FHIR's own pattern for
an ask and the chasing of it. `kernel/fhir.py` has no projection for
either, and inventing one here would be guessing at a profile. Named as
missing.

## Before you start

She is registered, and there is no referral already open. One at a time is
a simplification and it is a real limit: a woman referred for two different
things has to have the first closed before the second can be raised. The
count comparison that derives `referral.open` would handle several, but
nothing on screen could yet tell them apart, and an open referral nobody
can identify is worse than the limit.

`handover` is the capability, which six roles hold. Referring is not the
property of one desk.

## What happens

One `episode_of_care` row. Nothing moves in the line: she is still where
the line says she is, and this adds an obligation rather than a station.

## How you know it worked

The referral appears on her record as open, with where she was sent and
why, and it stays there at every visit until somebody closes it.

## When it goes wrong

- **She was referred by somebody else.** Record it anyway. The record of
  what this centre knows is more useful than a record of only what it did.
- **It was raised by mistake.** It is `correctable` while the visit is
  open; after that, close it as no longer needed, which says what happened
  rather than pretending it did not.
