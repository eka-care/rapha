---
id: lab.view.worklist
type: view
kind: queue
title: Worklist by status
summary: Today's specimens, grouped by station.
capability: worklist.read
workflow: lab.wf.specimen
scope: today
group_by: station
columns: [name, age, sex, token]
badges:
  lab.critical: crit
  result.rejected: warn
  report.released: ok
---

## In plain words

The bench, the draw room and the pathologist look at the same list. A group
per station in line order, and a Complete group for released reports. The
station is the specimen status: it is derived from which rows exist, so this
is the worklist by status without a status column. A rejected result badges
warn and stays at verification, because this bundle has no amend loop.
