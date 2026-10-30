# Core and plugins: Eka Scribe for PHCs

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax. Every step leaves
> `sh scripts/check.sh` green and unskipped, and every check it adds is mutation
> proved: break the implementation, confirm FAIL, revert, confirm PASS.

**Goal.** Make the core / plugin / bundle split concrete, so that a facility's
copy of this product is a choice of plugins rather than a fork of the code, and
so that removing a plugin removes an ability rather than a button.

**Status.** The split is decided, not proposed. What this plan decides is where
each seam falls in the code that exists today, and in what order to move it.

**Prior art, and the one conflict to resolve.**
`docs/superpowers/specs/2026-09-15-spine-and-plugins.md` already defines a
plugin, as "a named group of one bundle's own words": manifest data in
`bundles/<id>/bundle.yaml`, deliberately not a sixth declaration type, with a
per-user off map and the rule that a plugin which is off is a capability the
caller does not hold. That spec's reasoning holds and its runtime half is
adopted here unchanged. What it does not cover is packaging: it has no account
of a unit that also contributes routes, a renderer surface or store behaviour,
because at the time nothing needed to be independently removable from disk.

This plan treats those as two faces of one noun:

- **composition** (that spec) answers *is this plugin on for this caller*. It
  stays in `bundle.yaml` and `caller()`.
- **packaging** (this plan) answers *what does this plugin consist of, and what
  breaks if the directory is deleted*. It lives in the plugin's own directory.

They must not become two registries. The plugin id is the same string in both,
and a check asserts it (Step 2).

---

## 1. The three nouns, as checkable rules

### Core

`kernel/` (contracts, declarations, guard, state, mapping, spine, views),
`catalogue/` (the compiler, the validator, the vocabulary), `adapters/local`,
and the renderer shell: `web/src/app/`, `web/src/thread/`, `web/src/form/`,
`web/src/view/`, `web/src/screens/`, `web/src/style/` and the loose rule
modules beside them.

The core knows there are operations, threads, stations, views, instruments and
capabilities. It knows no clinical word. That is already enforced, two ways,
and both must survive this work:

- `web/src/ui.check.ts:60-131` derives every word the loaded bundle owns from
  the compiled catalogue and fails if any renderer file outside
  `types.ts`/`declarations.ts`/`abha/` types one of them as a quoted literal.
  It is self-growing: a bundle that declares more words checks more words.
- `kernel/declarations.py` closure linting: a `phc.*` atom may name only what
  `bundles/phc/bundle.yaml` declares.

### Plugin

A directory that may contribute any of five things and must be removable
without editing anything outside itself and its own registration line:

1. **declarations**: operation atoms, instruments, views, metrics, questionnaires
2. **API routes**: one `APIRouter`, mounted by the loader, never by `api/main.py`
3. **a renderer surface**: one directory under `web/src/`, with its own CSS
   imported by its own entry component (`web/src/scribe/ScribeBar.tsx:29` is
   already the pattern) and its own `*.check.ts`
4. **store behaviour**: a resource, a column, or a mapping verb
5. **a capability**, which is how it is switched off

Today's candidates, with their measured separability (file level inventory in
§6): `scribe`, `abha`, `voice`, `pharmacy/stock`, `agent`, plus the two new
concepts in §8.

### Bundle

Unchanged: a facility's choice of plugins plus its own vocabulary.
`bundles/phc`, `bundles/lab`. A bundle declaring no `plugins:` behaves exactly
as it does now, which is the clause that keeps `bundles/lab` valid on day one.

---

## 2. What a plugin manifest declares

`plugins/<id>/plugin.yaml`. Seven keys, four of them optional. The shape is
chosen so that every value is a list of ids the build already validates, which
means the manifest needs no new validator of its own, only a closure rule.

