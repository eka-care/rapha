# The lab bundle log: every time the kernel wanted changing

The task was a diagnostics laboratory on the PHC kernel with no kernel
change. This is the running log of every moment the kernel, `catalogue/vocab.py`
or a contract wanted changing, what was done instead, and what it cost. The
numbers are referenced from `check.py` and the atoms.

Scope of "unchanged", as first written: nothing under `kernel/`,
`catalogue/*.py`, `adapters/`, `api/`, `web/` or the Go source was edited.
What was added: five atoms in `catalogue/ops/`, five questionnaires, this
directory, one line in `scripts/check.sh`. The Go binary was rebuilt because it
embeds the catalogue.

**That scope was then deliberately broken.** Leaks 1 and 2 were the two worst
things in this file and neither could be fixed from inside a bundle, so on
2026.09.12 the kernel changed: an `{actor: id}` mapping source and an
`actor of <operation>` precondition (leak 1), and per bundle vocabularies
declared in `bundle.yaml` (leaks 2 and 4). Those three are struck through
below with what was actually done. Everything not struck through still stands,
and `check.py` still asserts each one with a running assert rather than a
comment. `api/`, `web/`, the Go source and `questionnaires/` are still
untouched.

## 1. ~~Separation of duties cannot be enforced. Only approximated.~~ FIXED

Wanted: a precondition that says "not by the actor who ran `lab.op.result-enter`
on this thread", or a `pathologist` role that does not hold `lab.result.enter`.
The guard sees a capability set and a flag set. It never sees who wrote the
rows the flags derive from, and the rows themselves carry no author: a kernel
write sets no `created_by`, because the mapping grammar has no `{actor}`
source. Only the audit line knows, and the guard does not read audit.

Did first: split enter and verify across two capabilities, which left the one
role holding validate holding enter as well, so the same person could key and
verify. `check.py` asserted the hole rather than pretending it did not exist.

Fixed, 2026.09.12, and it took a kernel change because there was nowhere to
write the rule down:

- `{actor: id}` is a mapping source, and lint now **refuses a record with no
  author**: every row every declaration writes carries who wrote it.
  `adapters/local` keeps the first author on an update, so linking an ABHA
  does not rewrite the registrar out of the patient row.
- `actor of <operation id>` is a precondition form.
  `lab.op.result-verify` carries `not actor of lab.op.result-enter`.
- `catalogue/guard.py` evaluates it against `{operation: actors}` built by
  `kernel/state.performers` from the thread's own audit trail, filtered to the
  outcomes `allowed` and `confirmed`. It fails closed: a caller that does not
  say who it is is denied, the same way a missing validator is denied.
- Both surfaces. `propose` returns no proposal and `commit` refuses, with
  `precondition not met: not actor of lab.op.result-enter`.
- `catalogue/guard.visible` reads the same rule, so where the actor is known
  the action is absent rather than greyed out.

The `senior_technologist` role exists to prove it: it holds `result.enter` and
`result.verify` both, which is the real arrangement in a small laboratory at
2am, and it is still refused on a specimen it keyed. `check.py` walks that
three ways in the pure half (rendered, machine, invisibility) and twice more
over HTTP against the SQLite file.

Closed on integration, 2026.09.13. `api/main.panel()` now passes
`caller(request)["id"]` to `state.thread_view`, so the Verify button is absent
for the person who entered the result instead of drawn and refused on the tap.
Seen in a browser on `:8001`: as `senior technologist` the composer holds one
pill, `Laboratory report`, and the agent says "Waiting at verification. Nobody
with your capabilities can act here"; switch to `pathologist` on the same
thread and `Verify` appears. `scripts/e2e.py` asserts both over HTTP.

