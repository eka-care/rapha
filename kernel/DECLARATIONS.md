# Declarations: the authoring spec

The product is the declarations. This page is the whole rule set for writing
one. The machine half is YAML frontmatter and compiles into `catalogue.json`;
the human half is the markdown body. They are one file so they cannot drift.

Every declaration type uses the operation atom format from `catalogue/ops`:
`---` frontmatter, a `type:` field, an `id` equal to the filename stem, and a
body that starts with `## In plain words`. Operations keep their five
mandatory body sections. The other four types need only `## In plain words`.
Shapes after compilation are the dataclasses in `kernel/contracts.py`; this
page is the source form.

Ids are `<bundle>.<kind>.<name>` with kind one of `op`, `wf`, `view`, `inst`,
`metric`. Operations live in `catalogue/ops/`. Everything else lives beside
`bundle.yaml` in `bundles/<bundle>/`, one flat directory.

Vocabularies are closed PER BUNDLE. A capability, state, station or role that
the bundle's own `bundle.yaml` does not declare is a lint failure, never a new
entry. `catalogue/vocab.py` keeps only what belongs to the kernel and the
adapter rather than to a facility: `CARE_RESOURCES`, `KERNEL_RESOURCES`,
`IRREVERSIBILITY`, `INSTRUMENTS`, `KINDS` and `BODY_SECTIONS`. No em dashes
anywhere, frontmatter included.

## The bundle file

`bundles/<id>/bundle.yaml` lists what the kernel loads. Operations are
referenced by id, not copied.

```yaml
id: phc
version: 2026.09.10           # date-stamped; bump on any change
title: Primary health centre

stations: [reception, nurse, ...]        # this facility's line, in order
states: [registered, vitals.recorded, ...]   # its flags; the workflow covers these exactly
capabilities: [patient.find, ...]        # what a person may do here
roles:                                   # which capabilities each role holds
  nurse: [patient.find, vitals.record, ...]

operations: [phc.op.patient-register, ...]   # ids in catalogue/ops
workflows: [phc.wf.outpatient]
views: [...]
instruments: [...]
metrics: [...]
```

All five lists are required, and every id listed must exist, and every
declaration file in the directory must be listed. Compiles to
`catalogue.json["manifest"]`.

The four vocabulary keys are required too, and they are this bundle's whole
world: `catalogue.vocab.for_bundle(id)` reads them, and
`kernel/declarations.py` checks closure over them. Every operation the
manifest lists must hold a capability, a station, preconditions and emits that
are all in these lists, or the build fails. That is what stops a laboratory
borrowing a primary health centre's words, which is how a released report came
to be called `dispensed.complete`; see `bundles/LAB-LOG.md`.

A role holding a capability the bundle does not declare is also a build
failure. `catalogue/ops/*.md` is shared between bundles, so `catalogue/build.py`
lints an atom against the union of every bundle's vocabulary (`vocab.every()`)
and the per bundle closure above is what actually bites.

## The query grammar

One shape, shared by workflow states, summary sections and metrics, so an
adapter implements two reads (`count`, `select`) and nothing else.

```yaml
{resource: <vocab.CARE_RESOURCES>, where: {<field>: <cond>, ...}}
```

`where` is optional. A condition is a literal (equality), `"*"` (present and
not null), `{gte: v}` or `{lt: v}`. In a metric, `v` may be the string
`window.start`. Field names are CARE's emr model field names; the SQLite
adapter stores them verbatim and the CARE adapter maps them. The fields this
bundle uses: `abha_number`, `category`, `status`, `code`, `value`, `unit`,
`text`, `medication`, `dosage_instruction`, `conclusion`, `created_by`,
`created_date`, `flag`. How a resource joins to a thread is never written in a
declaration; the adapter knows its own schema.

A metric numerator may name `thread_flag` (in `vocab.KERNEL_RESOURCES`),
which is how stored flags get counted. Nothing else may.

## 1. Operation

Required frontmatter: `id, type, kind, short, title, summary, capability,
station, instrument, preconditions, irreversibility, input, writes, emits,
surfaces, verified`, plus `mapping` on a `kind: write` operation. Optional:
`scope_qualifier, related`. See `catalogue/build.py` REQUIRED and any file in
`catalogue/ops`.

`instrument` on an operation is its default capture method. Instrument
declarations (section 4) add accelerators on top of it.

### Preconditions: flags, and who acted

A precondition is a flag from the bundle's `states`, optionally `not ` prefixed.
There is one other form:

```yaml
preconditions:
  - result.entered
  - not result.verified
  - not actor of lab.op.result-enter     # separation of duties
```

`actor of <operation id>` is true when the caller has already performed that
operation on this thread. The kernel reads the thread's own audit trail for
the answer (`kernel/state.performers`) and hands it to the guard, which
evaluates it on both surfaces. It fails closed: a caller that does not say who
it is gets a denial, never a pass. `catalogue/guard.visible` uses the same
predicate, so where the actor is known the action is absent rather than
refused on tap; where it is not, the action is drawn and the tap is refused
with the reason.

Lint refuses an `actor of` naming an operation that does not exist, or one the
bundle does not load, because a rule that can never fire reads like a
protection and is not one.

