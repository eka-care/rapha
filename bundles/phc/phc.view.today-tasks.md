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
  - title: Consent never asked
    where: {flag: registered, not: [capture.consented, capture.declined]}
---

## In plain words

A queue answers "what next on this visit". This answers "what needs someone,
across every visit today": a count of specimens nobody has resulted, a count
of patients nobody has asked about recording. The first row carries an
operation, so it opens straight into entering the result; the second carries
none, because asking for consent is not itself an operation and this is a
worklist to work from, not a button to tap.
