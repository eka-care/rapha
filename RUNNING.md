# Running this

Three processes, in this order: compile, serve, draw. Two facilities at once is
four, which is the whole demo:

```sh
python3 -m catalogue.build && python3 -m kernel.declarations
sh api/run.sh                                                   # PHC   :8000
PHC_BUNDLE=lab PHC_DB=lab.sqlite3 PORT=8001 sh api/run.sh        # LAB   :8001
(cd web && npm run dev)                                          #       :5173
(cd web && VITE_API_BASE=http://localhost:8001 npx vite --port 5174)
```

Nothing here needs CARE, a network, or a database server. Python 3.9 and
Node 22+ are the whole of it. There is now a second adapter, `PHC_STORE=care`,
and it does need all three; see "Switching adapters" below for what it can and
cannot do.

## 0. Once

```sh
python3 -m pip install --user fastapi uvicorn pyyaml     # the API and the linter
python3 -m pip install --user ekacare                    # the ABDM connector, optional
(cd web && npm install)                                   # the renderer
(cd care_phc_mcp && go build -o care_phc_mcp .)           # the MCP server (optional)
```

## 1. Compile the declarations

```sh
python3 -m catalogue.build          # lints catalogue/ops/*.md  -> catalogue/catalogue.json
python3 -m kernel.declarations      # lints bundles/phc/*.md    -> merges into the same file
python3 -m kernel.declarations lab --json   # lints bundles/lab/*.md, writes nothing
```

Both are linters first. `catalogue.build` writes the four original keys
(`capabilities, bundles, states, operations`); `kernel.declarations` merges in
the five new ones (`manifest, workflows, views, instruments, metrics`) and
copies the result to `care_phc_mcp/catalogue.json`, which the Go server embeds.
Run them in that order: the second reads what the first wrote.

If a declaration is wrong, both print `FAIL <file>: <reason>` and change
nothing. That is the whole build system.

## 2. Start the kernel API

```sh
sh api/run.sh                       # http://127.0.0.1:8000
```

On first start it creates `phc.sqlite3` in the repo root and writes whatever
`bundles/<id>/seed.yaml` declares, which for the health centre is six threads,
one standing at each station, so no screen is ever empty. Delete the file to
reseed. `PHC_DB` moves it, `PHC_BUNDLE` picks a different bundle, `PORT`
changes the port.

Every queue view is `scope: today`, so a demo file made last week would
otherwise open on an empty workspace. It does not: `SqliteStore` walks the
seeded threads forward to today whenever it opens the file. Only rows dated on
the seed's own day move, and a thread a person opened is never touched, so real
work keeps its real date and nothing is ever pushed into the future.

Check it:

```sh
curl -s localhost:8000/api/v1/phc/queue | python3 -m json.tool | head -20
```

Both `/api/...` and `/api/v1/phc/...` serve the same router, and both spellings
of every path work, with and without the trailing slash.

### Switching bundles

A bundle is chosen when the API starts, and nothing else changes:

```sh
PHC_BUNDLE=lab PHC_DB=lab.sqlite3 PORT=8001 sh api/run.sh
```

That is the whole switch. The same kernel now runs `bundles/lab/`: a five
station laboratory line (`accession, phlebotomy, processing, verification,
release`), its own operations, its own flags, its own capabilities and roles,
and its own worklist, report and turnaround board. All of those are declared
in `bundles/lab/bundle.yaml` and closed against that bundle alone, so a lab
declaration naming `nurse` or `vitals.recorded` fails the linter. Give it its
own `PHC_DB`: a bundle declares its own fixtures in `bundles/<id>/seed.yaml`,
and the laboratory's are seven specimens with their own names, accession
numbers, panels and referring clinicians. A bundle with no `seed.yaml` opens
empty and does not crash. What a bundle still cannot do is listed in
`bundles/LAB-LOG.md`, which is the honest answer to "does one kernel run
another facility": mostly, and read the log before believing the screens.

Three things the switch does not carry, all of them real:

- **`catalogue.json` holds one bundle's declarations at a time.** The last
  `python3 -m kernel.declarations <id>` to run wins. The API does not read that
  file for its declarations, it loads `bundles/<id>/` itself, so it is right
  either way; the file matters only to the Go MCP server, which embeds it.
- **The MCP server asks the kernel which bundle it loaded** (`/facility`) and
  offers only those operations, so one binary serves both. If it cannot ask, it
  says so on stderr and offers everything it embedded.
- **The renderer follows the API it is pointed at.** To see the laboratory,
  start a second Vite on the second port:

  ```sh
  VITE_API_BASE=http://localhost:8001 npm --prefix web run dev -- --port 5174
  ```

  Its nav tabs, forms and line all come from that kernel. Nothing in `web/` is
  written for a bundle. Questionnaires are the one exception: they are compiled
  in from `questionnaires/*.json` at build time, so a new form needs a restart,
  not a reload.

