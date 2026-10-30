# The application architecture: Eka Scribe for primary health centres

> **For agentic workers:** the only checkbox steps in this document are in
> section 11. Everything above it describes the code that exists on this
> branch, not a plan. Where something is not built, it says so and names the
> plan step that covers it. Every check named here is mutation proved and the
> mutations are in section 10.

**What this is.** A scribe first clinical workspace for Indian primary health
centres, built on Eka's platform. A patient is a thread. Staff speak or type,
and records are committed at stations. It is not a general electronic medical
record and must not become one. It emits ABDM compliant FHIR R4.

**What this document decides.** Where each seam falls in the code that is
actually here, what each layer may know, and how a record travels from a
spoken sentence to a document under a patient's ABHA number. It is written
against the branch `feat/phc-catalogue-and-guard` at commit `c9d9467`, where
`sh scripts/check.sh` exits 0 with 427 `ok` lines and nothing skipped.

**What is already decided elsewhere, and is not reopened here.**
`kernel/ARCHITECTURE.md` and `kernel/DECLARATIONS.md` hold the declaration
model. `docs/superpowers/plans/2026-10-30-core-and-plugins.md` holds the core,
plugin and bundle split. `docs/superpowers/plans/2026-10-30-coded-data-symbiosis.md`
holds coded data, whose decisions were settled on 2026-10-30. This document
builds on all three, resolves what they left open where this architecture needs
it settled, and section 12 lists everything in them that the code now
contradicts.

---

## 1. The one rule the whole thing exists to hold

Clinical capability is declared in markdown atoms compiled to
`catalogue.json`, never coded. No engine may name a station, a flag, a
capability, a bundle, or now a clinical concept.

This is not a style preference. It is the only reason the same kernel runs a
primary health centre and a diagnostics laboratory from two directories of
markdown, which `bundles/lab/check.py` proves on every run with 36 checks and
not one word of a health centre's vocabulary. And it is the reason the CARE
adapter could be deleted, 2135 lines, without a rewrite: nothing above it
knew its name.

Three layers now enforce it mechanically, in both directions:

- `web/src/ui.check.ts` derives every word the loaded bundle owns from the
  compiled catalogue and fails if a renderer file types one as a literal.
- `kernel/declarations.py` closes each bundle's vocabulary: a `phc.*` atom may
  name only what `bundles/phc/bundle.yaml` declares.
- `scripts/check_vitals.py` does the same for the engine's Python, over the
  clinical concepts rather than the facility's words: no module in `kernel/`,
  `catalogue/` or `adapters/local/` may type a reading's name, its LOINC code
  or its unit. Self growing, because the word list is read from the
  questionnaires rather than typed.

The third one is new and it exists because this branch added a layer that
could have broken the rule invisibly. A single `if code == "29463-7"` in the
FHIR projection would be the renderer's failure mode moved one layer down,
where nobody looks.

---

## 2. The layering, and what each layer may know

Seven layers. Each one is named by what it may know, because that is the only
definition that survives a refactor.

```
  DECLARATIONS      bundles/<id>/*.md, catalogue/ops/*.md, questionnaires/*.json
                    data. knows clinical meaning. knows no code.
        |  python3 -m catalogue.build ; python3 -m kernel.declarations
        v
  TERMINOLOGY       terminology/*.json  +  kernel/terminology.py
                    knows which codes exist. knows no station and no workflow.
        |
        v
  +-----------------------------------------------------------------+
  |  KERNEL                                                          |
  |   catalogue/guard.py      may this write happen                  |
  |   catalogue/validate.py   is this payload a valid answer         |
  |   kernel/declarations.py  load, lint, close a bundle             |
  |   kernel/mapping.py       which answer becomes which column      |
  |   kernel/state.py         which flags are true, where the thread |
  |                           stands, which actions are drawn        |
  |   kernel/proposals.py     the write path, and the audit          |
  |   kernel/views.py         a declared query, evaluated            |
  |   kernel/spine.py         one subject across visits              |
  |   kernel/fhir.py          rows to an ABDM document               |
  |  knows: operations, threads, stations, views, instruments,       |
  |         capabilities, code systems. knows no clinical word.      |
  +-----------------------------------------------------------------+
        ^                      ^                        ^
        |                      |                        |
   RENDERER              MACHINE SURFACES          PROJECTION OUT
   web/                  care_phc_mcp/, agent/     care_phc/connectors/
   draws ThreadView      propose_* only            abdm, scribe
   and ViewResult        no confirm verb           one interface each
        |
        v  kernel only, through the Store protocol
  +-----------------------------------------------------------------+
  |  ADAPTER        adapters/local, SQLite, FHIR shaped flat tables  |
  |  knows: its own schema, and how a row joins to a thread.         |
  |  knows no guard, no state rule, no clinical meaning.             |
  +-----------------------------------------------------------------+
```

### What may import what

The table in `kernel/ARCHITECTURE.md` stands, with one row added by this
branch.