Integration also found the hole underneath it. `api/main.say()` proposes as
`agent:<caller id>`, so the account that keyed a result could have the verify
proposed to itself by dictating the sentence instead of tapping the button.
The commit was still refused, but a card the person could never accept was put
in front of them, which is the greyed out button this rule exists to forbid.
`catalogue.guard.person()` now strips the prefix inside the one predicate both
enforcement and visibility read: an agent inherits the exclusions of whoever it
acts for. `catalogue/tests/test_guard.py` and `scripts/e2e.py` both hold it.

## 2. ~~The vocabularies are the PHC's, and they are closed.~~ FIXED

Wanted: `bundle.yaml` to declare its own stations, flags, capabilities and
roles, with closure checked per bundle. `vocab.STATIONS` is
`reception, nurse, doctor, lab, pharmacy, community`. `vocab.STATES` is
fifteen PHC flags. `vocab.CAPABILITIES` has no phlebotomy, accession or
release. `vocab.BUNDLES` has no phlebotomist, technologist or pathologist.

Did, and every one of these was a lie a user read on screen:

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

The renderer draws `human(label)` from the workflow, so the lies were visible,
not hidden. A laboratory would not ship this.

Fixed, 2026.09.12. `stations`, `states`, `capabilities` and `roles` are
declared in `bundles/<id>/bundle.yaml` and closure is checked per bundle:
`kernel/declarations.py` refuses any declaration, and any operation the
manifest lists, that names a word outside its own bundle. What stayed in
`catalogue/vocab.py` is what belongs to the kernel and the adapter rather than
to a facility, each with its reason in a comment: `CARE_RESOURCES` (the
adapter's tables), `KERNEL_RESOURCES`, `IRREVERSIBILITY` (the guard means one
thing by it), `INSTRUMENTS` and `KINDS` (the renderer implements exactly
these), and `BODY_SECTIONS` (a rule about documentation). `vocab.every()` is
the union and exists for one caller: `catalogue/build.py`, which lints
`catalogue/ops/*.md` and cannot know which facility a shared atom belongs to.

Every row of the table above is gone. The laboratory declares
`accession, phlebotomy, processing, verification, release` as its line;
`order.accessioned, specimen.collected, result.entered, result.rejected,
result.verified, report.released, lab.critical` as its flags;
`order.accession, specimen.collect, result.enter, result.verify,
report.release, worklist.read, reporting.view` as its capabilities; and
`phlebotomist, technologist, pathologist, senior_technologist` as its roles.
The PHC bundle keeps every word it had, moved verbatim into its own
`bundle.yaml`; its checks are unchanged and green.

One name is shared and it is not a lie: `lab.critical`. A laboratory is happy
to call a critical result that, and the questionnaire that raises it says
`flags: lab.critical` in `questionnaires/`, which this change does not own.

The module level `vocab.STATIONS / STATES / CAPABILITIES / BUNDLES` still
exist and are now the ACTIVE bundle's, chosen by `PHC_BUNDLE`, for the callers
that hold no bundle: `api/main.py`'s role table, `care_phc/permissions.py` and
`scripts/gen-fixtures.py`. So `PHC_BUNDLE=lab` gives the API a role list of
phlebotomist, technologist, pathologist and senior technologist, with no
change to `api/`.

## 3. Turnaround time is not declarable.

Wanted: a metric over a duration: for each thread, release time minus
accession time, then a mean or a percentile. A metric is `count(query)` or
`count(a) / count(b)` and a query has no join across two resources on the
same thread and no arithmetic on a field.

Did: accessioned count, released count, their ratio, and a critical rate.
The dashboard is titled "Turnaround today" and its plain words say it is
not turnaround time. A lab's single most watched number is missing.

## 4. ~~`states` must cover `vocab.STATES` exactly.~~ FIXED

Wanted: at least, or the bundle's own list. Did: six flags declared
`{stored: true}` that nothing raises and nothing reads
(`capture.consented, vitals.flagged, consult.documented, rx.confirmed,
dispensed.partial, followup.booked`). Lint passed. The workflow declaration
was forty percent padding.

