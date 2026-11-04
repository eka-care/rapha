#!/bin/sh
# Everything that can be checked without a running CARE. Run before committing.
#
# Order matters in one place only: the two compile steps come first, because
# catalogue.json is an input to almost everything below them.
set -e
cd "$(dirname "$0")/.."

# The outbox's spool root, for the whole gate. api/main.py starts the retention
# sweeper at import, so every check that imports the app opens a spool; without
# this it would be the developer's own ~/.local/share/phc/spool, and a gate that
# writes outside its own tree is a gate that can pass because of what an earlier
# run left there. Removed with the directory when the shell exits.
PHC_SPOOL=$(mktemp -d)/spool
export PHC_SPOOL
trap 'rm -rf "$(dirname "$PHC_SPOOL")"' EXIT


echo "== compile the declarations =="
# The templates first, because what they generate are ordinary operation atoms
# and ordinary questionnaires that the two steps below then lint like any
# other. A hand edit to a generated file fails in kernel/declarations.py.
python3 scripts/build_templates.py
python3 -m catalogue.build
python3 -m kernel.declarations

echo "\n== khoj: the rename actually happened, and stayed that way =="
python3 scripts/check_khoj.py

echo "\n== the instrument vocabulary is one list, not two =="
# catalogue/vocab.py owns it, kernel/contracts.py re-exports it, and an
# operation's default is the subset a pill can draw. They were written out
# twice and drifted (`palette` versus `spoken-prompt`); this is what fails if
# that starts again, in either direction.
python3 scripts/check_instruments.py

echo "\n== coded data: the terminology seam and the FHIR projection =="
# A coding exists only if the value set its question binds to vouched for it,
# and a thread projects to an ABDM document with LOINC codes and UCUM units.
python3 -m kernel.terminology
python3 -m kernel.fhir
# The codification seam, whose own definition is that it must work when it
# returns none. The stub returns none, and the five ways the answer is empty
# are five separate checks: nothing found, service down, service slow, a code
# this build cannot resolve, and a code from the wrong branch of the ontology.
python3 -m kernel.codification