| layer | may import | may not |
|---|---|---|
| declarations | nothing; they are data | any code |
| `terminology/*.json` | nothing; generated data | any code |
| `catalogue/` | stdlib, yaml | kernel, adapters, clients |
| `kernel/` | `catalogue/`, `kernel/contracts`, `terminology/*.json` through `kernel/terminology.py` | adapters except through the `Store` protocol, Django, **any network** |
| `adapters/*` | `kernel/contracts`, its own driver | the guard, state derivation, the renderer, the terminology |
| clients | the API over HTTP, and `catalogue.json` | the kernel in process, any adapter |
| connectors | `kernel/contracts` for `Draft`, their own vendor SDK | the Store, the guard, the kernel's write path |

The `kernel/` row is the one that matters most, and the clause in bold is why
the terminology is a local file. A kernel module that can open a socket is a
kernel module that can hang a clinic.

### The seams, as interfaces

Five seams. Each has a real implementation and, where absence is possible, a
degradation. The seam is the thing of value, because it is what makes the far
side swappable without a rewrite. `Store` has already proved that once.

**1. `Store`, in `kernel/contracts.py`.** Ten methods, the model for every
other seam here, unchanged by this work.

```
count(resource, *, thread, where) -> int
select(resource, *, thread, where, fields, limit) -> list[dict]
threads(*, workflow, scope) -> list[ThreadRef]
stored_flags(thread) -> frozenset[str]
write(resource, record, *, thread) -> str
raise_flag(thread, flag) -> None
put_proposal(proposal) -> None
proposals(thread, *, status=None) -> list[Proposal]
append_audit(record) -> None
audit(thread) -> list[AuditRecord]
```

Every read is scoped to a thread. How a resource joins to the thread's subject
is the adapter's business and is not expressible in a declaration, which is
what keeps declarations portable and adapters honest. `adapters/local/tests/test_store.py`
pins these ten names against the class.

One gap, stated rather than worked around: there is no `open_thread` on the
protocol. `adapters/local/store.py` has one and the comment says it is a gap
worth reporting. It is reported here. Opening a thread records no clinical
fact, so it is not urgent; the honest fix is an eleventh method when a second
adapter needs it.

**2. `Terminology`, in `kernel/terminology.py`.** Three methods.

```
validate(valueset, code) -> bool
bound(valueset, code)    -> Coding          # the only constructor
expand(valueset, query, count) -> [Coding]  # for a picker
```

`validate` is on the write path and works with no network. `bound` is the
only way a `Coding` comes into existence anywhere in the product, and it
consults `validate` before it returns. `expand` is for a picker and is allowed
to be poorer offline than online.

Implementation: `CachedTerminology`, reading `terminology/<slug>.json`. Read
only and generated. Nothing in the product writes a value set, which answers
"who may edit one": nobody, here.

**3. `Codification`, not built.** The seam's shape is settled in the coded
data plan section 2.2 and is one method.

```
suggest(text, valueset, context) -> [{coding, score, linked}]
```

One implementation, Eka's medical linking endpoint. The stub returns an empty
list and **everything must still work when it does**: a facility with no
network gets a picker instead of a prefill, which is slower and not broken. If
anything becomes unusable when `suggest` returns nothing, codification has
become load bearing, which the plan's own table forbids. Not built because
nothing in the PHC bundle binds an *answer* yet; see section 6.

**4. Capture, in `care_phc/connectors/scribe/base.py` and `api/extract.py`.**

```
submit(audio, operation) -> session            # Eka
fetch(session)           -> Draft              # Eka
extract(transcript, fields) -> {link_id: {value, confidence, evidence}}   # ours
build_draft(operation, schema, answers, transcript, *, instrument, today) -> dict  # ours
```

The division is settled: Eka owns audio to transcript, we own transcript to
questionnaire values. The rule that makes the second half ours is in
`api/extract.py` and nothing upstream does it:

> a field is answered only with a verbatim span copied from the transcript;
> no span, no answer.

**5. Bundle out, in `kernel/fhir.py`.**

```
sections(profile) -> {slice: {title, code}}
observation(row, *, subject, encounter, performer) -> dict
document(store, thread, *, profile, sections_wanted, now) -> dict
```

Rows in, an ABDM DocumentBundle out. `sections_wanted` maps a profile's own
section slice to the queries whose rows fill it, because which section a kind
of row belongs in is a declaration and not this module's business.

Below that sits the gateway, `care_phc/connectors/abdm/base.py`, which already
exists and already declares `link_care_context` irreversible.

---

## 3. How a record travels, end to end

One blood pressure, from the nurse's mouth to a document a district hospital
can read. Every arrow below is code on this branch except the two marked.

**1. Capture.** The nurse taps the microphone. The renderer offers it only
because `phc.inst.vitals-voice` declares `operations: [phc.op.vitals-record]`
and `requires: capture.consented`, and only because the thread holds that
flag. Constrained voice, not ambient scribe: `phc.op.vitals-record`'s own atom
says why, and a short numeric utterance is what speech recognition handles
worst.

**2. Extract.** `api/extract.py` fills the questionnaire the operation names
from the transcript, and drops any answer whose evidence span is not in the
transcript. `api/fill.py build_draft` coerces each heard value to the type its
field can hold, refuses the ones it cannot, prunes the ones `enable_when`
disables, and returns a `tick` list naming every non text value the person
must confirm individually.

