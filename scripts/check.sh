#!/bin/sh
# Everything that can be checked without a running CARE. Run before committing.
#
# Order matters in one place only: the two compile steps come first, because
# catalogue.json is an input to almost everything below them.
set -e
cd "$(dirname "$0")/.."

echo "== compile the declarations =="
python3 -m catalogue.build
python3 -m kernel.declarations

echo "\n== khoj: the rename actually happened, and stayed that way =="
python3 scripts/check_khoj.py

echo "\n== the kernel and its contracts =="
python3 -m catalogue.tests.test_guard
python3 -m catalogue.tests.test_validate
python3 -m care_phc.tests.test_thread
python3 -m kernel.tests.test_contracts
python3 -m kernel.tests.test_kernel
python3 -m kernel.tests.test_mapping
# The spine: one subject, every visit, joined by what the workflow declares
# rather than by a resource name written into the kernel.
python3 -m kernel.tests.test_spine
python3 -m bundles.lab.check      # a second bundle on the same kernel; SKIP_E2E=1 skips its socket half
python3 -m bundles.phc.check      # capture consent: raised, declined, scoped to the visit, withdrawable

echo "\n== the adapter and the service =="
python3 -m api.scribe          # the scribe's response reading, against a recorded live answer
python3 -m adapters.local.tests.test_store
python3 -m adapters.care.tests.test_store    # adapter 1, CARE REST, fake transport
python3 -m adapters.care.tests.test_live     # READ ONLY against a public CARE; skipped when offline or SKIP_E2E
python3 -m api.tests.test_api

echo "\n== the agent, and the ABDM connector =="
python3 -m agent.tests.test_planner
python3 -m agent.turn          # one conversational turn, no kernel and no key
python3 -m agent.tests.test_live      # binds a port; SKIP_E2E=1 skips that half
# The connector is the only thing here with a third party dependency, and it
# is optional: nothing the kernel serves goes through ABDM yet. Skip rather
# than fail on a machine that has not installed the SDK.
if python3 -c 'import ekacare' 2>/dev/null; then
  python3 -m care_phc.connectors.abdm.check
  # The scribe connector, against a recorded real response. No credential, no
  # socket, no recording: the live upload it was recorded from is in the
  # docstring, not in this script.
  python3 -m care_phc.connectors.scribe.check
else
  echo "warn abdm connector skipped: python3 -m pip install --user ekacare"
fi

echo "\n== the MCP server =="
(cd care_phc_mcp && go vet ./... && go test ./... && go build -o care_phc_mcp .)
# Two lines, not one `cmd && echo`: under `set -e` a failing command on the
# left of && does not stop the script, so that spelling let this check fail in
# silence. It did.
python3 scripts/agent_demo.py > /dev/null
echo "ok   agent demo runs end to end"

echo "\n== the browser side =="
# The voice grammar is pure and runs under plain node. The browser's own
# recogniser is NOT checked here and cannot be: it needs a microphone. Every
# line around it is, including that no voice path can write.
node packages/voice/src/grammar.check.ts
if [ -d web/node_modules ]; then
  (cd web && npm run check && npm run build >/dev/null)
  # Which fields take voice comes from the instrument declarations, and nothing
  # on the voice path can write. Both are asserted here; neither needs a mic.
  (cd web && node --experimental-strip-types src/voice/voice.check.ts)
  (cd web && node --experimental-strip-types src/scribe/scribe.check.ts)
  # One primary action per station, everything else in overflow: pure rules
  # over declarations, checked without a browser.
  (cd web && node --experimental-strip-types src/loops.check.ts)
  # A capability a workflow draws is grantable; one it does not is inert, and
  # says so from the operation's own station and the workflow's own title.
  (cd web && node --experimental-strip-types src/grants.check.ts)
  # The colour system: tokens.css is the only file that may name a colour,
  # every semantic pair clears WCAG 2.2 AA in BOTH themes, and every var()
  # resolves. npm run check runs this too; it is named here because the three
  # bugs it exists to catch (a flattened palette, a 1.3:1 banner, 240 dangling
  # references) all shipped on this branch.
  (cd web && node --experimental-strip-types src/style.check.ts)
  # The renderer's own rules: it types none of this bundle's 63 declared words
  # (checked against the compiled catalogue, so it grows when a bundle does),
  # the / and @ menus are sourced from declarations rather than written down,
  # the quick action row is capped and says what it hid, and the §68 basics.
  (cd web && node --experimental-strip-types src/ui.check.ts)
  # The brief and the suggested questions: composed from declarations and live
  # rows, in whatever words the bundle declared, and they read correctly at 0
  # and 1 as well as at the number somebody wrote them against.
  (cd web && node --experimental-strip-types src/agent.check.ts)
  echo "ok   web renderer typechecks and builds"
else
  echo "warn web: run (cd web && npm install) to check the renderer"
fi
echo "\n== end to end, over a real socket =="
# Starts uvicorn on a free port against a throwaway SQLite file, walks a
# patient through the line, and drives the Go MCP binary at it. The only check
# that binds a port; skip it with SKIP_E2E=1 if that is a problem where you are.
if [ -n "$SKIP_E2E" ]; then
  echo "warn e2e skipped: SKIP_E2E is set"
else
  python3 scripts/e2e.py
fi

printf '\nall checks passed\n'
