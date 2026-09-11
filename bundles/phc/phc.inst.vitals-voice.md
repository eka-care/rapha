---
id: phc.inst.vitals-voice
type: instrument
kind: constrained-voice
title: Speak a reading
summary: Say one number into one field.
operations: [phc.op.vitals-record]
fields: [systolic, diastolic, pulse, spo2, weight, temperature]
types: [integer, decimal]
grammar: number
readback: required
commit: tap
fallback: keypad
---

## In plain words

Hands are busy at the vitals station, so the nurse may say "one forty" into
the systolic field. That is all this does. The value appears in the field,
highlighted until the nurse looks at it, and nothing is recorded until the
nurse taps commit, at which point the range rule runs exactly as if the
number had been typed. "One fourteen" misheard for "one forty" is silent and
plausible, which is why the readback and the tap are not optional and the
linter refuses any other value for those two fields.
