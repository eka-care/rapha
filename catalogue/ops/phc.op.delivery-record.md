---
id: phc.op.delivery-record
type: operation
kind: write
short: Delivery
title: Record a delivery
summary: The pregnancy ends and postnatal care for the mother begins, in one act.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - pregnancy.open
irreversibility: correctable
input: phc.schema.delivery-record-v1
writes: [episode_of_care]
mapping:
  records:
    # TWO ROWS, AND THE ORDER OF THEM IS THE WHOLE POINT. The first ends the
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
        type: {const: postnatal}
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
  operations: [phc.op.pregnancy-close, phc.op.postnatal-close]
  concepts: []
---

## In plain words

She has had the baby. This records it, and in the same act it ends the
pregnancy and starts the postnatal care she is owed.

Both answers to the second question -- a live birth and a stillbirth -- open
postnatal care, because the mother needs the same checks either way. A
mother whose baby was stillborn is at the same risk of bleeding, infection
and depression as any other, and a product that stopped visiting her would
be making a judgement nobody asked it to make.

## Why this is not `phc.op.pregnancy-close`

Because the two have opposite consequences and one form offering both would
let a slip of the finger pick the wrong one.

Ending a pregnancy any other way -- a miscarriage, a termination, a woman
who moved away, a pregnancy that turned out not to be one -- opens nothing
and must open nothing. The whole architecture of the maternal half of this
product exists to make sure a woman who has just lost a baby is not chased
for anything, and an operation that could open a postnatal schedule after a
miscarriage would be the one path back to that. So it cannot: this operation
has no outcome that means a loss, and `phc.op.pregnancy-close` has no row
that opens anything.

## Before you start

A pregnancy must be open on this centre's books. You need `episode.manage`,
which an ANM, a community health officer and the medical officer hold.

## What happens

Two rows, in one commit. The pregnancy gains its ending row, so every
antenatal contact stops being owed the instant this lands. A postnatal
episode opens, dated from the delivery, so the home visits in
`bundles/phc/phc.sched.postnatal.md` begin to be owed from that date.

A delivery recorded late is normal rather than exceptional: a woman delivers
at the district hospital and comes home on the third day. The visits are
counted from the delivery and not from the record of it, so the first one
shows as already missed, which is the truth and is what somebody should see.

## How you know it worked

The pregnancy card on her record stops asking for anything and a postnatal
card appears in its place, with the first home visits already due.

## When it goes wrong

- **The date is wrong.** It is correctable. Recording it again moves the
  whole arc, because nothing was written down: there are no visit rows to
  regenerate and none to orphan.
- **She lost the baby.** This is not the form. Use End pregnancy, which
  records how it ended and opens nothing.
- **The baby needs a record of its own.** It does not have one. Whether and
  when a child becomes a patient here is an open decision for this facility's
  owner, recorded in the maternal and child health design note, and nothing
  in this operation presumes an answer. What is built today is the mother's
  half: her care, on her record.
