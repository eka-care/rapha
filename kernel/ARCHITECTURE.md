# Kernel architecture

One kernel. A hospital, a PHC, a dental chain and a diagnostics lab differ
only by which declaration bundle they load. The kernel is small and boring on
purpose: it evaluates the guard, derives thread state from the store, holds
the proposal queue, and writes audit. Everything a user sees is a plugin
declared in a bundle and drawn by a generic renderer.

```
 bundles/<id>/*.md + catalogue/ops/*.md          declarations: git, linted, versioned
                 |
                 |  python3 -m catalogue.build     (lint, then compile)
                 v
           catalogue.json                          one file, embedded by the MCP server
                 |
    +------------+-----------------------------------------------+
    |                    KERNEL   (kernel/)                       |
    |  guard      catalogue/guard.py, unchanged                    |
    |  state      flags from Workflow.states over Store.count      |
    |             station and actions from Workflow.steps          |
    |  proposals  put, list, confirm (second guard pass), reject   |
    |  audit      AuditRecord per decision, denials included       |
    |  api        the ROUTES in kernel/contracts.py                |
    +------------+-----------------------------------------------+
         ^                ^                     ^
         |                |                     |
   RENDERER          MCP / AGENT           ANALYTICS
   web/              care_phc_mcp/         analytics/
   draws declared    tools from            evaluates Metric
   forms and views   catalogue.json,       locally; nothing
   from ThreadView   proposes only         leaves the machine
   and ViewResult
         |
         v  (kernel only, via Store)
    +-----------------------------------------------------------+
    |  ADAPTERS  implement kernel.contracts.Store                 |
    |  adapters/local   SQLite, FHIR-shaped tables    adapter 0   |
    |  adapters/care    CARE REST, headless           adapter 1   |
    +-----------------------------------------------------------+
```

## What each layer may depend on

| layer | may import | may not |
|---|---|---|
| declarations | nothing; they are data | any code |
| `catalogue/` (vocab, build, guard, validate) | stdlib, yaml | kernel, adapters, clients |
| `kernel/` | `catalogue/`, `kernel/contracts` | adapters (only through the `Store` protocol, injected), Django, network |
| `adapters/*` | `kernel/contracts`, its own driver (sqlite3, requests) | the guard, state derivation, the renderer |
| clients (`care_phc_fe`, `care_phc_mcp`, `analytics`) | the API over HTTP and `catalogue.json` | the kernel in-process, any adapter |
| `care_phc/` (the CARE plug) | `catalogue/`, `kernel/contracts`, Django | nothing new tonight; it becomes adapter 1's home later |

Three rules with no exceptions:

1. Pure logic has no I/O. State derivation takes a `Store` and returns a set;
   it is tested with a dict-backed fake, never with SQLite or CARE.
2. There is no path to a write that does not pass `catalogue.guard.evaluate`.
   Not from the MCP server, not from an instrument, not from a confirm
   button. Confirming a proposal is a second guard pass on the rendered
   surface, with the edited payload.
3. Voice, device and scribe produce a `Draft`. A draft is drawn in editable
   fields and committed by a tap. Nothing else. Fail closed to the keypad.

## Directory ownership tonight

Each agent owns its directories and touches nothing else. Shared files have
one owner and an append-only rule.

| directory | owner | notes |
|---|---|---|
| `kernel/contracts.py`, `kernel/*.md` | architect | frozen. Report a gap, do not patch it |
| `bundles/phc/` | build agent | may fix a declaration the linter rejects; may not change shape |
| `catalogue/build.py`, `catalogue/vocab.py` | build agent | extend lint and compile to the four new types; existing keys unchanged |
| `catalogue/guard.py`, `catalogue/validate.py`, `catalogue/ops/` | nobody | unchanged tonight |
| `kernel/state.py`, `kernel/proposals.py`, `kernel/api.py`, `kernel/tests/` | kernel agent | pure modules plus one HTTP server (stdlib `http.server` is enough; `scripts/mock_care.py` shows the shape) |
| `adapters/local/` | adapter agent | SQLite, one table per `vocab.CARE_RESOURCES` name it needs plus `thread_flag`, `proposal`, `audit`. Field names verbatim from the query grammar |
| `adapters/care/` | later | not tonight |
| `care_phc_fe/` | frontend agent | rename `patient` to `subject`, draw `line` from the API instead of the LINE constant, add a `Draft` field state and the tap-to-commit control, generic queue, summary and dashboard renderers |
| `care_phc_mcp/` | MCP agent | point at the kernel API; add a `thread` and `view` read tool from `catalogue.json`. Still no confirm verb |
| `analytics/` | analytics agent | evaluate `Metric` over `Store`; local only |
| `care_phc/` | nobody | unchanged tonight; `thread.py` stays until `kernel/state.py` reproduces it and `test_contracts` proves it |
| `scripts/check.sh` | everyone, append only | one line per new check, placed after the kernel line |