**3. Readback.** The draft is drawn in editable fields. Commit stays disabled
until each owed value is ticked. The kernel cannot enforce that half and says
so: the guard sees a payload of tapped values and cannot tell which were heard.
`kernel/tests/test_contracts.py` owns the structural half, that every non text
value a scribe instrument can fill is a type the draft builder puts in `tick`;
`web/src/scribe/scribe.check.ts` owns the renderer half.

**4. Validate.** `catalogue/validate.py`, from the questionnaire the operation
names, so there is one definition of a valid payload and every surface uses
it. Required answers, types, choices, and the range rule. A reading outside
physiological range refuses the write and requires an explicit override
carrying a reason, which is recorded rather than waived.

**5. Guard.** `catalogue/guard.evaluate`, seven steps, four of them here:

1. schema. No validator is a denial, never a pass.
2. capability, then its scope qualifier.
3. preconditions over thread state, and over who has already acted here.
4. irreversibility. An irreversible operation needs the rendered surface and
   an explicit confirm, checked in that order so a machine asserting
   confirmation gets nowhere.

Then the caller's three: **the audit row is written before the write
executes**, the write, the state emit. `kernel/proposals.py` is that caller
and it is the only one. There is no path to `Store.write` that did not come
through here.

**6. Code.** `kernel/mapping.records` turns the payload into rows, one row per
answered reading, as the operation's own `mapping` declares. The code column
gets the LOINC concept the question binds to, the system it came from and the
display the value set gave it. `kernel/mapping._bound_fact` re-checks the code
against the value set before it will fill the column.

**7. Store.** Six readings are six `observation` rows, flat, each carrying its
author. The adapter refuses a column it does not have rather than dropping the
value, because a silently dropped clinical value is the worst failure it could
have.

**8. Derive.** `kernel/state.flags` walks the workflow's state rules over
`Store.count`. `vitals.recorded` becomes true because a vital signs
observation exists. `vitals.flagged` is stored, raised by
`catalogue/validate.flags` from the critical band the questionnaire declares.
The thread's station moves from `nurse` to `doctor` because the workflow says
so, and the doctor's first action becomes reviewing a flagged reading rather
than starting the consultation.

**9. Project.** `kernel/fhir.document` reads the rows back and builds an NRCeS
`WellnessRecord`: a Composition with a `VitalSigns` section, a Patient, an
Encounter, a Practitioner per author, and one Observation per reading with a
LOINC `code.coding` and a UCUM `valueQuantity`. The bundle identifier and
every `fullUrl` are derived from the row ids with uuid5, so the same rows
project to the same document and ABDM sees one visit once.

**10. Send.** *Not built.* `care_phc/connectors/abdm/base.py` is where it
attaches, `link_care_context` is already declared irreversible, and ECDH
encryption is M2's. Covered by coded data plan step 7.

A machine on the same path diverges at step 5 and nowhere else: a write from
the MCP surface is a proposal, never a commit. Confirming it is a second guard
pass on the rendered surface with the payload as the person edited it, judged
against the thread state as it is then. A proposal is a stored request, not a
stored permission.

---

## 4. Where Eka attaches, and how each piece degrades

Four attach points. The rule for all four: **absence degrades the product, it
does not break it.** A primary health centre with no network must still see
its queue, record a vital sign and finish a visit.

| Eka service | attaches at | without it |
|---|---|---|
| auth | *nothing* | the role comes from a header and the service is meant for localhost. See the ceiling below. |
| patient directory | *nothing yet* | patients are rows in the local store. The CARE adapter that used to hold them was deleted when patients moved to Eka's directory, so this is currently a gap rather than a degradation. |
| scribe | `api/scribe.py`, through `care_phc/connectors/scribe/base.py` | `api/scribe.py` raises with a sentence ending "or type the note", `api/main.py` turns it into a 503, and the doctor types. No consultation is blocked. |
| ABHA | `care_phc/connectors/abdm/eka.py`, behind `AbdmConnector` | `GET /abha/config` returns `hip_id: None`, which the journey reports honestly instead of pretending. A patient with no ABHA is an ordinary patient: the number is a FHIR identifier, never our row id. |
| codification | *not built*, seam shape settled | a picker instead of a prefill. The stub returns nothing and everything works. |
| terminology | `terminology/*.json`, through `kernel/terminology.py` | there is no "without it". It is local on purpose, so the offline path is the only path rather than a fallback nobody tests. |

The last row is the important one and it is a direct lesson from CARE.
`care/emr/fhir/client.py` is one `requests.request` with no try, no retry and
no circuit breaker, and its cache TTL is ten seconds. A terminology server
that is down turns a correct code into a 500; one that answers oddly turns it
into a 400 telling the clinician their correct code is invalid. Neither can
happen here, because there is no socket on the path at all. CARE's own test
suite replaces its value set validator with the identity function for the
whole run (`care/utils/tests/base.py:19`, with a comment admitting they could
not find a better way), so the best idea in that codebase is never exercised
in its CI. Ours is a constructor argument, so a check passes a fake and the
gate exercises the real one.

