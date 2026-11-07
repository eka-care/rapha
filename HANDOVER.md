# Handover: Rapha

Written 7 November 2026, for a person or an agent picking this up cold.
`README.md` says what the repository is. `RUNNING.md` says how to start it and
is the longest and most honest document here. This file is the third thing: how
the project got to where it is, what was decided and by whom, what is real
against live services and what only looks real, and what to do next.

Read this, then `RUNNING.md`, then the design note for whatever you are about
to touch (the index is in §11). Do not read the code first. The declarations
are the specification and the code is downstream of them.

---

## 1. What Rapha is, in one paragraph

A scribe-first clinical workspace for an Indian Primary Health Centre. A visit
is a conversation; a clinician speaks and the record fills itself; every value
a machine filled is shown back and a person taps to commit. What it writes is
ABDM-compliant FHIR R4, so a visit becomes a document India's national health
network accepts. It runs as one process per health centre today, reads people
and documents from Eka's own services, and is intended as a free and open
digital public good.

The name: the product was called `killer-doc` in the repository and Rapha on
screen. The repository is now `eka-care/rapha`; the folder on the owner's Mac
is still `killer-doc`, which is harmless.

### The one load-bearing product rule

From Product Scope v0.1 §4, and it is enforced by the linter rather than
remembered: **if an operation cannot be invoked identically from the screen and
from the agent, it does not ship.** An operation declaration missing
`surfaces: [rendered, mcp]` does not compile.

### The second rule, added by the owner on 4 November 2026

**"This is a scribe-first platform. No form can exist without scribe."** Every
field in the product must be fillable by voice; typing is the fallback, not the
other way round. Holding the `₹` key dictates into whichever field has focus.

---

## 2. Start it

Three processes. Full detail, including the laboratory bundle and the Eka
sign-in, is in `RUNNING.md`.

```sh
python3 -m catalogue.build && python3 -m kernel.declarations   # compile, in this order
sh api/run.sh                                                  # the kernel, :8000
(cd web && npm run dev)                                        # the screen,  :5173
```

**The build order is not optional.** `catalogue.build` writes four keys into
`catalogue/catalogue.json`; `kernel.declarations` merges in five more and copies
the result to `care_phc_mcp/catalogue.json`, which the Go engine embeds.
Running the first alone leaves the file half written and the Go engine stale.

To see the real Eka sign-in you need a subdomain of eka.care on https over port
443, because the session is a cookie on `.eka.care` and a cookie for that
domain is never sent to localhost. `RUNNING.md` has the four steps. On
localhost the gate is deliberately off.

---

## 3. The gate

```sh
sh scripts/check.sh
```

It must print `all checks passed` and exit 0. As of this handover: **exit 0,
1239 `ok` lines, zero warnings, about a minute.** It runs the linters, every
Python and Go unit check, 24 browser-side checks, the second bundle, a Go/Python
parity diff, and an end-to-end walk that starts its own server, drives a patient
through the line over HTTP, reads the SQLite file to prove the row landed,
drives the Go MCP binary at it, posts a sentence to the agent route, and proves
that an edited draft is what lands rather than the proposed one.

Three things about it worth knowing before you fight it:

- **A check that `scripts/check.sh` does not run is refused.** There is a check
  for that. Adding a check file is two edits: the line in `scripts/check.sh`,
  and the `exclude` list in `web/tsconfig.json` for a `.check.ts`.
- `web/package.json`'s own `check` script runs only nine of the browser checks.
  The rest are invoked from `scripts/check.sh` directly. Do not assume
  `npm run check` covers the front end.
- `SKIP_E2E=1` skips the two steps that bind a port. Use it while iterating,
  never to claim the gate is green.

---

## 4. The seven rules of working in this repository

These were learned the hard way, most of them from a failure recorded in the
commit log.

1. **Declare, do not code.** Clinical capability lives in markdown with
   frontmatter: `catalogue/ops/*.md` (35 operations) and `bundles/phc/*.md` (18
   declarations) plus `bundles/phc/bundle.yaml`. A new capability is usually a
   new declaration and no new code. `catalogue/vocab.py` is a **closed** list:
   an atom naming a capability, state or resource that is not already there is
   a lint failure, never a reason to add an entry.

