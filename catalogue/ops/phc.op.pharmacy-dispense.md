---
id: phc.op.pharmacy-dispense
type: operation
kind: write
short: Dispense
title: Dispense a prescription
summary: Record what was handed over, and drop stock by that much.
capability: pharmacy.dispense
scope_qualifier: null
station: pharmacy
instrument: form
preconditions:
  - rx.confirmed
  - not dispensed.complete
irreversibility: correctable
input: phc.schema.dispense-v1
writes: [medication_dispense, inventory_item]
mapping:
  # The batch is read back to the person at the counter and not stored: no
  # resource here has a column for it. Saying so is the point of this list.
  ignored: [batch, partial]
  records:
    - resource: medication_dispense
      per_item: dispenses
      fields:
        created_by: {actor: id}
        medication: {item: [medication, drug, code]}
        quantity: {item: [quantity, qty]}
        status: {const: completed}
    - resource: inventory_item
      per_item: dispenses
      fields:
        created_by: {actor: id}
        code: {item: [medication, drug, code]}
        quantity: {minus: [quantity, qty]}
        status: {const: issued}
emits: [dispensed.partial, dispensed.complete]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.rx-prescribe]
  concepts: []
---

## In plain words

The pharmacist hands over medicine and records it. What gets recorded is what
the patient was actually given, which is not always what the doctor wrote.
Stockouts at a primary health centre are routine, so a partial dispense is a
normal outcome and not an error.

## Before you start

A prescription must exist and be confirmed for this encounter. Until it is,
this operation does not appear on the pharmacist's screen at all. It is not
shown greyed out and it is not shown with an error on tap. Addendum SSD.1 is
explicit that no action appears before its precondition, and hiding it is the
behaviour, not a nicety.

You need `pharmacy.dispense`. A medical officer does not hold it.

## What happens

The pharmacist opens the confirmed prescription, enters the quantity handed
over per line and the batch, and confirms. Each line writes a
`medication_dispense` against the prescription it came from, and decrements
the matching `inventory_item` in the same transaction so stock cannot drift
from what was handed out.

If every line is dispensed in full, the operation emits `dispensed.complete`.
If any line is short, it emits `dispensed.partial` and the thread keeps the
operation available so the rest can be given when stock arrives.

## How you know it worked

The patient thread moves to dispensed, the facility stock figure for each
product drops by the quantity entered, and the prescribing medical officer
sees the dispensed quantity against their prescription. For a partial
dispense, the outstanding quantity stays visible on the thread rather than
disappearing.

## When it goes wrong

- **Stock is lower than the quantity entered.** The commit is blocked. Enter
  what was actually handed over. Do not adjust the number to match the
  prescription.
- **The prescription was changed after the patient reached the counter.** The
  thread carries the current prescription. Re-open it rather than dispensing
  from a printed copy.
- **A substitution is needed.** That is a separate operation bounded by an
  approved generic-equivalence list, and it notifies the prescriber. Dispensing
  a different drug through this operation is not possible and should not be
  worked around by editing the prescription.
