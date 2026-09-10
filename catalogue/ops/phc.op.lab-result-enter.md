---
id: phc.op.lab-result-enter
type: operation
kind: write
title: Enter a laboratory result
summary: >
  Record the value a bench test produced, against the investigation a doctor
  ordered for this patient.
capability: lab.result.enter
scope_qualifier: null
station: lab
instrument: form
preconditions:
  - lab.ordered
  - not lab.resulted
irreversibility: correctable
input: phc.schema.lab-result-v1
writes: [diagnostic_report, specimen]
emits: [lab.resulted, lab.critical]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.lab-order]
  concepts: []
---

## In plain words

The lab technician types in what the test measured. This is a number, and a
number entered wrongly here is acted on at district review months later
without anybody noticing it was ever wrong.

## Before you start

An investigation must have been ordered for this patient. You need
`lab.result.enter`.

Entering a result is not the same as releasing it. Releasing requires
`lab.result.validate`, which a lab technician does not hold and a medical
officer does not hold either.

## What happens

The technician enters a value per analyte on a form with a range check on each
field. This is deliberately not dictation. Addendum SSA gives the reason:
unedited speech recognition runs about a 7.4 percent error rate with deletions
and insertions dominating, and a short numeric utterance has no redundancy to
recover from, so "one forty" heard as "one fourteen" is silent, plausible and
permanent.

A value inside the physiological range commits and emits `lab.resulted`. A
value outside it blocks the commit and requires an explicit override carrying
a reason, which is stored with the result. A value past the critical threshold
also emits `lab.critical`, which promotes a review action onto the ordering
doctor's thread.

## How you know it worked

The result appears on the patient thread and on the ordering doctor's pending
list. A critical value additionally raises a flagged action on the doctor's
surface rather than waiting to be noticed.

## When it goes wrong

- **The value is genuinely outside the range.** Override with the reason. The
  override is recorded and reviewable. Do not round the value into range.
- **The analyser produced the number.** Prefer the analyser feed or the LIS
  import. Re-keying a result that is already digital upstream adds an error
  source for no gain.
- **Wrong patient.** Do not overwrite. A result on the wrong patient is
  corrected by amendment, which retains the original value, per addendum SSC.