2. **No screen may type a declared name.** `web/src/ui.check.ts` fails the
   build if a screen contains a capability, station, flag, operation id or
   subject field name as a literal. Only `.id` is exempt. If you need a field,
   declare it on the instrument and read it through the declaration.

3. **One file may name a colour.** `web/src/style/tokens.css`. `style.check.ts`
   enforces WCAG 4.5:1 and that every `var()` without a fallback resolves to a
   declared token.

4. **Decision logic goes in a pure module with a sibling check.** `thing.ts`
   next to `thing.check.ts`, run under `node --experimental-strip-types`. This
   is how the front end is tested; there is no test framework.

5. **Prove it, do not assert it.** Every claim in this repository's documents is
   meant to be backed by a check or by a recorded live run. When you add a
   check, mutate the thing it guards and confirm the check fails. Reports in
   this project routinely say "five of six mutations caught and the sixth proves
   nothing", and that honesty is the house style.

6. **Two engines must agree.** Python FastAPI in `api/` and `kernel/`, a Go twin
   in `care_phc_mcp/`, both reading the same compiled declarations.
   `scripts/check_go_parity.py` asserts they name the same routes and answer
   identically. A route added to one must be added or explicitly listed as
   unserved in the other.

7. **Commit with a pathspec.** `git commit -- <paths>`, never a bare
   `git commit`. Several agent sessions share this one checkout and one git
   index; a bare commit writes the whole index and sweeps in other sessions'
   work. This happened three times in two days. Files that are never yours:
   `.claude/launch.json`, `.gitignore`, `care_phc_mcp/care_phc_mcp`,
   `care_phc_mcp/care_phc_api`, `.claude/task-modules.json`, `prototypes/`,
   `.superpowers/`, `web/.env.local`, the SQLite files.
   `care_phc_mcp/catalogue.json` **is** tracked and must be committed when the
   declarations change.

---

## 5. The shape of it

```
catalogue/      35 operation atoms, the linter, the compiler, the guard
  ops/*.md        one atom per operation. THESE ARE THE SPECIFICATION.
  vocab.py        closed lists: capabilities, bundles, states, resources
  build.py        lint and compile -> catalogue.json
  guard.py        the four permission checks CARE does not do
kernel/         the engine: state, proposals, mapping, terminology, queues
bundles/phc/    this facility's workflow, views, instruments, roles, seed
bundles/lab/    a second facility shape on the same kernel, to prove it bends
adapters/local/ the only adapter: a SQLite file. The seam is a 10-method protocol
api/            FastAPI routes, the scribe seam, the records proxy, the outbox
care_phc/       connectors: Eka scribe, Eka patient directory, ABDM
care_phc_mcp/   the Go twin, and the MCP server the agent talks to
web/            React 19 + TypeScript + Vite. Hand-written CSS, Radix primitives
questionnaires/ 31 forms, authored not coded
terminology/    the condition and medicine code lists
docs/           the decision record and every design note
agent/          the planner, which can propose and cannot commit
```

### How a value gets into the record

1. A clinician speaks. The browser records and the audio goes to Eka's scribe.
2. Eka returns a structured note. `kernel/mapping.py` turns it into **filled
   declared fields**, not prose. This step is ours and nothing at Eka does it.
3. The form shows each filled value marked "filled by an instrument, not
   typed", and every non-text value owes a tick.
4. A person taps Commit. The guard runs again on what is on screen after any
   edits. The tap is what writes.
5. The row lands, an audit line is written, and the visit projects to a FHIR
   document.

The guard refuses; Eka does not. The kernel names the surface, the caller does
not: a body claiming `"surface": "voice"` is recorded as `rendered`.

### What the agent can and cannot do

It can propose. It cannot commit. `agent/client.py` holds no verb that would,
and refuses to assemble a URL containing `/confirm` or `/commit` before it opens
a socket. Every MCP write tool is `propose_*`. There is no confirm verb on that
surface at all.

