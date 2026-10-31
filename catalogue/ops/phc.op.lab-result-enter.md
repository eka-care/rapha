---
id: phc.op.lab-result-enter
type: operation
kind: write
short: Result
title: Enter a laboratory result
summary: Record a bench result against the order it answers.
capability: lab.result.enter
scope_qualifier: null
station: lab
instrument: form
preconditions:
  - lab.ordered
  - not lab.resulted
irreversibility: correctable
input: phc.schema.lab-result-v1
writes: [observation, diagnostic_report, specimen]
mapping:
  # The reason for an override is recorded on the audit line, which is where a
  # reader looks for why a value outside range was accepted. It is not a
  # column on the report.
  ignored: [override_reason]
  records:
    # The result itself, as a quantity. This record is the point of the
    # operation and it did not exist: the number was squashed into the
    # report's prose by `conclusion: {joined: [value, unit]}`, so it could not
    # be trended, counted or sent as a FHIR Quantity, and the code column held
    # whatever free text the technician typed into the analyte field.
    #
    # The analyte is now a coded ANSWER, which is the third binding form: the
    # question is a slot and the concept is whichever test was run, so the
    # code is resolved from the answer through the value set it binds to. The
    # unit is an answer too, and the validator refuses one that is not the
    # unit LOINC reports that analyte in.
    - resource: observation
      fields:
        created_by: {actor: id}
        category: {const: laboratory}
        code: {answer_code: analyte}
        code_system: {answer_code_system: analyte}
        code_display: {answer_code_display: analyte}
        value: {answer: value}
        unit: {answer_code: unit}
        unit_system: {answer_code_system: unit}
        # `preliminary`, matching the report below and R4's own meaning: a
        # value recorded and not yet verified. A health centre has no
        # verification station, so nothing here will ever move it, and a
        # status that says "this may change" is the honest one to be stuck on.
        status: {const: preliminary}
    # The report stays, and keeps a narrative conclusion. The narrative is now
    # one the technician wrote rather than a number reformatted as prose.
    - resource: diagnostic_report
      fields:
        created_by: {actor: id}
        code: {answer_code: analyte}
        code_system: {answer_code_system: analyte}
        conclusion: {answer: note}
        status: {const: preliminary}
    # The specimen no longer carries the analyte in its code column. A
    # specimen's code is a specimen TYPE (blood, serum, urine), not the name
    # of the test run on it, and this form does not ask which specimen was
    # taken. Writing the test name there made the row claim something false,
    # so the claim is dropped rather than restated: the row records that a
    # specimen exists and who recorded it. Giving it a real type needs a
    # specimen value set and a question, which is its own piece of work.
    - resource: specimen
      fields:
        created_by: {actor: id}
        status: {const: available}
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
