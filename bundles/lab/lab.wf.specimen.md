---
id: lab.wf.specimen
type: workflow
title: Specimen line
summary: >
  Accession, collection, bench, then verification and release by a second
  person. The current station is the first step not done.
subject: encounter
steps:
  - station: reception
    done_when: lab.ordered
    operations: [lab.op.referral-accession]
  - station: nurse
    done_when: vitals.recorded
    operations: [lab.op.specimen-collect]
  - station: lab
    done_when: lab.resulted
    operations: [lab.op.result-enter]
  - station: doctor
    done_when: dispensed.complete
    operations: [lab.op.result-verify, lab.op.report-release]
states:
  registered:
    exists: {resource: patient}
  abha.linked:
    exists: {resource: patient, where: {abha_number: "*"}}
  abha.pending:
    all_of: [registered, "not abha.linked"]
  lab.ordered:
    exists: {resource: service_request, where: {status: active}}
  # specimen collected. The vocabulary is closed; this is the free slot.
  vitals.recorded:
    exists: {resource: specimen}
  lab.resulted:
    exists: {resource: observation, where: {category: laboratory}}
  lab.validated:
    exists: {resource: diagnostic_report, where: {status: verified}}
  # report released to the referrer. Same reason for the name.
  dispensed.complete:
    exists: {resource: questionnaire_response, where: {questionnaire: lab.schema.release-v1}}
  lab.critical: {stored: true}
  # Everything below is padding. Lint demands every vocabulary flag be
  # declared; nothing in this bundle raises or reads these six.
  capture.consented: {stored: true}
  vitals.flagged: {stored: true}
  consult.documented: {stored: true}
  rx.confirmed: {stored: true}
  dispensed.partial: {stored: true}
  followup.booked: {stored: true}
---

## In plain words

A specimen walks a line: accessioned at the front desk, drawn by the
phlebotomist, run at the bench by the technologist, then verified and
released by the pathologist. Nobody consults and nobody prescribes. The
person who enters a result cannot verify it; the person who verifies it is
the one who may release it.

Read the station names as the laboratory's: reception is accession, nurse is
the draw room, lab is the bench, doctor is the pathologist's desk. The
vocabulary has no others. Read `vitals.recorded` as specimen collected and
`dispensed.complete` as report released, for the same reason. Six flags at
the bottom exist only because lint demands the whole PHC vocabulary be
covered.
