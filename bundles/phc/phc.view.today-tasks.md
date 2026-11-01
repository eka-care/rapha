---
id: phc.view.today-tasks
type: view
kind: tasklist
title: Needs you
summary: What is waiting across today's visits, not what is waiting on one.
capability: patient.find
workflow: phc.wf.outpatient
tasks:
  - title: Waiting on a lab result
    where: {flag: lab.ordered, not: lab.resulted}
    operation: phc.op.lab-result-enter
---

## In plain words

A queue answers "what next on this visit". This answers "what needs someone,
across every visit today": today, a count of specimens nobody has resulted.
The row carries an operation, so it opens straight into entering the result.

A second row counted the patients nobody had asked about recording. It is
gone with the owner's decision of 2026-11-01: consent is presumed unless the
patient refuses, so there is nobody left to chase and a row that is always
zero is worse than no row. The decline on the registration form still stops
a recording; it is just not a task for anyone to go and collect.
