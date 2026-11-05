---
id: phc.op.postnatal-close-high-risk
type: operation
kind: write
short: End postnatal
title: Close postnatal care for a high-risk mother
summary: Postnatal care is over, and every home visit and the day 45 check still owed stop.
capability: episode.manage
scope_qualifier: null
station: nurse
irreversibility: correctable
instrument: form
preconditions:
  - postnatal.open
  - postnatal_high_risk.open
input: phc.schema.postnatal-close-v1
writes: [episode_of_care]
mapping:
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: postnatal}
        status: {const: ended}
        outcome: {answer: outcome}
    # The high-risk tail ends in the same commit, as the high-risk pregnancy
    # ends with the pregnancy. Without this row a mother who has died would go
    # on owing the day 45 check to the ANM.
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: postnatal_high_risk}
        status: {const: ended}
        outcome: {answer: outcome}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.postnatal-close, phc.op.delivery-record-high-risk, phc.op.postnatal-outcome]
  concepts: []
---

## In plain words

Her postnatal care is finished, or it is not going to happen, and this says
so. It ends her seven home visits and her day 45 check together, so nobody
is sent to a house for a mother who has moved away, cannot be reached, or
has died.

## Why this is not `phc.op.postnatal-close`

A high-risk mother has two postnatal episodes, and a form cannot choose
between one row and two. The ordinary form is offered only when no high-risk
tail is open, because ending only the home visits would leave the day 45
check owed to a woman who may have died. This one is offered only when the
tail is open. Between them, no way of ending postnatal care leaves one
episode running.

The day 45 form (`phc.op.postnatal-outcome`) does not offer "mother died" or
"not found" for the same reason: it ends only the tail, and the home visits
would go on being owed. Those answers are recorded here.

## Before you start

Both kinds of postnatal care must be open for her, which they are from a
high-risk delivery until one of them is closed. You need `episode.manage`.

## What happens

Two rows in one commit, and the chasing stops, because it was derived from the
episodes and nothing was written down. There is nothing to cancel.

Closing with "completed" before day 45 also ends the day 45 check, since it
ends both. The day 45 outcome is then not recorded. If that check should still
happen, record the outcome first with the day 45 form, then close the
home visits with the ordinary form.

## How you know it worked

The postnatal card says this is over and asks for nothing, and no day 45
check is listed.

## When it goes wrong

- **You closed it too early.** It is correctable while the visit is open:
  amend it, and both kinds of postnatal care read as open again, because open
  is worked out from the rows and no visit was ever stored.
- **She has died.** Record it here so nobody calls her house. This operation
  records only that postnatal care has ended, and a death is a fact this
  build has nowhere else to keep yet.
