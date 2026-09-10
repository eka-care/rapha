---
id: phc.wf.outpatient
type: workflow
title: Outpatient line
summary: >
  Reception, vitals, doctor, then lab and pharmacy only when the doctor sent
  the patient there. The current station is the first step not done.
subject: encounter
steps:
  - station: reception
    done_when: registered
    operations: [phc.op.patient-register, phc.op.abha-link]
  - station: nurse
    done_when: vitals.recorded
    operations: [phc.op.vitals-record]
  - station: doctor
    done_when: consult.documented
    operations: [phc.op.consult-document, phc.op.rx-prescribe, phc.op.lab-order]
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
  capture.consented: {stored: true}
  vitals.flagged: {stored: true}
  lab.critical: {stored: true}
---

## In plain words

The patient walks a line: registered at reception, vitals with the nurse, a
consultation with the doctor, and then the lab and the pharmacy only if the
doctor ordered a test or wrote a prescription. A patient nobody sent to the
lab is not waiting at the lab; they have skipped it.

Every state flag above is derived from records at read time, except the three
marked stored, which no record can answer: whether the patient consented to
ambient capture this visit, and whether a vital or a lab value crossed a
critical threshold. Those thresholds are ours, so those flags are ours.

This declaration is care_phc/thread.py LINE and derive() written down.
kernel/tests/test_contracts.py asserts the two agree, step for step, until
thread.py is retired.
