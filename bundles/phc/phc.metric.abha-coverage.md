---
id: phc.metric.abha-coverage
type: metric
title: ABHA coverage
summary: Share of patients seen in the window who have an ABHA linked.
unit: percent
window: week
numerator: {resource: patient, where: {abha_number: "*", created_date: {gte: window.start}}}
denominator: {resource: patient, where: {created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

Registered without an ABHA is a worklist item, not a barrier. This is the
size of that worklist as a share of everyone seen.
