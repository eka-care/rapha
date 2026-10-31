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
- **G4. Views, state, the spine and the seed.** The declared views, the
  metrics, the patient spine and the seeded demo day.

  **Brought forward from sixth place on 2026-10-31, after G3.** Two of the
  three acceptance tests are blocked on exactly this and on nothing else:
  `scripts/check_live.py` reports 0 of 16 because its first `ok` sits after a
  facility capture needing `GET /views/{id}` and `GET /subjects/{id}`, and
  `scripts/e2e.py main()` reports 1 of 49 because it opens on `GET /queue`.
  Until this slice lands, every later slice can only be measured by the
  differential check, which compares two engines against each other and
  cannot see the pair drifting together. Restoring the socket checks as a
  measure is worth more than the original order.

  **Landed 2026-10-31.** `scripts/check_live.py` is 16 of 16 against Go.
  `scripts/e2e.py main()` reaches 21 of 49 and stops at `POST /khoj`, which
  is the planner in `agent/turn.py` and not this slice; `facility_shape()`
  stays 4 of 4. The patient routes `check_live.py` reaches are served from
  the LOCAL half of `kernel/directory.py` only: there is no vendor behind
  that seam in Go, so a lookup always answers the kernel's own
  AbsentDirectory, and the differential check sets `PHC_DIRECTORY=absent` so
  the two engines are compared where they honestly can be.
  `POST /patients/publish` still answers 501, because publishing is the one
  verb that sends a person's details off this machine and faking it would be
  inventing a vendor.
- **G5. Terminology.** A coding that cannot be constructed unvalidated, the
  three binding forms, the offline value sets. `GET /valuesets/{slug}` is
  already routed, from G3, because a bound choice with nothing to choose is an
  empty dropdown; what is left is the rest of `kernel/terminology.py`.

  **Landed 2026-10-31.** The invariant is carried as a SHAPE rather than as a
  sentinel, because Go cannot make a struct literal illegal from another
  package: `Coding`'s fields are unexported, no method takes a pointer
  receiver, and a coding built anywhere else is the zero value that
  `kernel/mapping`'s own refusal then stops. That shape is held by a test in
  an EXTERNAL test package, because a check that could write the struct would
  be proving the opposite of what it claims.

  The three binding forms are read out of the questionnaires rather than out
  of the compiled artifact. Two of them are build time in the Python, so
  `catalogue.json` already carries them resolved and the Go serving path only
  re-checks one before a column is written; `QuestionCodings` is the other
  half, and it is what fails if a declared code or unit drifts from its value
  set on this side of the port.

  `scripts/check_go_parity.py` gained the SECOND terminology rule, which no
  scenario reached: a unit that is in its value set and is simply not the one
  that analyte is reported in. Both answers are legal alone and the pair is
  nonsense, which is the case a per-answer check passes. Two of the three
  shapes withhold the laboratory, so the check says which of the two things
  it compared in each shape rather than letting a capability denial stand in
  for the unit rule.

  **Three things this slice could not prove, and did not pretend to.** The
  `display` key is omitted when the cache records none — every one of the 87
  cached concepts declares one, so the branch is unreachable and writing the
  display unconditionally passes the whole gate. The ORDER of `semantic_tags`
  is the file's, which nothing can see: both value sets that declare tags
  declare them already sorted, and the one caller reads them as a set. And
  the 200 expansion ceiling stays what it already was, unobservable against a
  largest value set of nine concepts and awaiting the owner's decision.

  `kernel/terminology.Coding.to_fhir()` has exactly one caller in the whole
  tree, its own demo: `kernel/fhir.py` builds its codings from stored ROWS,
  not from `Coding` objects. Carried into Go as `ToFHIR` because G6 is the
  slice that fills those rows, and reported rather than deleted.
