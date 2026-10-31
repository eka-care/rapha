# Porting the backend to Go

**Status.** Decision taken 2026-10-31 by the owner. The team works in Go, so
the backend they maintain should be in Go. Monday becomes a code and
architecture walkthrough rather than a working demo, which the owner accepted
explicitly when choosing this over demonstrating the Python build first.

**This document is the spec the port is built against.** It is not a proposal.

## Why this is cheaper than a 15,400 line rewrite sounds

Three facts about the existing build, each measured on 2026-10-31:

1. **The clinical rules are not in the Python.** 7,982 lines of markdown atoms,
   YAML bundle and JSON questionnaires and value sets compile to
   `catalogue.json`. They do not move, and `care_phc_mcp/catalogue.go` already
   reads that file in Go today. The declared-not-coded architecture was built
   so that the engine could be replaced without touching clinical capability;
   this is that claim being cashed.
2. **The Python depends on almost nothing.** FastAPI, and otherwise the
   standard library: `sqlite3`, `json`, `dataclasses`, `datetime`, `hashlib`,
   `base64`, `re`, `pathlib`, `functools`. There is no scientific stack, no
   ORM and no framework magic to find a Go equivalent for.
3. **A third of the proof survives the port untouched.** Seven check scripts,
   3,725 lines, drive the product over a real socket and do not care what
   language answers. 19 files, roughly 7,000 lines, import the Python kernel
   directly and must be rewritten as Go tests.

## The rule that governs the whole port

**The socket-level checks are the acceptance test, and they are already
written.** No Go slice is finished until the real check scripts pass against
the Go server, unmodified except for which backend they launch.

The Python stays in the tree as the reference implementation until the port is
complete. Where behaviour is in doubt, the Python is right and the Go is
wrong, and a differential run says so. The Python is deleted only when every
check passes against Go and the owner says so.

**Nothing proven is allowed to become unproven.** This build found a real
defect in almost every module — a diagnosis stored as confirmed whatever the
clinician said, every lab value published as signed off, a fallback three
files promised and none provided, two checks filing the same consultation
under different headings. Those were caught by checks. A port that reaches
feature parity without test parity throws away the entire week.

## What does not change

- `catalogue/`, `bundles/`, `questionnaires/`, `terminology/` — the
  declarations. The Go engine reads them; it does not restate them.
- **The renderer may never name a station, flag, capability or bundle.** The
  rule survives the port and so does the check that holds it.
- The React frontend. TypeScript compiles to JavaScript already, and its types
  caught a real defect this week. It keeps them.
- `care_phc_mcp` — the Go MCP server. It builds its tool list from
  `GET /whoami` and the catalogue, so a Go backend serving the same contract
  needs no change in it. That it keeps working is itself a check.

## Decisions taken up front

**SQLite driver: `modernc.org/sqlite`, the pure-Go one.** Not
`mattn/go-sqlite3`, which needs cgo. The whole deployment argument for Go here
is one file copied to a clinic PC, and cgo breaks cross-compilation for that
file. If the pure-Go driver proves unworkable, stop and report rather than
reaching for cgo.

**One Go module, two commands.** `care_phc_mcp` already parses
`catalogue.json`. Restructure so the catalogue reader is a shared package with
`cmd/api` and `cmd/mcp` beside it, rather than copying the parser. An agent
that disagrees should say why rather than quietly doing something else.

**Behaviour is copied, not reinterpreted.** Where the Python does something
that looks wrong, it is reported, not fixed in passing. Several apparent
oddities are deliberate and documented: a verified laboratory value stays
`preliminary`, a visit leaves as two documents, `lab.op.result-verify` stores
a word FHIR does not have. Section 12 of the architecture plan lists 38
contradictions already found; read it before deciding anything is a bug.

## The slices

Each is finished when the gate is green and the named checks pass against Go.

- **G1. The switch, the skeleton and the store.** One place decides which
  backend a socket check launches. Go serves the catalogue, the facility and
  the account. SQLite behind the ten-method store protocol. Note the eleventh
  method the Python kernel calls but the protocol never declared
  (`record_directory_id`, contradiction 29) — the Go interface declares every
  method it serves.
- **G2. The guard.** Seven steps. The audit row written before execute.
  Machine surfaces get proposals only. A proposal judged again at confirm.
- **G3. Validation and fill.** Questionnaire validation, repeating groups, row
  addressing, bound choices, and the tick: every non-text value a recording
  fills is owed a per-field confirmation.
- **G4. Terminology.** A coding that cannot be constructed unvalidated, the
  three binding forms, the offline value sets.
- **G5. Mapping and the record projection.** Rows per group row, the author on
  each, and the three OPConsultRecord slices this build fills, plus the
  narrative fallback.
- **G6. Views, state and metrics.** The station line, the flags, the declared
  views and the dashboard.
- **G7. Plugins.** A facility's shape as one list of what it does not run,
  subtracted once, denied and never hidden.
- **G8. The outbox.** Durable, nothing lost, nothing sent twice, nothing
  reported as sent when it was not. Still switched off: the audio retention
  window is unsigned.
- **G9. Retire the Python.** Only on the owner's word, and only when every
  check passes against Go.

## Open, and the owner's

- **Authentication.** There is none today: `caller()` reads an HTTP header and
  the one account holds every capability. The port must not invent an auth
  model. Carry the header, name the gap, and leave the decision.
- **When the Python goes.** Not an agent's call.
