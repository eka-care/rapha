---
id: phc.op.antenatal-measure
type: operation
kind: write
short: ANC readings
title: Record antenatal measurements
summary: Fundal height, the fetal heart rate and haemoglobin, as coded numbers.
capability: vitals.record
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - registered
  - pregnancy.open
irreversibility: correctable
input: phc.schema.antenatal-measure-v1
writes: [observation]
mapping:
  records:
    - resource: observation
      per_question: [fundal_height, fetal_heart_rate, haemoglobin]
      fields:
        created_by: {actor: id}
        category: {const: vital-signs}
        code: {question: code}
        code_system: {question: code_system}
        code_display: {question: code_display}
        value: {question: answer}
        unit: {question: unit}
        unit_system: {question: unit_system}
        # `final` for the same reason a blood pressure is final: nobody owes
        # a second pair of eyes on a tape measure, the value is range checked
        # on this form, and nothing here is amended by a later reading. The
        # next contact's reading is its own row, which is the point.
        status: {const: final}
emits: [vitals.flagged]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.antenatal-visit, phc.op.vitals-record]
  concepts: []
---

## In plain words

The three numbers an antenatal contact turns on. How big the uterus is, what
the baby's heart is doing, and how anaemic she is.

They exist as a separate recording from the antenatal visit for one reason:
**a number is not a sentence.** The antenatal visit is dictated and lands as
narrative, which is the right shape for a history and an assessment and the
wrong shape for a measurement. A fundal height that arrives as the words
"fundus about thirty weeks" cannot be put on an axis, cannot be compared with
the last one, and cannot reach a district return. The same reading taken here
is a coded observation with a LOINC code and a UCUM unit, and it can do all
three.

## Before you start

The patient must be registered and must have a pregnancy open on this
centre's books, which is what `pregnancy.open` means. You need
`vitals.record`, which an ANM holds.

The pregnancy precondition is deliberate and it is the whole reason this is a
separate operation rather than three more questions on a form. A fundal
height on somebody who is not pregnant is not a cautious reading, it is a
record of something that did not happen.

## What happens

Each answer becomes one observation row, coded, with its unit. A fetal heart
rate or a haemoglobin outside the range below raises `vitals.flagged`, which
puts a review in front of the doctor before the consultation starts.

NEEDS SIGN-OFF on the thresholds, in the same words
`terminology/condition-code.json` carries. The ranges this form refuses
outright are wide and only exclude impossibilities. The narrower pair that
raise the flag -- a fetal heart rate outside 110 to 160 a minute, and a
haemoglobin below 11 grams per decilitre -- are a product choice and must not
be read as a protocol. They were chosen to be the commonly cited figures and
not to be clinically authoritative, and a named clinical officer has to
confirm or replace them before anybody is asked to act on the flag.

## How you know it worked

Three rows on the patient thread, each with its own code and unit, and the
doctor's next action becomes a review of what was flagged rather than
starting the consultation, when anything was flagged.

The readings do NOT close an antenatal contact. What closes a contact is a
committed `phc.op.antenatal-visit`, and that stays true here: measuring
somebody is not the same as having seen them, and a schedule discharged by a
tape measure would read as care that did not happen.

## When it goes wrong

- **The field you want is not here.** Three measurements, because three are
  what this build can code honestly. Urine protein by dipstick is reported as
  a grade and not a number, and no value set for those grades has been
  confirmed, so it belongs in the visit's narrative until one is. Mid upper
  arm circumference is measured on the left arm and the only LOINC concept
  that resolved is specific to the right, so storing it would claim the wrong
  arm. Both reasons are written down in
  `terminology/observation-code.json`.
- **She is pregnant and this is not offered.** Nobody has opened the
  pregnancy. Open it at this station, with New pregnancy, and the readings
  appear.
- **A reading is wrong.** It is correctable: record it again and the
  correction carries the audit of both.
