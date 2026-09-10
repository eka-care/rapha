---
id: phc.op.household-visit
type: operation
kind: write
short: Scribe visit
title: Record a household visit
summary: >
  A frontline worker records what happened at a visit to someone's home, and
  anything that needs following up.
capability: visit.household
scope_qualifier: null
station: community
instrument: scribe
preconditions:
  - registered
irreversibility: correctable
input: phc.schema.household-visit-v1
writes: [encounter, questionnaire_response]
emits: [consult.documented]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.patient-register]
  concepts: []
---

## In plain words

An accredited social health activist or auxiliary nurse midwife visits a
household and records the visit. This is the community half of the system and
the half that CARE was not built for, so it is ours to design.

## Before you start

The person visited must be registered, which the frontline worker can do at
the door. You need `visit.household`.

A household visit takes its own consent at the door. The facility's visit
scoped consent does not travel to someone's home.

## What happens

The conversation is narrative, so scribe fits. Assessment items are a form,
and assessment scoring is computed by rule and never by the model. The agent
may prompt the next question and transcribe the answer. It does not decide the
score and it does not decide the referral threshold.

Any guidance shown comes from the approved content library with a visible
source.

## How you know it worked

The visit is on the patient's thread and is attributed to the worker who made
it. Anything needing follow up appears as an action rather than as a note
somebody has to read.

## When it goes wrong

- **No network at the door.** In this phase the surface is online only.
  Offline first capture is a later phase and is not promised here.
- **The household declines.** Record the visit, not the conversation.
- **The assessment suggests a referral.** The threshold comes from the
  instrument, which carries a version and a named clinical owner. A stale
  instrument in the field is a compliance failure, not a minor drift.
