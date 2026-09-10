# ABDM Developer Portal, V1 Phase 1: Architecture and Execution Plan

**Bedrock:** "The ABDM Developer Portal, shipped in six weeks" deck (four building blocks, weekly increments)
**Target:** usable V1 in the first week of September 2026 (roughly ten working days from 23 August)
**Functional and strategic owner:** Product · **Technical owner:** Shyamjith
**Status:** Draft v1.0, refineable. No em dashes anywhere in this document or in anything it produces.

---

<a id="p0-summary"></a>
## 0. The one-paragraph version

We are building one knowledge catalogue of India's health gateways, scoped in phases: HIE-CM M1 to M3 in Phase 1, HIE-CM M4 and UHI in Phase 2, NHCX out of scope (§7). It is written so a first-day developer can follow it and structured so a machine can compile it. A self-hosted Docusaurus site with Scalar's open source reference component renders the human side; our own Go MCP server with hybrid retrieval serves the machine side. A build pipeline compiles the same catalogue into agent skills, a plugin, an index and the MCP's snapshot, and re-runs whenever NHA changes something. The first consumers of the MCP are integrators' coding agents and the site's search box. Everything is FOSS, self-hosted, and runs without Eka. Eka is the first user, not a dependency.

---

<a id="p1-building-blocks"></a>
## 1. The four building blocks and how they connect

Four things are built. One is the source, three are renderings of it.

```mermaid
flowchart TB
    subgraph SRC["Building block 01 · The Catalogue (source of truth)"]
        ATOMS["Typed atoms<br/>markdown + frontmatter<br/>HIE-CM M1 to M3 · shared"]
        OAS["HIE-CM OpenAPI, one file per module<br/>callbacks as OpenAPI 3.1 webhooks<br/>ingested from NHA, linted"]
    end
    subgraph REND["Renderings, all generated from 01"]
        DOCS["04 · Docs site<br/>Docusaurus + Scalar references, self-hosted"]
        MCP["02 · Docs MCP server<br/>own Go server, hybrid retrieval, nine tools"]
        SK["03 · Skills + plugin + index<br/>compiled, validated, installable alone or together"]
    end
    subgraph USERS["Who uses what"]
        DEV["Integrator reading in a browser"]
        AGENT["Coding agent in the integrator's repo"]
        SUP["Internal support agent"]
    end
    ATOMS --> DOCS
    OAS --> DOCS
    ATOMS --> SK
    OAS --> MCP
    DOCS --> MCP
    DOCS --> DEV
    SK --> AGENT
    MCP --> AGENT
    MCP --> SUP
    NHA["NHA sources<br/>swagger · GitHub · sandbox docs"] -->|watched daily| SRC
```

| Block | What it is in V1 | Rule that keeps it honest |
|---|---|---|
| 01 Catalogue | NHA's HIE-CM M1 to M3 endpoints, written as atoms that a first-day developer can read and a compiler can parse (§3) | Nothing downstream is hand-maintained. CI fails if a skill names an endpoint or error the Catalogue does not have. |
| 02 MCP | Our own Go Docs MCP server: nine read tools over one indexed snapshot of the Catalogue, hybrid keyword plus semantic retrieval (§6) | Retrieval only. Nothing executes against NHA. Every response carries catalogue version and verification status. |
| 03 Skills | Compiled from atoms. One index skill, per-milestone build/test/debug skills, one plugin bundle. Every skill runs an OODA loop (§4.2) | The compiler may reword, never add facts. |
| 04 Docs | Docusaurus site with self-hosted Scalar API references, structured after developer.eka.care's flow pages | Stale atoms render a banner; unverified ones say so. |

Every two days ends with something an integrator can actually use (§8.2).

<a id="p2-principles"></a>
## 2. Principles (the ones we will be held to)

| # | Principle | How it is enforced, not just stated |
|---|---|---|
| P1 | Scope is phased and declared, never implied: HIE-CM M1 to M3 now, M4 and UHI in Phase 2, NHCX out of scope (§7) | Catalogue schema keeps the mandatory `gateway` field. The index skill refuses to build if any Phase 1 milestone has zero verified atoms, and lint rejects any atom with `gateway: nhcx`. |
| P2 | The documentation is the knowledge base that powers everything | Skills, llms.txt, MCP resources and the support agent are all build outputs of the Catalogue. Nothing is hand-maintained downstream. CI fails if a skill references an endpoint or error code that is not in the Catalogue. |
| P3 | No em dashes anywhere, write like a person | A lint rule in CI blocks any U+2014 character. A writing guide (§3.5) is part of the repo and the skill-compiler prompt. |
| P4 | Human readable and machine readable from one source, not two versions | Typed atoms with frontmatter plus structured blocks inside prose (§3). One file, many renderings. |
| P5 | Fool, idiot and dummy proof | Every atom must carry the five dummy-proof fields (§3.4) or CI rejects it. A "first-day developer" test is part of the definition of done (§9). |
| P6 | FOSS, replicable, no Eka dependency, no vendor cloud | Catalogue in a public git repo under a neutral licence, copyright NHA. Everything self-hosted from day one: Docusaurus with the MIT Scalar packages vendored (no CDN, no Scalar cloud services, telemetry off), our own Go MCP server, embeddings from a self-hosted Ollama sidecar. The handover unit is one compose file. No `eka.care` URL anywhere in the core Catalogue. Eka-specific content, if any, lives in a separate overlay repo. |
| P7 | Update once, everything moves | A source watcher opens a pull request when NHA changes a spec. Merge triggers docs publish, skill recompile, plugin version bump (§5). |

