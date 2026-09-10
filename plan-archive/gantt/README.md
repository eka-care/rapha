# Gantt

The shared schedule, as a Google Sheet partners can be given a link to.

**[Open the gantt](https://docs.google.com/spreadsheets/d/17OkDm9-wUSgMZ5G2Tegv69-MP-aXTdjjjN37t4-HxSE/edit)**

## What is in here

- `build_gantt.py` generates the workbook. The `TASKS` table in it is compiled
  from [plan#p8-schedule](../abdm-v1-phase1-architecture-and-plan.md), and carries
  a `PLAN_VERSION` stamp that `scripts/plan-check.sh` checks.

The generated `.xlsx` is not committed. It is one command to rebuild and it would
otherwise be a binary that churns on every schedule change.

## The one rule

**Status lives in the Sheet. Structure lives in the plan.**

Task names, dates, durations, owners and streams flow plan to script to Sheet.
Percent complete and status are typed into the Sheet as work lands, and exist
nowhere else. There is deliberately no `status.json` here: two mutable copies of
progress drift, and the copy partners read is the one that must not.

## What is live in the Sheet

Four tabs: `Gantt`, `Checkpoints`, `Definition of done`, `Actions`.

On the Gantt tab:

- Bars draw from Start and Days. Move either and the bar moves. Due is a formula
- Percent done shades that portion of the bar green
- Stream rows roll up from their children: earliest start, latest due, weighted percent
- Today's column highlights, weekends grey, both off the real date
- Status is a coloured dropdown. Overdue task names go red on their own
- Header counters: percent complete, days to ship, task count, blocked count

Nothing in the day grid is typed. Every bar is conditional formatting.

## Rebuilding

Only needed when the plan schedule changes. Follow `plan-sync` for the plan edit
itself, then:

```sh
python3 gantt/build_gantt.py --status live.csv
```

`live.csv` is a CSV export of the Gantt tab, so current progress survives the
rebuild. Without it every task returns to zero.

Then, inside the existing Sheet: **File > Import > Replace spreadsheet.**

Uploading the workbook as a new Drive file creates a new URL and orphans every
link already shared with a partner. Import in place keeps the URL and the
sharing.

Self-check without generating anything:

```sh
python3 gantt/build_gantt.py --check
```

Requires `openpyxl`.

## Updating status

Day to day this is `/gantt-update`, which reads the Sheet, proposes the edits
that landed work justifies, and applies them once approved. The rules, the cell
map and what counts as done are in the `gantt-sync` skill.
