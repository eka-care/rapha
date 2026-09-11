---
id: lab.metric.accessioned
type: metric
title: Orders accessioned
summary: Active orders accessioned.
unit: count
window: day
numerator: {resource: service_request, where: {status: active, created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

One per accession. The service request row is written once and never
updated, so it is a clean count.
