---
id: phc.wf.outpatient
type: workflow
title: Outpatient line
summary: Reception, vitals, doctor, then lab and pharmacy when ordered.
subject: encounter
spine: patient
# THE LEVEL BETWEEN THE TWO. `spine` says what joins visits into a person;
# this says what joins some of a person's visits into one course of care
# that starts, runs and ends. A bundle declaring none writes no episode row
# and behaves exactly as before, which is bundles/lab.
episode: episode_of_care
steps:
  - station: reception
    done_when: registered
    operations: [phc.op.patient-register, phc.op.abha-link]
  - station: nurse
    done_when: vitals.recorded
    # Vitals first: it is what this station is for, and the order inside a
    # step is this bundle saying which of the things here is the point.
    # Background from elsewhere is seated behind it on purpose -- copying
    # in somebody else's letter must never be the headline advice at a
    # bench whose job is to take a reading.
    operations: [phc.op.vitals-record, phc.op.context-add,
                 phc.op.pregnancy-open, phc.op.pregnancy-close]
  - station: doctor
    done_when: consult.documented
    operations: [phc.op.consult-document, phc.op.ncd-review,
                 phc.op.antenatal-visit, phc.op.followup,
                 phc.op.rx-prescribe, phc.op.lab-order,
                 phc.op.capture-withdraw, phc.op.handover, phc.op.handover-reply,
                 phc.op.referral-raise, phc.op.referral-close]
  - station: lab
    done_when: lab.resulted
    applies_when: lab.ordered
    operations: [phc.op.lab-result-enter]
  - station: pharmacy
    done_when: dispensed.complete
    applies_when: rx.confirmed
    operations: [phc.op.pharmacy-dispense]
states:
  registered:
    exists: {resource: patient}
  abha.linked:
    exists: {resource: patient, where: {abha_number: "*"}}
  abha.pending:
    all_of: [registered, "not abha.linked"]
  vitals.recorded:
    exists: {resource: observation, where: {category: vital-signs}}
  consult.documented:
    exists: {resource: notes}
  # A handover has been raised on this visit. Derived from the handover's own
  # questionnaire response, so it is true exactly when one exists and no flag
  # has to be stored. The filter on `questionnaire` is what keeps a REPLY --
  # which writes the same resource under a different slug -- from raising it.
  handover.raised:
    exists: {resource: questionnaire_response,
             where: {questionnaire: phc.schema.handover-v1}}
  rx.confirmed:
    exists: {resource: medication_request, where: {status: active}}
  lab.ordered:
    exists: {resource: service_request}
  lab.resulted:
    exists: {resource: diagnostic_report}
  lab.validated:
    exists: {resource: diagnostic_report, where: {status: final}}
  dispensed.complete:
    gte:
      - {resource: medication_dispense}
      - {resource: medication_request, where: {status: active}}
  dispensed.partial:
    all_of:
      - {exists: {resource: medication_dispense}}
      - "not dispensed.complete"
  followup.booked:
    exists: {resource: token_booking, where: {status: booked}}
  # AN EPISODE ENDS BY GAINING A ROW, so "closed" is the count of endings
  # against the count of openings and "open" is an opening with no ending
  # yet. This is `dispensed.complete` and `dispensed.partial` exactly, over
  # a different pair of rows, which is why it needs no new rule form.
  #
  # Both are patient scoped rather than visit scoped: the adapter reads an
  # episode through the thread's patient, so a pregnancy opened at one
  # visit is still open at the next one without anything being carried
  # across a thread boundary.
  pregnancy.ended:
    gte:
      - {resource: episode_of_care, where: {type: pregnancy, status: ended}}
      - {resource: episode_of_care, where: {type: pregnancy, status: active}}
  pregnancy.open:
    all_of:
      - {exists: {resource: episode_of_care, where: {type: pregnancy, status: active}}}
      - "not pregnancy.ended"
  # The same pair over the same table, for the other kind of episode this
  # bundle keeps. "Every referral closed" is this flag being false.
  referral.ended:
    gte:
      - {resource: episode_of_care, where: {type: referral, status: ended}}
      - {resource: episode_of_care, where: {type: referral, status: active}}
  referral.open:
    all_of:
      - {exists: {resource: episode_of_care, where: {type: referral, status: active}}}
      - "not referral.ended"
  capture.agreed: {stored: true}
  capture.declined: {stored: true}
  capture.withdrawn: {stored: true}
  capture.consented:
    all_of: ["not capture.declined", "not capture.withdrawn"]
  vitals.flagged: {stored: true}
  lab.critical: {stored: true}
---

## In plain words

The patient walks a line: registered at reception, vitals with the nurse, a
consultation with the doctor, and then the lab and the pharmacy only if the
doctor ordered a test or wrote a prescription. A patient nobody sent to the
lab is not waiting at the lab; they have skipped it.

Every state flag above is derived from records at read time, except the five
marked stored, which no record can answer: the three halves of this visit's
capture consent, and whether a vital or a lab value crossed a critical
threshold. Those thresholds are ours, so those flags are ours.

## Consent to ambient capture

`capture.consented` is the flag every scribe is gated on, and it is not
stored. It is composed, because the store can raise a flag and cannot lower
one, and a capture that cannot be stopped is not one a patient controls.

THE OWNER'S DECISION OF 2026-11-01 CHANGED WHAT IT COMPOSES. It used to
require `capture.agreed`, so a visit nobody had asked about could not be
recorded, and the station answered a refusal instead of a reading. It now
requires only that nobody refused: consent is presumed, and the two ways a
patient says no are what lower it. The change is this one line and nothing
else, which is the point of the flag being declared rather than coded.

- `capture.declined` is raised by the consent question's own answer on the
  registration form, so a visit the patient said no to is not recorded. This
  is the half that still gates, and it is deliberately the only one: not
  asking is not the same as being told no.
- `capture.withdrawn` is raised by `phc.op.capture-withdraw`, which is its
  own action at the doctor and asks one question. From that commit the gate
  is false and nothing listens for the rest of the visit. Records already
  confirmed are rows, and rows are untouched. Its precondition is
  `capture.consented`, which now stands on every visit nobody refused, so
  the stop is where a patient can always reach it rather than only where
  somebody remembered to ask first.
- `capture.agreed` is still raised by the same question and is still a
  recorded fact about what the patient was asked. It gates nothing.

All three are thread flags, and a thread is one encounter, so consent is
scoped to the visit and the next encounter starts with nothing raised. There
is nothing patient scoped to leak.

This declaration is care_phc/thread.py LINE and derive() written down.
kernel/tests/test_contracts.py asserts the two agree, step for step, until
thread.py is retired.