---

<a id="p3-catalogue"></a>
## 3. The Catalogue: one source, many renderings

<a id="p3-1-problem"></a>
### 3.1 The problem we are solving

Humans need narrative, context, warnings and examples. Machines need schemas, identifiers, typed relationships and exact values. Most teams write both and they drift within a month. We will not write both. We will write atoms.

<a id="p3-2-atom"></a>
### 3.2 What an atom is

An atom is one markdown file with YAML frontmatter. The frontmatter is the machine half. The body is the human half. Structured facts inside the body live in fenced blocks with a declared schema so the compiler can lift them out without parsing prose.

```
catalogue/
  hiecm/
    concepts/        consent-artefact.md, care-context.md, hip-hiu-roles.md ...
    flows/           m1-abha-create-aadhaar.md, m2-link-care-context.md ...
    endpoints/       (generated stubs, one per OpenAPI operation, prose added by hand)
    callbacks/       on-fetch-modes.md, hip-data-request.md ...
    errors/          abdm-1035.md, gateway-1401.md ...
    tests/           m1-tc-01.md ... (NHA functional test cases, one atom each)
    decisions/       data-custody.md, integration-method.md ...
  uhi/               (Phase 2, empty in V1, the folder exists so Phase 2 adds files rather than moving them)
  shared/
    glossary/        abha.md, hfr.md, x-cm-id.md ...
    fhir/            opconsultation.md, prescription.md, diagnosticreport.md ...
    sandbox/         registration.md, credentials.md, callback-url.md ...
  openapi/
    CONVENTIONS.md          (the rules every spec file follows)
    hiecm-gateway.yaml      (session token, used by every module)
    hiecm-m1.yaml           (one self-contained file per module; callbacks
    hiecm-m2.yaml            live inside the module file that owns them, as
    hiecm-m3.yaml            OpenAPI 3.1 webhooks, so one file is the whole
    hiecm-m4.yaml            contract for that module)
    .raw/                   (upstream NHA files, stored untouched)
    corrections/            (recorded patches, never silent fixes)
```

<a id="p3-3-frontmatter"></a>
### 3.3 The frontmatter schema (mandatory fields)

```yaml
id: hiecm.flow.m2-link-care-context      # stable, never reused
type: flow                               # concept | flow | endpoint | callback | error | test | decision | glossary | fhir | sandbox
gateway: hiecm                           # hiecm | uhi | shared (uhi is Phase 2, nhcx is out of scope)
milestone: M2                            # M1 | M2 | M3 | M4 | n/a (M4 is Phase 2)
version: abdm-v3                         # the NHA spec version this is true for
title: Link a care context to a patient's ABHA
summary: >                               # one sentence a new developer understands
  Tell ABDM that this patient had a visit at your facility so their records can be found later.
sources:                                 # where this came from, always at least one
  - url: https://sandbox.abdm.gov.in/swagger/ndhm-hip.yaml
    fetched: 2026-08-24
    hash: sha256:...
verified:
  status: verified                       # verified | unverified | stale
  against: sandbox                       # sandbox | prod | docs-only
  on: 2026-08-25
  by: shyamjith
related:
  endpoints: [hiecm.endpoint.links-link-add-contexts]
  callbacks: [hiecm.callback.on-add-contexts]
  errors: [hiecm.error.abdm-1035, hiecm.error.abdm-1037]
  tests: [hiecm.test.m2-tc-03]
  concepts: [hiecm.concept.care-context]
skills:                                  # which compiled skills consume this atom
  - hiecm-m2-build
  - hiecm-m2-test
```

The `related` map is what turns the Catalogue into a graph. The index skill is generated by walking it.

<a id="p3-4-dummy-proof"></a>
### 3.4 The five dummy-proof fields (every atom, no exceptions)

Inside the body, five headings are required. The compiler checks for them. A reviewer checks they are honest.

1. **In plain words.** What this is, for someone who has never heard of ABDM. No acronyms without a glossary link.
2. **Before you start.** What must already be true. Credentials, registrations, a previous step. Each item links to the atom that gets you there.
3. **What happens.** The sequence, with who calls whom. Flows get a mermaid sequence diagram. Endpoints get a working curl with every placeholder named like `<YOUR_CLIENT_ID>`.
4. **How you know it worked.** The exact response, callback or state change to look for. Not "success" but "you receive a callback at `/on-add-contexts` with `status: SUCCESS` within 60 seconds."
5. **When it goes wrong.** The three to five most common failures, each linking to an error atom that names the fix.

<a id="p3-5-writing-guide"></a>
### 3.5 Writing guide (short, binding)

- Short sentences. One idea per sentence.
- Say "you" and "your system." Say "NHA's gateway," not "the platform."
- Explain the why once, then get to the how.
- No em dashes. Use a full stop, a comma, or a colon.
- No "simply," "just," "obviously." If it were simple they would not be reading.
- Every acronym links to the glossary on first use in every atom.
- Every code sample runs against sandbox as written, once placeholders are filled.
- When we are not sure, we say "unverified" in the frontmatter and in the prose. Never guess.

