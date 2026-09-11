---
id: phc.inst.consult-scribe
type: instrument
kind: scribe
title: Ambient scribe
summary: Transcribes the consultation into a draft note and prescription.
operations: [phc.op.consult-document, phc.op.rx-prescribe]
readback: required
commit: tap
fallback: form
---

## In plain words

Only where `capture.consented` is set on the thread; the renderer must not
start capture otherwise. The scribe produces a Draft for the consult form and,
if it heard a prescription, a Draft for the prescription form. Each is shown
in editable fields and each is committed by the doctor separately. The scribe
is never offered on the vitals operation, and this is why vitals is not in
its operations list: short numeric utterances are what ambient recognition
gets wrong.