**Ceiling, stated rather than hidden.** `caller()` in `api/main.py` has no
authentication, and `ROLES["demo"]` is the union of every declared capability.
So the browser can only be a superuser, which means no capability based
behaviour can be demonstrated in the browser until there are accounts. Every
proof of a capability rule in this repository is therefore server side, in
`bundles/phc/check.py`, `bundles/lab/check.py` and `scripts/check_vitals.py`.
The core and plugins plan already records this as decision 4 and it is still
the owner's.

---

## 5. The plugin boundary

The core and plugins plan decides this and is not duplicated. Its three nouns
hold: core is `kernel/`, `catalogue/`, `adapters/local`; a plugin is a
directory contributing declarations, routes, a renderer surface, store
behaviour and a capability, removable without editing anything outside itself;
a bundle is a facility's choice of plugins plus its own vocabulary.

Two things this architecture needs settled that the plan left open, and one
correction to its inventory.

**`kernel/terminology.py` and `kernel/fhir.py` are core, not plugins.** Both
are pure, both name no clinical word, both are checked for that, and neither
has a vendor in it. More to the point, neither can be switched off: a facility
that can turn off "codes are checked against their value set" has turned off
the thing that makes its records mean anything elsewhere. A plugin is defined
by having an off switch, so these are not plugins.

**`terminology/` is core data, not a bundle's.** LOINC and UCUM are nobody's
choice. A bundle declares *which* concept each of its questions binds to, which
is the bundle's business; *whether that concept exists* is not. This is the
same division as `catalogue/vocab.py CARE_RESOURCES`, which is the adapter's
grammar rather than a facility's words, and it is why the directory sits
beside `questionnaires/` rather than inside `bundles/<id>/`.

**Correction to the plan's section 6 inventory.** It says `pharmacy/stock` is
"the only candidate that adds resources". Coded data now adds columns too,
three to `observation`, and they belong to no plugin: they are core, for the
reason above. The inventory's point survives, which is that a plugin owning a
kernel verb is a problem; the parenthetical does not.

**On decision 6, whether `api/fill.py` becomes `kernel/fill.py`.** Not done,
because the brief for this work holds it as the owner's. My recommendation, as
the architect the directory is reserved for, is yes, and this branch is the
argument: adding `kernel/terminology.py` and `kernel/fhir.py` establishes that
a pure, vendor free, clinically mute module belongs in `kernel/`, and
`api/fill.py` is all three. The dependency already points the wrong way,
because `kernel/tests/test_contracts.py` imports it to check a clinical safety
property. Moving it is two importers and makes the scribe plugin's boundary
honest. The decision is still the owner's; the gap is no longer ambiguous.

---

## 6. The data model

### What we persist

Flat rows, one table per resource name in `catalogue/vocab.py CARE_RESOURCES`,
columns named exactly as the query grammar names them. The tables that carry
clinical facts today:

| table | carries | coded |
|---|---|---|
| `patient` | demographics, `abha_number` | no. Demographics are not clinical concepts. |
| `encounter` | the thread itself, its token and status | no |
| `observation` | `category`, `code`, `code_system`, `code_display`, `value`, `unit`, `unit_system` | **yes**, this branch |
| `condition` | `code`, `verification_status` | not yet. Needs repeating groups, plan step 4. |
| `notes` | narrative text | no, and narrative stays narrative |
| `medication_request`, `medication_dispense` | `medication`, dosage, quantity, status | not yet. Needs a medication ontology, plan step 4. |
| `service_request`, `specimen`, `diagnostic_report`, `inventory_item` | the laboratory and pharmacy lines | not yet |
| `thread_flag`, `proposal`, `audit` | the kernel's own records | not applicable |

A coding is three columns and not one: the code, the system it came from, and
the display the value set gave it.

### Why flat rows and not documents

Three reasons, in the order they bite.

1. **A district count is a `WHERE`.** `WHERE code = '8480-6'` means the same
   thing in every facility in the state. A document store makes that a JSON
   path expression, and the people who need the number have a spreadsheet, not
   a query planner. CARE stores its codings in untyped `JSONField`s
   (`care/emr/models/observation.py:9-11`), which is exactly why nothing there
   can count them without unpacking JSON in SQL.
2. **A trend is an `ORDER BY`.** A hypertensive patient's blood pressures
   across eight visits is a column scan over a spine, which `kernel/spine.py`
   already joins by what the workflow declares.
3. **A document is an envelope for sending, not a record for keeping.** A
   DocumentBundle carries a signature, a timestamp and a Composition that
   exists to say "these resources were published together on this date".
   Keeping it would mean keeping a snapshot that goes stale the moment a
   correction lands. So we store rows and generate the document at the edge.

`code_display` is stored rather than looked up again on read, for two reasons
that pull the same way: a screen that draws a row must not need a terminology
to draw it, and the display is part of what was recorded. A value set that
renames a concept next year must not silently restate what a nurse wrote this
year.

### How a question binds to a concept

Two forms, because there are two kinds of question. This is CARE's division
and it is the right one.

**`code` on the question, when the question is the concept.** Systolic blood
pressure is always LOINC `8480-6`. Declared as a bare code and not a triple:

```json
{"link_id": "systolic", "type": "integer", "code": "8480-6", ...}
```

The system comes from the value set and the display comes from the cache, so
neither can be retyped wrongly. CARE declares all three per field and its
displays are free text as a result, with `system` optional while `code` is
required, which is how a systemless code gets in. Here a `Coding` always has a
system, because the value set carries it and every `Coding` came from one.

