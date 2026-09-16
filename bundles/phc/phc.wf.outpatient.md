---
id: phc.wf.outpatient
type: workflow
title: Outpatient line
summary: Reception, vitals, doctor, then lab and pharmacy when ordered.
subject: encounter
spine: patient
steps:
  - station: reception
    done_when: registered
    operations: [phc.op.patient-register, phc.op.abha-link]
  - station: nurse
    done_when: vitals.recorded
    operations: [phc.op.vitals-record]
  - station: doctor
    done_when: consult.documented
    operations: [phc.op.consult-document, phc.op.rx-prescribe, phc.op.lab-order,
                 phc.op.capture-withdraw, phc.op.handover, phc.op.handover-reply]
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
  capture.agreed: {stored: true}
  capture.declined: {stored: true}
  capture.withdrawn: {stored: true}
  capture.consented:
    all_of: [capture.agreed, "not capture.declined", "not capture.withdrawn"]
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
one, and a consent that cannot be withdrawn is not a consent:

- `capture.agreed` is raised by the consent question on the registration
  form, which is read out at the desk.
- `capture.declined` is raised by its own answer on the same form, so a visit
  the patient said no to is visibly declined rather than merely unconsented
  and no station asks again. Ticking both is a contradiction, and the safe
  answer wins: declined beats agreed.
- `capture.withdrawn` is raised by `phc.op.capture-withdraw`, which is its
  own action at the doctor and asks one question. From that commit the gate
  is false and nothing listens for the rest of the visit. Records already
  confirmed are rows, and rows are untouched. It rode on the consultation
  form until now, where `assessment` is required, so withdrawing a consent
  meant writing a note as well. Its precondition is `capture.consented`, so
  the action is absent when there is nothing to withdraw.
- A visit with none of the three was never asked. That is not the same as a
  decline and is not drawn as one.

All three are thread flags, and a thread is one encounter, so consent is
scoped to the visit and the next encounter starts with nothing raised. There
is nothing patient scoped to leak.

This declaration is care_phc/thread.py LINE and derive() written down.
kernel/tests/test_contracts.py asserts the two agree, step for step, until
thread.py is retired.
