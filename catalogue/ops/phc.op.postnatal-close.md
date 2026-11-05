---
id: phc.op.postnatal-close
type: operation
kind: write
short: End postnatal
title: Close postnatal care
summary: Postnatal care is over, and every home visit still owed stops.
capability: episode.manage
scope_qualifier: null
station: nurse
irreversibility: correctable
instrument: form
preconditions:
  - postnatal.open
  - not postnatal_high_risk.open
input: phc.schema.postnatal-close-v1
writes: [episode_of_care]
mapping:
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: postnatal}
        # The second row, exactly as a pregnancy gains one. Every clinical
        # table here is insert only, so an episode ends by being added to and
        # never by being rewritten, and the audit keeps both halves.
        status: {const: ended}
        outcome: {answer: outcome}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.delivery-record, phc.op.postnatal-close-high-risk]
  concepts: []
---

## In plain words

Her postnatal care is finished, or it is not going to happen, and this says
so. The home visits still owed stop the moment it lands.

## Why it exists when the schedule runs out anyway

The last home visit is six weeks after the delivery, so an episode nobody
closes stops asking for anything by itself. This is not for that case. It is
for the three where six weeks is too long to go on asking: she has moved
away, nobody can reach her, or she has died.

Leaving an episode open in any of those is the same failure the pregnancy
half is built to prevent, in a smaller size. A visit shown as owed to a woman
who is not there is work somebody will do and find nothing, and a visit shown
as owed to a woman who has died is worse than that.

## Before you start

Postnatal care must be open for her, and she must not be a high-risk mother
with her day 45 check still open. You need `episode.manage`.

## What happens

One row, and the chasing stops, because the chasing was derived from the
episode rather than written down. There is nothing to cancel.

## How you know it worked

The postnatal card says this is over and asks for nothing.

## When it goes wrong

- **You closed it too early.** It is correctable: record the delivery again
  and the arc comes back where it was, since no visit was ever stored.
- **She is a high-risk mother.** This form is not offered to her, because it
  would end her home visits and leave her day 45 check owed. Use
  Close postnatal care for a high-risk mother, which ends both.
- **She has died.** Record it here so nobody calls her house. This operation
  records only that postnatal care has ended, and a death is a fact this
  build has nowhere else to keep yet.
