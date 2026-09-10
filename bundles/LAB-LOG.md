# The lab bundle log: every time the kernel wanted changing

The task was a diagnostics laboratory on the PHC kernel with no kernel
change. This is the running log of every moment the kernel, `catalogue/vocab.py`
or a contract wanted changing, what was done instead, and what it cost. The
numbers are referenced from `check.py` and the atoms.

Scope of "unchanged": nothing under `kernel/`, `catalogue/*.py`, `adapters/`,
`api/`, `web/` or the Go source was edited. What was added: five atoms in
`catalogue/ops/`, five questionnaires, this directory, one line in
`scripts/check.sh`. The Go binary was rebuilt because it embeds the catalogue.

## 1. Separation of duties cannot be enforced. Only approximated.

Wanted: a precondition that says "not by the actor who ran `lab.op.result-enter`
on this thread", or a `pathologist` role that does not hold `lab.result.enter`.
The guard sees a capability set and a flag set. It never sees who wrote the
rows the flags derive from, and the rows themselves carry no author: a kernel
write sets no `created_by`, because the mapping grammar has no `{actor}`
source. Only the audit line knows, and the guard does not read audit.

Did: split enter and verify across two capabilities. `vocab.BUNDLES["lab"]`
holds enter and not validate, so a technologist is refused. But
`lab_incharge`, the only role holding validate, also holds enter, so the
pathologist can key and verify the same result. `check.py` asserts the hole
exists rather than pretending it does not.

Cost: the central safety property a laboratory runs on is a convention about
which role bundle you log in with. That is not enforcement.

## 2. The vocabularies are the PHC's, and they are closed.

Wanted: `bundle.yaml` to declare its own stations, flags, capabilities and
roles, with closure checked per bundle. `vocab.STATIONS` is
`reception, nurse, doctor, lab, pharmacy, community`. `vocab.STATES` is
fifteen PHC flags. `vocab.CAPABILITIES` has no phlebotomy, accession or
release. `vocab.BUNDLES` has no phlebotomist, technologist or pathologist.

Did, and every one of these is a lie a user will read on screen:

| lab fact | declared as | why |
|---|---|---|
| accession desk | `reception` | free slot |
| draw room | `nurse` | free slot |
| bench | `lab` | true |
| pathologist's desk | `doctor` | free slot |
| specimen collected | `vitals.recorded` | free slot; the line label reads "Vitals recorded" |
| report released | `dispensed.complete` | free slot; the label reads "Dispensed complete" |
| phlebotomy | `assessment.record` | the one capability `nurse` holds and `lab` does not |
| phlebotomist | `nurse` role | |
| technologist | `lab` role | |
| pathologist | `lab_incharge` role | see 1 |

The renderer draws `human(label)` from the workflow, so the lies are visible,
not hidden. A laboratory would not ship this.

## 3. Turnaround time is not declarable.

Wanted: a metric over a duration: for each thread, release time minus
accession time, then a mean or a percentile. A metric is `count(query)` or
`count(a) / count(b)` and a query has no join across two resources on the
same thread and no arithmetic on a field.

Did: accessioned count, released count, their ratio, and a critical rate.
The dashboard is titled "Turnaround today" and its plain words say it is
not turnaround time. A lab's single most watched number is missing.

## 4. `states` must cover `vocab.STATES` exactly.

Wanted: at least, or the bundle's own list. Did: six flags declared
`{stored: true}` that nothing raises and nothing reads
(`capture.consented, vitals.flagged, consult.documented, rx.confirmed,
dispensed.partial, followup.booked`). Lint passes. The workflow declaration
is forty percent padding.

## 5. There is no amend or reject loop.

Wanted: a state rule that can say "more entries than rejections" or "the
latest report row is verified". The four rule forms are stored, exists,
gte (which also demands the right side be non zero) and all_of. Nothing
reads a latest row, nothing compares strictly.

Did: a rejection writes a report row with status rejected and leaves
`lab.validated` false. The technologist cannot re-enter because
`lab.resulted` is already true. The specimen is stranded at the
pathologist's desk. `check.py` asserts the stranding.

## 6. A mapping cannot address an existing row.

Wanted: verification to move the preliminary report to final. A record is an
insert; the only update in the system is the adapter's private special case
for a second patient row on a thread. Did: verification writes a second
`diagnostic_report` row with `code: verification` and the decision as its
status, and `lab.validated` is "a row with status verified exists". Two
report rows per specimen; the report view shows both.

## 7. One flag per question, spent on critical. No reference interval.

Wanted: per analyte, three bands: plausible (blocks), reference (marks high
or low), critical (flags), with the reference band conditional on sex and
age. The questionnaire grammar has `range` (blocks) and `critical` plus a
single `flags` name. Did: `range` holds the plausible band, `critical` holds
the critical band and raises `lab.critical`, and a `reference` key is written
on each analyte that nothing in the kernel or the renderer reads. A sodium of
133 commits and raises nothing; `check.py` asserts it. Haemoglobin 12 to 16
is one interval for everyone. The renderer labels the plausible band "Usual
range", which for a lab is the wrong word.