<a id="p3-6-scalar"></a>
### 3.6 How the docs site renders it

The site is Docusaurus, self-hosted, with Scalar's MIT licensed API Reference component embedded through `@scalar/docusaurus`. Docusaurus owns the guides, navigation, search (a local build-time index, no third party service), theming and versioning; Scalar renders one interactive reference per specification file, `/reference/hiecm-gateway` and `/reference/hiecm-m1` through `-m4`. Callbacks render inside each module's reference from its `webhooks` section. The catalogue version is stamped into the footer from `catalogue/VERSION`.

Self-hosting is total, not partial: the Scalar browser bundle is vendored into the site at build time (nothing loads from a CDN), and every Scalar cloud touchpoint is off: the request proxy, Ask AI, the hosted API client link, telemetry, the platform toolbar. The decision was made when the hosting requirement became "our infra now, NHA's later": the earlier hosted-for-speed stance in this plan is superseded.

What this choice costs, and what replaces it: Scalar's hosted platform would have provided a Docs MCP, Ask AI, and a mock server for free. Instead the Docs MCP is our own Go server (§6), answer synthesis is deliberately left to the consuming agent, and a mock server is unbuilt until something needs it. Spectral linting runs in our own CI.

What the site does not do: author long guides (that is the atom bodies), compile skills (§4), watch NHA for changes (§5), serve machine retrieval (§6).


<a id="p3-7-graph"></a>
### 3.7 What the Catalogue looks like as a graph

The `related` map turns files into a graph. This is what the index skill walks and what the support agent cites. A small slice for M2:

```mermaid
flowchart LR
    C1["concept<br/>care-context"]
    F1["flow<br/>m2-link-care-context"]
    E1["endpoint<br/>links/link/add-contexts"]
    CB1["callback<br/>on-add-contexts"]
    ER1["error<br/>ABDM-1035<br/>facility not onboarded"]
    ER2["error<br/>ABDM-1037<br/>invalid care context"]
    T1["test<br/>M2-TC-03"]
    D1["decision<br/>integration-method"]
    G1["glossary<br/>X-HIP-ID"]
    S1["skill<br/>hiecm-m2-build"]
    S2["skill<br/>hiecm-m2-debug"]
    C1 --> F1
    F1 --> E1
    F1 --> CB1
    F1 --> ER1
    F1 --> ER2
    F1 --> T1
    F1 --> D1
    E1 --> G1
    F1 -.-> S1
    ER1 -.-> S2
    ER2 -.-> S2
    T1 -.-> S1
```

<a id="p3-8-atom-life"></a>
### 3.8 The life of an atom

```mermaid
stateDiagram-v2
    [*] --> draft : stub generated from OpenAPI or created by hand
    draft --> unverified : five sections written, lint passes
    unverified --> verified : run against sandbox, response recorded, reviewer stamps
    verified --> stale : watcher sees the source hash change
    stale --> unverified : atom edited to match new source
    stale --> verified : reviewed, change did not affect this atom
    note right of stale : renders a banner on the site, compiled skill warns the agent
    note right of unverified : renders an "unverified" label, support agent says so when citing
```

<a id="p3-9-docs-ux"></a>
### 3.9 Docs site structure and UX

The rendered site follows the Mintlify pattern integrators already know from code.claude.com/docs and developer.eka.care: a top bar of tabs, a left sidebar per tab, and a content pane. Three features sit in the chrome on every page: a language selector, spotlight search (Cmd+K), and an agent path into the content. Search is the site's local build-time index. The agent path is the Docs MCP rather than an embedded assistant: answer synthesis stays in the consuming agent in V1, and an on-site assistant is a later addition in front of `/api/search`. The language selector ships when a second locale exists.

Four principles govern every page, on top of the writing guide (§3.5):

- Simple language, and never an em dash.
- Interlinked. Every mention of a concept, API, error or section is a hyperlink to its atom. No dead-end mentions.
- Chronological. A reader is always on a step of a journey, with the previous and next step visible. Pages order by when a developer needs them, not alphabetically.
- Progress based. A module page walks one ladder: overview and prerequisites, user journey with flow diagrams, use cases, agent skill install CTA per agent (Claude, Cursor and others), implementation methodology with mandatory and optional paths, API sequence with webhooks, per-API explanation, error mapping, then test cases stated functionally and technically.

Four tabs:

1. **Overview.** ABDM in plain words, get started and sandbox signup, the glossary, and the building blocks tree: gateways (HIE-CM with its modules and roles PHR, HMIS, EMR, LIMS, pharmacy, HIP, HIU; UHI with HSPA and EUA; NHCX), registries (ABHA, NHPR with HPR and HFR), and what you can build.
2. **API References.** Choose gateway, then role, then module, then descend the module ladder above. Phase scope applies: HIE-CM M1 to M3 have content, UHI and M4 say Phase 2, NHCX says out of scope.
3. **What's New.** The changelog, fed by the update pipeline (§5).
4. **Support.** Contact channels and links to connectors.

The tab and sidebar tree is the specification the navigation generator (§3.6) targets. It is still generated from atom frontmatter, never hand-edited. Full detail lives in the `docs-ux` skill.

---

<a id="p4-skills"></a>
## 4. Skills, plugin and index: compiled, not written

