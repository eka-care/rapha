---
id: phc.op.vitals-record
type: operation
kind: write
short: Vitals
title: Record vitals and triage
summary: >
  Measure and record blood pressure, oxygen saturation, weight and the other
  basic readings, and flag anything abnormal for the doctor.
capability: vitals.record
scope_qualifier: null
station: nurse
instrument: device
preconditions:
  - registered
  - not vitals.recorded
irreversibility: correctable
input: phc.schema.vitals-v1
writes: [observation]
emits: [vitals.recorded, vitals.flagged]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.consult-document]
  concepts: []
---

## In plain words

The nurse takes the patient's readings and records them. These are numbers,
and they travel: an abnormal blood pressure recorded here becomes a district
level statistic and a treatment decision.

## Before you start

The patient must be registered. You need `vitals.record`.

## What happens

Readings come from a connected device where the hardware exists, and from a
form with a range check per field where it does not. Constrained voice is
available as an accelerator when hands are busy. It accepts a bounded grammar,
shows the parsed value on screen, and requires a tap to commit. It is not
ambient scribe and it falls back to the numeric keypad.

Ambient scribe is not offered at this station at all. Addendum SSA sets out
why: short numeric utterances are exactly the payload speech recognition
handles worst, and a misheard vital has no redundancy to recover it.

A reading outside range raises `vitals.flagged`, which promotes a review
action onto the doctor's surface ahead of starting the consultation.

## How you know it worked

The readings appear on the patient thread and the doctor's next action becomes
review flagged vitals rather than start consultation, when anything was
flagged.

## When it goes wrong

- **The device will not pair.** Enter on the form. Do not dictate.
- **A reading looks implausible.** Re-check before committing. A re-check is
  cheaper than an amendment.
- **The doctor thinks the value is wrong later.** They raise an amendment,
  which routes to the nurse and retains the original value. They cannot
  silently overwrite it.
