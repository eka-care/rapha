---
id: lab.view.turnaround
type: view
kind: dashboard
title: Turnaround today
summary: In, out, the ratio, and the critical rate.
capability: reporting.view
metrics: [lab.metric.accessioned, lab.metric.released, lab.metric.release-ratio, lab.metric.critical-rate]
window: day
---

## In plain words

What the metric grammar can say about turnaround: how many came in, how many
went out, and the ratio. What it cannot say is turnaround time itself, the
hours between accession and release, because a metric is a count or a ratio
of counts and has no way to subtract two timestamps on the same thread.