**`unit` on the question, read from `styling_metadata.phc.unit`.** Not moved
and not duplicated. The unit is still declared exactly where
`kernel/DECLARATIONS.md` already said it lives, once, next to the range that
validates it, because the symbol a UCUM value set holds is the same symbol the
renderer prints and the voice grammar matches. What is new is that every unit
in both shipped bundles, nine of them, is now checked against UCUM at build
time.

**`answer_value_set` on the question, when the answer carries the concept.**
The third form, for diagnosis and medication, where the question is a slot and
"type 2 diabetes" is the concept. **Not implemented.** Nothing in the PHC
bundle binds an answer yet, and an unused binding is a promise with no check
behind it. It arrives with repeating groups, plan step 4, and it is the form
that needs codification, which is why section 2 seam 3 is a shape and not a
file.

### How the binding is held

Invariant I1 says a stored coding is in the value set its question binds to,
enforced as a type at the write path and not as a lint. It is held in two
places, and the reason it needs two is worth stating because it is a genuine
amendment to the plan.

**At build time**, `kernel/mapping._compile_record` resolves each of a
question's bound facts through `Terminology.bound()`, whose only way to return
anything is to have found the code in the value set. A `Coding` cannot exist
otherwise: its constructor is gated by a module private sentinel that
`kernel/terminology.py` never exports, so `Coding(...)` called from any other
file raises `UnboundCoding`. A question declaring a code its value set does
not hold fails the build, naming both.

**At write time**, `kernel/mapping._bound_fact` re-checks the code against the
same authority before it will fill a column with it, and refuses a coding
column that would land null.

Why not just the type, as the plan says? Because the compiled mapping
travels. `web/src/structured.ts` reads an operation's mapping to know which
sub fields a structured item may carry, `api/main.py` serves it on
`/operations`, and `web/src/messages.check.ts` runs `json.dumps` over the whole
of it. A `Coding` object there is a 500 on the thread panel, which the gate
found. So the facts arrive at the write path as strings, a string carries no
proof, and the proof is re-established where the row is made. The re-check is
a dictionary lookup in an lru_cached local file: no socket, no database,
nothing that can be down. CARE pays a Postgres read plus an HTTP round trip
per bound field per write for the same guarantee, which is six of each before
a `201` on a MedicationRequest.

**One honest hole.** A mapping record can still put a literal in a code column
with `{const: ...}`. The kernel cannot refuse that without knowing which of an
adapter's columns hold a coding, which the layering forbids in as many words:
"Column names are not linted here, because the kernel must not know an
adapter's schema." What stops it today is that it is written in the atom and
the atom is reviewed. The fix, when there is a second adapter, is a `coding:`
column kind declared on the resource, which is the right place for it.

### Certainty and attribution are fields, not cleverness

FHIR already has them, so nothing is invented. A denied symptom is
`verification_status: refuted`. A past illness is `resolved` with an onset. A
scribe's guess is `unconfirmed`. There is no human coding queue and nothing
blocks on a person confirming a code; the status is the mechanism. That is
invariants I4 and I6, settled, and it is why `condition` already carries a
`verification_status` column with nothing writing it yet.

A stored row is always `status: final` in the projection, and that is not
laziness. There is one path to a stored row and it has a person's tap on it. A
proposal is not a row: the unconfirmed state lives on the proposal, in the
kernel, and never reaches the store, so there is nothing that could be
`preliminary`.

---

## 7. Error handling, offline, and a half written visit

### The four failure classes, and what each one does

| failure | where it is caught | what the clinic sees |
|---|---|---|
| an invalid answer | `catalogue/validate.py`, guard step 1 | the field, the range and a sentence. A reason overrides, and is recorded. |
| an action not allowed | guard steps 2 to 4 | for a capability or a precondition the person can never satisfy, the action is absent rather than greyed out. For one they could, a sentence a clerk reads correctly, never the literal precondition string. |
| a code nothing vouches for | the build, or `_bound_fact` on the write | the build fails naming the code and the value set. At write time the row is not made. |
| a vendor that is down | the connector, one error type per boundary | a 503 with a sentence that names the fallback. The scribe's ends "or type the note". |

Two rules behind that table. Every error that crosses a connector boundary is
that connector's own type, scrubbed on the way out, because an SDK exception
carries the gateway's response body and a local file path, and the file path of
a consultation recording is not a thing to put in a traceback. And a guard
denial carries a machine stable `kind` alongside the human sentence, so a
caller can react to the shape of a denial without parsing prose a copy pass is
free to reword.

### Offline

The design target is a primary health centre on a bad line, not a hospital on
a leased one. Three consequences, two of them already true:

- **The terminology is local.** Already true, by construction. This is the one
  that would otherwise stop a nurse recording a blood pressure.
- **The store is a file.** Already true. `adapters/local/store.py` is SQLite
  with WAL on a thread local connection, and nothing in a write path reaches a
  socket.
- **Audio and ABDM are queues.** *Not built.* A recording and a document are
  both "something to hand to a vendor when the line comes back", and neither
  is a clinical write. They are the only two things on the whole path that
  need a network, which is the property to protect rather than a problem to
  solve. Section 11 has the step.