### The mapping: which answer becomes which column

`writes` says which resources a payload becomes. `mapping` says which answer
becomes which field of one, and it is required on every `kind: write`
operation. Without it an adapter has to re-derive what a blood pressure is,
and the second adapter re-derives it differently.

```yaml
mapping:
  ignored: [method, consent_given]     # answers deliberately not stored
  records:
    - resource: observation            # must be one of writes
      per_question: [systolic, diastolic, pulse]   # one row per answered question
      fields:
        created_by: {actor: id}          # required: every row says who wrote it
        category: {const: vital-signs}
        code: {question: link_id}
        value: {question: answer}
        unit: {question: unit}
```

A record names one `resource`, an optional fan out, and its `fields`. The two
fan outs are alternatives: `per_item: <link_id>` walks a repeating structured
answer and gives one row per item, `per_question: [<link_id>]` gives one row
per answered question. With neither, a record is one row.

A field's value is a single key source:

| source | value |
|---|---|
| `{answer: <link_id>}` | the payload's answer |
| `{const: <literal>}` | a literal |
| `{item: <key>}` or `{item: [<key>]}` | the current item's value, first non empty |
| `{minus: <key>}` | the same, negated, for a stock decrement |
| `{question: link_id \| answer \| unit}` | about the current question |
| `{joined: [<link_id>]}` | non empty answers joined with a space |
| `{note: [<link_id>]}` | non empty answers as labelled paragraphs |
| `{json: payload}` | the whole payload as sorted JSON |
| `{actor: id}` | who is performing this operation |

`{question: unit}` reads `styling_metadata.phc.unit` from the questionnaire,
which is why no adapter repeats a unit: it is written once, next to the range
that validates it.

Lint refuses, and every one of these is a build failure and not a warning:

- a record naming a link_id the questionnaire does not have, anywhere;
- a record naming a resource the operation does not list in `writes`, or a
  `writes` entry no record maps anything into;
- `{item: ...}` or `{minus: ...}` without `per_item`, `{question: ...}`
  without `per_question`, `{question: unit}` where a listed question declares
  no unit;
- a required question that is neither mapped nor listed under `ignored`. An
  answer with nowhere to go is a clinical value dropped in silence, so
  dropping one has to be written down;
- a record with no `{actor: id}` field. Every row says who wrote it. A row
  with a null author is why "the same person must not verify their own
  result" could be declared nowhere and enforced nowhere.

`{actor: id}` and `{const: ...}` do not read the payload, so a record made
only of them is still written every time, and an unanswered form is still no
row rather than a row carrying only its author.

A record whose fields are all `const` is written every time. A record with any
answer derived field is written only when one of them produced a value, so an
unanswered question is no row rather than an empty one. Column names are not
linted here, because the kernel must not know an adapter's schema:
`adapters/local/tests/test_store.py` checks them against its own tables, and
`adapters/local/store.py` raises on a column it does not have rather than
dropping the value.

The compiled mapping is not written into `catalogue.json`. Nothing outside the
kernel turns a payload into rows, and the MCP server proposes only; add it to
the compiled artifact when an out of process consumer needs it.

Worked example: `catalogue/ops/phc.op.vitals-record.md`. The code is
`kernel/mapping.py` and the checks are `kernel/tests/test_mapping.py`.

## 2. Workflow

The order operations happen in, and how each state flag is derived. This is
`care_phc/thread.py` `LINE` and `derive()` written down.

| field | required | value |
|---|---|---|
| `id, type, title, summary` | yes | `type: workflow` |
| `subject` | yes | the resource a thread is about; `encounter` today |
| `steps` | yes | ordered list, see below |
| `states` | yes | ordered map, flag to rule; must cover the bundle's `states` exactly |

A step:

| field | required | value |
|---|---|---|
| `station` | yes | one of the bundle's `stations` |
| `done_when` | yes | a flag; the step is done once it is true |
| `applies_when` | no | a flag; while it is false the step is skipped, not pending |
| `operations` | yes | op ids drawn at this station, in the order to offer them; each op's own `station` must match |

The current station is the first step that applies and is not done. `None`
once every applicable step is done. That is `thread.station()` exactly.

A state rule is one of four forms, evaluated in declaration order, and a
rule may only reference a flag declared above it:

```yaml
flag: {stored: true}                     # the store holds it; no record answers it
flag: {exists: <query>}                  # count > 0
flag: {gte: [<query a>, <query b>]}      # count(a) >= count(b) and count(b) > 0
flag: {all_of: [flag, "not flag", <rule>]}
```

The compiled `Workflow.stored` is the list of flags with `{stored: true}`.
`Store.raise_flag` refuses any other flag, as `EncounterThread.raise_flag`
does today.

### How LINE becomes a workflow

`care_phc/thread.py`:

```python
LINE = (
    ("reception", "registered", None),
    ("nurse", "vitals.recorded", None),
    ("doctor", "consult.documented", None),
    ("lab", "lab.resulted", "lab.ordered"),
    ("pharmacy", "dispensed.complete", "rx.confirmed"),
)
```