Note the PHC's own `phc.schema.lab-result-v1` already carries a dead
`range_from: analyte` key and the renderer prints "Not checked here or on
the server" beside it. The gap predates this exercise.

## 8. The report cannot show what a report shows.

Wanted: value, unit, reference interval, H or L, side by side. A summary
section shows columns of one resource's rows. The interval lives on the
questionnaire, not in a row, and a section cannot join to it or compute.
Did: raw observation rows. The referrer's name is inside a JSON blob in the
Referral section, because of 9.

## 9. The adapter's schema is the PHC's.

`service_request` has no requester, `diagnostic_report` no performer or
issued time, `observation` no interpretation or reference range, and no
table has a reliable author (see 1). Did: the whole accession form as a
`questionnaire_response` with `{json: payload}`, and the same for release.
The adapter was not changed, which kept the exercise honest, but it means
the referring clinician exists only as a JSON string.

## 10. The seed and the demo role are the PHC's, and they run under any bundle.

`adapters/local/store.py seed()` runs on any empty database. Under
`PHC_BUNDLE=lab` the worklist opens with six PHC patients carrying vitals and
prescriptions. `api/main.py DEMO_ROLE` is the union of five PHC roles and
excludes `lab_incharge`, so the default caller cannot verify or release
anything in a laboratory. Wanted: fixtures and a default role declared by
the bundle. Did: `?role=` on every call; `check.py` asserts the six intruders.

## 11. `catalogue.json` holds one bundle. The MCP server embeds it at build.

`kernel.declarations` overwrites the five declaration keys with whichever
bundle ran last, and `check.sh` depends on it being `phc`. So the lab bundle
is linted with `--json` and never written. Meanwhile `operations` is
catalogue wide, so the Go server offers every bundle's operations to anyone
holding the capability, and the API 404s the ones outside the loaded bundle.
The checked in binary predated the lab atoms and offered none of them until
rebuilt. Wanted: manifests keyed by bundle, and an MCP server that reads
`/catalogue` from the kernel it is pointed at.

## 12. `subject: encounter` is decorative.

The adapter's `threads()` reads the encounter table and `THREAD_COLUMN`
joins everything to it. A lab thread is an accession, not an encounter, and
there is no operation that opens a thread: accession had to run against a
thread opened by `POST /threads`, which the store author already flagged as
a gap in the nine method protocol.

## 13. Analytes as flat questions do not scale.

Seven optional analytes on one form, hidden by `enable_when` in the renderer
and not enforced by the server: a glucose on a CBC commits. `per_item` walks
a structured answer but items have no sub schema, so a per item range cannot
be declared or linted, so one question per analyte is the only way to get a
range per analyte. A real menu of a few hundred analytes is a few hundred
questions, or one operation per panel and one MCP tool per panel.

## 14. Cosmetic, left alone.

`styling_metadata.phc`, `/api/v1/phc`, `X-PHC-Role`, "care-phc kernel".
Tool names are the id stem and are not linted for collisions across bundles.
A view's capability must be a vocab capability, and `reporting.view` belongs
to `mo` only, so the turnaround board is gated on `lab.result.validate`.

## What worked without argument

The guard, the proposal queue, confirm as a second guard pass, the four
state rule forms for the happy path, `per_question` fan out with
`{question: unit}`, stored flags raised from a questionnaire's `critical`
band, the queue and summary and dashboard renderers, the API, the renderer,
and the MCP server. Not one of them knew this was a laboratory. That part of
the claim holds.

## 15. The bundle directory may hold nothing but declarations.

This log was first written as `bundles/lab/LOG.md`. `declarations.load`
parses every `*.md` in the directory as a declaration, so the build failed
with "LOG.md: no frontmatter" and so did the API at import. A bundle cannot
carry a README. The log now lives one level up.

## 16. A kernel test encoded "one bundle per catalogue".

`kernel/tests/test_contracts.py` asserted that the PHC manifest references
every operation in `catalogue.json`. True while there was one bundle, false
the moment `lab.*` atoms joined the shared `catalogue/ops`. This is the one
edit made under `kernel/`: the assertion now says the PHC manifest owns
every `phc.*` atom and nothing outside the catalogue. Kernel logic is
untouched; a kernel test was.

## 17. The agent's router planned over every bundle's atoms.

`agent/planner.py load()` read `catalogue.json["operations"]`, which is
catalogue wide, so "new patient, register her" routed to the lab accession
atom as well as PHC registration and `agent/tests/test_planner.py` failed.
The fix, made in that client and not the kernel: `load()` narrows
`operations` to what `manifest.operations` names, the way the API's
`/catalogue` already does. The Go MCP server has the same exposure and was
not changed; it offers every atom whose capability the account holds, and
the kernel 404s the ones outside the loaded bundle.

## 18. The renderer compiles the questionnaires in; the API does not serve them.

`web/src/declarations.ts` already calls this an honest gap: there is no
questionnaire route in `kernel/contracts.py ROUTES`, so the forms are baked
into the renderer with `import.meta.glob` at dev server start. A running
renderer showed "No questionnaire for lab.op.referral-accession" for every
lab form until restarted. A bundle is not loadable at runtime while its
forms are a build artefact of the renderer.
