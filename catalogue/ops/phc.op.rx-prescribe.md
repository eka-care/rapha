---
id: phc.op.rx-prescribe
type: operation
kind: write
short: Rx
title: Write a prescription
summary: Prescribe medicines for this patient, with what the pharmacy actually has in view.
capability: rx.prescribe
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - consult.documented
  - not rx.confirmed
irreversibility: correctable
input: phc.schema.rx-v1
writes: [medication_request]
emits: [rx.confirmed]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.pharmacy-dispense, phc.op.consult-document]
  concepts: []
---

## In plain words

The doctor prescribes. Confirming the prescription is what makes the
pharmacist's dispense action exist at all.

## Before you start

A consultation must be documented. You need `rx.prescribe`.

For a community health officer this capability is bounded to an approved
formulary and protocol set. That bound is a qualifier on the capability rather
than a separate capability, so there is one thing for the guard to evaluate.
It is declared and not yet enforced, and it needs a named clinical signatory
before it is.

## What happens

The doctor selects drugs, doses and durations on a form. Scribe output from
the consultation can pre fill it as a draft, which is edited and confirmed
like any other proposal.

Current facility stock is shown at the point of prescribing. An out of stock
drug should be visible to the person choosing it, not discovered by the
patient at the counter. This is the cheapest useful signal in the whole design
and it only works because dispense events feed stock.

## How you know it worked

The prescription is on the thread and the pharmacist's dispense action, which
did not exist a moment ago, appears on their surface.

## When it goes wrong

- **The drug is out of stock.** It is marked at the point of prescribing.
  Choose an alternative then, or accept that the dispense will be partial.
- **An allergy is recorded.** The allergy is on the thread. Read it. Nothing
  here decides for the prescriber.
- **The patient is already on something interacting.** Current medications are
  on the thread for the same reason.