Fixed with leak 2: a workflow must cover its own bundle's `states` exactly, so
the six padding flags are deleted and a flag belonging to another bundle is as
much a lint failure as a missing one. `lab.wf.specimen` declares seven flags
and every one of them is raised and read.

## 5. There is no amend or reject loop. Still open.

Wanted: a state rule that can say "more entries than rejections" or "the
latest report row is verified". The four rule forms are stored, exists,
gte (which also demands the right side be non zero) and all_of. Nothing
reads a latest row, nothing compares strictly.

Did: a rejection writes a report row with status rejected and leaves
`result.verified` false. The technologist cannot re-enter because
`result.entered` is already true. The specimen is stranded at verification.
`check.py` asserts the stranding.

Now that the vocabulary is the lab's own, the stranding is at least visible:
`result.rejected` is a declared flag, derived from the rejected report row,
and the worklist badges it `warn`. The specimen is still stranded.

## 6. A mapping cannot address an existing row.

Wanted: verification to move the preliminary report to final. A record is an
insert; the only update in the system is the adapter's private special case
for a second patient row on a thread. Did: verification writes a second
`diagnostic_report` row with `code: verification` and the decision as its
status, and `result.verified` is "a row with status verified exists". Two
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
issued time, `observation` no interpretation or reference range. Did: the whole accession form as a
`questionnaire_response` with `{json: payload}`, and the same for release.
The adapter was not changed, which kept the exercise honest, but it means
the referring clinician exists only as a JSON string.

## 10. The seed is the PHC's, and it runs under any bundle.

`adapters/local/store.py seed()` runs on any empty database. Under
`PHC_BUNDLE=lab` the worklist opens with six PHC patients carrying vitals and
prescriptions. Wanted: fixtures declared by the bundle. Did: nothing;
`check.py` asserts the six intruders are still there.

Now that the rest of the words are the laboratory's, this is the loudest thing
left on the screen and the first thing a visitor sees. On `:8001` today the
specimen line reads Accession 5, and the five names standing there are Kamala
Devi, Ramesh Kumar, Sunita Bai, Meera Patel and Iqbal Ahmed, with tokens like
`A01`. One seeded proposal is worse than a name: it is a pending
`phc.op.rx-prescribe` on a laboratory thread, an operation this bundle does not
declare, and the renderer draws it as a superseded agent card offering
Amoxicillin. It cannot be confirmed (the kernel 404s the operation) but it
should never have been drawn. A `seed` on the Bundle, defaulting to none, is
the shape.

The demo role half of this is fixed by leak 2: `api/main.py` builds its role
table from `vocab.BUNDLES`, which is now the loaded bundle's roles, so under
`PHC_BUNDLE=lab` the demo account is the union of the laboratory's four roles
and holds no PHC capability at all. It does hold `result.enter` and
`result.verify` together, so the demo account is refused verifying a result it
entered, which is the rule working rather than a leak.

## 11. `catalogue.json` holds one bundle. The MCP server embeds it at build.

Still open, and one half of it is now deliberate: see the end of this section.

`kernel.declarations` overwrites the five declaration keys with whichever
bundle ran last, and `check.sh` depends on it being `phc`. So the lab bundle
is linted with `--json` and never written. Meanwhile `operations` is
catalogue wide, so the Go server offers every bundle's operations to anyone
holding the capability, and the API 404s the ones outside the loaded bundle.
The checked in binary predated the lab atoms and offered none of them until
rebuilt. Wanted: manifests keyed by bundle, and an MCP server that reads
`/catalogue` from the kernel it is pointed at.

The three vocabulary keys (`capabilities`, `bundles`, `states`) stay the union
over every bundle on purpose, because `operations` is catalogue wide and the
Go server's own test asserts that an account holding every capability in the
file can see every operation in it. The API answers per bundle instead: it
serves the vocabulary of the bundle it loaded.

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
The turnaround board is gated on the laboratory's own `reporting.view` now,
which the pathologist holds; it used to be gated on `lab.result.validate`
because `reporting.view` belonged to the PHC's `mo`.

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