- **G6. Mapping and the record projection.** Rows per group row, the author on
  each, and the three OPConsultRecord slices this build fills, plus the
  narrative fallback.

  **Landed 2026-10-31.** The mapping half was already in Go from G3, so what
  this slice carried is `kernel/fhir.py`, as `care_phc_mcp/fhir`. The four
  measures are unmoved and could not have moved: `scripts/check_live.py` is
  16 of 16, `scripts/e2e.py main()` is 21 of 49 and still stops at
  `POST /khoj`, and `facility_shape()` is 4 of 4. **A document is on no HTTP
  route in either engine and never will be** — it is what the outbox sends to
  ABDM, not something a clinic asks for over the wire — so there is nothing
  for the socket checks to compare, and no route was invented so that a check
  could reach behind the service. It is compared the way G3's fill is: a Go
  test that asserts nothing, driven by `scripts/check_go_parity.py`, over rows
  the real `kernel/mapping.py` made from payloads generated off the
  questionnaires. 83 parity checks became 89.

  Every refusal is carried as a refusal: an observation with no status, an
  observation carrying a certainty R4 has no element for, a section slice
  NRCeS does not declare, a visit with nobody on it, a resource with no
  projection. An empty narrative is DECLINED rather than published as a
  heading claiming a note, and the engine then refuses the document for
  having nothing in it, which is the hole the fallback was built to close said
  by the engine rather than asserted by a check.

  **`ToFHIR` keeps its one caller, and that is the decision rather than an
  omission.** The Go projection goes the way the Python does: a coding is
  built from stored COLUMNS, which are text read back out of SQLite. Routing
  it through `terminology.Coding` instead would re-resolve every stored code
  at projection time, which changes behaviour rather than porting it — a row
  whose code its value set no longer holds is published by the Python as what
  the row says, and a Coding-based path would refuse to publish it at all.
  The write path is where a code is vouched for; by the time a row is read
  back, the row IS the record of that proof.

  **A THIRD SEAM THAT BELONGS TO NO SLICE: the placement declaration does not
  travel.** `documents` in `bundles/<id>/bundle.yaml` says which section of
  which profile each kind of row is filed under. It is absent from
  `kernel/contracts.BUNDLE_KEYS`, so the word "documents" does not appear in
  `catalogue.json` at all and **no Go process can read it**. `Document()`
  therefore takes the placement as an argument, exactly as the Python does,
  and the parity check passes it the Python bundle's own. The production
  caller is the outbox, so this is G8's to close, and closing it means editing
  `kernel/contracts.py` and `kernel/declarations.py` — outside what this slice
  was allowed to touch. Until it is closed, no Go path can publish a document
  even once the outbox exists. Like the planner and codification before it,
  this was found by the slice that bumped into it.

  Also landed, and it is a gap rather than a port: **the Go engine is now held
  to the rule the Python engine was already held to.** `scripts/check_rx.py`
  and `scripts/check_vitals.py` assert that no engine MODULE types a
  diagnosis, a drug, a route, a frequency or a unit; nothing asserted it of a
  Go file, so the port could have moved `if code == "29463-7"` across the
  language boundary unobserved. 24 Go files against 56 words from 5 value
  sets.
