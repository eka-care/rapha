---
id: phc.op.delivery-record-high-risk
type: operation
kind: write
short: Delivery
title: Record a delivery for a high-risk pregnancy
summary: The pregnancy and its extra visits end and the longer postnatal care begins, in one act.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - pregnancy_high_risk.open
irreversibility: correctable
input: phc.schema.delivery-record-v1
writes: [episode_of_care]
mapping:
  records:
    # THREE ROWS, AND THE ORDER OF THEM IS THE WHOLE POINT. The first ends the
    # pregnancy, which stops every antenatal contact instantly, because a
    # contact is derived and there is nothing to cancel. The second opens
    # postnatal care, which starts the home visits owed to the mother. One
    # commit, so there is no window in which she is neither pregnant nor
    # postnatal and nobody owes her anything.
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy}
        status: {const: ended}
        outcome: {answer: outcome}
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy_high_risk}
        status: {const: ended}
        outcome: {answer: outcome}
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: postnatal_high_risk}
        status: {const: active}
        # Measured from the day she delivered and not from the day somebody
        # keyed this in. A woman discharged on the third day is recorded on
        # the third day, and the first home visit was due on the first.
        anchor_date: {answer: delivery_date}
        anchor_basis: {const: delivery}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.delivery-record, phc.op.pregnancy-close-high-risk]
  concepts: []
---

## In plain words

She is a high-risk woman and she has delivered. This records it, and in the
same act it ends the pregnancy, ends the extra doctor visits, and starts the
postnatal care she is owed, which runs to day 45 rather than day 42.

## Why this is not `phc.op.delivery-record`

A form cannot choose between two sets of records, so the choice is made by
state. That form is offered only to a woman with no high-risk episode open.
This one is offered only to a woman who has one. Between them every
delivery ends the high-risk episode when there is one.

## Before you start

A high-risk pregnancy is open for her. You need `episode.manage`.

## What happens

THREE rows, in one commit: the pregnancy ends, the high-risk episode ends,
and `postnatal_high_risk` opens, dated from the delivery. They are written
together because a gap between them would be an instant in which nothing is
owed to her. Ending the high-risk episode is what stops her three extra
visits; nothing is cancelled, because they are derived.

The tail is `bundles/phc/phc.sched.postnatal-high-risk.md`.

## How you know it worked

Her pregnancy and the extra visits read as closed, and a postnatal card
appears with the first home visits due.

## When it goes wrong

- **The date is wrong.** Correctable. Record it again.
- **She lost the baby.** Not this form. Use End pregnancy (high risk), which
  ends both episodes and opens nothing.