```yaml
id: scribe
title: Ambient scribe
# The capability that is also the off switch. Required: a plugin with no
# capability has no off switch, and the spine spec's whole argument is that
# capability is the only per-caller set the guard, visible(), state.actions,
# GET /whoami and care_phc_mcp all already read.
capability: capture.scribe
# Optional. Ids this plugin owns. Every one must resolve, and must not be
# claimed by another plugin.
declarations:
  operations:   [phc.op.capture-withdraw]
  instruments:  [phc.inst.consult-scribe, phc.inst.consent-speak]
  views:        []
  metrics:      []
  questionnaires: [phc.schema.capture-withdraw-v1]
# Optional. The module exporting `router: APIRouter`. The loader mounts it
# under the same two prefixes api/main.py:777 already uses.
routes: plugins.scribe.routes
# Optional. The renderer directory, relative to web/src.
surface: scribe
# Optional. Resources this plugin introduces, and mapping verbs it needs.
# Named so that deleting the plugin tells you which store columns go unused,
# rather than leaving them to be discovered later.
store:
  resources: []
  verbs: []
# Optional, default false. A floor a composition may not turn off.
always: false
```

Three rules, linted at build time beside the existing closure checks:

- **R1, closure.** Every id a plugin names must exist, and must be named by
  exactly one plugin. An id no plugin claims belongs to the core bundle and is
  always on. That makes "which plugin owns this" total without requiring every
  atom to be assigned on day one.
- **R2, the handover rule** (from the spine spec, kept verbatim in force). A
  plugin that owns instruments must not own the capability of any operation
  those instruments draft for. Turning `scribe` off must remove the microphone
  and leave `encounter.document` and `rx.prescribe` intact, so the doctor types
  and the visit still finishes. Checkable from declarations alone:
  `plugin.instruments -> instrument.operations -> operation.capability` must not
  intersect `{plugin.capability}`.
- **R3, one id.** The plugin ids in `plugins/*/plugin.yaml` and the keys of
  `bundle.yaml`'s `plugins:` must be the same set, modulo plugins a bundle does
  not install. A plugin on disk that no bundle installs is inert, not an error.
  A bundle installing a plugin that is not on disk is a build failure.

---

## 3. The loader

One module, `plugins/__init__.py`, with one function and no framework.

```python
def installed(bundle) -> list[Plugin]:
    """Every plugin this bundle installs, in bundle.yaml order."""
```

Discovery is explicit, not a directory scan: the bundle lists what it installs.
A scan would mean that dropping a directory into the tree changes a facility's
behaviour, which is the opposite of the property we want.

Composition, by contributor kind:

| contributes | composed by | where |
|---|---|---|
| declarations | nothing new. The ids are already in `bundle.yaml`'s lists and compile through `catalogue.build` + `kernel.declarations` as they do today. The manifest only records ownership. | `catalogue/build.py`, `kernel/declarations.py` |
| routes | the loader imports `routes` and calls `app.include_router` for each installed plugin, under the two existing prefixes | new, in `api/main.py` where the two `include_router` calls already are (`api/main.py:777-778`) |
| a surface | the renderer reads `catalogue.manifest.plugins` and mounts the surface whose id matches, from a single static map in the shell. A dynamic import keyed off a declaration would defeat Vite's bundling and `npm run build` is part of the gate. | new, `web/src/plugins.ts` |
| store behaviour | nothing new. A resource is a table in `adapters/local/store.py` and a name in `catalogue/vocab.py CARE_RESOURCES`; the manifest records which plugin needs it. | `adapters/local/store.py` |
| a capability | `caller()`, once. See §4. | `api/main.py:123-132` |

The renderer map is the one place where the shell names plugin ids. It is a
contract between the shell and its plugins, in the same class as
`ui.check.ts:97-101`'s `IMPLEMENTED` list, and it is kept honest the same way:
every id in the map must be a plugin the compiled catalogue declares, and every
plugin with a `surface` must be in the map. Both directions, checked.

---

## 4. `caller()` narrowing: subtract once

The rule, from the spine spec and unchanged: **a plugin that is off is a
capability the caller does not hold.** Subtracted once, in `caller()`, before
anything reads it, so there is no render time hide to implement and nothing to
forget.

`api/main.py:123-132` today:

```python
caps = OVERRIDES.get(role, ROLES[role])
```

becomes, with the off map beside `OVERRIDES` (`api/main.py:85`):

```python
caps = [c for c in OVERRIDES.get(role, ROLES[role]) if c not in withheld(actor)]
```

where `withheld(actor)` maps the actor's off plugin ids to their capabilities.
Three consequences, all of which the spine spec already worked through and none
of which this plan changes:

- The guard denies rather than hides, and the denial names both the capability
  and the plugin, so an admin can reconstruct it six months later.
- `kernel.state.actions` and `visible()` stop offering the operation, because
  they read the same narrowed set.
- `care_phc_mcp`'s `For()` narrows too, because it asks the kernel.

**One hazard this plan must name, because `caller()` makes it worse.**
`api/main.py:75` sets the demo role to `sorted(vocab.CAPABILITIES)`, the union
of every declared capability. Every capability a plugin adds therefore lands in
the demo role's hands with nobody deciding it, and the demo role is the only
account the browser can be. That is already recorded as a hazard in the comment
at `api/main.py:60-75`. It means the browser cannot demonstrate a plugin being
off until there are real accounts, so **Step 5's proof is the MCP surface and
`bundles/phc/check.py`, not a screenshot.** Do not let the plan's acceptance
rest on the browser here.

---

## 5. How `bundles/lab` stays green

`bundles/lab/check.py` (36 checks, run from `scripts/check.sh:28`) is the
portability proof: the same kernel, the same renderer, a laboratory's own
vocabulary, no PHC word anywhere on screen. Four rules keep it green:

1. **A bundle with no `plugins:` key is a bundle with every core ability and no
   plugin.** `bundles/lab/bundle.yaml` gains nothing in Step 1.
2. **Nothing the loader does may be required.** Zero installed plugins must
   produce byte-identical behaviour to today. Step 1's acceptance is exactly
   that: `compile_json(BUNDLE)` differs from the pre-plugin compile only by the
   added key.
3. **`lab.inst.analyser`** is an instrument with no capability today. The
   optional `capability:` field means absent stays ungated stays on, which is
   what keeps every other bundle's instruments working untouched.
4. **`ui.check.ts` grows rather than being exempted.** The portability check
   derives its word list from the compiled catalogue, so a plugin that adds a
   capability adds a word the renderer may not type. No plugin may be added to
   the `abha/` style carve-out at `ui.check.ts:117-119` without the owner
   saying so in writing. That carve-out exists for one documented reason, that
   ABHA is a national identifier rather than a facility's concept, and a second
   one would turn an exception into a convention.

---

## 6. The inventory: what each candidate owns today

Measured, not estimated. Line counts from `wc -l`.

| plugin | python | routes | atoms | renderer | store | separability |
|---|---|---|---|---|---|---|
| `scribe` | 2075 (`api/scribe.py` 531, `api/extract.py` 141, `api/fill.py` 215, `care_phc/connectors/scribe/*` 1188) | 6 | 2 instruments, 1 op, 1 questionnaire, the `scribe:` block in `bundle.yaml:52-56`, 4 `capture.*` states | 888 in `web/src/scribe/` | none. `api/scribe.py:9-11` states it has no Store | medium |
| `abha` | 651 (`care_phc/connectors/abdm/*`), imported by nothing in `api/` or `kernel/` | 1 | 1 op, 1 metric, 1 questionnaire, 2 states, 1 capability | 781 in `web/src/abha/` | `patient.abha_number`, plus the whole `abha_config` concept in the CARE adapter | medium: cleanest python, worst renderer entanglement |
| `voice` | 0 (pure `packages/voice`) | 0 | 2 instruments | 587 in `web/src/voice/` + `packages/voice` | none | **highest.** Same shape as scribe and abha, not in the brief's candidate list, and the easiest first proof |
| `pharmacy/stock` | 0 | 0 | 1 op, 1 questionnaire | 0 | **the only candidate that adds resources**: `medication_dispense`, `inventory_item`, and it owns the `{minus:}` mapping verb (`kernel/mapping.py:50,84`) outright | high as vocabulary, but it owns a kernel verb |
| `agent` | 1781 python + 604 Go | 2 | 0 atoms, but owns `KHOJ` in `kernel/contracts.py:284-287` and `MCP`/`AGENT_PREFIX` in `catalogue/guard.py:15,36` | 458 spread across 4 loose files, one of them inside the shell (`web/src/app/Khoj.tsx`) | none | **lowest.** See below |