<a id="p4-1-model"></a>
### 4.1 The model

The existing `abdm-connect` plugin is the structural template: a `plugins/<name>/` directory with `skills/`, `agents/`, `commands/`, and a manifest. We keep the shape and change the content source. Every skill is a build output of the Catalogue.

```mermaid
flowchart LR
    CAT["Catalogue atoms<br/>(markdown + frontmatter)"] --> SEL["Selector<br/>reads atom.skills[]"]
    SEL --> TPL["Skill templates<br/>one per skill kind"]
    TPL --> GEN["Compiler<br/>deterministic assembly<br/>+ LLM prose pass with the writing guide"]
    GEN --> VAL["Validator<br/>links resolve · ids exist in Catalogue<br/>no em dash · required sections present<br/>SKILL.md frontmatter valid"]
    VAL --> OUT["plugins/abdm/skills/*/SKILL.md<br/>+ references/ + scripts/"]
    OUT --> IDX["Index skill<br/>generated from the atom graph"]
    OUT --> PKG["Plugin manifest<br/>+ per-skill install via skills CLI"]
```

The LLM prose pass exists because deterministic assembly produces stilted text. It is constrained: it may reword, it may not add facts. The validator diffs every identifier, URL, header name and status code in the output against the Catalogue. Anything new fails the build.


<a id="p4-2-ooda"></a>
### 4.2 Every skill runs an OODA loop

Integration against NHA is asynchronous, the sandbox is flaky, and the counterparty you need (a PHR app, a live HIP) is often not there. A skill that reads like a recipe fails the first time the sandbox returns something the recipe did not expect. So every build, test and debug skill is written as a loop, not a list. The loop is Boyd's OODA: observe, orient, decide, act, and back to observe. Speed through the loop matters more than perfection in any one pass.

```mermaid
flowchart LR
    O1["OBSERVE<br/>what is the actual state right now?<br/>last response · last callback · state table<br/>sandbox status · error code"]
    O2["ORIENT<br/>which Catalogue atom does this match?<br/>flow step · error atom · test case<br/>which hypotheses fit, which do not?"]
    D["DECIDE<br/>pick the cheapest action that<br/>produces a new observation<br/>state the hypothesis and the timeout"]
    A["ACT<br/>run the step · call the endpoint<br/>apply the fix · wait for the callback"]
    O1 --> O2 --> D --> A
    A --> STOP{"exit condition met?<br/>'how you know it worked'<br/>from the atom"}
    STOP -->|yes| DONE["report: atoms used,<br/>observations, evidence"]
    STOP -->|no, under loop limit| O1
    STOP -->|no, limit hit| ESC["escalate: what was observed,<br/>what was tried, which atom to read,<br/>one question for the human"]
```

What each phase reads from the Catalogue, and what it writes:

| Phase | Reads | Writes | Time box |
|---|---|---|---|
| Observe | Nothing from the Catalogue. Only live facts: responses, callbacks, state, logs. The skill is forbidden from assuming the previous step worked. | An observation record: timestamp, request id, what came back. | The atom's "how you know it worked" wait time, for example 60 seconds for a callback. |
| Orient | The atom graph. Match the observation to a flow step, an error atom, or a test case. List at least two hypotheses when the match is not exact. | A short orientation note: "matches `hiecm.error.abdm-1035`, facility not onboarded; alternative: wrong `X-HIP-ID`." | One pass. No re-reading the whole Catalogue. |
| Decide | The matched atom's "when it goes wrong" and "before you start" sections. | A decision with a hypothesis, the observation that will confirm it, and a fallback. Reversible actions first. | Immediate. Seventy percent confidence now beats certainty after the sandbox session expires. |
| Act | The atom's curl, script or fix. | The action and its raw result, appended to the loop log. | The action's own timeout. |

Three rules make the loop dummy proof rather than merely iterative:

1. **Exit conditions come from the atom, not the agent.** A skill is done when the matched atom's "how you know it worked" is observed. It is never done because the agent feels finished.
2. **Loop limits are explicit.** Build skills allow eight loops per step, test skills allow three per test case, debug skills allow five per error. Hitting the limit is an escalation, and the escalation must name the observation, the hypotheses tried, and the one atom the human should read.
3. **Pre-planned responses skip Decide.** For error atoms with a single known fix (reused REQUEST-ID, missing X-CM-ID, clock skew), the skill goes Observe, Orient, Act. The Catalogue marks these atoms `fix.deterministic: true` and the compiler emits them as direct actions.

The skill kinds differ only in where they start and what counts as exit:

| Skill kind | Starts by observing | Exit condition | Typical loops |
|---|---|---|---|
| build | the repo: what exists, which credentials are configured, which steps are already done | every flow step's "how you know it worked" observed once against sandbox | one per flow step |
| test | the test atom's preconditions | every NHA test case in the milestone passes or is marked "needs human" with the reason | one per test case |
| debug | the error, the last request id, the state table | the error atom's fix applied and the original step's exit condition observed | one per hypothesis |

Parallel loops are allowed where steps are independent (FHIR bundles per hi_type, test cases without shared state). The index skill says which steps are independent; everything else runs one loop at a time because the state it depends on (token, hip id, patient id, consent id) is shared.


<a id="p4-3-skill-set"></a>
### 4.3 The skill set for V1

