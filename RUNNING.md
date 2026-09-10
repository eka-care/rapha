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
python3 -m agent "bp is 140 over 90 and pulse 72" --role nurse
```

With `ANTHROPIC_API_KEY` set and `pip install anthropic` it asks Claude;
without either it uses a keyword router. Either way every proposal is run
past the guard on the machine surface before it is printed, and none of them
can commit.

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

- **No microphone.** `packages/voice` is checked and is not imported by `web`.
  The grammar and the fail-closed logic are tested; the Web Speech wiring in
  `v2dd.ts` has never run.
- **No authentication.** The role comes from `?role=` or `X-PHC-Role` and
  defaults to a union role holding every capability. This is a localhost demo.
- **No CARE.** `adapters/local` is the only adapter. The column names in it are
  taken from `care/emr/models` and are unverified against a running CARE.