Four couplings worth naming before anyone starts moving files.

**The agent is not separable yet, and should not be attempted in this plan.**
The shell's conversation model is agent typed at the type level:
`web/src/messages.ts:35` declares `who: "user" | "agent"`, `messages.ts:268`
exports `agentLine()`, `web/src/thread/Message.tsx:16,21-22` branches on it, and
`web/src/screens/Today.tsx` is effectively an agent screen inside the shell.
Making `agent` a plugin requires the shell to own a generic message author
first. That is a separate piece of work with its own value, and it is the right
order: generic author, then plugin.

**`pharmacy/stock` owns a kernel verb.** `{minus:}` exists in
`kernel/mapping.py` for exactly one use site, the stock decrement in
`catalogue/ops/phc.op.pharmacy-dispense.md`. Either the verb is core (a general
mapping verb that happens to have one user) or it moves with the plugin. This
is a decision, listed in §10.

**`scribe` depends on `abha`.** `care_phc/connectors/scribe/eka.py:71` imports
`_scrub` from `care_phc/connectors/abdm/eka.py` to redact Aadhaar numbers. A
plugin that cannot be removed without breaking another plugin is not
independently removable. `_scrub` is a redaction utility, not an ABHA concept:
it moves to the core before either becomes a plugin.

**`api/fill.py` already leaks into the core.** `kernel/tests/test_contracts.py`
imports `from api import fill` to check that every non-text value a scribe fills
comes back owing a tick. That import is deliberate and was added knowingly: the
tick type table is the kernel side half of a clinical safety property. It means
`api/fill.py` is **core, not plugin** (see §7).

---

## 7. The scribe split: Eka for audio, ours for evidence

**Proposal, for the owner's review before any deletion.** Nothing in
`web/src/scribe/` is touched until this is signed off.

Eka's `@eka-care/ekascribe-ts-sdk` v3.0.58 covers audio to transcript: session
based, `POST /voice/v1/sessions`, upload, `POST .../end`, poll
`GET /voice/v1/sessions/{id}`. Its `templates[]` carry `{status, document_id,
data}` with `data` as structured key-value, and there is a Templates API and a
re-run endpoint.

What Eka's templates do not do, and `api/extract.py` does:

> a field is answered only with a verbatim span copied from the transcript;
> no span, no answer.

That is the rule at `api/extract.py` and in the design spec's §4.4, and it is
the reason a model cannot fill in a value nobody said. It is not a duplicate of
anything Eka offers.

So the split is:

| stage | owner | today | after |
|---|---|---|---|
| audio capture, upload, poll | **Eka SDK** | `care_phc/connectors/scribe/eka.py` (281), our own upload and poll plumbing | delete our plumbing, keep the connector interface at `base.py` so a second vendor stays possible |
| transcript to questionnaire values with evidence | **ours** | `api/extract.py` (141) | keep, unchanged |
| flatten, coerce, enable_when, tick | **ours, and core** | `api/fill.py` (215) | **move to `kernel/fill.py`.** It is pure, it names no clinical word, it has no vendor in it, and the kernel's own contract test already depends on it. Leaving it under `api/` while calling it a plugin is the leak described in §6 |
| session, retention, consent gate | **ours** | `api/scribe.py` (531) | the plugin's core |