Each milestone has three independently installable skills, because an integrator debugging M2 on a Tuesday should not have to load M1 build instructions.

| Skill | Kind | Atoms it draws from | Installs alone? |
|---|---|---|---|
| `abdm-index` | router | whole graph | yes, and it is the recommended first install |
| `abdm-overview` | orient | shared concepts, milestones, which-do-I-need table | yes |
| `abdm-sandbox` | orient | sandbox registration, credentials, callback URL, test ABHAs | yes |
| `hiecm-m1-build` / `-test` / `-debug` | build, test, debug | M1 flows, endpoints, callbacks, tests, errors | yes, each |
| `hiecm-m2-build` / `-test` / `-debug` | same | M2 incl. discovery, on-fetch, ECDH | yes, each |
| `hiecm-m3-build` / `-test` / `-debug` | same | M3 incl. consent lifecycle, keysets, decryption | yes, each |
| `fhir-bundles` | build | shared FHIR atoms per hi_type, NRCeS validator | yes |
| `abdm-errors` | debug | every error atom in scope | yes |
| `abdm-plugin` | bundle | all of the above | the whole thing in one install |

`hiecm-m4-*` and `uhi-*` are Phase 2 and are not built in V1. There are no NHCX skills, now or later.

`build` skills scaffold code and say exactly which atoms they used. All three kinds run the loop in §4.2. `test` skills drive the NHA functional test cases as runnable steps and mark which need a human (OTP). `debug` skills take an error or a stuck state and walk the error atoms to a named fix.

<a id="p4-4-index"></a>
### 4.4 The index skill

`abdm-index` is generated, not written. It lists every skill, every agent and every tool with a one-line trigger description, and a decision tree: "What are you building?" leads to "Which gateway?" leads to "Which milestone?" leads to "Build, test or debug?" It is the only skill that needs to be loaded for an agent to know what else exists. It also carries `catalogue_version`, so an agent can tell the developer "your skills are from catalogue 2026.08.30, the docs are at 2026.09.02, run update."

<a id="p4-5-accumulation"></a>
### 4.5 Agent and tool accumulation

Agents (sub-agent definitions) and tools (scripts under `skills/*/scripts/`) accumulate in the same plugin. V1 ships: a `fhir-validate` script wrapping the NRCeS validator, a `callback-tunnel` script that sets up a public URL for sandbox callbacks, a `request-id` helper, and an `error-decode` script that reads a response and prints the matching error atom. Each is registered in the index.

---

<a id="p5-update-pipeline"></a>
## 5. The update pipeline (the "RAG that updates skills")

Two different things hide behind the word RAG. We separate them.

**Retrieval at question time.** Our Docs MCP does this over the indexed Catalogue: hybrid keyword plus semantic search (§6). The site search box and the support agent use the same server. No separate vector database: embeddings live inside the same SQLite snapshot the indexer builds.

**Regeneration at change time.** This is the pipeline that makes skills follow the docs. It is not retrieval; it is a build.

```mermaid
flowchart TB
    subgraph SOURCES["NHA sources (watched)"]
        S1["sandbox.abdm.gov.in swagger YAMLs"]
        S2["github.com/NHA-ABDM (ABDM-wrapper)"]
        S3["sandbox docs pages (JS app, fetched headless)"]
        S4["NHA circulars / release notes (manual drop folder)"]
    end
    W["Watcher (GitHub Action, daily)<br/>fetch · hash · diff against stored hash"]
    PR["Pull request<br/>changed source + affected atom ids<br/>+ draft edits to atoms flagged stale"]
    REV["Human review<br/>accept, edit, or mark unverified"]
    MERGE["Merge to main"]
    subgraph BUILD["CI on merge"]
        B1["Lint atoms (schema · sections · no em dash · links)"]
        B2["Spectral lint OpenAPI"]
        B3["Build the Docusaurus site (specs synced from the catalogue)"]
        B4["Compile skills · validate · build index"]
        B5["Generate llms.txt + llms-full.txt"]
        B6["Bump catalogue_version · index the catalogue into catalogue.db<br/>(keyword-only on PRs; the deploy build embeds via Ollama)"]
    end
    PUB1["Deploy: static site + docs-mcp image with the new snapshot"]
    PUB2["Plugin release (git tag + skills registry)"]
    PUB3["Context7 refresh (OpenAPI + llms.txt)"]

    S1 --> W
    S2 --> W
    S3 --> W
    S4 --> W
    W --> PR --> REV --> MERGE --> B1 --> B2 --> B3 --> B4 --> B5 --> B6
    B6 --> PUB1
    B6 --> PUB2
    B6 --> PUB3
```

Rules that make this dummy proof:

- A source change never edits a verified atom silently. It flips `verified.status` to `stale` and opens a PR. Stale atoms render with a visible banner on the site and the compiled skill says "this step may have changed, check the docs."
- Every skill and every page carries the `catalogue_version` and the source hashes it was built from.
- The watcher cannot merge. A person does.

---

<a id="p6-mcp"></a>
## 6. MCP in V1 and the internal support agent

<a id="p6-1-surfaces"></a>
### 6.1 What we stand up