---

## 6. What is live against real services

Verified against `https://api.eka.care` with the owner's production
credentials. This is the short list of things that are real rather than mocked.

| What | How | State |
| --- | --- | --- |
| People | Eka patient directory, `care_phc/connectors/directory/eka.py` | **live** |
| Documents | Eka medical records, `api/vault.py` proxy plus the TypeScript SDK in the browser | **live** |
| Recordings and notes | Eka Scribe, `api/scribe.py` | **live**, verified end to end 11 September |
| Sign-in | login.eka.care, production since 7 November | **live** |
| The assistant | Eka's own Ask AI widget, vendored at `web/public/ask-ai.js` | **live** |
| ABDM / ABHA | Eka's web SDK mounted in `web/src/abha/` | **staging only** |
| Clinical resources | CARE | **not wired.** `adapters/` holds only `local/` |

Two sentences about the scribe that are worth reading twice, because they are
the reason for the whole readback-and-tap design. The doctor dictated
**Cetirizine 10 mg** and Eka returned **"Antihistamine 10 mg tablet"**, twice,
on two separate uploads of the same audio. An earlier run heard "No" as
"Number". **The prose is good and the discrete values are not.**

ABHA defaults to staging on purpose: production creates real, permanent
national health accounts. `ABHA_ENV=production` exists and says so in red on
screen.

### What has never been proven

- No real ABHA has been created or logged into from here. Everything past the
  first screen of the staging journey is unverified.
- No webhook from Eka has ever been delivered. Polling is what runs.
- No held recording has ever reached the speech service from the offline queue,
  because that needs a live credential and a real outage at the same time.
- The audit cannot tell a dictated note from a typed one. A `scribe` badge is a
  static field on the operation, not provenance. **Tell anyone who reads the
  audit as provenance before they rely on it.**

---

## 7. The decision record

Everything below was decided by the owner. Where a document holds the detail,
it is named rather than restated.

### Architecture

- **Build on CARE's models, not a CARE instance.** 10 September. There was a
  `adapters/care/` over CARE's REST API; it is deleted. It never served a
  request. What was kept is the ten-method protocol and the FHIR-shaped
  resource names.
- **Go as well as Python**, because the team works in Go and this should be
  easy to contribute to as a public good. 31 October: *"the team largely works
  on go, I should have asked you to do it in go from the get go."* The Go twin
  is the result. It is not a replacement; both are held to parity.
- **Eka's patient directory is the source of truth for people.** 30 October,
  *"eka's directory for now."* The local `patient` table is a copy and
  `directory_id` is the join.
- **All data FHIR R4 native.** 30 October. Diagnoses and medicines are coded
  row by row against value sets; a symptom the patient denied can no longer be
  stored as a confirmed disease.
- **Everything configurable, with good presets.** 11 September: *"you want your
  front desk to do more, you have the ability to enable functions for them...
  But well defined presets, which work for 70% of them."* This is what the
  bundle and plugin system is.
- **Keep Rapha's own kernel; do not move it inside Eka's scribe backend.**
  Recommended 4 November and reaffirmed 7 November. Eka's scribe backend is
  properly multi-tenant but holds transactions, audio, documents, templates and
  template results. No patient, no encounter, no prescription, no queue. It is
  a scribe and cannot hold a clinic. Detail:
  `docs/superpowers/specs/2026-11-04-the-build-plan.md` §1 and
  `docs/superpowers/specs/2026-11-07-workspace-tenancy-design.md`.

### Product

- **A patient is a conversation, and a visit is the thread.** 11 and 15
  September, after looking at Glass Health and Heidi. A patient is the durable
  spine; an encounter is the thread. The reasoning for why a patient cannot be
  the thread (preconditions invert permanently, consent leaks across visits) is
  in `docs/superpowers/specs/2026-09-15-spine-and-plugins.md`.
- **Handover is intrinsic, not a form.** 4 November: after registration, ask
  only "hand over with a note or without"; with a note, open the scribe. Clear
  beginnings and ends; the next cue is always obvious.
