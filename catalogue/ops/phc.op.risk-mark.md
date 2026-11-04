---
id: phc.op.risk-mark
type: operation
kind: write
short: Mark high risk
title: Mark a pregnancy high risk
summary: Record the risk factor found, and open the three extra check-ups it earns.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - pregnancy.open
  - not pregnancy_high_risk.open
irreversibility: correctable
input: phc.schema.risk-mark-v1
writes: [episode_of_care]
mapping:
  # The risk factor is the point of the form but has no column on the
  # episode row; it travels on the audit line, as abha-link's method does.
  ignored: [risk_factor]
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy_high_risk}
        status: {const: active}
        anchor_date: {answer: marked_date}
        anchor_basis: {const: marked}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.pregnancy-open, phc.op.antenatal-visit]
  concepts: []
---

## In plain words

A woman's pregnancy is judged high risk. This records the risk factor
found and the date, and from that day she is owed three extra check-ups
with a doctor, over and above her ordinary four.

## Before you start

She has an open pregnancy and has not already been marked. A second mark
is refused. You hold `episode.manage`. The ASHA reports what she finds and
the centre decides, so she cannot mark; the nurse and the medical officer
can. The operation is offered at the nurse's bench only, whoever decides:
the build refuses an operation drawn at a station other than its own.
The medical officer holds the capability but marks her at that bench.
The design says he may mark her; that needs the owner's correction.

## What happens

One `episode_of_care` row of type `pregnancy_high_risk`. Nothing else is
stored: the three visits are worked out when someone asks. The system
never infers risk. A clinician names the factor, and that is recorded.

## How you know it worked

The pregnancy shows as high risk, and three extra check-ups appear for the
doctor.

## When it goes wrong

- **The date or factor was wrong.** While this same visit is still open,
  amend it and the three extra check-ups move with the date, because they
  are worked out when asked. After the visit closes, no correction path has
  been built for this operation. NEEDS DECISION from the owner.
- **She cannot be unmarked.** There is no operation for it, by decision.

## Verification

Unverified against CARE.