One server, built by us, in Go: `docs-mcp`. It serves the Catalogue to machines the way the site serves it to people. A CI-run indexer compiles the Catalogue (atoms plus the OpenAPI files) into a single SQLite snapshot: full-text index, chunk embeddings, the atom relationship graph, error-code mappings, and every operation's contract. The server reads that snapshot read-only and exposes streamable HTTP MCP at `/mcp`, a JSON search endpoint for the site's search box at `/api/search`, and `/healthz`.

Nine tools, each answering a different kind of question:

| Tool | Answers |
|---|---|
| `search_docs` | hybrid keyword plus semantic search, ranked, with verification status on every hit |
| `get_atom` | one atom in full |
| `related_atoms` | the graph walk: a flow's errors, callbacks, tests, concepts, both directions |
| `decode_error` | paste an error code or raw gateway body, get the matching error atoms and fixes |
| `list_atoms` | enumeration by type and milestone |
| `catalogue_info` | version, build time, coverage and verification counts |
| `list_operations` / `get_operation` | the exact machine contract from the OpenAPI files |
| `validate_request` | check a candidate request body against an operation's schema locally, before the sandbox |

Retrieval is hybrid: FTS5 keyword ranking (error codes weighted highest) fused with cosine similarity over per-section chunk embeddings from a self-hosted Ollama sidecar running `nomic-embed-text`. Reciprocal rank fusion merges the two. Degradation is a design rule: without Ollama the indexer builds keyword-only and the server answers from keyword search alone, reporting `embeddings: false` on `/healthz`. Search never hard-depends on the sidecar.

Rules that keep it honest: every response carries `catalogue_version`; every atom result carries `verification_status`; an unknown id returns the closest valid ids, never a guess; `decode_error` with no matching atom says exactly that. Nothing executes against NHA: the earlier idea of a Scalar Installation MCP is superseded, its search-mode value covered by `get_operation` and `validate_request`, and execute mode remains a Phase 2 concern with its own safety design (per-caller credentials, never shared).

| MCP | Where it comes from | Use in V1 |
|---|---|---|
| Docs MCP (`docs-mcp`) | this repo's `mcp/` module, one binary plus one snapshot, deployed with the site | integrators' coding agents; the site search box; later the internal support agent |
| Harness MCP | custom, Phase 2 | ledger, gate, evidence (per v0.2 architecture); not in V1 |

<a id="p6-2-support-agent"></a>
### 6.2 The internal support agent

A Slack or Claude-based agent for the Eka support team, connected to the Docs MCP's public endpoint. It answers integrator questions strictly from the Catalogue, cites the atom id, and says "unverified" when the atom says so. It has no surface of its own on the site in V1: answer synthesis stays in the consuming agent, not the server. When it cannot answer, it opens a GitHub issue against the Catalogue with the question, which is how gaps get found. Paste an error, get the error atom and its fix.

The support agent runs the same loop as the skills, with a human in the Act phase:

```mermaid
sequenceDiagram
    participant H as Support engineer
    participant A as Support agent
    participant M as Docs MCP
    participant G as GitHub (Catalogue)
    H->>A: pastes integrator's error and request id
    A->>M: search(error code, endpoint)
    M-->>A: error atom + flow atom, with verified status
    A->>A: orient: match, list two hypotheses
    A-->>H: answer with atom ids, status labels, the named fix, and what to ask the integrator next
    alt no atom matches
        A->>G: open issue: question, context, closest atoms
        A-->>H: "not in the Catalogue yet, issue #N opened"
    end
```



---

<a id="p7-coverage"></a>
## 7. Gateway coverage and phasing in V1 (honest scope)

Documentation scope is phased. Phase 1 is HIE-CM M1 to M3 at full depth. M4 and UHI are Phase 2. NHCX is out of scope, which is not the same as deferred: nothing is written for it and no NHCX skill ever ships from this Catalogue. Depth and phase are stated on the landing page, in the index skill, and in frontmatter.

| Gateway and milestone | Phase | V1 target depth | What "done" means |
|---|---|---|---|
| HIE-CM (ABDM V3) M1, M2, M3 | **1** | **Dummy proof** | All five dummy-proof sections on every atom. Every endpoint curl verified against sandbox. Every NHA functional test case is an atom. All nine skills compile and pass validation. First-day developer test passes for M1 (§9). |
| HIE-CM M4 (HPR, HFR, bridge linkage) | 2 | Not written in V1 | Nothing ships. The landing page and the index say M4 is Phase 2, so its absence reads as a decision rather than a gap. |
| UHI | 2 | Not written in V1 | Same. The `gateway: uhi` value stays in the schema so Phase 2 adds atoms and needs no migration. |
| NHCX | out of scope | None | Lint rejects any atom with `gateway: nhcx`. The landing page says NHCX is out of scope. |

Three gateways in ten days could never all be dummy proof, and reference-depth pages for gateways nobody is integrating this quarter cost the review time M1 to M3 needs. One gateway, three milestones, fully proven, beats three gateways half-written. A confident wrong page is harmful; a page that does not exist is merely absent, and the index says so out loud.

---

<a id="p8-schedule"></a>
## 8. Execution plan: 23 August to 5 September

Five workstreams, two owners, two-day increments. Functional and strategic work (Product) runs in front of technical work (Shyamjith) by about two days on every stream.

