---
id: lab.metric.critical-rate
type: metric
title: Critical result rate
summary: Share of threads in the window where an analyte crossed its critical band.
unit: percent
window: week
numerator: {resource: thread_flag, where: {flag: lab.critical, created_date: {gte: window.start}}}
denominator: {resource: encounter, where: {created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

Stored flags are records, so the critical flag is counted the way the PHC
bundle counts flagged vitals. The denominator is every thread, not every
result, because a thread is an encounter row on this adapter.
