# Running this

Three processes, in this order: compile, serve, draw. Nothing here needs CARE,
a network, or a database server. Python 3.9 and Node 22+ are the whole of it.

## 0. Once

```sh
python3 -m pip install --user fastapi uvicorn pyyaml     # the API and the linter
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

On first start it creates `phc.sqlite3` in the repo root and seeds six threads,
one standing at each station, so no screen is ever empty. Delete the file to
reseed. `PHC_DB` moves it, `PHC_BUNDLE` picks a different bundle, `PORT`
changes the port.

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

That is the whole switch. The same kernel now runs `bundles/lab/`: a four
station laboratory line, its own operations, its own worklist, report and
turnaround board. Give it its own `PHC_DB`, because the seed is written for
the PHC and its six patients turn up on the laboratory's worklist otherwise
(they still do inside one database; see `bundles/LAB-LOG.md`).

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

## 3. Start the renderer

```sh
(cd web && npm run dev)             # http://localhost:5173
```

It reads `VITE_API_BASE`, default `http://localhost:8000`. The header carries a
"Use demo data" toggle that draws every screen from a fixture and refuses every
write, for when the API is not up.

Note `care_phc_fe/` (the older, fixture-driven prototype) also runs on 5173.
Run one at a time, or give the second one `--port 5174`.

## 4. The agent surfaces, optional

The MCP server, pointed at the kernel:

```sh
CARE_BASE_URL=http://127.0.0.1:8000 ./care_phc_mcp/care_phc_mcp
```

It reads `/whoami` to learn its capabilities and offers only the operations
that account may use. Every write tool is `propose_*`; there is no confirm verb
and no path by which it can commit.

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

What it leaves behind is a proposal id. Open that thread in the renderer and it
is at the top of the panel, "awaiting a person", with a Review button; the
values are editable and the tap is what writes. Watch it happen:

```sh
python3 -m agent "bp 138 over 86, pulse 74" --thread enc-002
open http://localhost:5173/#/threads/enc-002
```

## 5. The checks

```sh
sh scripts/check.sh                 # everything, about 9 seconds
```

That runs the linters, every Python and Go unit check, the browser-side checks,
and `scripts/e2e.py`, which starts its own uvicorn on a free port, walks a
patient through the line over HTTP, reads the SQLite file to prove the row
landed, and drives the Go MCP binary at it. `SKIP_E2E=1` skips the only step
that binds a port.

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
- **No CARE.** `adapters/local` is the only adapter. The column names in it are
  taken from `care/emr/models` and are unverified against a running CARE.
- **`phc.op.household-visit` is in the PHC manifest and in no PHC step.** It
  stands at `community`, and the outpatient line has no such station, so
  `kernel/state.drawn_by` keeps it off every thread and `kernel/proposals`
  refuses to write it: "not a step of phc.wf.outpatient". The atom stays in
  `catalogue/ops` for a bundle that declares a household workflow. Nothing here
  declares one yet.
- **The lab bundle's line wears PHC words.** `vocab.STATES` and `vocab.STATIONS`
  are closed and the PHC's, so a laboratory's draw room is called `nurse` and a
  released report is `dispensed.complete`. Every substitution is listed in
  `bundles/LAB-LOG.md`. That file is the honest answer to "does one kernel run
  another facility": yes, and read the log before believing the screens.