- **G7. Plugins.** A facility's shape as one list of what it does not run,
  subtracted once, denied and never hidden.

  **Landed 2026-11-01.** The subtraction had already crossed, as five
  unexported functions beside the routes in `cmd/api`, and `facility_shape()`
  was 4 of 4 on it. What had not crossed is the half of `kernel/plugins.py`
  that REFUSES, and the gap was measurable rather than theoretical:
  `PHC_FACILITY` misspelt by one letter resolved to no declaration, no
  declaration withheld nothing, and the Go kernel came up answering
  `GET /facility` with the misspelt name and an empty `withheld`, serving
  every laboratory tool to a centre meant to have no laboratory. The Python
  refuses to load. So the five functions moved to `care_phc_mcp/plugins`,
  where a test and the differential check can reach them, and `Lint` moved
  with them; it runs at startup and is fatal, which is what
  `kernel/declarations.load` raising `DeclarationError` means on this side.

  **Every DECLARED shape is linted, not the chosen one.** That is the
  Python's loop and it is the asymmetry this slice invites: a lint reading
  only the shape this build runs passes at the centre that runs every plugin
  and ships a narrowed one that stops the line.

  Also served: `GET /roles` and `PUT /roles/{role}`, which the Go route table
  had already marked G7's. A role editor is the one place a capability can be
  ADDED to a caller after the bundle declared it, so it is the one place the
  facility's subtraction can be stepped around. The override is what a caller
  holds BEFORE the subtraction, never after, and a save is validated against
  the loaded bundle's sixteen capabilities rather than the embedded file's
  twenty-two. Both orders are indistinguishable at `all-plugins`, which is why
  the check asserts them at every shape that withholds something and says the
  claim is vacuous at the one that does not.

  The four measures are unmoved and could not have moved: `check_live.py` is
  16 of 16, `e2e.py main()` is 21 of 49 and still stops at `POST /khoj`, and
  `facility_shape()` stays 4 of 4, still 14 tools to the no-laboratory centre.
  89 parity checks became 102.

  **A FOURTH SEAM THAT BELONGS TO NO SLICE: the SHAPE of a declaration is
  linted only where the YAML is parsed.** Three of `plugins.lint`'s refusals
  are about shape rather than content -- an unknown key on a plugin or a
  facility, a declaration that is not a mapping, and the `off:` spelling YAML
  1.1 reads as the boolean false -- and `kernel/declarations.compile_json`
  writes only the known keys of `plugins:` and `facilities:` into
  `catalogue.json` and drops the rest. So they have already been discarded by
  the time any Go process can look, and nothing here pretends otherwise: the
  parity check names them instead of carrying them. This is not a dependency
  problem (`gopkg.in/yaml.v3` is already in `go.mod`); it is the question of
  whether the Go kernel re-reads `bundles/<id>/bundle.yaml` or whether the
  compile step stays the only place a declaration's shape is checked. It
  matters at G9: retire the Python and a threshold typed into a facility
  declaration is silently dropped by nothing and refused by nobody. Like the
  planner, codification and the placement declaration before it, this was
  found by the slice that bumped into it.
- **G8. The outbox.** Durable, nothing lost, nothing sent twice, nothing
  reported as sent when it was not. Still switched off: the audio retention
  window is unsigned.
- **G8b. The planner. LANDED 2026-11-01.** `POST /khoj`, the ask-and-search
  turn in `agent/turn.py`. **Added 2026-10-31, after G4,** because no slice
  owned it and 28 of the 49 socket checks in `scripts/e2e.py main()` sat
  behind it. The nine original slices were drawn from the kernel and the API;
  the planner is neither, which is how it went unnamed.

  What landed: `care_phc_mcp/planner`, the deterministic router of
  `agent/planner.py` and the ordering, carding and wording of `agent/turn.py`,
  over the same guard on the same machine surface. `scripts/e2e.py` on Go went
  from 21 of 49 to 44 of 49, and `scripts/check_go_parity.py` from 102 checks
  to 108. The spoken field names are read from the tree at startup, beside the
  questionnaires and the value sets, and not restated in Go.

  **The half that did NOT land, and is not a stub.** `agent/planner.py` has
  two backends. `route()` is ported. `llm()`, the anthropic SDK on
  claude-opus-5 when `ANTHROPIC_API_KEY` is set, is not: it would need a
  network call and a third-party dependency, and this port may take neither.
  `planner.Backend()` answers `"llm"` exactly where the Python's does, and
  `Plan()` then returns an error naming the gap rather than planning with the
  router and reporting a backend that did not run. Nothing compares the two
  engines on that branch, because there is nothing on the Go side to compare;
  the Python's own `llm()` has never been run against api.anthropic.com
  either. **This is the owner's: whether the Go kernel grows an SDK
  dependency, or whether khoj's llm backend stays a Python-only path after
  G9.** It blocks G9 for any facility that sets a key.

  **The deprecated spelling is held by the route table and not by a call.**
  `/agent/say` is served on Go by the same handler as `/khoj`, exactly as
  `api/main.py` serves it by delegating. The two engines are compared on the
  route table and on the verb, but no check POSTs a sentence to that spelling
  across engines, because `scripts/check_khoj.py` forbids any tracked source
  file outside the alias itself from naming that path in code and
  `scripts/check_go_parity.py` is not on its allowlist. **Widening that
  allowlist is a human call**, and the exposure that file already documents
  for `api/main.py` is the same one.