### What happens to a half written thread when the network dies mid visit

Nothing, because nothing on the clinical path crossed the network. The precise
answer, station by station:

- **A reading already committed stays committed.** It is a row in a local
  file, written by an autocommit connection with no multi row invariant to
  violate. The audit line went in before it.
- **A reading being typed is lost**, as a form being typed anywhere is lost.
  It was never a record.
- **A recording in flight fails closed.** `api/scribe.py` holds the audio in
  one temporary file, hands it to the connector, and deletes it in a
  `finally`. A failed upload is a `ScribeError` and a 503, the session id
  survives on the error so a second fetch is possible, and the doctor types.
  Unconfirmed audio is deleted after a backstop window whether or not anything
  was derived from it.
- **A proposal in flight either exists or does not.** `put_proposal` is a
  single insert or replace. A proposal that landed is re-judged when somebody
  taps confirm, against the thread state as it is then, so a proposal made
  when a precondition held is denied at confirm if the precondition has since
  gone.
- **The thread stands where its rows say it stands.** This is the deepest
  reason the state rules are declarative: there is no cursor, no "current
  step" column, nothing to be left inconsistent. `kernel/state.flags` derives
  the whole of a thread's position from `Store.count` every time it is asked.
  A thread cannot be half way through a transition, because there are no
  transitions, only facts and rules over them. A kernel that crashed between
  the audit row and the write leaves a thread that is exactly where its rows
  put it, with a record that somebody tried. `scripts/check_vitals.py` proves
  that case by handing the kernel a store whose `write` raises.
- **What is genuinely at risk is the two network queues**, which is why they
  are the next piece of work and why they are queues rather than calls.

### What is not durable, and is not pretended to be

Role overrides, the scribe's session table and the plugin off map are all in
process, one facility per kernel. `api/main.py` already says so. They are
configuration rather than record, and the day a second facility shares a
process is the day they move to the store.

---

## 8. The renderer

Mentioned here only for the boundary, because `web/` is not this document's
subject and `web/src/scribe/` is explicitly not to be touched.

The renderer draws `ThreadView` and `ViewResult` and may name nothing. It gets
one new behaviour from this branch and it needed no code: the visit summary's
vitals section changed from `fields: [code, value, unit, created_date]` to
`fields: [code_display, ...]`, in the view declaration. A nurse sees "Systolic
blood pressure 186 mm[Hg]" rather than "8480-6 186 mm[Hg]", and not one
renderer file changed. That is the architecture working, and it is the cheapest
demonstration of it in the whole branch.

---

## 9. Testing strategy

Every check in this repository is mutation proved: break the implementation,
confirm FAIL, revert, confirm PASS. A mutation that applied nothing proved
nothing and is reported as such, never as a pass.

### What each layer's checks assert

| layer | check | asserts |
|---|---|---|
| declarations | `catalogue/build.py`, `kernel/declarations.py` | every id resolves, every vocabulary is closed per bundle, every required answer is mapped or declared dropped, every row names its author, no em dash |
| terminology | `kernel/terminology.py` demo | a coding cannot be built around the value set check, a code outside its set cannot be bound, an uncached value set answers nothing, a coding cannot be rewritten in place |
| validation | `catalogue/tests/test_validate.py`, `web/src/validate.check.ts` | the same 21 payloads get the same verdict from the Python and the TypeScript validators |
| guard | `catalogue/tests/test_guard.py` | each of the four steps, fail closed on a missing validator and on an unevaluable separation of duties rule |
| mapping | `kernel/tests/test_mapping.py` | the declared mapping reproduces the rows the deleted adapter derived; a question that binds no concept may not write a code column |
| kernel state | `kernel/tests/test_kernel.py`, `test_contracts.py`, `test_spine.py` | the declaration and the code it replaced agree; every non text value a recording fills comes back owing a tick |
| adapter | `adapters/local/tests/test_store.py` | the ten protocol names, the query grammar over real SQL, a column the table lacks is refused and not dropped, two threads writing at once do not corrupt the file |
| projection | `kernel/fhir.py` demo, `scripts/check_vitals.py` | a LOINC coded Observation with a UCUM quantity, a numeric value that is a number and not a quoted string, a code with no system is text rather than a resolvable coding, the same rows give the same document |
| portability | `bundles/lab/check.py` | the same kernel runs a laboratory, 36 checks, not one word of a health centre's vocabulary |
| the whole slice | `scripts/check_vitals.py` | 27 checks across every layer above, no socket |
| over a socket | `scripts/e2e.py` | 45 checks against a real uvicorn and a real SQLite file, including that a stored vital carries its LOINC code |
| the renderer | 9 `*.check.ts` files | no renderer file types a bundle's word, no voice path can write, colour contrast in both themes |

### The two rules this branch paid for again

**Anchor a regex on the whole attribute.** Named in the core and plugins plan
after `/composer__mic/` matched `composer__micro`.

**Assert the mutation target exists before mutating.** The harness for this
branch counts matches and reports `NO TARGET (n matches): proves nothing`
rather than a pass. That is not theoretical: three of this branch's twenty
mutations came back `DID NOT FAIL`, and all three were real holes in my own
checks rather than false alarms. They are in section 10 and they are fixed.