is, tuple for tuple, the `steps` list of `bundles/phc/phc.wf.outpatient.md`,
with the third element becoming `applies_when`. The conditional steps are the
point: a patient nobody ordered a test for has `lab.ordered` false, so the
lab step is skipped and the station moves on to pharmacy or to `None`.

`derive()` becomes `states`. Three examples from the same file:

```yaml
vitals.recorded:                              # if s.vitals_observations:
  exists: {resource: observation, where: {category: vital-signs}}
dispensed.complete:                           # dispensed >= prescribed, prescribed > 0
  gte:
    - {resource: medication_dispense}
    - {resource: medication_request, where: {status: active}}
abha.pending:                                 # registered and no abha
  all_of: [registered, "not abha.linked"]
vitals.flagged: {stored: true}                # STORED
```

`kernel/tests/test_contracts.py` asserts the declaration and `thread.py`
agree, so the two cannot diverge while both exist.

Complete worked example: `bundles/phc/phc.wf.outpatient.md`.

## 3. View

A queue, summary or dashboard declared as a query. The renderer draws each
`kind` one way for every bundle; there is no per-screen code.

| field | required | value |
|---|---|---|
| `id, type, title, summary` | yes | `type: view` |
| `kind` | yes | `queue`, `summary`, `dashboard` |
| `capability` | yes | one of the bundle's `capabilities`; who may open it |
| `workflow` | queue, summary | a workflow id |

Queue fields: `scope` (`today`, `open`, `all`; default `today`), `group_by`
(`station` or a flag; omitted means one list), `columns` (subject fields to
show), `badges` (flag to `warn`, `crit`, `ok`, `mute`). Rows are
`QueueRow`; groups come back in workflow step order with a trailing group for
`station: None`.

Summary fields: `sections`, an ordered list where each item has `title` and
exactly one of `show` (`line`, `flags`, `actions`, `proposals`, `audit`) or
`resource` with optional `where` and `fields`. Called with `?thread=`.

Dashboard fields: `metrics` (ids), `window` (`day`, `week`, `month`, `all`;
overrides each metric's default).

Worked examples: `bundles/phc/phc.view.station-queue.md`,
`phc.view.patient-summary.md`, `phc.view.facility-dashboard.md`.

## 4. Instrument

How a value is captured. Declared per field or question type, never per
screen. An instrument only changes how a value arrives: it produces a
`Draft`, the renderer puts the draft values in editable fields, a person
taps commit, and the guard and the range rule run on the tapped values as if
typed. The kernel has no path from an instrument to a write.

| field | required | value |
|---|---|---|
| `id, type, title, summary` | yes | `type: instrument` |
| `kind` | yes | `form`, `device`, `constrained-voice`, `scribe` |
| `operations` | yes | op ids this applies to |
| `fields` | no | link_ids in those operations' questionnaires; empty means all |
| `types` | no | question types; empty means all |
| `grammar` | constrained-voice | `number`, `choice`, `date`, `free` |
| `readback` | yes | must be `required` |
| `commit` | yes | must be `tap` |
| `fallback` | yes | `keypad` or `form` |

Lint rules that encode the product's speech rule:

- `readback: required` and `commit: tap` are the only accepted values. This
  is the "one forty over ninety" rule: a misheard discrete value is silent,
  plausible and unrecoverable, so it is always shown and always tapped.
- A `scribe` instrument may not list an operation whose default
  `instrument` is `device`. Ambient recognition is worst at short numeric
  utterances, so vitals get constrained voice or nothing.
- A `scribe` instrument is offered only when `capture.consented` is in the
  thread's flags. The renderer checks; the guard does not know about
  instruments and should not.
- A `Draft` with no values means the instrument failed. The renderer shows
  the fallback. Voice fails closed to a keypad.

Worked example: `bundles/phc/phc.inst.vitals-voice.md`.

## 5. Metric

A certified count or ratio, evaluated locally by the analytics client.
Data never leaves the machine; a metric has no export.

| field | required | value |
|---|---|---|
| `id, type, title, summary` | yes | `type: metric` |
| `unit` | yes | `count`, `percent`, `ratio` |
| `window` | yes | `day`, `week`, `month`, `all`; the default bucket |
| `numerator` | yes | a query; may use `{gte: window.start}` |
| `denominator` | `percent`, `ratio` | a query |
| `certified_by` | no | free text; say honestly who checked it and against what |

Value is `numerator / denominator` (times 100 for percent), or the count for
`unit: count`. A zero denominator yields `value: 0` and `denominator: 0`, not
an error, because an empty week is a normal week.

Worked example: `bundles/phc/phc.metric.abha-coverage.md`.

## Compilation

`python3 -m catalogue.build` today lints `catalogue/ops` and writes
`catalogue.json` with `capabilities, bundles, states, operations`. The build
agent extends it to read `bundles/<id>/bundle.yaml` and add `manifest,
workflows, views, instruments, metrics`, keyed by id, with the frontmatter
fields verbatim plus `description` (the plain-words section). The existing
four keys do not change shape; `care_phc_mcp/catalogue.go` keeps working
unmodified because Go ignores unknown keys.