- **Capture consent is presumed.** 1 November, and the owner removed the
  consent interface entirely on 3 and 4 November: *"remove the consent
  talkback"*, *"please remove the whole consent thing"*. The workflow now
  composes consent from two refusals alone. The registration form still records
  the answer; withdrawal is its own operation and is enforced on the server.
- **A recording may be held for 24 hours.** 1 November. Enforced by the code
  that deletes, not by a constant: a deployment asking for 48 gets 24. Detail
  and the two bugs wiring it found: `docs/DECISIONS-2026-11-01.md` §2.
- **Staff sign in through login.eka.care.** 1 November, live 7 November. Two
  things this did not answer and they are still open: what a signed-in person
  maps to in the kernel's roles, and what happens on a shared station phone
  passed between colleagues mid-shift. `docs/DECISIONS-2026-11-01.md` §3.
- **Identity: OTP now, fingerprint on a desk PC when a reader exists, face
  never.** 1 November. Fingerprint cannot be reached from a phone browser;
  face runs inside the patient's own ABHA app and is not ours to build.
  `docs/DECISIONS-2026-11-01.md` §4.
- **Token numbers are plain integers**, and a self-registered patient shares
  the same sequence with a desk-registered one, labelled. 31 October.
- **Handovers: desk to nurse to doctor to pharmacy are mandatory with a skip;
  doctor to lab and back are subjective.** 31 October.
- **Mobile first, and an Android app for the frontline worker.** 31 October.
  Superseded in part on 7 November: the existing native app
  `eka-care/Hera-android` becomes the frontline worker's tool rather than a
  wrap of the web app.
- **High-risk pregnancy follows NHM guidelines**, and is built on the rails
  that already exist rather than new ones. 4 November. This is the largest
  clinical feature in the product: a second arc of visits beside the ordinary
  pregnancy, which stops on delivery or loss, and a day-45 check that closes
  the tail. A nurse can undo a mark made in error. A woman who dies while
  pregnant can be recorded, and it ends the pregnancy and opens no postnatal
  care. `docs/superpowers/specs/2026-11-05-high-risk-decisions.md`.
- **A child is linked to the mother in the patient directory** as "baby of",
  using the directory's own related-profile feature. 5 November.
- **The phoned-in visit is in the plan and built later.** 4 November. An ASHA
  calls the clinic's own number, has an ambient conversation with the patient,
  and the recording creates the patient and fills the record. Three things it
  still needs: a confirm-the-match screen, spoken consent, and a decision about
  whether the demo leads with it.
- **Flags stay automatic.** They are declared rules, not a model. The owner has
  not yet reconciled this with a deck slide saying clinicians mark risk; the
  recommendation on record is to keep the flags and change the slide.

### Design

The owner's design feedback is the most repeated thing in the history, and
three rules come up more than any others.

- **Sentence case everywhere, and no standalone word starts lowercase.** Units
  are the exception: mmHg, mL and pH survive by a guard in `web/src/words.ts`.
- **Text-light.** 11 September: *"remove all the fluff and disclaimer texts...
  Dont be trigger happy with generating too much text everywhere."*
- **One thing expanded at a time.** Every previous station on a thread collapses.
  Cards do not nest inside cards. The right rail collapses by default.
- Restrained colour, not monochrome. Gradients only on request. Icons across
  the board. Skeleton loaders, semantic colours.
- The daffodil and the creeper garland are the product's identity: on the
  sign-in page, and as low-opacity elements inside the app. The daffodil rotates
  while the scribe is listening.
- `web/src/abha/Lotus.tsx` is ABDM's national-identity lotus. **Do not
  restyle it.**

The owner's own taste rules live outside this repository, in
`~/.claude/design-craft/ledger.md` and the `design-craft` plugin, built in this
project's sessions for exactly this purpose.

---

## 8. Known hazards

Each of these cost real time. They are listed so they cost it once.

- **The shared git index.** See rule 7. This is the single most expensive trap
  in the repository.