### The property worth copying from CARE, and the one not to

Copy the repeating group validation pattern at
`care/emr/resources/questionnaire/utils.py:225-252`: a repeating group recurses
into itself once per occurrence, with the group's definition cloned and
`repeats` flipped off and a **fresh response scope** per occurrence, so
`required` is enforced per occurrence and an answer in occurrence one cannot
satisfy a required field in occurrence two. It is tested there, twice.

Do not copy `structured`. `care/emr/resources/questionnaire/spec.py:133` is
`structured_type: str | None = None  # TODO : Add validation later` and accepts
any string, and `utils.py:223-224` returns before the required check, the type
check and the value set check. The real validation lives in whichever typed
endpoint the *client* chooses to call, so a required structured question can be
skipped and the submission succeeds, and there is not one test in that
repository that submits one. For a scribe first product, where structured
clinical data is the primary output, "structured" must be the most validated
path and not the least. That is why repeating groups replace it here, settled
as coded data decision 2.

---

## 10. The mutations run on this branch

Twenty, all proved: FAIL with the mutation, PASS after revert.

| what it proves | mutation |
|---|---|
| a coding cannot be built unvalidated | the sentinel check in `Coding.__init__` always passes |
| `bound()` checks membership first | the missing concept check always passes |
| the write path re-checks the code | the `validate` call in `_bound_fact` always passes |
| a coding column may not land null | the blank check in `_bound_fact` always passes |
| a question binding no code may not write one | the lint's `_declares` check always continues |
| the UCUM system travels | drop `system` and `code` from `valueQuantity` |
| a FHIR decimal is a number | `_number` returns the string |
| a systemless code is text, not a coding | `_coding` stops requiring a system |
| the same rows give the same document | `_urn` uses uuid4 |
| `Bundle.meta.versionId` is emitted | drop it |
| `Composition.type` is emitted | drop it |
| an undeclared section is refused | the slice check always passes |
| an empty visit publishes nothing | the empty section check always passes |
| the audit row goes before the write | swap the two statements in `commit()` |
| the audit trail is oldest first | order by `at, id DESC` |
| the atom maps the code system column | drop `code_system` from the mapping |
| a declared code must be in its value set | change a question's code to one that is not |
| a code the cache lacks stops the build | rename the concept key in the cache |
| the engine may not type a clinical word | add a module level constant holding a LOINC code |
| the renderer is served plain JSON | leave the `Coding` object in the compiled mapping |

Three of these came back `DID NOT FAIL` on the first run, and each was a hole
in my own check rather than a false alarm:

1. **A coding column that lands null.** The check nulled the code itself,
   which the value set lookup catches anyway, so it never exercised the guard
   it was aimed at. A good code with a missing system is the dangerous case:
   nothing about it looks wrong and the row is written without the thing that
   makes the code resolvable. The check now nulls only the system and asserts
   the code is still valid first, so it cannot pass for the old reason.
2. **The audit row going first.** Unobservable from outside unless the write
   fails, which is exactly why the order matters. The kernel is now handed a
   store whose `write` raises, and the audit line has to survive it.
3. **A question that binds no concept writing a code column.** The lint rule
   was there with no case behind it.

---

## 11. What this architecture owes next

Ordered by what unblocks what, not by size. Each step leaves
`sh scripts/check.sh` green and unskipped, and each check it adds is mutation
proved.

- [ ] **Repeating groups**, replacing `structured` for diagnosis,
      medications, investigations and dispense. One repeat is one resource and
      one codification call. This is coded data plan step 4 and it is the
      gate on everything coded below. Copy the CARE recursion pattern cited
      in section 9. Check: a repeat whose coding is outside its bound value
      set is refused. Mutation: bind diagnosis to the observation value set
      instead.
- [ ] **`answer_value_set` as the third binding form**, which repeating
      groups need and nothing before them does.
- [ ] **The codification seam plus its empty stub.** Check: the whole PHC
      flow passes with `suggest` returning nothing.
- [ ] **`OPConsultRecord`**, once there are Conditions, MedicationRequests
      and ServiceRequests to put in its sections. The profile table in
      `kernel/fhir.py` takes one more entry; the rest is declaration.
- [ ] **The two network queues**, for audio and for ABDM documents. They are
      the only two things on the path that need a network, and they are
      queues so that a bad line is a delay rather than a failure.
- [ ] **The section codes.** `Composition.section.code` is how NRCeS
      discriminates a section slice, and the ABDM catalogue's own
      `WellnessRecord` atom is a stub that lists the slice names and says the
      mapping is not authored. The table in `kernel/fhir.py` therefore has
      `code: None` and the document is emitted without them, which passes the
      tier one validator and will not match the slice. Somebody has to read
      the implementation guide. **This is a request for a fact, not a
      decision:** inventing a SNOMED code here files a record under the wrong
      heading, which reads as correct everywhere it is read.
- [ ] **Confirm the LOINC codes.** The six in `terminology/observation-code.json`
      are hand seeded from the published vital signs panel and every one is
      marked `unverified` with its provenance. Coded data plan step 2 is to
      batch them through Eka codification with unit as context and confirm the
      list once by hand. This is design time work that never runs at the point
      of care.

