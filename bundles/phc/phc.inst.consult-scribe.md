---
id: phc.inst.consult-scribe
type: instrument
kind: scribe
title: Scribe
summary: Transcribes a recording into the station's template.
operations: [phc.op.patient-register, phc.op.vitals-record, phc.op.consult-document,
             phc.op.ncd-review, phc.op.antenatal-visit, phc.op.followup,
             phc.op.rx-prescribe, phc.op.household-visit]
readback: required
commit: tap
fallback: form
---

## In plain words

THIS INSTRUMENT NO LONGER DECLARES A GATE. It carried `requires:
capture.consented`, and a recording was refused on any visit that did not
hold that flag. The owner removed the consent mechanism in full on 4
November 2026 and the `requires` line went with it: there is no flag left to
require.

The `requires` key itself still exists and still works, for any bundle that
wants an instrument gated on a state. What is gone is this bundle's use of
it. The scribe produces a Draft for the consult form and,
if it heard a prescription, a Draft for the prescription form. Each is shown
in editable fields and each is committed by the doctor separately.

Vitals are now on this list, which reverses the earlier rule. A number a
recording fills arrives with the words it came from beside it, and the form
will not commit until the person ticks each one (spec 2026-09-16 §10.4). The
misheard "one forty" is still the risk; the tick is where it is caught.
