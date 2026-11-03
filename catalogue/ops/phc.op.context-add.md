---
id: phc.op.context-add
type: operation
kind: write
short: Background
title: Add background from elsewhere
summary: A letter, a result or a discharge note another facility wrote, copied in as given.
capability: context.record
scope_qualifier: null
station: nurse
instrument: form
presents: artifact
preconditions:
  - registered
irreversibility: correctable
input: phc.schema.context-v1
writes: [questionnaire_response]
mapping:
  records:
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.context-v1}
        payload: {json: payload}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.handover, phc.op.consult-document]
  concepts: []
---

## In plain words

A patient arrives holding paper. A discharge summary from the district
hospital, a scan report from a private laboratory, an old prescription from a
camp. None of it is ours and none of it is in our records, so today it is read
once at the desk and then it goes home in the same bag it came in.

This copies it in before the consultation starts, so the person writing the
note has already read it.

## It is a copy, and it says so

Every answer here is somebody else's statement. `source` is who wrote it,
`dated` is the date the paper carries, and `body` is what it says, as given.
That is the whole shape, and the shape is the safety: there is no field for
our interpretation of it, because the moment a clinician summarises a letter
into one of our own findings, the record stops being able to tell the two
apart.

Nothing here is a finding of this facility. It writes no observation, no
condition and no note. A blood pressure in a letter from 2019 does not become
a reading we took, and a diagnosis written by somebody else does not become a
diagnosis we confirmed. If the doctor agrees with it, they say so in their own
consultation, under their own name, and that is a separate row.

## Before you start

The visit is registered. Nothing else: paper arrives before anything has been
done, which is the point.

You hold `context.record`. The front desk, the nurse and the medical officer
hold it, because all three meet the paper. The community roles do not yet; a
facility that wants an ASHA to carry a letter in grants it in the role editor,
which is one switch and not a code change.

## What happens

One `questionnaire_response` row, signed with who copied it in and when, and
the visit carries it from then on.

`questionnaire_response` for the same reason the handover uses it: it carries
a `questionnaire` discriminator, it drives no state rule of this bundle, and
so copying in a letter cannot close a step of the line. A letter mentioning a
blood pressure must not mark vitals as recorded, and if this wrote
`observation` it would.

## Where it stands

`station: nurse` is where this SORTS, not where it is allowed.
kernel/state.actions() filters on drawn_by, capability and preconditions and
never on the caller's station, so it is reachable from the front desk, from
the nurse's bench and from the consulting room. Paper does not arrive at one
place.

## Why there is no date control

`dated` is a string, because this kernel's questionnaires have no date type
and the form falls through to a plain box. A string is honest about that: a
field that looks like a date picker and stores whatever was typed is worse.
The question says to leave it empty rather than guess, because an invented
date on somebody else's document is a fabricated fact.

## What it cannot do

It emits no flag and writes no resource any `done_when` reads, so the line
does not move. It cannot be dictated: `instrument: form`, because this is
paper being copied, not speech being heard, and a scribe guessing at a
discharge summary is the exact failure this operation exists to avoid.

It is `correctable`, not reversible: a letter copied in wrongly is corrected
in place and the correction is signed, the same as every other row here.

## How you know it worked

The background appears on the visit, with who copied it in and when, and it is
there for the consultation that follows. No step closes and the patient does
not move.

## When it goes wrong

An empty source or an empty body is refused by the validator before anything
is written. A caller without `context.record` is refused at guard step 2 and
never sees the row offered. An agent may propose one and may not commit one,
like every other write here.

## Verification

Unverified against CARE. It writes the same `questionnaire_response` resource
the handover and the laboratory's release already write, and adds no field
neither of them has.
