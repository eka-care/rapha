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
The medical officer holds the capability and marks her at that bench too.
The design first said he could not, and was corrected while this was built.

## What happens

One `episode_of_care` row of type `pregnancy_high_risk`. Nothing else is
stored: the three visits are worked out when someone asks. The system
never infers risk. A clinician names the factor, and that is recorded.

## How you know it worked

The pregnancy shows as high risk, and three extra check-ups appear for the
doctor.

## NEEDS SIGN-OFF: the list of risk factors

The 23 factors in the form are the programme's categories as this build
transcribed them. Nobody clinical has checked the transcription. If one is
miscopied or missing, a nurse may be unable to name the real reason, pick
"other", or record the wrong one, and the audit line then carries a wrong
clinical assertion. The extra check-ups do not depend on which is chosen.

## When it goes wrong

- **The date or factor was wrong, in the same visit.** While this same visit
  is still open, amend it and the three extra check-ups move with the date,
  because they are worked out when asked.
- **The mark was a mistake, after the visit closed.** The wrong patient or
  the wrong date: use `phc.op.risk-unmark`, which ends the high-risk episode
  with the outcome "marked in error" and stops the three extra check-ups.
  Then mark her again with the right date if she is high risk. Both the
  mark and the undo stay in her record.
- **She has got better.** Not covered, on purpose. The undo is for a wrong
  record, not a clinical change of mind. Whether a woman whose anaemia has
  been treated should stop receiving high-risk care is still an open
  question for the owner and clinical staff.

## Verification

Unverified against CARE.