---

## 12. What the code now contradicts in the two existing plans

Reported rather than quietly worked around. Four of these need a word changed
in a plan; one is a fact about the renderer that was already wrong.

**1. Coded data, invariant I1: "Enforced as a type at the write path, not as a
lint."** Not achievable as written, and the reason is structural rather than
awkward. The compiled mapping is served to the renderer as JSON, so a type
object cannot reach the write path. The invariant as built is: one validated
constructor, which makes an unvalidated coding unconstructible anywhere, plus a
re-check against the same offline authority at the write path. Stronger than a
lint in both halves, and the plan's wording should say so.

**2. Coded data, section 2.1: `validate(valueset_slug, coding) -> bool`.** The
signature cannot be right alongside I1. If a `Coding` can only be constructed
by validating, then `validate` cannot take one. It takes a code. The
implemented seam is `validate(valueset, code)`, `bound(valueset, code) ->
Coding`, `expand(valueset, query, count) -> [Coding]`.

**3. Coded data, step 3: "Switch the 6 vitals and the lab result to
`quantity`".** Not done, and on the evidence of this branch not needed for the
stated outcome. A question of type `integer` or `decimal` with a bound unit
already produces a correct FHIR `valueQuantity` carrying the UCUM system, which
section 3 step 9 and the tier one validator both confirm. Switching the type
would change `api/fill.py` coercion, the voice grammar's number handling and
the renderer's field, for no change in what reaches ABDM. The step is worth
keeping only if a question must carry a unit chosen per answer rather than per
question, which no PHC vitals question does. Recommend narrowing it to the lab
result, where the unit genuinely is an answer.

**4. Core and plugins, section 6 inventory.** "`pharmacy/stock` is the only
candidate that adds resources" is no longer true: coded data adds three columns
to `observation`. They belong to no plugin, because a facility cannot turn off
"codes mean something elsewhere". The inventory's actual point, that a plugin
owning a kernel verb is a problem, is untouched.

**5. `web/src/types.ts` `MappingRecord.per_question?: string[] | null`.**
Wrong, and wrong before this branch: the compiled form has always been a list
of objects, `[{link_id, unit}]` then and
`[{link_id, code, code_system, code_display, unit, unit_system}]` now. Nothing
breaks because `web/src/structured.ts` only reads `per_item` records. It is a
type that lies, in a file whose whole job is to describe the wire, and it
should be corrected when somebody is next in there.

**And one bug, fixed here rather than reported.** `Store.audit` is documented
as oldest first and could not deliver it. `AuditRecord.at` is ISO 8601 to the
second, so two decisions on one thread inside the same second tied on `at`, and
the tiebreak was `id`, a random uuid hex. An audit panel showing a refusal
after the write it refused reads as a different sequence of events from the one
that happened, and the audit trail is the record we would defend. It now breaks
the tie on SQLite's insertion order. `Store.proposals` had the same tie and the
same fix.

---

## 13. What I deliberately did not architect, and why

**Authentication and accounts.** The single largest hole, and deliberately not
mine to fill: it decides what a user is, which is a product decision about
whether staff log in as themselves, as a station, or through Eka's identity.
Everything in section 4's ceiling follows from it. Until it exists, every
capability proof in this repository is server side and the browser is a
superuser sandbox.

**The patient directory.** Patients are local rows. The plan says they live in
Eka's directory now, which is why the CARE adapter went, but nothing replaced
it. Whether a thread's subject is an Eka patient id, a local row, or both with
a join is a public contract decision with an ABHA shaped question inside it.

**`OPConsultRecord`.** Section 11 has it. It needs Condition,
MedicationRequest and ServiceRequest projections, all of which need repeating
groups first, so architecting it now would be architecting against a data
model that is about to change. `WellnessRecord` was chosen for the slice
precisely because it is complete today: six readings, one section, nothing
pending.

**Favourites and recents for codes.** Coded data section 4 wants them and is
right that forty concepts out of a hundred thousand is the difference between a
usable picker and an unusable one in a four minute consultation. Not
architected because there is nothing to pick yet: the picker arrives with
`answer_value_set`. When it does, copy CARE's *resource* favourites
(`care/emr/api/viewsets/favorites.py`, named lists, facility scoped, cap
enforced, ordering preserved in the queryset) and not its *code* favourites,
whose declared cap of fifty has zero readers and is an unbounded per user JSON
column.

**A terminology server.** The seam is there and the local file is behind it.
Building the second implementation, a local index over the NRCeS release files,
needs the release files, which needs the licence, which is the one open item
with a lead time. Nothing on the near path may depend on it, which is why
`expand` over a full SNOMED branch is a named ceiling rather than a missing
feature.

**The agent as a plugin.** The core and plugins plan is right that it is not
separable yet, and for a reason outside this document: the shell's
conversation model is agent typed at the type level. Generic message author
first, then plugin. I have not reordered that.

**Anything in `web/src/scribe/`.** Out of scope by instruction, and the Eka
scribe split is a proposal awaiting review.

**Moving `api/fill.py`.** Out of scope by instruction. Section 5 states my
recommendation and the argument for it.
