---
id: phc.op.postnatal-visit
type: operation
kind: write
short: PNC visit
title: Record a postnatal home visit
summary: Somebody went to the house in the six weeks after she delivered.
capability: visit.household
scope_qualifier: null
station: community
instrument: form
preconditions:
  - registered
  - postnatal.open
irreversibility: correctable
input: phc.schema.postnatal-visit-v1
writes: [encounter, questionnaire_response]
mapping:
  records:
    - resource: encounter
      fields:
        created_by: {actor: id}
        status: {const: in_progress}
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.postnatal-visit-v1}
        payload: {json: payload}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.delivery-record, phc.op.household-visit]
  concepts: []
---

## In plain words

Somebody went to the house. This is what says so, and it is what closes one
of the seven contacts in `bundles/phc/phc.sched.postnatal.md`.

Nobody at home is an answer. A visit that was made and found an empty house
is not the same as a visit nobody made, and a schedule that cannot tell them
apart sends the same person back tomorrow and blames her for the gap.

## Why it is not `phc.op.household-visit`

The household visit is the general one: a routine round, an immunisation
call, a tuberculosis follow up. It records what kind of visit it was and
whether consent was given at the door, and it stands at the same station.

THE REASON THEY ARE TWO IS A FINDING RATHER THAN A PREFERENCE. The
household visit is declared, loaded, listed by the scribe instrument, and
drawn by no step of the outpatient line, so the guard refuses every attempt
at it with "no station in this line draws it". It cannot be performed by
anybody today. That is a real gap and it is somebody's decision to close,
because closing it means either a line of its own for outreach work or
putting a household round inside a clinic queue where it does not belong.

Rather than decide that here, this operation is narrow enough not to need
the decision: it applies only while postnatal care is open, so it cannot
land on an ordinary clinic visit, and it closes exactly the contacts the
postnatal schedule declares.

## Before you start

The patient must be registered and postnatal care must be open for her,
which happens when somebody records her delivery. You need
`visit.household`, which an ASHA and an ANM both hold.

## What happens

The visit is recorded against her, and the contact whose window today falls
in stops being owed. One visit closes one contact: the earliest open one
whose window contains the day it was committed.

## How you know it worked

The postnatal card on her record moves that contact to done, with the date,
and shows the next one.

## When it goes wrong

- **She has moved, or nobody can reach her.** Do not keep recording empty
  visits. Close postnatal care with End postnatal, which stops the rest.
- **The baby is the problem.** There is nowhere to put that yet. The baby
  has no record in this build, and whether a child becomes a patient here is
  an open decision for this facility's owner. What is found about the baby
  goes in the narrative and travels as text, which is the designed fallback
  and is honest about being one.