```mermaid
gantt
    dateFormat  YYYY-MM-DD
    axisFormat  %d %b
    section Catalogue
    Atom schema, writing guide, lint rules      :a1, 2026-08-24, 2d
    Ingest NHA HIE-CM OpenAPI, callbacks as webhooks :a2, 2026-08-25, 2d
    HIE-CM M1 atoms (all types)                  :a3, 2026-08-26, 2d
    HIE-CM M2 + M3 atoms                         :a4, 2026-08-28, 3d
    Shared FHIR, glossary, sandbox               :a5, 2026-08-31, 2d
    M1 to M3 verification sweep, gap fixes       :a6, 2026-09-01, 2d
    section Site and MCP
    Docusaurus + Scalar setup, theme, self-host  :b1, 2026-08-25, 2d
    Module specs, conventions, nav               :b2, 2026-08-27, 1d
    Docs MCP server (indexer + nine tools)       :b3, 2026-08-28, 1d
    Deploys, publish pipeline                    :b4, 2026-08-29, 1d
    section Skills
    Compiler, templates, validator               :c1, 2026-08-27, 3d
    Index generator, plugin manifest             :c2, 2026-08-30, 1d
    Compile M1 set, iterate with Catalogue       :c3, 2026-08-31, 2d
    Compile full set, per-skill install test     :c4, 2026-09-02, 2d
    section Pipeline
    Watcher, hash store, PR bot                  :d1, 2026-08-29, 2d
    CI: lint, spectral, compile, publish         :d2, 2026-08-31, 2d
    llms.txt, Context7 publish                   :d3, 2026-09-02, 1d
    section Proof
    Support agent on Docs MCP                    :e1, 2026-09-01, 2d
    First-day developer test (M1)                :e2, 2026-09-03, 1d
    Eval set, score, fix               :e3, 2026-09-03, 2d
    Ship V1                                      :milestone, 2026-09-05, 0d
```

<a id="p8-1-owners"></a>
### 8.1 Who does what

| Stream | Product (functional, strategic) | Shyamjith (technical) |
|---|---|---|
| Catalogue | Atom schema decisions, writing guide, every atom body's five sections, review every PR for dummy-proofness, glossary | OpenAPI ingestion and cleanup, callbacks as webhooks per module file, endpoint atom stubs, sandbox verification runs, `verified` stamps |
| Site and MCP | Information architecture mirroring developer.eka.care flows, theme, landing page copy, depth labels | Docusaurus and Scalar setup, spec conventions, the docs-mcp server and indexer, domains, deploys |
| Skills | Skill templates' prose, index decision tree, trigger descriptions, what each skill must refuse to guess | Compiler, validator, plugin manifest, per-agent adapters (Claude Code first, Cursor and Copilot by manifest) |
| Pipeline | Source inventory (which NHA URLs, which repos, who owns the manual drop folder), review rota | Watcher, PR bot, CI, publishers |
| Proof | Recruit the first-day developer, run the test, write up gaps | Wire the support agent, run the eval set, fix |

<a id="p8-2-increments"></a>
### 8.2 Two-day increments (what an integrator can use at each checkpoint)

| By end of | An integrator can |
|---|---|
| 26 Aug | Open the docs site with NHA's HIE-CM OpenAPI references rendered and searchable, with the sandbox registration guide. |
| 28 Aug | Read dummy-proof M1 pages, run the M1 curls against sandbox, ask the Docs MCP questions. |
| 30 Aug | Install `abdm-index` and `hiecm-m1-*` skills into Claude Code and scaffold M1. |
| 2 Sep | Read M2 and M3 at the same depth, install the full plugin, and see the phase scope stated on every landing page. |
| 5 Sep | Use the whole thing, file a gap from the support agent, and see that a source change to NHA's swagger opens a PR. |

---

<a id="p9-done"></a>
## 9. Definition of done for V1

Every item is checkable. None is a judgement call.

1. Catalogue lint passes on main: schema valid, five sections present, no em dash, all `related` ids resolve, all sources have hashes.
2. Every HIE-CM M1 to M3 endpoint atom has a curl that was run against sandbox on or after 28 August and the response recorded in the atom.
3. Every NHA functional test case for M1 to M3 exists as a test atom and is referenced by a `-test` skill.
4. All skills compile, validate, and install individually with the skills CLI into Claude Code; the plugin installs as one unit.
5. `abdm-index` is generated from the graph and lists every skill, agent and tool.
6. Docs site live (GitHub Pages first, custom domain when ready) with search and the module references; docs-mcp deployed with its nine tools answering over the current snapshot, `/healthz` reporting the catalogue version.
7. The watcher has opened at least one real PR from a real NHA source change (or a staged one if NHA is quiet that week).
8. The support agent answered the six eval tasks (§9.1) from the Catalogue, citing atom ids, with the score recorded.
9. **First-day developer test:** a developer with no ABDM exposure, given only the docs URL and sandbox credentials, reaches a successful M1 ABHA verification sandbox call in under two hours without asking a human. Where they got stuck is filed as Catalogue issues.
10. The landing page, index entries and skill descriptions state the phase scope: HIE-CM M1 to M3 in Phase 1, M4 and UHI in Phase 2, NHCX out of scope. Every unverified atom renders the banner, and lint rejects any atom with `gateway: nhcx`.
11. Public repo, neutral licence, `CONTRIBUTING.md`, `SECURITY.md`, `GOVERNANCE.md`, and no `eka.care` reference in the core Catalogue.

