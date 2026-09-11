---
id: lab.wf.specimen
type: workflow
title: Specimen line
summary: Accession, phlebotomy, processing, verification, release.
subject: encounter
steps:
  - station: accession
    done_when: order.accessioned
    operations: [lab.op.referral-accession]
  - station: phlebotomy
    done_when: specimen.collected
    operations: [lab.op.specimen-collect]
  - station: processing
    done_when: result.entered
    operations: [lab.op.result-enter]
  - station: verification
    done_when: result.verified
    operations: [lab.op.result-verify]
  - station: release
    done_when: report.released
    operations: [lab.op.report-release]
states:
  order.accessioned:
    exists: {resource: service_request, where: {status: active}}
  specimen.collected:
    exists: {resource: specimen}
  result.entered:
    exists: {resource: observation, where: {category: laboratory}}
  # A rejection writes a report row with status rejected. Declaring the flag
  # is what makes the stranded specimen visible on the worklist instead of
  # silent; it does not un-strand it, because there is no amend operation.
  result.rejected:
    exists: {resource: diagnostic_report, where: {status: rejected}}
  result.verified:
    exists: {resource: diagnostic_report, where: {status: verified}}
  report.released:
    exists: {resource: questionnaire_response, where: {questionnaire: lab.schema.release-v1}}
  lab.critical: {stored: true}
---

## In plain words

A specimen walks a line: accessioned at the front desk, drawn by the
phlebotomist, run at the bench by the technologist, then verified and
released. Nobody consults and nobody prescribes.

Every word on this line is the laboratory's own, declared in
`bundles/lab/bundle.yaml` and closed there: five stations, six flags derived
from rows and one stored. The line used to wear a primary health centre's
vocabulary, so the draw room was called `nurse` and a released report was
`dispensed.complete`.

The person who enters a result cannot verify it. That is a precondition on
`lab.op.result-verify` naming the actor of `lab.op.result-enter`, not a hope
about how the roles are handed out: the `senior_technologist` role holds both
capabilities, and is still refused on a specimen it keyed.