## The one check that already exists

`python3 -m kernel.tests.test_contracts` asserts that the PHC bundle agrees
with the code it replaces: the workflow steps equal `thread.LINE`, the states
cover `vocab.STATES`, every referenced operation exists, and every voice or
scribe instrument reads back and commits by tap. It runs from `check.sh`.

## What moved after that night, 2026.09.12

The table above is the work plan for one night and is kept as written. Four
things in it are no longer true, and an out of date map is worse than a
patched one:

- **A facility's words are its own.** `stations`, `states`, `capabilities` and
  `roles` now live in `bundles/<id>/bundle.yaml`, not `catalogue/vocab.py`, and
  `kernel/declarations.py` closes them per bundle. What survives in `vocab.py`
  is the kernel's and the adapter's grammar (`CARE_RESOURCES`,
  `KERNEL_RESOURCES`, `IRREVERSIBILITY`, `INSTRUMENTS`, `KINDS`), each with the
  reason it is not a facility's to choose. This is why a laboratory's draw room
  is no longer called `nurse`.
- **`catalogue/guard.py` changed.** It grew `actor of <operation>` as a
  precondition form, `parse_precondition` shared with the linter, and
  `person()`, which strips the `agent:` prefix so an agent inherits the
  exclusions of whoever it acts for. Rule 2 is unchanged and is what made this
  necessary: if there is one path to a write, the separation of duties rule has
  to live on it.
- **Every row carries its author.** `{actor: id}` is a mapping source and a
  record that declares no author fails lint, so "who did this" is not a
  question only the audit can answer.
- **`api/` and `agent/` exist.** `api/main.py` is the HTTP server the table
  gives to the kernel agent, and it carries one route the diagram does not:
  `POST /agent/say`, a sentence in and proposals out. It reaches a write only
  through `kernel.proposals.propose` on `guard.MCP`, which takes no `confirmed`
  argument, so it is a machine surface like any other. `web/` replaced
  `care_phc_fe/` as the renderer; the older one still builds and is still
  fixture driven.

## What moved after that, 2026.09.14

- **`care_phc_fe/` is deleted.** It was the module-federation remote the table
  above gives to the frontend agent: a CARE plugin exposing `./manifest` with
  an encounter tab and a `/phc/queue` route, drawn from `fixtures.json`, which
  `scripts/gen-fixtures.py` precomputed from `care_phc/thread.py`. `web/`
  replaced it as the renderer and reads the kernel API instead of a fixture,
  so the second one was a prototype nobody shipped that still had to compile,
  still had 72MB of `node_modules`, and still claimed a port. Nothing was moved
  out of it: every CSS class it defined already exists in `web/src/theme.css`,
  and its two components are the pre-kernel ancestors of `web/src/Thread.tsx`
  and `web/src/ViewRenderer.tsx`. `scripts/gen-fixtures.py` went with it,
  having had exactly one consumer. `web/src/mock.ts` is the demo data now and
  is its own thing, behind a button in the header.

  What is lost with it is the only worked example of the care_fe federation
  shape (`@originjs/vite-plugin-federation`, `exposes: { "./manifest": ... }`,
  port 10123). It is in the history at `9253069:care_phc_fe/vite.config.mts`
  if adapter 1 ever wants it, and `care_eka_scribe_fe` is the upstream one.
