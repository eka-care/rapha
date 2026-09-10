---
id: phc.op.abha-link
type: operation
kind: write
title: Create or link an ABHA for this patient
summary: >
  Connect this patient's record to their national health account so their
  records can be found elsewhere later.
capability: abha.link
scope_qualifier: null
station: reception
instrument: form
preconditions:
  - registered
  - not abha.linked
irreversibility: irreversible
input: phc.schema.abha-link-v1
writes: [patient]
emits: [abha.linked]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.patient-register]
  concepts: []
---

## In plain words

An ABHA is the patient's national health number. Linking one to their record
here is how a hospital in another district finds their history later.

## Before you start

The patient must be registered. Registration comes first and is never blocked
by this: a patient with no ABHA is registered, given a token, and seen.
Addendum SSB.3 makes register now and link later a first class path, and the
gap becomes a worklist item rather than a queue blocker at the counter.

You need `abha.link`. The patient must consent and must be present, because
the journey involves one time passwords sent to them.

## What happens

The clerk offers the ABHA journey. It is skippable. If the patient declines or
has no time, the record is flagged ABHA pending and joins the unlinked
worklist, which whoever is free picks up at the next contact.

If the patient proceeds, the connector runs the create or link journey and the
returned identifier is written to the patient record.

## How you know it worked

The patient record carries an ABHA number and the thread stops showing the
link action. The unlinked worklist no longer lists this patient.

## When it goes wrong

- **This operation is irreversible.** A duplicate ABHA cannot be undone, only
  deprecated. The confirm is explicit and un-prefilled, per v0.1 SS5, and it
  cannot be satisfied by an agent. There is no `confirm` verb on the machine
  surface for this or any other write.
- **The patient may already have one.** Search before creating. Most footfall
  at an outpatient department is repeat patients, and defaulting to create is
  how duplicate records get manufactured.
- **The one time password fails at the counter.** Skip it. Flag ABHA pending
  and move the queue. Do not retry while twenty people wait.