- **macOS has a case-insensitive filesystem.** `web/src/ui/Pick.tsx` resolved to
  `pick.ts`. It is `Picker.tsx` now. After a rename like that,
  `rm -rf web/node_modules/.vite`.
- **A check that reads a wall clock against a literal timestamp will pass until
  that instant and fail forever after.** One did, at 10:00 UTC on 31 October,
  and cost twenty minutes of bisecting the wrong thing. Take today from the same
  clock the kernel does.
- **The gate scans git-tracked files only.** A new file is invisible to it until
  committed, so a run can pass before the commit and fail after.
- **One end-to-end check flakes** in the MCP exchange, roughly once in four to
  once in eight runs. A re-run passes. It has not been diagnosed.
- **Running `python3 -m catalogue.build` alone overwrites `catalogue.json`** and
  drops the five keys the second step adds.
- **A `sudo` run of the dev server leaves root-owned files** in
  `web/node_modules/.vite`, after which the ordinary `npm run dev` fails with a
  permission error. This is live right now on the owner's machine.
- **The medical records SDK sends `credentials: 'include'`**, which a wildcard
  CORS origin forbids. `api/main.py` has a scoped middleware for this. A
  successful preflight followed by "Failed to fetch" is this.
- **`api/vault.py` is an allow-listed proxy and the allow list is a whitelist,
  not a ban on `..`.** Its own check caught
  `/mr/api/v1/docs/../../profiles/v1/patient/` passing a prefix test, which
  would have reached the patient directory API on the facility's credential.
  Do not loosen it.
- **`.env` holds Eka production credentials**, mode 600, gitignored. They have
  appeared in a transcript and rotation was advised. Never print them back.
- **Two scribe implementations exist and only one is wired.** `api/scribe.py`
  serves the routes; `care_phc/connectors/scribe/` has the boundary, the
  retention rule and the poll loop, and no caller. They map the same response
  twice, and the split already cost one bug. Merging them is a real job.

---

## 9. What is not built

In the order the build plan puts it
(`docs/superpowers/specs/2026-11-04-the-build-plan.md` §5).

1. **Multi-tenancy in the kernel.** Designed 7 November, not built. Seven tables
   need a workspace column: `encounter`, `thread_flag`, `proposal`, `audit`,
   `day_sequence`, `token_booking`, `inventory_item`. Nothing else: the other
   twelve belong to Eka or to CARE. The filter belongs in the Store, not in
   callers. **Write the adversarial two-workspace leak test before the column,
   so it fails first.** One centre reading another's row is not a bug, it is a
   disclosure. Full design:
   `docs/superpowers/specs/2026-11-07-workspace-tenancy-design.md`. Today a
   single workspace is pinned by `VITE_WORKSPACE` in `web/.env.local`.
2. **Audio straight from the browser to Eka**, deleting roughly 2,000 lines of
   our own backend and making the transcript appear during the consultation
   rather than after it. The one cost is the offline hold; the honest middle is
   direct upload when the line is up and our hold when it is not.
3. **Forms open in place, not over a scrim.** The largest remaining renderer
   change, and nothing new should be built on a modal before it lands.
4. **The scribe canvas**: waveform, live transcript, then the draft with each
   value's field. Depends on 2 and 3.
5. **A referral that stays open** past the visit that raised it, with an owner,
   a due date and a closure. There is nothing to build on. Needed for the
   demo's "every referral closed" promise.
6. **Reminders**, through Eka's own telephony and messenger, carrying
   identifiers only.
7. **Tasks that outlive the visit**, a district tier above the facility, and
   the pregnancy as a first-class arc rather than a list of visits.
8. **The condition and medicine lists are three and six entries.** Approved on
   1 November, and approval was never the problem: they need entries. Nothing
   obstetric is in either. The antenatal form codes nothing. This blocked five
   modules in a row and is still the highest-value outstanding item that is not
   a build job.

`docs/MONDAY-READINESS.md`, written 31 October, is the honest answer to "can a
clinician use this": no, and it says exactly why. Most of its five blockers are
now closed; the clinical lists are not.