echo "\n== the front desk: the number, and how they got here =="
# The day sequence on its own, over a list and with no store: numeric, one per
# facility, one past the highest issued.
python3 -m kernel.tokens
# And over the real service, through BOTH ways into the queue, because two
# routes each numbering their own arrivals is the failure that leaves every
# check above green and puts two people called four in one waiting room.
python3 scripts/check_front_desk.py
# And no check writes the developer's own demo day. One of them did: it
# registered a patient through the real route with no PHC_DB set, so a gate
# run added a patient to the database a person opens the app against, which
# looks exactly like the duplicate-patient defect this repository had just
# fixed. Read from the syntax, because the first draft read the text and a
# COMMENT about PHC_DB satisfied it.
python3 scripts/check_isolation.py
# And the number issued ONCE, proved by racing rather than by inspection: real
# parallel processes against a real file, asserting no duplicate and no hole.
# A sequential test passed against the broken code for as long as it shipped.
python3 scripts/check_tokens_race.py

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
# `now` in the query grammar: the one symbolic value a state rule may
# compare a date against, resolved in the kernel so no adapter learns it.
python3 -m kernel.tests.test_clock
# What a pregnancy owes, derived from the schedule declaration and the
# episode's own date. An episode that has ended owes nothing, with no
# cancellation step anybody could forget to call.
python3 -m kernel.tests.test_schedule
# What a centre owes between two dates, swept across every open episode. A
# woman nobody has seen for months must still be listed, and an ended
# pregnancy must owe nothing to any day: both fail if episodes are found
# through recent visits or if anything is stored.
python3 -m kernel.tests.test_cohort
# The calendar view: a day as rows and its month as counts, which must agree
# about a missed contact that is owed on every day after its window shuts.
python3 -m kernel.tests.test_views
# A view declaration whose kind, workflow or episode types name something
# that does not exist: it would draw an empty screen and report nothing.
python3 -m kernel.tests.test_declarations
python3 -m bundles.lab.check      # a second bundle on the same kernel; SKIP_E2E=1 skips its socket half
python3 -m bundles.phc.check      # consent is gone, and gone from both engines
# One vertical slice through every layer: a nurse records a blood pressure, it
# validates, it is coded, the guard allows it, the rows land, the thread
# projects to an ABDM WellnessRecord. No socket.
python3 scripts/check_vitals.py
# The same slice for the three numbers an antenatal contact turns on, plus the
# two properties only this operation has: it cannot be reached without a
# pregnancy open, and measuring somebody does not close a contact. The ANM's
# own capability set drives it, so taking an ability off her fails here.
python3 scripts/check_antenatal.py
# The other end of the same arc: a delivery ends the pregnancy and opens
# postnatal care in one commit, and a pregnancy that ended any other way
# opens nothing. The second half is the one that matters.
python3 scripts/check_postnatal.py
# The facility calendar over women whose pregnancies ended, were lost or were
# never seen: an ended episode owed on any day, or a miscarriage given a
# home visit, fails here, as does a window off by a day or an ungated route.
python3 scripts/check_calendar.py
# A laboratory value and its unit are one checked thing: the analyte is a coded
# ANSWER (the third binding form) and the unit must be the one LOINC reports
# that analyte in. scripts/seed_terminology.py generated the value set and is
# deliberately NOT run here: it needs a network and confirming a code list is
# design time work.
python3 scripts/check_lab.py
# A diagnosis and a medicine are repeating groups: a list of rows, each row
# validated, coded, stored and published on its own. This is what replaces
# `type: structured`, which CARE never finished validating and neither did we.
python3 scripts/check_rx.py
# Codification, end to end, with the stub answering nothing: the consultation
# path is unchanged, a candidate never becomes a value, and an uncoded finding
# travels as narrative text into an ABDM document. The last of those is proved
# rather than asserted; it was written down twice and did not exist.
python3 scripts/check_codification.py
# A consultation leaves as an NRCeS OPConsultRecord: the section placement is
# the bundle's own declaration rather than three callers' guesses, every
# section code is held against the file that recorded where it was read from,
# and the seven honest consultations each publish. Which bundles were put
# through the ABDM tier one structural validator, and what that does not
# prove, is in the file's docstring rather than in a commit message.
python3 scripts/check_op_bundle.py
# The doctor's three templates. A template is an operation whose form and
# mapping are generated from one declaration by narrowing another operation's,
# so there is no second questionnaire to keep in step: a hand edit to a
# generated atom fails, every template publishes through the one `documents`
# declaration into the same slices as the general consultation, the narrative
# fallback is inherited rather than retyped, and a question a template does
# not ask cannot be filled, so no value can be committed untickable. What it
# does NOT prove is that any of the three narrowings is clinically correct;
# the file's docstring says so and two of the three carry a sign-off banner.
python3 scripts/check_templates.py
# How sure anybody was, on every coded thing rather than only on a diagnosis.
# Every status literal an operation stores is held against the published FHIR
# list R4 binds that element to; no projection chooses a clinical certainty
# for itself; and invariant I6 is proved case by case, including the two
# resources where it is NOT kept and the reason it cannot be.
python3 scripts/check_verification.py
# A health centre's copy is a choice and not a fork. Which plugins a centre
# runs is one declared list, a plugin that is off is a capability the caller
# does not hold, and this holds three shapes of the same bundle against each
# other: the compiled catalogue is identical, the withheld capabilities are
# derived, the operation is absent from the quick action row AND from what the
# MCP server builds its tool list from, the guard refuses it on both surfaces
# with an audit row naming the plugin, the step it closed is skipped rather
# than pending, and the dashboard this centre does not run answers 403. Runs
# the service in process as the SMALLEST shape; the socket half, driving the
# real Go binary, is in scripts/e2e.py.
PHC_FACILITY=consulting-room-only python3 scripts/check_plugins.py
# Audio and national records wait for the line and never drop. Three separate
# properties, each one proved by MAKING IT HAPPEN rather than by asserting the
# code looks right: a real child process, against a real SQLite file, killed
# with SIGKILL between claiming an item and sending it, between sending it and
# writing the receipt, and in the middle of writing the receipt. Also: the
# guard re-run at the moment of sending, with the audit row proved to be on
# the trail before a byte leaves; a centre refusing to HOLD work for a plugin
# it does not run; and what a queue row may contain, against the Aadhaar,
# mobile and OTP rules. No socket and no call to Eka or ABDM, and the file's
# docstring says what that leaves unproved.
python3 scripts/check_queues.py
# And the outbox actually REACHED, with the owner's 24 hour ceiling on held
# audio enforced by code that runs: real files on a real disk, the clock moved
# forward, and the recording gone from the disk rather than its row tidied up.
python3 scripts/check_audio_ceiling.py
python3 -m kernel.queues
python3 -m adapters.local.spool
# The connector behind the seam, against a stand-in transport fed the vendor's
# own published response examples. No credential, no socket, no recording of a
# live call, and the check says so in its docstring.
python3 -m care_phc.connectors.codification.check
# Patient identity lives in Eka's directory, and the clinic works without it.
# Runs with PHC_DIRECTORY=absent and opens no socket; the one module that can
# is the vendor connector, and this is what fails if that stops being true.
python3 -m care_phc.connectors.directory.eka
python3 scripts/check_directory.py