<a id="p9-1-evals"></a>
### 9.1 The six eval tasks

Each is run by an agent using only the plugin and the MCP, scored pass or fail on the exit condition from the relevant atom, and re-run on every Catalogue change.

| # | Task | Exit condition observed |
|---|---|---|
| 1 | Scaffold an ABHA verification flow from an empty repo | sandbox returns a verified ABHA profile |
| 2 | Build and validate an OPConsultation bundle | NRCeS validator passes |
| 3 | Link a care context and push encrypted data | `on-add-contexts` callback with SUCCESS, then a data push acknowledged |
| 4 | Raise an HIU consent request and fetch records | consent artefact received, bundle decrypted and valid |
| 5 | Diagnose a failing HIP data push from its error | correct error atom cited, fix applied, original push succeeds |
| 6 | Walk the M1 to M3 test cases to completion | every test atom passed or marked "needs human" with reason |

<a id="p9-2-firstday"></a>
### 9.2 The first-day developer test, as a flow

```mermaid
flowchart TD
    S["Developer with no ABDM exposure<br/>gets: docs URL, sandbox credentials, a timer"]
    S --> R1["Reads Introduction and Sandbox pages"]
    R1 --> R2["Reads the M1 flow atom: ABHA verification"]
    R2 --> C["Runs the curl from the endpoint atom"]
    C --> Q{"Got the response<br/>the atom said to expect?"}
    Q -->|yes| W["Reads 'how you know it worked', confirms"]
    Q -->|no| E["Reads 'when it goes wrong', follows the error atom"]
    E --> C
    W --> DONE["Stops the timer. Under two hours, no human asked: pass"]
    E -->|stuck, asks a human| FAIL["Fail. Where they got stuck is filed as a Catalogue issue and fixed before ship"]
```


---

<a id="p10-risks"></a>
## 10. Risks and the decision each one needs

| Risk | Mitigation | Decision needed |
|---|---|---|
| NHA swagger YAMLs are inconsistent or incomplete (known 403s on some V3 endpoints in sandbox) | Ingest, then hand-correct with `sources` recording both the NHA file and our correction; mark the endpoint unverified until sandbox confirms | Accept that some endpoints ship unverified in V1 |
| Docusaurus guides and Scalar references are two rendering systems on one site | Keep prose in plain markdown, avoid MDX beyond callouts and steps, so it ports anywhere; specs stay the single source under `catalogue/openapi/` | Decided: fully self-hosted from day one, no hosted-Scalar phase |
| abdm-docs.pages.dev overlaps heavily | Reach out to OHCN before 26 August; propose the Catalogue as the shared upstream | Product to make the call and the call |
| Ten days is not enough for three gateways at full depth | Phase 1 is HIE-CM M1 to M3 only. M4 and UHI move to Phase 2, NHCX is out of scope (§7) | Already decided in this document, needs sign-off |
| LLM prose pass invents facts | Validator diffs every identifier against the Catalogue; any new token fails | None, it is a hard rule |
| The Docs MCP is public with no auth in V1 | Read-only server over public docs; rate limiting at the reverse proxy; Ollama sidecar never exposed | Add auth and quotas only when abuse is observed |
| Ollama sidecar down at query time | Search degrades to keyword-only by design; `/healthz` reports `embeddings: false` | None, the degradation is tested |
| Sandbox credentials take three to four days | Apply on 24 August, in parallel with schema work | Shyamjith applies today |

---

<a id="p11-not-in-v1"></a>
## 11. What is explicitly not in V1

- HIE-CM M4 (HPR, HFR, bridge linkage) and UHI. Both are Phase 2 (§7). The `gateway` and `milestone` values already exist in the schema, so Phase 2 adds atoms rather than migrating any.
- NHCX, entirely. Out of scope rather than deferred, and lint enforces it.
- The conformance harness, ledger, gate and simulators from architecture v0.2. They are Phase 2 and depend on this Catalogue.
- Execute-mode MCP for the public.
- Any Eka-specific overlay (ABDM Connect endpoints, `X-Hip-Id`, `OHPL_001`). That becomes a separate overlay repo that depends on the Catalogue, built after V1.
- Multi-agent orchestration. The index skill routes; a single agent executes.
- Generated SDKs. Scalar can do this from the OpenAPI later; not needed to prove the model.

---

<a id="p12-sources"></a>
## 12. Sources consulted for this plan

- The Phase 1 deck
- developer.eka.care ABDM Connect flow pages (information architecture reference)
- abdm-docs.pages.dev (OHCN community docs; already covers ABDM V3, UHI, NHCX; serves `.md` per page and `llms.txt`)
- Scalar product docs: Docs, Agent and MCP (Docs MCP versus Installation MCP, search versus execute, passthrough auth), Registry, CLI mock server, AsyncAPI support in API Reference 1.57, Enterprise self-host note
- NHA sources: sandbox.abdm.gov.in swagger YAMLs, github.com/NHA-ABDM (UHI, nhcx, ABDM-wrapper), sandbox documentation, functional test case templates
- Agent Skills specification (agentskills.io) for SKILL.md format and per-skill install
- Inkeep's docs-to-skills build pattern (frontmatter tagging, build-time extraction, GitHub Action publish to a dedicated repo)
- Eka `abdm-connect` plugin (structural template for the plugin layout)
