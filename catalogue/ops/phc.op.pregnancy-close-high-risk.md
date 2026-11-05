---
id: phc.op.pregnancy-close-high-risk
type: operation
kind: write
short: End pregnancy
title: Close a high-risk pregnancy record
summary: Record how the pregnancy ended, and stop both the ordinary and the extra visits.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - pregnancy_high_risk.open
irreversibility: correctable
input: phc.schema.pregnancy-close-v1
writes: [episode_of_care]
mapping:
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy}
        # The SECOND row. An episode ends by gaining one rather than by
        # having its first rewritten, because every clinical table here is
        # insert only and the audit has to keep both halves. `pregnancy.open`
        # is the count comparison between the two.
        status: {const: ended}
        outcome: {answer: outcome}
    # The high-risk episode ends in the same commit. Without this row a woman
    # who had lost her baby would go on owing three extra doctor visits.
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy_high_risk}
        status: {const: ended}
        outcome: {answer: outcome}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.pregnancy-close, phc.op.risk-mark]
  concepts: []
---

## In plain words

The pregnancy of a woman marked high risk is over without a birth. This
ends the pregnancy and the extra visits together, and opens nothing.

## Why this is not `phc.op.pregnancy-close`

A form cannot choose between two sets of records, so the choice is made by
state. The ordinary form is offered only when no high-risk episode is open.
This one is offered only when one is. Between them, no way of ending a
pregnancy leaves the extra visits running.

## Before you start

A high-risk pregnancy is open for her. If she has none, this form is not
offered to her, and she is given End pregnancy for an ordinary woman instead
(`phc.op.pregnancy-close`). A form cannot choose between one ending row and
two, so the choice is made by state: this one ends both episodes, and using
it for an ordinary woman would have nothing to end on the second. You need
`episode.manage`.

## What happens

Two rows in one commit: the pregnancy ends and the high-risk episode ends.
Both stop being owed on the next read, because contacts are derived.

It opens no postnatal care of either kind. A pregnancy that ended without a
birth is not followed by home visits, and that absence is deliberate. This
holds for every answer on the form, including that the woman has died: a
death in pregnancy ends both episodes and opens nothing.

## How you know it worked

Both the pregnancy and the extra visits read as closed, and nothing is due.

## When it goes wrong

- **A birth was recorded here by mistake.** Correct it, then use
  Record a delivery for a high-risk pregnancy.
