---
id: phc.inst.consult-scribe
type: instrument
kind: scribe
title: Scribe
summary: Transcribes a recording into the station's template.
operations: [phc.op.patient-register, phc.op.vitals-record, phc.op.consult-document, phc.op.rx-prescribe, phc.op.household-visit]
requires: capture.consented
readback: required
commit: tap
fallback: form
---

## In plain words

Only where `capture.consented` is set on the thread, which is what `requires`
above declares: the renderer reads that field and does not start capture
without it. This paragraph used to be the only place the rule existed, and the
renderer hard-coded the flag to honour it -- which meant a bundle spelling its
consent flag differently got no gate at all. The scribe produces a Draft for the consult form and,
if it heard a prescription, a Draft for the prescription form. Each is shown
in editable fields and each is committed by the doctor separately.

Vitals are now on this list, which reverses the earlier rule. A number a
recording fills arrives with the words it came from beside it, and the form
will not commit until the person ticks each one (spec 2026-09-16 §10.4). The
misheard "one forty" is still the risk; the tick is where it is caught.
