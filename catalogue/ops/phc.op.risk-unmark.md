---
id: phc.op.risk-unmark
type: operation
kind: write
short: Undo mark
title: Undo a high-risk mark made in error
summary: Take back a high-risk mark that was made on the wrong woman or with the wrong date, and stop the extra check-ups.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - pregnancy_high_risk.open
irreversibility: correctable
input: phc.schema.risk-unmark-v1
writes: [episode_of_care]
mapping:
  # Why the mark was wrong has no column on the episode row; it travels on
  # the audit line, as the risk factor does on the mark.
  ignored: [reason, note]
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy_high_risk}
        status: {const: ended}
        outcome: {const: marked_in_error}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.risk-mark, phc.op.antenatal-visit-high-risk]
  concepts: []
---

## In plain words

A high-risk mark was put on the wrong woman, or with the wrong date. This
takes it back. The three extra check-ups stop, and she goes on with her
ordinary pregnancy care exactly as before.

## Before you start

She has an open high-risk mark. You hold `episode.manage`, as for the mark,
and you do this at the same bench where the mark is made. A woman who was
never marked, or whose mark was already undone, cannot be unmarked.

## What happens

One `episode_of_care` row of type `pregnancy_high_risk` with status ended and
the outcome "marked in error". Nothing is deleted. The mark stays in her
record, and so does this, each with who did it and when. Her ordinary
pregnancy is not touched: no row for it is written. The extra check-ups were
never stored, so there is nothing to cancel. They are worked out when
someone asks, and an ended episode owes nothing.

## How you know it worked

Her pregnancy no longer shows as high risk, and the three extra check-ups
are gone from the doctor's list. Her four ordinary check-ups are unchanged.

## This is not a clinical reversal

The reasons are about the record being wrong, not about the woman getting
better. Whether a woman whose anaemia has been treated, or whose fever has
gone, should stop receiving high-risk care is a separate question the owner
has not answered. The programme treats the category as sticky for the
pregnancy. NEEDS DECISION from the owner. Do not add a reason such as
"risk resolved" before it is answered.

## If the date was wrong

Undo the mark, then mark her again with the right date. The three extra
check-ups are then counted from the new date, and the old mark owes nothing.

## When it goes wrong

- **She is marked, undone and marked again within one second.** Episodes of
  one type are paired with their endings in time order, to the second. All
  three inside a single second could pair the undo with the wrong mark. A
  nurse cannot do this by hand; a script could.

## Verification

Unverified against CARE.