**Explicitly not decided here:** whether to adopt Eka's Templates API at all.
Our templates are operation ids (scribe design decision 5, "a template is an
operation", because only an operation's mapping can write). Eka's are prose
instructions returning markdown. Adopting both means two template systems.
Listed in §10.

---

## 8. Two new plugin concepts, designed not built

### `catchment`

PHC, sub-centre, village or habitation, ASHA, with the ANM attached to the
sub-centre.

**The one decision that makes this cheap: a patient stores exactly one
habitation id. Sub-centre, ANM and ASHA all derive.** Storing any of the four
on the patient makes them four facts that can disagree, and the one that
disagrees is the one that decides who visits the house.

- Shape: configuration, not clinical data. A facility's tree, loaded beside
  `bundle.yaml`, not written through an operation.
- Store: one column, `patient.habitation`. No new resource, no new Store method.
- Declaration: the tree is a bundle file (`bundles/phc/catchment.yaml`), because
  it is this facility's own vocabulary in exactly the sense `stations:` is.
- Renderer: no surface of its own. A habitation appears in `subject`, which the
  queue and the patient page already draw from declarations.
- Derivation belongs in `kernel/state.py` beside flag derivation, as pure
  functions of the tree plus the stored habitation.
- Capability: `catchment.view`. Off means the fields do not appear, which is
  correct for a facility that has no sub-centres.

### `tags`

Programme membership: NCD/NPCDCS, ANC+RCH/RMNCH+A, TB/NTEP.

A tag decides two things and must decide nothing else, or it becomes a second
workflow engine: **the default scribe template, and the follow-up interval.**

- Two provenances, stored distinctly: `assigned` by a person, `derived` by a
  rule. They must not collapse into one field. A derived tag that a person
  cannot see the reason for is a tag nobody trusts, and an assigned tag a rule
  can silently overwrite is a clinical record that changed itself.
- Store: `patient_tag` rows, `{patient, tag, provenance, at, actor}`. A row, not
  a column, because provenance and actor are per tag.
- Declaration: the tag vocabulary is the bundle's (`tags:` in `bundle.yaml`).
  The rules that derive them are atoms, so the reason is readable.
- The scribe template link is the interesting one: `bundle.yaml`'s `scribe:`
  block is keyed by station today (`bundles/phc/bundle.yaml:52-56`). A tag
  default is a **second** key on the same lookup, not a second config system.
  Station picks the default; a tag overrides it for that patient. One lookup,
  two inputs, stated in one place.
- Depends on `catchment` for nothing. They are independent and should ship
  independently.

Neither is built in this plan. Both are specified far enough that the next
person does not re-decide the storage shape.

---

## 9. Sequencing, smallest risk first

Each step is one commit or a short series, each leaving the gate green and
unskipped.

- [x] **Step 0. The gate.** Done. Two commits: the derived metric window and
      compiled key set, and the scribe tick property replacing the structural
      numeric ban. Both mutation proved.

- [x] **Step 1. Delete the CARE adapter.** Done, 2135 lines removed. Pure subtraction, no new concept.
      `adapters/care/` is 2053 lines across 6 files and its entire load bearing
      surface outside itself is 4 lines in `api/main.py` (:93, :102, :103, :110)
      and 2 in `scripts/check.sh` (:32, :33). `PHC_STORE` already defaults to
      `local`. Nothing in `kernel/`, `catalogue/`, `bundles/`, `web/` or
      `care_phc_mcp/` imports it.
      **Keep the resource names.** `patient`, `encounter`, `observation`,
      `medication_dispense`, `inventory_item` stay in `catalogue/vocab.py`
      `CARE_RESOURCES`. They are FHIR shaped vocabulary that costs nothing and
      keeps the door open. Removing the adapter is not removing the model.
      **One thing must be relocated, not dropped.**
      `adapters/care/tests/test_store.py:481-499` is the only assertion in the
      repo that pins the Store protocol's exact ten method names against a
      class. It moves to `adapters/local/tests/test_store.py` with its comment
      about the "nine methods" docstring intact, since the discrepancy it
      records is still there.
      Also: a documentation sweep of `RUNNING.md` (9 lines) and
      `kernel/ARCHITECTURE.md` (:38, :77).

- [ ] **Step 2. Declare the plugins, all on, no loader, no off map.**
      `plugins/<id>/plugin.yaml` for the five candidates, `plugins:` in
      `bundles/phc/bundle.yaml`, `Manifest.plugins`, `Vocabulary.plugins`, and
      R1/R2/R3 from §2. Nothing changes behaviour.
      **Acceptance, which is the whole point of the step:** with the off map
      empty, the effective capability set for every role in
      `bundles/phc/bundle.yaml` is byte identical to `vocab.BUNDLES[role]`
      today, and `compile_json(BUNDLE)` differs from the pre-plugin compile only
      by the added `plugins` key. `bundles/lab/bundle.yaml` gains nothing.
      **Mutation:** pre-populate the off map with any plugin, or mark one
      `always: false` and have `caller()` subtract it by default. Must FAIL.

- [ ] **Step 3. Move `_scrub` and `api/fill.py` to the core.** Two small moves
      that remove the two cross-plugin dependencies named in §6, before any
      plugin is asked to be removable.
      - [x] `_scrub` out of `care_phc/connectors/abdm/eka.py` into
            `care_phc/connectors/redact.py`, owned by neither connector, whose
            check asserts that no connector imports a sibling.
      - [ ] `api/fill.py` to `kernel/fill.py`, with
            `kernel/tests/test_contracts.py`'s import following the file.
            **Not done, and held deliberately.** It is mechanically small, two
            importers, but it adds a module to `kernel/`, and
            `kernel/ARCHITECTURE.md:70` says that directory is the architect's:
            report a gap, do not patch it. The gap is reported in §6 and in
            decision 6 below. The leak is live meanwhile and is not dangerous:
            a kernel test imports an api module, which is the wrong direction
            but not a runtime dependency.

- [ ] **Step 4. `voice` as the first real plugin.** Chosen over scribe because
      it is the same shape with a fifth of the entanglement: `web/src/voice/`
      is self contained with its own CSS and check, `packages/voice` is pure,
      there are no routes and no store behaviour. It proves the manifest, the
      renderer map, the capability and R2 in one pass.
      Acceptance: deleting `plugins/voice/` and its `bundle.yaml` line leaves
      the gate green, and the two voice instruments' operations are still
      committable by typing.

- [ ] **Step 5. The off map and the guard reason.** `OFF`, the subtraction in
      `caller()`, `withheld` threaded into guard step 2, the plugin named
      denial, `PUT`/`GET /users/{user}/plugins` behind `facility.admin`, and the
      audit line against the reserved thread id `facility`. Still no screen.
      The proof is `bundles/phc/check.py` and the MCP surface, for the reason in
      §4: the browser can only be the demo role, which holds every capability.

- [ ] **Step 6. `scribe` as a plugin, and the Eka split.** Only after §7 is
      signed off. Routes move to `plugins/scribe/routes.py`, the surface stays
      where it is and is registered, the Eka upload and poll plumbing goes, and
      `api/extract.py` stays exactly as it is.

- [ ] **Step 7. `abha` as a plugin.** Needs the eleven coupling points in
      `web/src/form/Panel.tsx` cut first. That is a renderer refactor with its
      own risk, not a packaging change, and it is last among the ready
      candidates for that reason.

Not in this plan: `agent` (needs a generic message author first, §6),
`pharmacy/stock` (needs the `{minus:}` decision, §10), `catchment` and `tags`
(designed in §8, not built).

---

## 10. Decisions for the owner

These are product, architecture or public contract decisions. They are stated
rather than invented.

1. **One plugin noun, two faces.** This plan folds the 2026-09-15
   spine-and-plugins spec's composition model into the brief's packaging model,
   with one shared id and a check asserting the two sets agree. The alternative
   is two registries. Confirm, and the older spec's §Composition should be
   annotated as superseded on packaging and in force on composition.
2. **Does `{minus:}` stay a core mapping verb?** It exists in
   `kernel/mapping.py` for exactly one use site, the pharmacy stock decrement.
   Core verb with one user, or it moves with the plugin and the kernel loses a
   verb. Either is defensible; this changes the kernel's public contract.
3. **Two template systems, or one?** Scribe design decision 5 says a template is
   an operation id, because only an operation's mapping can write. Eka ships a
   Templates API with prose templates returning markdown. Adopting it means two
   template concepts in one product. Recommendation: do not adopt it, keep
   operations as templates, and use Eka for transcript only. This is the owner's
   call because it affects what Eka can be asked for later.
4. **The demo role is the union of every capability** (`api/main.py:75`). It
   means no plugin can be demonstrated as off in the browser until there are
   accounts. Accept that Step 5's proof is server side, or do accounts first.
5. **The `abha/` carve-out in `ui.check.ts:117-119` stays a carve-out of one.**
   A second one turns a documented exception into a convention. Confirm.
6. **Should `api/fill.py` become `kernel/fill.py`?** It is pure, it names no
   clinical word, it has no vendor in it, and `kernel/tests/test_contracts.py`
   already imports it to check the scribe tick property, so the dependency
   already points the wrong way. Moving it fixes that and makes the scribe
   plugin's boundary honest. Not done, because `kernel/ARCHITECTURE.md:70`
   reserves that directory. Owner's call.
7. **Local HTTPS port.** `~/code/nectar/apps/abdm-parent/vite.config.ts` uses
   port 443, which needs elevated permissions. 8443 with
   `@vitejs/plugin-basic-ssl` and `server.host = "sam.eka.care"` needs none.
   Owner picks; no `sudo` was run.

---

## 11. Checks this plan owes

Every one mutation proved, with the mutation named.

| check | asserts | mutation that must FAIL |
|---|---|---|
| `catalogue/vocab.py` `problems()` | R1 closure: every plugin owned id exists and is claimed once | give two plugins the same instrument id |
| the same | R2 handover: a plugin owning instruments does not own its operations' capability | add `encounter.document` to scribe's capability |
| the same | R3 one id: `plugins/*/plugin.yaml` ids and `bundle.yaml` `plugins:` keys agree | add a `plugins:` key naming a plugin not on disk |
| `kernel/tests/test_contracts.py` | default composition changes nothing: off map empty gives byte identical role capability sets | pre-populate the off map |
| `web/src/ui.check.ts` | the renderer map and the declared plugins agree in both directions | add a surface to a plugin and not to the map |
| `bundles/phc/check.py` | a plugin that is off denies on the MCP surface, and the audit names both the capability and the plugin | drop the capability name from the denial string |
| `bundles/lab/check.py` | stays green, unmodified, at every step | any step that needs a `plugins:` key in the lab bundle |
| `adapters/local/tests/test_store.py` | the Store protocol's ten method names, relocated from the deleted CARE adapter | rename a protocol method |

Two rules this branch has already paid for and that apply to all of the above:

- **Anchor regexes on whole attributes.** `/composer__mic/` once matched
  `composer__micro` and passed against a build with no microphone.
- **Assert the mutation target exists before mutating.** A mutation that applies
  nothing reads as proof. One mutation in this plan's own Step 0 work silently
  applied nothing and was reported as having proved nothing, rather than as
  having passed.

---

## 12. Known ceilings, stated rather than hidden

- The off map is in process, one facility per kernel, the same ceiling
  `OVERRIDES` already carries and states (`api/main.py:77-84`).
- `caller()` has no authentication. The role comes from a header. Composition
  per user is therefore per header value until there are accounts.
- `care_phc/thread.py:33-42` still carries a hard coded station table that
  duplicates the workflow declaration. It is used only by
  `scripts/mock_care.py`. It is not touched here and it is not a plugin
  problem, but it is the kind of duplication that makes a plugin look removable
  when it is not.
- `catalogue/vocab.py:81` `INSTRUMENTS` and `kernel/contracts.py:68`
  `INSTRUMENT_KINDS` disagree: `palette` versus `spoken-prompt`. One of them is
  stale. Found while inventorying; not fixed here because it is not this plan's
  change, and `scripts/check_khoj.py` exists specifically to assert the
  `Palette` rename stayed done.