echo "\n== the adapter and the service =="
python3 -m api.scribe          # the scribe's response reading, against a recorded live answer
python3 -m api.structured      # the structured note read into form answers, evidence found not trusted
python3 scripts/check_scribe_library.py   # Eka's template library, and a note written in one
python3 -m api.shaped          # fields from the service's own note, with no model of our own
python3 -m adapters.local.tests.test_store   # the one adapter, and the Store protocol's ten names
python3 -m api.tests.test_api

echo "\n== the agent, and the ABDM connector =="
# What no connector may let through, and what no connector may import: the
# scribe used to borrow the ABDM connector's Aadhaar pattern, which meant a
# facility could not have dictation without ABHA. Needs no SDK, so it runs
# whether or not ekacare is installed, unlike the two connector checks below.
python3 -m care_phc.connectors.redact
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
# One module, two commands: the catalogue reader is the module root package
# (where the embedded catalogue.json is) and cmd/mcp and cmd/api are beside
# its files. `./cmd/mcp` rather than `.`, because the root is a library now.
(cd care_phc_mcp && go vet ./... && go test ./... \
   && go build -o care_phc_mcp ./cmd/mcp \
   && go build -o care_phc_api ./cmd/api)
# Two lines, not one `cmd && echo`: under `set -e` a failing command on the
# left of && does not stop the script, so that spelling let this check fail in
# silence. It did.
python3 scripts/agent_demo.py > /dev/null
echo "ok   agent demo runs end to end"

echo "\n== the Go backend, beside the Python =="
# Two engines on one set of declarations, over two real sockets at once, with
# their answers compared rather than asserted: nothing about either shape is
# written down here, because a literal would pass while both engines drifted
# from each other. What Go does not serve yet answers 501 naming the slice
# that will bring it, and that list is in this check's output rather than in a
# commit message. Needs the Go toolchain, and fails loudly if cmd/api does not
# build; it opens two ports, so SKIP_E2E skips it.
if [ -n "$SKIP_E2E" ]; then
  echo "warn go parity skipped: SKIP_E2E is set"
else
  python3 scripts/check_go_parity.py
fi

