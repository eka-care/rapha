---
id: phc.inst.consult-scribe
type: instrument
kind: scribe
title: Scribe
summary: Transcribes a recording into the station's template.
operations: [phc.op.patient-register, phc.op.vitals-record, phc.op.consult-document,
             phc.op.ncd-review, phc.op.antenatal-visit, phc.op.antenatal-visit-high-risk,
             phc.op.followup,
             phc.op.rx-prescribe, phc.op.household-visit]
# WHERE IN EKA'S STRUCTURED NOTE EACH ANSWER LIVES. The service writes a
# note section by section, and these name the section and how to take the
# value from it; api/structured.py is the only reader. A form with no entry is
# filled from the markdown note, as before. The evidence for each value is
# looked for in the transcript by the reader, and a value with none is dropped.
reads_from: Default Prescription Print
reads:
  phc.op.vitals-record:
    systolic:    {section: vital_signs, where: {vital_name: Blood Pressure}, take: value, split: ["/", 0]}
    diastolic:   {section: vital_signs, where: {vital_name: Blood Pressure}, take: value, split: ["/", 1]}
    pulse:       {section: vital_signs, where: {vital_name: Pulse}, take: value}
    spo2:        {section: vital_signs, where: {vital_name: SpO2}, take: value}
    weight:      {section: vital_signs, where: {vital_name: Weight}, take: value}
    temperature: {section: vital_signs, where: {vital_name: Temperature}, take: value}
  phc.op.consult-document:
    history:     {section: history_of_present_illness, join: "; "}
    examination: {section: physical_examination, format: "{finding}: {detail}", join: "; "}
    plan:        {section: advice, join: "; "}
    condition:   {section: assessment, rows: true, take: diagnosis}
  phc.op.rx-prescribe:
    drug:          {section: prescribed_medications, rows: true, take: name}
    dose:          {section: prescribed_medications, rows: true, take: strength, part: number}
    dose_unit:     {section: prescribed_medications, rows: true, take: strength, part: unit}
    frequency:     {section: prescribed_medications, rows: true, take: frequency}
    duration:      {section: prescribed_medications, rows: true, take: duration, part: number}
    duration_unit: {section: prescribed_medications, rows: true, take: duration, part: unit}
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
