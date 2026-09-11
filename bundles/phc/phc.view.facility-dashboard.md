---
id: phc.view.facility-dashboard
type: view
kind: dashboard
title: Facility today
summary: Visits, ABHA coverage and flagged vitals.
capability: reporting.view
metrics: [phc.metric.visits, phc.metric.abha-coverage, phc.metric.vitals-flagged-rate]
window: week
---

## In plain words

Three certified numbers, computed on this machine from this machine's
records. Nothing leaves. The window on the view overrides the metric's own
default window, so the same metric can sit on a daily and a monthly board.