echo "\n== the browser side =="
# The microphone itself is NOT checked here and cannot be: it needs a
# microphone. Every line around it is, in src/voice/voice.check.ts and
# src/scribe/scribe.check.ts below: that no voice path can write, that what
# reaches a field is narrowed to what the instrument declares, and that the
# browser's own number grammar is gone rather than merely unused.
if [ -d web/node_modules ]; then
  (cd web && npm run check && npm run build >/dev/null)
  # Which fields take voice comes from the instrument declarations, and nothing
  # on the voice path can write. Both are asserted here; neither needs a mic.
  (cd web && node --experimental-strip-types src/voice/voice.check.ts)
  (cd web && node --experimental-strip-types src/scribe/scribe.check.ts)
  # What earlier visits say about this one: which values carry forward, which
  # one is worth a trend, and who has been near the visit. Pure rules over
  # two visits' values, so no browser and no kernel.
  (cd web && node --experimental-strip-types src/thread/earlier.check.ts)
  (cd web && node --experimental-strip-types src/thread/fold.check.ts)
  (cd web && node --experimental-strip-types src/thread/commands.check.ts)
  # An arc laid out as months: first month to last, the empty ones included.
  (cd web && node --experimental-strip-types src/thread/arc-scale.check.ts)
  # The calendar grid: a contact sits in the one cell the kernel names and no other, a month
  # draws its spill days, a year ignores the room limit, one cell is today.
  (cd web && node --experimental-strip-types src/view/grid.check.ts)
  # The tour: it points at elements that are really on screen, and its card
  # never leaves one. Pure rules over a rectangle, so no browser.
  (cd web && node --experimental-strip-types src/app/guide.check.ts)
  (cd web && node --experimental-strip-types src/app/width.check.ts)
  python3 -m api.paper
  python3 -m api.vault
  (cd web && node --experimental-strip-types src/form/span.check.ts)
  (cd web && node --experimental-strip-types src/ui/pick.check.ts)
  # Speaking into whatever field has the cursor: where the words land, what
  # the gesture means, and which fields take them. No microphone needed.
  (cd web && node --experimental-strip-types src/scribe/dictate.check.ts)
  # The Eka session: which surface is asking, when a session is worth
  # refreshing, and the one origin where the gate cannot apply. Nectar's own
  # rules, so the claims product and this one behave the same way.
  (cd web && node --experimental-strip-types src/auth/client.check.ts)
  (cd web && node --experimental-strip-types src/assistant/assistant.check.ts)
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
  # The screens are live, not mocked: the real renderer modules run over what
  # two real kernels answered, for two facility shapes of one bundle. Needs
  # web/node_modules only for the strip-types run, and binds a port unless
  # SKIP_E2E is set, in which case it drives the same routes in process.
  python3 scripts/check_live.py
else
  echo "warn web: run (cd web && npm install) to check the renderer"
  SKIPPED="${SKIPPED}the renderer (web/node_modules is missing), "
fi
echo "\n== end to end, over a real socket =="
# Starts uvicorn on a free port against a throwaway SQLite file, walks a
# patient through the line, and drives the Go MCP binary at it. The only check
# that binds a port; skip it with SKIP_E2E=1 if that is a problem where you are.
if [ -n "$SKIP_E2E" ]; then
  echo "warn e2e skipped: SKIP_E2E is set"
  SKIPPED="${SKIPPED}end to end over a socket (SKIP_E2E is set), "
else
  python3 scripts/e2e.py
fi

# What was skipped is said HERE, next to the verdict, and not only where
# it was skipped. A fresh worktree has no web/node_modules, which drops
# about eighty checks, and the one-line warning scrolls off the top long
# before "all checks passed" appears at the bottom. An agent read that
# bottom line, reported a green gate, and was counting 778 where this
# checkout counts 894. A green that does not say what it did not look at
# is the same defect this repository keeps finding in its own checks.
if [ -n "$SKIPPED" ]; then
  printf '\nall checks that ran passed, and these did NOT run: %s\n' "${SKIPPED%, }"
else
  printf '\nall checks passed\n'
fi
