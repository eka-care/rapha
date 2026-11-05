---
id: phc.op.antenatal-visit-high-risk
type: operation
kind: write
short: Extra visit
title: Extra antenatal visit for a high-risk pregnancy
summary: One of the three extra doctor visits a high-risk pregnancy is owed, recorded as narrative.
capability: encounter.document
scope_qualifier: null
station: doctor
instrument: scribe
preconditions:
  - registered
  - pregnancy_high_risk.open
irreversibility: correctable
input: phc.schema.antenatal-visit-v1
writes: [encounter, notes]
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
emits: [consult.documented]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.antenatal-visit, phc.op.risk-mark, phc.op.consult-document]
  concepts: []
---

## In plain words

The doctor's visit for a woman marked high risk, one of the three extra ones
over and above her ordinary four. It asks the same four things the ordinary
antenatal visit asks, on the same form, and it travels as narrative text in
the same way.

## Why this is not `phc.op.antenatal-visit`

Because a recorded visit closes the contact belonging to the operation that
was committed. When both schedules named the ordinary visit, one recorded
visit closed an ordinary contact and an extra one at the same time. She was
then owed fewer visits than the programme requires, and an ANM's visit
discharged the medical officer's. With two operations, one visit closes one
contact.

The form is shared, not copied: `phc.schema.antenatal-visit-v1` names both
operations, so a change to a question is made once.

## Before you start

She is registered and has a high-risk pregnancy open. You need
`encounter.document`. It is offered at the doctor's bench, where the medical
officer works, because the programme requires a doctor for these visits.

A high-risk woman still owes her ordinary four, and those are recorded with
the ordinary antenatal visit. Her doctor sees both choices, so this one is
labelled Extra visit.

## What happens

The same as the ordinary antenatal visit: an encounter and a note. The visit
closes the earliest extra contact whose window contains the day it is
committed, as described in `bundles/phc/phc.sched.antenatal-high-risk.md`.
It closes no ordinary contact.

## How you know it worked

One of her three extra check-ups reads as done, and her ordinary four are
exactly as they were.

## When it goes wrong

- **It was recorded on the wrong one.** If this should have been an ordinary
  visit, record it again with the ordinary antenatal visit. Neither form
  discharges the other's contact.
- **Her pregnancy has ended.** This is no longer offered, because her extra
  visits ended with it.
