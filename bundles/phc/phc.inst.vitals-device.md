---
id: phc.inst.vitals-device
type: instrument
kind: device
title: Read from a connected monitor
summary: A paired BP cuff or pulse oximeter fills the field. The nurse still commits.
operations: [phc.op.vitals-record]
fields: [systolic, diastolic, pulse, spo2]
readback: required
commit: tap
fallback: keypad
---

## In plain words

Where a paired device exists it fills the field. Device readings are shown
and committed the same way as spoken ones: a wrong cuff size produces a wrong
number just as quietly as a misheard one.
