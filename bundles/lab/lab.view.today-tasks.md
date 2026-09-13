---
id: lab.view.today-tasks
type: view
kind: tasklist
title: Needs you
summary: What is waiting across today's specimens, not what is waiting on one.
capability: worklist.read
workflow: lab.wf.specimen
tasks:
  - title: Collected, no result yet
    where: {flag: specimen.collected, not: result.entered}
    operation: lab.op.result-enter
  - title: Entered, not yet verified
    where: {flag: result.entered, not: result.verified}
---

## In plain words

The worklist answers "where does this specimen stand". This answers "what
needs someone, across every specimen today": a count drawn but not keyed, a
count keyed but not verified. The first row carries an operation, so it opens
straight into entering the result; the second carries none, because
verifying is a separate role's step and this is a worklist for that role to
work from.

Same kind, same resolver, as the primary health centre's tasklist. Every word
here is this bundle's own, declared in `bundles/lab/bundle.yaml`.
