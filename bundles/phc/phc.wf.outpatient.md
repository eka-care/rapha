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
    operations: [phc.op.vitals-record, phc.op.antenatal-measure,
                 phc.op.context-add,
                 phc.op.pregnancy-open, phc.op.delivery-record,
                 phc.op.pregnancy-close, phc.op.postnatal-close]
  - station: doctor
    done_when: consult.documented
    operations: [phc.op.consult-document, phc.op.ncd-review,
                 phc.op.antenatal-visit, phc.op.followup,
                 phc.op.rx-prescribe, phc.op.lab-order,
                 phc.op.handover, phc.op.handover-reply,
                 phc.op.referral-raise, phc.op.referral-close]
  - station: lab
    done_when: lab.resulted
    applies_when: lab.ordered
    operations: [phc.op.lab-result-enter]
  - station: pharmacy
    done_when: dispensed.complete
    applies_when: rx.confirmed
    operations: [phc.op.pharmacy-dispense]
  # THE HOUSE, AND IT IS LAST BECAUSE IT IS NOT A BENCH. Every other step is
  # somewhere a patient waits; this one is a door somebody knocks on, and it
  # is at the end so that it cannot park a woman at a station while she is
  # still owed a prescription.
  #
  # It draws the POSTNATAL visit and not the general household visit, which
  # is a finding rather than a preference: `phc.op.household-visit` is
  # loaded, listed by the scribe, and drawn by no step, so nobody can perform
  # it at all. Closing that gap means either a line of its own for outreach
  # or a household round inside a clinic queue, and that is a decision for
  # this facility's owner rather than one to make while building a schedule.
  # catalogue/ops/phc.op.postnatal-visit.md carries the same note.
  #
  # `applies_when: postnatal.open` keeps the step out of an ordinary visit,
  # and `done_when` is the flag the postnatal visit itself raises, so it
  # parks nobody who is not owed a home visit.
  - station: community
    done_when: consult.documented
    applies_when: postnatal.open
    operations: [phc.op.postnatal-visit]
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
  # The six weeks after a delivery, the same pair over the same table. Note
  # what is NOT here: no rule relates this to how the pregnancy ended. A
  # postnatal episode exists because somebody recorded a delivery, and a
  # pregnancy that ended any other way produced no row for this to find.
  postnatal.ended:
    gte:
      - {resource: episode_of_care, where: {type: postnatal, status: ended}}
      - {resource: episode_of_care, where: {type: postnatal, status: active}}
  postnatal.open:
    all_of:
      - {exists: {resource: episode_of_care, where: {type: postnatal, status: active}}}
      - "not postnatal.ended"
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
  vitals.flagged: {stored: true}
  lab.critical: {stored: true}
---

## In plain words

The patient walks a line: registered at reception, vitals with the nurse, a
consultation with the doctor, and then the lab and the pharmacy only if the
doctor ordered a test or wrote a prescription. A patient nobody sent to the
lab is not waiting at the lab; they have skipped it.

Every state flag above is derived from records at read time, except the two
marked stored, which no record can answer: whether a vital or a lab value
crossed a critical threshold. Those thresholds are ours, so those flags are
ours. It was five until the capture consent flags went; see below.

## There is no consent gate on recording

REMOVED ON THE OWNER'S DECISION OF 4 NOVEMBER 2026, in full. This workflow
declared three stored flags -- agreed, declined, withdrawn -- and composed a
fourth from them that every recording was gated on. The registration form
asked the question, an operation at the doctor withdrew it, and an
instrument read the sentence out.

All of it is gone. A recording is now refused for one reason only: the
caller does not hold the capability. Nothing about a patient's answer stops
it, because there is no longer an answer to give.

What this costs is written here rather than in a commit message, because
the next person to read this file is the one who needs to know. The gate
was the mechanism by which a patient could stop a recording of themselves,
and this product has no other. Putting it back is this file's four lines,
the question on the registration form, and the operation that lowered it;
that is the whole of what was taken out, and it was taken out in one commit
so it can be read back in one diff.

This declaration is care_phc/thread.py LINE and derive() written down.
kernel/tests/test_contracts.py asserts the two agree, step for step, until
thread.py is retired.
