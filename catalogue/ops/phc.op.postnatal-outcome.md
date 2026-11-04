---
id: phc.op.postnatal-outcome
type: operation
kind: write
short: Day 45 check
title: Record the day 45 outcome
summary: Record how mother and baby are at day 45 after a high-risk delivery, which ends this check.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - postnatal_high_risk.open
irreversibility: correctable
input: phc.schema.postnatal-outcome-v1
writes: [episode_of_care]
mapping:
  # What was found and whether it needs following up have no column on the
  # episode row; they travel on the audit line, as the risk mark's factor does.
  ignored: [narrative, followup_needed]
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: postnatal_high_risk}
        # The second row, exactly as every other episode ends. Whatever the
        # outcome, the episode ends: a poor outcome is a finding to act on,
        # not a reason to go on chasing the same check.
        status: {const: ended}
        outcome: {answer: outcome}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.delivery-record-high-risk, phc.op.postnatal-visit]
  concepts: []
---

## In plain words

The ANM's check at day 45 after a high-risk delivery. It says how the mother
and baby are, and it ends the high-risk tail of her care.

## Before you start

High-risk postnatal care must be open for her, which happens when somebody
records a high-risk delivery. You need `episode.manage`. It is offered at the
nurse's bench, as the risk mark is.

## What happens

One row ends the high-risk postnatal episode, with the outcome as its result.
The unsatisfactory outcomes end it too. The check was done and a finding is a
finding; keeping the check open would only chase the same person again.
Her seven home visits are a different episode and are not affected.

## How you know it worked

The postnatal card no longer lists a day 45 check.

## When it goes wrong

- **She could not be found.** Record that. It ends the check and says why.
- **Something is wrong with the mother or baby.** Record how things are and
  tick the follow-up question. This form does not arrange the care.

## NEEDS SIGN-OFF

The answer list, and the choice to end the episode on every answer, are this
bundle's. A named clinical officer has to confirm them.