---

## 10. Open questions only the owner can answer

Do not invent answers to these. Ask.

1. **Is a workspace a facility?** Today they are the same thing by accident. A
   workspace holding two centres is a real case and decides what the tenant key
   is.
2. **Does a clinician move between workspaces mid-shift?** If yes, the id
   cannot be read once at sign-in.
3. **What closes a referral?** The receiving facility recording the visit, the
   sending clinician marking it, or the agent seeing a record appear. Only the
   first is evidence; only the second works offline.
4. **Is the district tier real or seeded?** A week against an afternoon.
5. **Does audio still need our offline hold** once the browser uploads direct?
6. **When is the hackathon.** Asked four times. It decides how much of §9 is
   real and how much is seeded.

---

## 11. The design note index

`docs/superpowers/specs/` holds the designs and `docs/superpowers/plans/` the
plans built from them. Both are worth reading in date order for a feature you
are about to touch. The ones that carry decisions rather than description:

| Note | What it settles |
| --- | --- |
| `2026-09-15-spine-and-plugins.md` | why a patient cannot be the thread |
| `2026-09-16-emr-ui-ux-spec-v0.3.md` | the owner's own interface specification |
| `2026-11-01-front-desk-and-design-system-design.md` | the desk, and the design system |
| `2026-11-01-mobile-pwa-and-android-design.md` | mobile first, and what a phone cannot do |
| `2026-11-02-thread-as-channel-design.md` | tabs, files, the agent chat |
| `2026-11-03-heidi-teardown.md` | what a mature scribe product has that we do not |
| `2026-11-03-eka-scribe-backend-notes.md` | what Eka's scribe backend really does |
| `2026-11-04-the-build-plan.md` | **the current order of work** |
| `2026-11-04-maternal-and-child-health-design.md` | the clinical scope |
| `2026-11-05-high-risk-decisions.md` | the high-risk arc, as built |
| `2026-11-07-workspace-tenancy-design.md` | what the kernel must own, and what it must not |

`docs/DECISIONS-2026-11-01.md` holds four owner decisions in full.
`docs/MONDAY-READINESS.md` is the readiness assessment.

**Four design notes are written but not committed** and so would not reach a
colleague who clones this: the Hera Android plan and design, the newborn record
design, and the `docs/demo/` end-to-end video plan. They belong to sessions
still working. Ask the owner before committing another session's files.

---

## 12. Working with the owner

Written down because it is the difference between work being accepted and work
being rejected.

The owner is not a programmer. Every reply, recap and pull request description
is written for a sharp colleague who has never written code: the answer first,
short sentences, everyday words, no file paths or function names inside
sentences, under about 120 words, and one clear next step at the end. Say what
a change means for them, not how it works inside. The full rule is in the
owner's own `~/.claude/CLAUDE.md` and it overrides the house style of any
document except the code and the commit messages.

Two further things that come from the history rather than from a rule. The
owner notices design before anything else and will say so bluntly; take it at
face value and look at the rendered screen rather than the code. And the owner
asks for the thing that was asked for, not a nearby thing that was easier:
*"please be concious of what's being asked"* is on the record, after the fourth
attempt at one screen.

---

## 13. Facts, for orientation

- 489 commits at `eka-care/rapha`, all of them on `main`. Nearly all were
  authored on the branch `feat/phc-catalogue-and-guard`, which is what the
  owner's own checkout still has checked out and which points at the same
  commit as `origin/main`. A local branch called `main` in that checkout is
  stale at 17 commits and should be ignored or deleted.
- 35 operation declarations, 18 PHC declarations, 31 questionnaires, 2 bundles.
- 36 check scripts, 24 browser-side checks, 1239 `ok` lines in the gate.
- Python 3.9 and stdlib `sqlite3`; Go 1.25; React 19, TypeScript 5.9, Vite 7.
- No database server, no network and no API key are needed to run or check it.
  `ANTHROPIC_API_KEY` is optional and only improves the agent's planner; without
  it a keyword router runs and the guard is unchanged.

