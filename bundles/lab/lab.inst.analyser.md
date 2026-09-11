---
id: lab.inst.analyser
type: instrument
kind: device
title: Read from the analyser
summary: The analyser fills the analyte fields.
operations: [lab.op.result-enter]
fields: [haemoglobin, wbc, platelets, glucose, creatinine, sodium, potassium]
readback: required
commit: tap
fallback: keypad
---

## In plain words

Where an analyser interface exists it fills the fields. The values are shown
back and committed by a tap through the same validator as typing, so a
mislabelled tube produces a wrong number that a person still has to accept.