- **G8c. Codification.** `kernel/codification.py`, the seam that turns spoken
  words into suggested codes. **Added 2026-10-31, after G5,** for the same
  reason G8b was: no slice owned it. It is the only product caller of the
  terminology package's semantic tags, which is how G5 found it. Its Go
  counterpart decides whether an uncached value set is an error or simply a
  set with no categories; today the Python raises and the Go returns nothing,
  and no Go caller reads it either way.
- **The fifth seam: one bundle is compiled INTO the binary.** Found by G8b,
  which is the slice that bumped into it. `care_phc_mcp/catalogue.json` is
  embedded at build time with `//go:embed`, and `cmd/api` refuses by name to
  serve a bundle it was not compiled for. That refusal is right and is not the
  problem. The problem is that `scripts/e2e.py`'s `lab_separation()` starts a
  SECOND bundle on its own kernel and its own file, so the last 5 of the 49
  socket checks cannot pass against Go however correct the engine is: the
  binary would have to be rebuilt between them. It belongs to no slice. G1
  embedded the file, every slice since has read it, and no slice owns the
  question of whether a Go kernel reads `catalogue.json` from the tree at
  startup, the way it already reads the questionnaires, the value sets, the
  seed and now the spoken field names. **It blocks G9: a facility running two
  bundles cannot be served by one Go binary today, and the laboratory's own
  separation rule is unproven on Go for that reason and no other.**
- **G9. Retire the Python.** Only on the owner's word, and only when every
  check passes against Go.

## Two facts about this repository, learned the hard way

**`main` is not this project.** It carries an ABDM documentation portal, an
unrelated piece of work that happens to share this repository. Every line of
Eka Scribe lives on `feat/phc-catalogue-and-guard` and nowhere else. So a pull
request from this branch to `main` would propose replacing that portal with
this product. Nobody should open one. A fresh session is told "main branch:
main" by its own tooling and will believe it.

**A green gate does not always mean the whole gate.** `scripts/check.sh` skips
every renderer check when `web/node_modules` is missing, which is the normal
state of a fresh worktree. That is 109 of the 894 checks. It printed one
warning line and then "all checks passed", and an agent working in a worktree
read the bottom line, reported green, and was counting 785. Its work was
sound; its verdict was narrower than it knew. The script now names what it
skipped beside the verdict.

## Open, and the owner's

- **Authentication.** There is none today: `caller()` reads an HTTP header and
  the one account holds every capability. The port must not invent an auth
  model. Carry the header, name the gap, and leave the decision.
- **When the Python goes.** Not an agent's call.
- **Whether `documents` joins `kernel/contracts.BUNDLE_KEYS`.** Added
  2026-10-31, after G6. The placement declaration in `bundles/<id>/bundle.yaml`
  says which section of which profile each kind of row is filed under. It is
  not a bundle key, so the word never reaches `catalogue.json` and no Go
  process can read it. `Document()` takes it as an argument instead. This is
  a change to the compiled artifact's public contract, and it blocks G8: no
  Go path can publish a document even once the outbox exists.
- **What replaces the two Python-only holds at G9.** Added 2026-10-31, after
  G6. The Go section table and the Go observation-status refusal are held by
  the differential check PLUS two Python checks and nothing else:
  `scripts/check_rx.py`'s section-code assertion, which pins the codes
  against the NRCeS fact sheet, and `python3 -m kernel.fhir`'s own demo.
  Retiring the Python without replacing those two loses both holds. They
  must move, not be deleted with it.
- **Whether the Go kernel re-lints a declaration's SHAPE.** Added 2026-11-01,
  after G7. Three of `kernel/plugins.lint`'s refusals are about the shape of a
  plugin or a facility declaration and are caught where `bundle.yaml` is
  parsed; `catalogue.json` carries only the known keys, so no Go process can
  see them. Either the Go kernel reads the bundle's YAML itself, or the
  compile step remains the only gate and something must hold it after G9. Not
  an agent's call: it decides whether a Go-only deployment can be trusted with
  a hand-edited facility declaration.

- **`MedicationRequest.status` defaults to `"unknown"` where
  `Observation.status` refuses.** Added 2026-10-31, after G6. Two resources,
  two answers to the same question, in one file whose docstring says it may
  not choose how settled a measurement is. `"unknown"` is in the bound value
  set, so it is legal. Which of the two is right is a clinical call, and the
  Go side copies the Python exactly until it is made.