### Switching adapters

`PHC_STORE` names the system of record. It is read once, in `api/main.py`,
and nothing downstream of it changes: the kernel only ever sees
`kernel.contracts.Store`.

```sh
sh api/run.sh                       # PHC_STORE=local, the default
PHC_STORE=care CARE_BASE_URL=https://your-care CARE_TOKEN=... sh api/run.sh
```

- **`local`** is `adapters/local`, the SQLite file. It needs nothing, it is
  what every check in `scripts/check.sh` runs against, and it is the only
  adapter that has been run end to end. Both bundles, both screens.
- **`care`** is `adapters/care`, CARE's REST API over HTTP. It reads
  `CARE_BASE_URL` and `CARE_TOKEN`, both required, plus `CARE_FACILITY`,
  `CARE_GEO_ORGANIZATION`, `CARE_ABHA_CONFIG` and `CARE_AUTH_PREFIX`
  (`Bearer`, or `Token` for CARE's other scheme) when the calls that need
  them are made. **This has never served a request.** There is no CARE in
  this repository and no credentials for one, so what is proven is the field
  mapping against CARE's published schema and 24 checks against a fake
  transport, not a working facility. Read `adapters/care/map.py` before
  believing any of it: every one of its 88 fields carries a mark saying
  whether it was seen in a live response, read in the schema, read in CARE's
  source, or guessed.

Four things `care` does not do, and refuses rather than guesses:

- **`write("observation", ...)` raises.** CARE exposes no POST that creates
  an observation, so the PHC vitals operation cannot run against CARE today.
  That is the largest single gap.
- **`open_thread` raises.** `EncounterCreateSpec` requires a patient, so CARE
  cannot open a walk-in encounter before the person exists; `adapters/local`
  can. That is a real ordering constraint on a bundle, not a missing feature.
- **A dispense and a specimen are refused** for the same kind of reason:
  CARE wants product and location ids a PHC payload does not carry, and a
  specimen is created from the order it belongs to.
- **Six of the Store methods are not CARE's at all.** The proposal queue, the
  per-thread flags and this kernel's audit trail have no CARE equivalent, so
  they are delegated to a sidecar `SqliteStore` on the same `PHC_DB` file. A
  check asserts none of the six ever reaches the network.

Getting it wrong ends in a sentence, not a traceback. `PHC_STORE=care` with
nothing listening, with no `CARE_TOKEN`, or pointed at something that is not a
CARE, prints what is wrong and how to go back to SQLite, and the kernel does
not start:

```
Cannot use CARE at https://careapi.ohc.network.
CARE is there and refused CARE_TOKEN: {'detail': 'Invalid Token, please relogin to continue'}
Fix that, or run on the SQLite adapter instead: sh api/run.sh
```

## 3. Start the renderer

```sh
(cd web && npm run dev)             # http://localhost:5173
```

It reads `VITE_API_BASE`, default `http://localhost:8000`. The header carries a
"Use demo data" toggle that draws every screen from a fixture and refuses every
write, for when the API is not up.

To watch both facilities at once, run a second Vite against the second kernel:

```sh
(cd web && VITE_API_BASE=http://localhost:8001 npx vite --port 5174)
```

Everything this browser remembers is keyed by that `VITE_API_BASE` (recents,
the questions typed into a composer), because a thread id means nothing on a
different kernel. The role and the theme are not: a role the other kernel does
not declare falls back to its demo account with a toast saying so.

### What you are looking at

A workspace, not a tabbed forms application. Nothing in `web/src` is written
for a bundle; every word below comes from a declaration on the kernel it is
pointed at.

- **The sidebar.** The manifest's title and version. `New chat`, which opens a
  workspace thread scoped to no patient. `Search`, which is the palette.
  Then one nav entry per declared view that is not a summary AND whose
  capability this role holds, with a live count from that view's own read; then
  the last ten threads this browser opened; then the role, its capability count
  and a menu of every role the kernel declares.
- **A patient is a conversation.** Open a thread and the record is a stream of
  messages: what somebody said, what the agent said, one card per posted
  operation with its values labelled by the questionnaire, one card per refusal,
  and a pending proposal with its own commit surface inside the bubble. The
  agent always speaks last: where the visit stands, and up to five things this
  role can do here, each with the reason and an instrument tag. The composer is
  quick-action pills plus an ask box.
- **What you cannot do is absent.** Not greyed. `kernel/state.actions()`
  returns only what the guard says is visible, so the renderer has nothing to
  grey out; the reason for an absence is the agent's second sentence, and the
  right rail's "Capabilities held" card is where the shape of the hidden part
  is visible. The nav obeys the same rule.
- **The palette** (⌘K, the sidebar button, or the topbar pill). Find first:
  threads by name, phone, token and village, declared views, and the agent.
  Selecting one previews it before you commit to it. A query that matches
  nothing offers Register, under the sentence saying a new record is permanent.
- **The right rail.** The workflow's own steps with where the baton is, the
  care unit accrued from the audit, every capability with the held ones lit,
  and the audit trail with its refusals.

## 4. The agent surfaces, optional

The MCP server, pointed at the kernel:

```sh
CARE_BASE_URL=http://127.0.0.1:8000 ./care_phc_mcp/care_phc_mcp
```

It reads `/whoami` to learn its capabilities and offers only the operations
that account may use. Every write tool is `propose_*`; there is no confirm verb
and no path by which it can commit.

The ask box on screen, which needs nothing extra started: the composer at the
foot of every thread posts to the kernel's own route.

```sh
curl -s localhost:8000/api/v1/phc/agent/say \
  -H 'Content-Type: application/json' \
  -d '{"thread": "enc-002", "utterance": "bp 138 over 86, pulse 74"}' \
  | python3 -m json.tool | head -30
```

That route is `api/main.say()`. It calls `agent/turn.py`, which plans with
`agent/planner.py` and then calls `kernel.proposals.propose` on the machine
surface. It takes no `confirmed` argument and has no branch that reaches
`confirm` or `commit`, so the worst a sentence can do is put a card in front
of a person. The reply carries the full thread panel after the turn, and per
proposal the guard's own verdict, the payload it filled, and one plain
sentence saying what to do next. `web/src/ask.ts` posts to exactly this. There
is no second process and no `VITE_AGENT_BASE`.

The planner, from a sentence:

```sh
python3 -m agent                                        # a conversation
python3 -m agent "bp is 140 over 90 and pulse 72"       # one turn and out
python3 -m agent "order a blood sugar" --thread enc-004 --role mo
```

`--thread` defaults to the first thread waiting, `--role` to the kernel's demo
account, `PHC_API` or `--api` to `http://127.0.0.1:8000`. In the conversation:
`:queue`, `:thread <id>`, `:quit`.

With `ANTHROPIC_API_KEY` set and `pip install anthropic` it asks Claude;
without either it uses a keyword router. Either way every proposal is run
past the guard on the machine surface before it is printed, and none of them
can commit: `agent/client.py` holds no verb that would, and refuses to
assemble a URL containing `/confirm` or `/commit` before it opens a socket.

What it leaves behind is a proposal id. Open that thread in the renderer and
the proposal is a message in the conversation, badged "awaiting a person", with
the commit surface drawn inside the bubble: the values a machine filled in,
editable, with the questionnaire's own ranges and a "You changed" diff under
them. What is sent is what is on screen after the edits, the guard runs again
on that payload, and the tap is what writes. Watch it happen:

```sh
python3 -m agent "bp 138 over 86, pulse 74" --thread enc-002
open http://localhost:5173/#/threads/enc-002
```

## 5. The checks

```sh
sh scripts/check.sh                 # everything, about 20 seconds, 273 ok lines
```

That runs the linters, every Python and Go unit check, the browser-side checks,
`bundles/lab/check.py` (a second bundle on the same kernel, with its own socket
half), and `scripts/e2e.py`, which starts its own uvicorn on a free port, walks
a patient through the line over HTTP, reads the SQLite file to prove the row
landed, drives the Go MCP binary at it, posts a sentence to `/agent/say` and
confirms what comes back, confirms one of those cards with an EDITED payload
and proves the edited value is what lands rather than the proposed one, then
starts a second kernel as the laboratory and proves that the account which
keyed a result cannot verify it: not on the panel, not on either surface, and
not by asking the agent to do it. `SKIP_E2E=1` skips the two steps that bind a
port.

## What is not wired

- **The microphone is wired, the recogniser is the browser's.** `web/src/voice`
  mounts `packages/voice` on any operation an instrument declaration names, in
  Chrome or Edge, on localhost or https. Firefox has no Web Speech API and
  falls back to the keypad, which is a supported outcome, not a failure. A
  spoken value never commits: it lands in the form marked unconfirmed and a
  person taps. Three checks hold that down: `packages/voice/src/grammar.check.ts`
  and `web/src/voice/voice.check.ts` on the browser side, and the four voice
  checks in `scripts/e2e.py` on the kernel side.

  To use it: open a thread standing at the nurse, tap **Vitals**, then **Speak
  a reading**, and say the field name and the number, for example "systolic one
  forty over ninety and pulse seventy two". Every value is listed back with its
  own confidence and lands in the ordinary form fields marked unsure. Nothing
  is written until you tap Commit. Deny the microphone and it says so and puts
  the cursor in the first empty field; the keypad is the same record.

  There is no voice route on the kernel and there is no surface argument on
  `commit()`. A body claiming `"surface": "voice"` is recorded as `rendered`,
  because the kernel names the surface and the caller does not.
- **Nothing raises `capture.consented`,** so the scribe on the consultation is
  gated off and says so on screen. To see it, raise the flag by hand:
  `python3 -c "import sqlite3,datetime;c=sqlite3.connect('phc.sqlite3');c.execute('insert into thread_flag values (?,?,?,?,?)',('f1','enc-002','capture.consented','you',datetime.datetime.now().isoformat()));c.commit()"`
- **No authentication.** The role comes from `?role=` or `X-PHC-Role` and
  defaults to a union role holding every capability. This is a localhost demo.
- **No CARE is running.** `adapters/local` is the only adapter that has
  served a request. `adapters/care` exists and is selectable with
  `PHC_STORE=care`, but nothing here has a CARE to point it at: three GETs
  against the public `careapi.ohc.network` confirmed its pagination envelope,
  its error shape and five field names, and everything past that is the
  published schema. See "Switching adapters".

- **ABDM is a connector, not a capability.** `care_phc/connectors/abdm/`
  speaks to Eka's ABDM Connect gateway, on the official `ekacare` SDK for
  auth, profile, ABHA card and QR and KYC, and on raw REST for the three
  calls the SDK does not expose (PHR address check, Aadhaar enrolment init,
  care context link). It is verified live against `https://api.eka.care`:
  login succeeds, and the PHR check reaches Eka's own validator and comes
  back with its errors. `python3 -m care_phc.connectors.abdm.check` is its
  16 checks and needs no network. Three things to know:

  - **Nothing in the kernel calls it.** `phc.op.abha-link` writes an ABHA
    number to a patient row in the store. It does not reach ABDM, and no
    route here does. The connector is wiring waiting for an operation.
  - **Creating an ABHA is not finished.** The journey past the OTP raises
    `NotImplementedError`, and `testuser99` on the sandbox still answers 500
    `couldn't connect with ABDM servers`, which is the gateway's own words
    and the blocker.
  - **`.env`'s `EKA_BASE_URL` names `api.dev.eka.care`, where these
    credentials are refused** with `pwd mismatch`. They work on
    `https://api.eka.care`, which is the connector's default, so pass no base
    URL rather than that one. The SDK is an extra install:
    `python3 -m pip install --user ekacare`; `check.sh` skips the connector
    with a warning when it is missing.
- **`phc.op.household-visit` is in the PHC manifest and in no PHC step.** It
  stands at `community`, and the outpatient line has no such station, so
  `kernel/state.drawn_by` keeps it off every thread and `kernel/proposals`
  refuses to write it: "not a step of phc.wf.outpatient". The atom stays in
  `catalogue/ops` for a bundle that declares a household workflow. Nothing here
  declares one yet.
- **A seeded day has no clock in it.** The seed grammar declares rows, not
  times, so every row a bundle seeds shares one timestamp: turnaround on the
  demo day is zero and the order of rows inside a thread is declaration order,
  held by sequential `seed-NNNN` ids. Nothing reads those durations anyway,
  which is `bundles/LAB-LOG.md` leak 3.

- **A seeded thread's conversation is as good as its declared audit.** A
  posted card draws its values from the payload on the audit line, so a seed
  that writes rows and declares no trail produces a thread of no cards at all
  and an agent saying nothing has been recorded over a stepper full of ticks.
  Both seeds now declare theirs, the linter refuses a payload key the
  questionnaire does not ask for, and `test_contracts` refuses an empty one. A
  third bundle has to write its own; nothing derives a trail from rows.

- **`enable_when` is the renderer's rule and not the kernel's.** The lab's
  result questionnaire hides the analytes the chosen panel does not use and
  prunes them out of the payload it sends, so a glucose never rides along on a
  CBC from the screen. `catalogue/validate.py` does not know the keyword at
  all, so a machine surface that puts one in the payload is not refused. The
  renderer is doing the whole of what a renderer can do here; the gap is on the
  server, and it is `bundles/LAB-LOG.md` leak 13.

- **Separation of duties is declared, not authenticated.** `actor of` and
  `not actor of` are real preconditions, enforced on both surfaces and read by
  `guard.visible` so the action is absent rather than greyed out. But with no
  authentication the actor is `user:<role>`, so "a different person" means "a
  different role". `catalogue.guard.person()` strips the `agent:` prefix, so an
  agent inherits the exclusions of whoever it is acting for; without that, the
  account that keyed a result could have the verify proposed to itself by
  dictating instead of tapping.
