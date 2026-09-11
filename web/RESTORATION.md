# Restoring the workspace: from the shipped renderer back to the prototype

Spec for whoever rebuilds `web/src`. It is written against two things you
must open before you touch code:

- `/Users/samdennis/Downloads/agentic-emr-prototype.html`, the designer's
  single-file prototype. Every function and CSS class named below in
  `monospace` is in that file. Open it in a browser and click around it for
  ten minutes before reading further.
- `/Users/samdennis/Downloads/agentic-emr-role-modules.md`, the spec the
  prototype was built to. Section D (the thread is the baton, state-driven
  quick actions) and section B (find first, create on miss) are the two the
  shipped UI drifted from most.

The verdict, bluntly: the prototype is a chat workspace. A patient is a
conversation thread; posted operations are messages in it; the agent speaks
last and offers what to do next; the composer holds the quick actions and an
"Ask about this patient" box; a sidebar carries the facility, the views, the
recent threads and who you are. The shipped renderer is a tabbed forms and
tables application with a microphone bolted onto one form. It draws the right
data from the right declarations, and it looks like a debugging screen for
the kernel. Both things are true.

The constraint that makes this a spec and not a copy job: the prototype
hard-codes a PHC. Six patients, seven roles, five stations, the sentence the
agent says in each of nine states, the words "BP 158/96". We run one kernel
under any bundle, and `bundles/lab/` must get the same workspace from the
same code. So every restored element below says where it comes from in the
declaration model, and anything that would need a PHC word in `web/src` is
named as a declaration to add instead.

Two rules from the kernel that the prototype breaks and we must not:

1. The prototype greys out a blocked action (`.prop:disabled`,
   `.cq:disabled`, `a.off` with `a.why`). We do not. An action whose
   precondition is unmet, or whose capability is not held, is absent. The
   reason for absence is said in words, in the agent line, never as a grey
   button. `kernel/state.py actions()` already returns only what is visible,
   so the renderer has no way to draw a greyed one and must not invent one.
2. The prototype's `commit()` runs `_run()` in the browser and mutates state.
   Ours posts to `/operations/{op}/commit` or `/proposals/{id}/confirm`, the
   kernel runs the guard again, and the thread is re-read. Nothing in this
   spec adds a client-side write path, and the "Ask" box below cannot commit.

---

## 1. The gap table

Everything the prototype has that the shipped UI lacks, by area. "Shipped"
is `web/src` at HEAD `8279600`. Where the shipped UI has something the
prototype lacks, it is listed at the end of the table so it survives.

### 1.1 Shell

| Prototype element | Where in the file | What it does | Shipped |
|---|---|---|---|
| Two-column app frame `.app` | `<div class="app">` | 248px sidebar `.sb` beside a `.main` column; the page never scrolls, only `.view` or the thread does | A single column with a sticky `.topbar`, page scrolls, `.main` capped at 1180px |
| Brand block `.sb-top` | `.brand-mark` + `.brand-n` "PHC Yadiki" + `.brand-s` "Anantapur · Workspace" | Facility identity, top left, with the eight-petal mark `#i-mark` | The manifest title as plain text in the topbar; no mark, no second line |
| New chat `.sb-btn` | `newChat()` | Opens a workspace thread not scoped to a patient | None. There is no notion of a chat |
| Search `.sb-btn.ghost` with `.kbd` ⌘K | `openSpot()` | Opens the command palette | None |
| Nav `.sb-nav` / `.nv` with counts `.ct` | `renderNav()`, `NAV` | Home, Queue (count), Patient directory (count), Analytics, Organisation, Control panel; active state `.nv.on` | Views as `.qtab` buttons in the topbar, no counts, no Home |
| Recents `.sb-sec` + `.sb-list` / `.th` | `renderThreads()` | Last ten threads, patient or workspace, with icon and active state; empty copy "No chats yet." | None. Back button only |
| Role switcher `.sb-foot` / `.rolebtn` / `.menu` / `.mi` | `renderRole()`, `toggleRoleMenu()`, `setRole()` | Avatar, role label, "N capabilities", a pop-up menu of every role with its capability count; switching re-renders and toasts | None. The renderer is always the `demo` union role; the API supports `X-PHC-Role` and the renderer never sends it |
| Topbar title and subtitle `.tb-title` / `.tb-sub` | `render()`, `TITLES` | On a thread: patient name, "Station · State label"; on a view: the view title and one-line description | `.h1` above the view; a breadcrumb on a thread |
| Scribe control in the topbar `#scCtl` / `.scbtn` | `scCtl()` | "Start scribe", "Transcribing 00:42" (pulsing red), "Resume session" | None |
| "Search or ask ⌘K" pill `.pill` | topbar | Second entry point to the palette | None |
| Theme toggle `.icon-btn` | `toggleTheme()` | Light/dark, `data-theme` on `<html>` | Tokens for dark exist in `theme.css`; no toggle, `data-theme` never set |
| Toast `.toast` | `toast()` | One-line bottom-centre confirmation after every commit and role switch | None |
| Keyboard: ⌘K, Esc, arrows, Enter | `document.addEventListener('keydown')` | Palette open, dismiss, navigate, run | None |
| Icon sheet | `<svg style="display:none">` with 38 `<symbol id="i-...">` | Consistent 16px stroke icons everywhere | None. Avatars carry the characters `*`, `+`, `x` |
| Inter from Google Fonts | `<link>` in `<head>` | The typeface the whole design is set in | `theme.css` names Inter but nothing loads it; falls to system-ui |

### 1.2 Home (`vHome`)

Nothing in the shipped UI corresponds to this screen.

| Prototype element | What it does |
|---|---|
| Hero `.hero` with `.hero-mark` watermark, `.hero-eye` "Nurse · PHC Yadiki", `.hero-h` "Good morning. 4 patients today, 0 complete.", `.hero-sub` "Everything below is a read..." | Orientation and the read/write promise |
| `.hero-ask` read-only input that opens the palette, with `.chips` of role-specific starter questions (`ASKS`) | The agent-first entry point |
| `.arc` "OPD session" clock with progress bar 09:00 to 14:00 | Session time left |
| Shift brief `.brief` | `brief()`: one paragraph with inline `<em>` links, "4 patients are in the facility right now, heaviest at Vitals. 2 still need vitals..." |
| Patient flow `.flow` / `.fl-col` / `.fl-rail` / `.fl-p` | One column per station with a count, an animated rail, a chip per patient (red `.alert` when flagged), `.jam` on the heaviest station |
| Needs you `.att` / `.at` | `attention()`: up to six items filtered by the capabilities the role holds, each with icon, title, subtitle, "Open →" on hover |
| Facility pulse `.pulse` / `.split` / `.leg` | Two stacked bars: seen today (complete vs in progress) and ABHA linkage |
| Pick up where you left off `.cont` / `.cn` | Four most recent threads |

### 1.3 The patient thread (`vChat`, `renderThread`)

| Prototype element | What it does | Shipped |
|---|---|---|
| `.chatgrid` 1fr + 300px, `height:100%` | Thread card and right rail fill the viewport; the thread scrolls inside `.thread`; composer is pinned to the bottom of the card | `.chatgrid` exists but the page scrolls and the composer sits wherever the content ends |
| Header `.pt-head` | Avatar initials, name, "52F · Yadiki · 98•••• 4471 · NCD", then a badge row: `.id-badge` ABHA in the one real blue, or `.b-warn` "ABHA pending"; `.b-blue` station; `.b-mute` token; `.b-crit` clinical flags | Present and close: initials, name, meta from subject, ABHA badge, station badge, risky flags by regex |
| Message kinds | `msgs[].who` is `user` (right aligned, `.msg.right`), `agent` (`.m-av.agent` spark icon), or `sys` (a posted operation card) | Two kinds only: a pending-proposals bubble and audit rows drawn as `.opcard`. Nothing a person said, nothing the agent said |
| Posted operation card | `.bubble` with `.t` title ("Vitals recorded"), `.m-meta` "System · 10:42 · Nurse · flagged", optional `.quote` (what was heard), `.kvbox` of labelled values with `.kv.crit` on the flagged ones | `.opcard` with the operation id humanised, an outcome badge, "at · actor · surface". No values. A committed vitals row shows no vitals |
| The agent line | The last message is always the agent: `agentLine()` says what state the visit is in, which station it is at, and "Here is what you can do as nurse", followed by `.props`: up to five `.prop` buttons each with icon, `.p-l` label, `.p-s` one-line reason, `.p-tag` instrument tag (`scribe`, `form`, `irr`, `hand`); the first is `.prop.primary` (ink filled) | None. `thread.nudge` is drawn in the rail as a `.nudge` |
| Pending proposal | Not in the prototype as such (its agent proposes inside the modal as a `.draft`); the closest is `.prop-card` "Proposed schema, unconfirmed" in `vAdmin` | A `.opcard.prop` with "awaiting a person" and a Review button. This is the one thing shipped that the prototype lacks and it must be kept, restyled |
| Composer `.composer` | `.cbar` of `.cq` pills (`cbar()`): Scribe (`.cq.rose`), Doc assist, Vitals, Rx, Order, Result, Dispense, CBAC, Hand over, Timeline; then `.crow` with an `input` "Ask about this patient" and a round `.send` button | `.cbar` of `.cq` pills from `thread.actions`, first is `.rose`. No input, no send |
| Workspace chat (no patient) | Header "Workspace chat · Not scoped to a patient"; `cbar()` gives Queue today, Pending ABHA, Stock, NCD cohort; `askAgent()` answers via `wsAnswer()` with a `.kvbox` | None |
| `askAgent()` | Posts the question as a user message, answers with an agent message, appends `agent.read` to the audit | None |
| `docAssist()`, `timeline()` | Read-only modals: protocol reference and stock; record timeline across visits and ABDM | None (the summary view is the timeline, one tab away) |

### 1.4 The right rail (`.panel`)

| Prototype card | Contents | Shipped |
|---|---|---|
| Patient state | Eyebrow "Visit", title, `.b-mute` state label; `.states` list of `STEPS` with `.st.done` ticks and `.st.now`; `.nudge` per role (`NUDGES`) | "Where this stands" with the workflow line and the kernel nudge. Close |
| Care unit | Eyebrow "Level 4 · per patient", member rows `.tm` with initials and role-in-episode, "Join care unit" button, a `.nudge` explaining it is episode-scoped | "Who touched this" from audit actors. No join. Correct to not have one; see 4 |
| Capabilities held | `.caps` of every capability as a `.cap` chip, `.cap.on` for the held ones, badge "at PHC Yadiki" | Present, without the "at" badge. Has an extra "Flags" card the prototype does not |
| Audit trail | `.au` rows: time, mono op name, actor, newest first, max-height 150 | Present |

### 1.5 Command palette (`openSpot`, `renderSpot`, `prev`, `rows`)

Nothing shipped corresponds.

| Element | What it does |
|---|---|
| Overlay `.ov` with blur, `.spot` 780px, `.spot-in` 19px input "Search patients, jump to a view, or ask the agent" | Opens on ⌘K, the sidebar button, the topbar pill, or the hero input |
| Rows `rows()` in three groups `.spot-sec`: "Ask the agent" (when `isAsk(q)`), "Patients" or "Today's queue" (name, phone, ABHA, village, token), "Go to" (`CMDS`) | Find first |
| Selection `.sr.sel` with arrow keys, `onmouseenter` | Keyboard first |
| Preview pane `.spot-prev` (`prev()`): for a patient, `.pv-top` avatar and name, `.pv-rows` of Station, ABHA, Category, Active problem, Current meds, Alerts, then `.qa-grid` of four quick actions filtered by the role's capabilities, and `.hint` "Filtered by your bundle" | The disambiguation preview from spec B: the clerk sees age, village, last visit before choosing |
| Empty state | "No patient matches “q”. Registering creates a permanent record that cannot be undone, only deprecated." then one button "Register new patient" | Create only on miss |
| Footer `.spot-foot` | "↑↓ navigate · ↵ run · esc dismiss" and, right aligned in rose ink, "Find first · create only on miss" | The rule, on the screen |
| `registerNew()` / `regModal()` | Three-step register: ABHA SDK (`.sdk`, `.sdk-tabs` Aadhaar OTP / Mobile OTP / Existing ABHA, `.skip` "Register without ABHA"), OTP, confirm with `.verified` "Verified from ABHA, not typed" and an un-prefilled `.chk` gate; the manual path has its own gate "I have searched and confirmed no existing record matches" | We have `phc.op.patient-register` and `phc.op.abha-link` as two operations with questionnaires; the SDK theatre is not restorable and should not be faked |

### 1.6 Queue (`vQueue`), directory (`vDir`)

| Element | What it does | Shipped |
|---|---|---|
| `.qtabs` All / Reception / Vitals / Doctor / Lab / Pharmacy / Complete with counts | Station tabs | Present, generic from `groups` |
| `.qgrid` of `.qc` cards: avatar, name, "52F · Yadiki", `.qc-tok` T24, chips: station, state label, category, ABHA pending, BP flagged | Card per patient | Present, generic from `columns` and `badges`. Missing the token chip styling and the state label chip |
| Directory `.dir-bar` search input + `.f-chip` category filters, then a `<table>` Patient / Category / Village / ABHA / Active problem / Last visit | All patients, searchable | None. No view declares it (see 5.7) |

### 1.7 Analytics (`vAna`), organisation (`vOrg`), control panel (`vAdmin`)

| Element | What it does | Shipped |
|---|---|---|
| "Ask for a view" `.ai-box` with Compose button; `compose()` matches keywords to `METRICS`; `.deny` box "No certified metric, nothing composed" with "Request a metric definition" (`reqMetric()`) | Composed from a registry, never from SQL | A `.mgrid` of metric cards. No compose, no registry list |
| Metric cards `.mc` with `.mc-v`, `.mc-d` delta vs last week, `.spark` bars, `.mc-id` "m.abha.rate · v2026.2" | Trend per metric | `.metric` card with value, "n of m in the week", "since date". No sparkline (the API returns one window, so honest) |
| `lineChart()`, `barChart()` | 13-day line, 7-day bars for the lead metric | None, and nothing in the API to draw them from |
| Certified metric registry `.mr` rows: name, definition, owner, source operation, id and version | The guardrail | None. `catalogue.metrics` carries `title`, `summary`, `certified_by`, `unit`, `window` and is not drawn anywhere |
| Organisation tree `.tree` / `.tn` / `.spine`, node detail `nDetail()`, person detail `pDetail()`, `ESPEC` required fields | Facility levels 1 to 3, people, assignments, HPR | None, and no declaration exists for any of it |
| Control panel: operation registry with `.sw` toggles, `proposeField()` "Ask for a field", capability bundles list with Preview, pharmacy stock | Configuration as versioned proposals | None. The manifest and role bundles are in `/catalogue` and never drawn |

### 1.8 Operation modals and the scribe sheet

| Element | What it does | Shipped |
|---|---|---|
| `modal()` / `.mod` | Centred 520px card with `.mod-bar` gradient line, title, subtitle, body, footer "Actor, surface, payload and outcome are written to the audit log." Cancel, primary button; `gate` disables the primary until an `.chk` box is ticked | `OperationPanel` renders inline, above the thread, as a full-width `.panelcard`, pushing the thread down the page |
| Per-operation bodies `aVitals`, `aRx`, `aLab`, `aResult`, `aDisp`, `aABHA`, `aCBAC`, `aAppt`, `aHand` | Hand-written fields with `.draft` "Proposed from the consultation", `.warn-box` range and stock notes, `.crit-box` critical value with a gate, `.readback` for the voice value | `Form.tsx` from the questionnaire: the same things generically (range, critical, override reason, unsure highlighting). Better than the prototype's; keep it |
| `cVoice()` | Mic button in the form, 1.3s later a `.readback` "158 / 96 mmHg · Heard: ..." | `VoiceCapture` does this for real with the browser's recogniser. Keep it |
| Scribe sheet `.sheet` (`scRender`, `scBody`, `scFoot`) | Right-hand 500px drawer: `.sh-h` with live `.wave`, spoken/note/handout language pickers `.lang`/`.lp`, tabs Transcript / Context / Output, streaming `.tl` transcript with gloss `.tl-g`, `.sc-hero` start card, `.outbox` note, handout and structured payload, "Confirm & post" | A Dictate button inside the form that appends prose to one text field, gated on `capture.consented`. Honest, but nothing like the sheet |
| Handover `aHand()` | Destination list `.dest` with "suggested", optional note, "Confirm handover" | None. The `handover` capability is in vocab and no operation exists (see 5.6) |

### 1.9 Shipped things the prototype lacks. Keep them.

- `Loading`, `Failed` with a `next` sentence, `Boundary`. The prototype has
  no failure states because it has no network.
- The proposal review surface: original payload, editable fields, "You
  changed" diff, provenance, Reject.
- The two-stage un-prefilled confirm on irreversible operations.
- Range block with override reason, critical-band flag preview, unsure
  highlighting of heard values, fail-closed to the keypad.
- "Use demo data" and the API status dot.
- Skipped steps drawn as "not this visit".

---

## 2. The central miss: the patient view is a chat thread

The product owner's primary interaction mode is agent-first, with voice
reserved for discrete data. In the prototype that is literal: you open a
patient and you are in a conversation. The record accumulates as posted
messages, the agent's last message tells you where the visit stands and
offers what to do, and you either tap one of its offers or type a question.
The forms exist, but they are modals that open from the conversation and
post back into it. Rebuild exactly this.

### 2.1 Layout

Inside `.view` (which does not scroll on this screen), `.wrap` holds a
`.chatgrid`: `grid-template-columns: 1fr 300px`, `height: 100%`.

Left, `.card.chatcard`, a flex column at full height:

1. `.pt-head` (fixed). Avatar initials, `.pt-name`, `.pt-meta`, badge row.
2. `.thread` (`flex:1; overflow-y:auto`), the messages, newest at the
   bottom, scrolled to the bottom on every render.
3. `.composer` (fixed at the bottom of the card). `.cbar` of pills, then
   `.crow` with the ask input and the round send button.

Right, `.panel`, the four cards of section 4, scrolling on its own.

Below 1100px the panel hides (`@media(max-width:1100px){.panel{display:none}}`);
below 900px the sidebar hides. Copy those two rules.

Operation forms open in a modal `.ov > .mod` over this screen, never inline.
The scribe opens in the `.sheet` drawer from the right. When either closes
after a commit, the thread is re-read and the new posted card appears at the
bottom. Nothing else on the page moves.

### 2.2 The header

| Part | Source |
|---|---|
| Initials and name | `thread.subject.name` if present, else the first string field, else the thread id. A lab thread today has no patient row (LAB-LOG 12), so it shows the token; that is correct and the fix is a declaration, not a guess in the renderer |
| Meta line | The subject fields that the workflow's queue view lists in `columns`, minus the name, joined with " · ". Today `Thread.tsx` guesses with a plumbing regex; use the declaration instead. Fall back to the regex only when no queue view exists for this workflow |
| Identity badge `.id-badge` | Any subject field whose key matches `abha`. The one real blue. Absent when null; a `.b-warn` "ABHA pending" badge is drawn when the flag `abha.pending` is true (a flag name, not a PHC word: the flag is in `vocab.STATES` and the queue view's `badges` says `warn`) |
| Station badge `.b-blue` | `thread.station` humanised, or "Complete" |
| Token `.b-mute` | `subject.token` if present |
| Risk badges `.b-crit` / `.b-warn` | `thread.flags` filtered and styled by the queue view's `badges` map for this workflow. Replace the `risky()` regex in `Thread.tsx` with that map; keep the regex only as a fallback when no queue view declares badges |

### 2.3 Message kinds

The thread is one list sorted by time. Five kinds:

**System: a posted operation.** One per `thread.audit` row whose outcome is
`allowed`, `confirmed`, or `rejected`.

```
[m-av: check icon]   System · 10:42   [badge: Nurse]   [badge: flagged]
  .bubble
    .t   Record vitals and triage            (op.title from the catalogue)
    .kvbox
      .kv        Systolic     140 mmHg       (label = question text, unit = styling_metadata.phc.unit)
      .kv.crit   Diastolic     96 mmHg       (crit when outside styling_metadata.phc.critical)
      .kv        Pulse         72 bpm
    .quote  "systolic one forty over ninety"   (proposal.transcript, when the audit row came from one)
```

The values are `audit.payload` keyed by link_id, labelled by walking
`questionnaire(op.input)` with `labelled()` from `Form.tsx`, which already
exists. Answers not in the questionnaire are shown with the raw key. An
`override_reason` in the payload is drawn as its own `.kv.crit` row labelled
"Override reason". A `rejected` outcome draws the card muted with a
`.b-mute` "rejected" tag and no values.

Tags on the meta line, all generic: the actor (role or name, see 3.3), the
instrument the operation declares (`form`, `device`, `voice`, `scribe`),
`irreversible` in `.b-crit` when the operation is, and each flag in
`proposal.flags_raised` styled by the queue view's badge map.

**System: a denial.** One per audit row whose outcome starts with `denied:`.
The prototype has no such thing; we have them and the product owner asked to
see both halves of the agent's work in the trail. Draw it as a muted card:

```
[m-av: x]   System · 10:50   [badge: agent]   [badge b-mute: refused]
  .bubble (muted)
    .t   Order investigation
    precondition not met: consult.documented
```

Collapse denials older than the last posted operation behind one line "3
earlier refusals" that expands. They matter, and they should not drown the
record.

**Agent: a pending proposal.** One per `thread.proposals` with status
`pending`, placed by `created_at`.

```
[m-av.agent: spark]   Agent · 10:53   [badge: over mcp]   [badge b-warn: awaiting a person]
  .bubble
    .t   Record vitals and triage
    Proposed by agent. Nothing in it has been recorded.
    .kvbox   (same labelled values; every value drawn as unsure because it is unconfirmed)
    .props
      .prop.primary   Review and commit      "Opens the values in editable fields; you tap."
      .prop           Reject
```

Review opens `OperationPanel` in proposal mode inside the modal, exactly as
it works today. Reject calls `client.reject`.

A proposal is **stale** when its operation is not in `thread.actions` any
more (the live thread `enc-002` has three pending `vitals-record` proposals
and `vitals.recorded` is already true). Draw it with a `.b-mute` "superseded"
tag, hide Review, keep Reject. Confirming it would be refused by the guard
anyway; the UI should say so first.

**User: a question or an utterance.** `.msg.right`, `.bubble` in the accent
tint, meta right-aligned "Nurse · 10:55". Produced by the ask box. These are
not audit records and the kernel does not store them; keep them in the
renderer's memory for the session (and in `localStorage` per thread as a
convenience, capped). Say in the empty state that questions are not part of
the record.

**Agent: the state line, always last.** Rendered from the thread, never
stored. One bubble:

```
[m-av.agent: spark]   Agent · now
  .bubble
    <sentence 1: what just happened>   <sentence 2: where it stands>   <sentence 3: what you can do>
    .props  (up to five, see 2.5)
```

Sentence 1 is the newest posted operation's title in the past tense of its
outcome: "Record vitals and triage was committed by the nurse at 10:42." If
the newest audit row is a denial, say that: "The agent's Order investigation
was refused: precondition not met: consult.documented." If there is nothing:
"Nothing has been recorded on this visit yet."

Sentence 2 is `thread.nudge` from the kernel ("doctor: Consultation" or
"Waiting at doctor. Nobody with your capabilities can act here." or "Line
complete."). This is the sentence that replaces every greyed button: when the
role cannot act, this says why.

Sentence 3 is "Here is what you can do as <role>." when `thread.actions` is
non-empty, else nothing.

The prototype's `agentLine()` has nine hand-written sentences keyed to PHC
states ("HbA1c is on the lab worklist..."). There is no declaration field to
carry per-state prose today. Do not add PHC sentences to the renderer. If the
product owner wants them, the place is a `says:` string on each entry of
`Workflow.states` in the declaration, and `kernel/contracts.py` is frozen
(report the gap, do not patch it). Until then the three composed sentences
above are what the agent says, and they are true for the lab too.

### 2.4 Where voice sits

Voice is an instrument on an operation, so it lives in the operation's
modal, exactly where `VoiceCapture` sits today: above the form, values land
in the fields marked unsure, the person taps Commit. Do not put a microphone
in the composer.

Two things do surface in the thread:

- A composer pill for the scribe (`.cq.rose`, mic icon, the instrument's
  `title`) when a `kind: scribe` instrument declares an operation that is in
  `thread.actions` and `capture.consented` is in `thread.flags`. Tapping it
  opens that operation's modal with the dictation control ready. When consent
  is absent the pill is absent, and the agent line's sentence 2 gets one
  extra sentence: "Capture consent is not recorded on this visit, so the
  scribe is off." That sentence is generic: it is the `CONSENT` constant
  `VoiceCapture.tsx` already holds.
- The transcript, when a proposal or audit row carries one, as the `.quote`
  on the card.

The scribe sheet (`.sheet`, three tabs, languages) is polish; see 6.

### 2.5 The composer

`.cbar` first, one row, horizontal scroll, no wrapping:

1. The scribe pill, if any (2.4), `.cq.rose`.
2. One `.cq` per `thread.actions` entry, label `op.short`, an icon by
   `op.instrument` (form, device, voice, scribe), a leading "!" glyph or lock
   icon when `op.irreversibility === "irreversible"`. Capped at six (spec D:
   "hard cap of six visible actions; the rest live behind the palette").
   The first action whose `station === thread.station` is `.cq.rose` when
   there is no scribe pill; otherwise plain.
3. "More" (`.cq`) when actions exceed six, opening the palette filtered to
   this thread's actions.
4. One `.cq` per summary view declared on this workflow, label the view
   title (for the PHC that is "Visit summary"; the prototype calls it
   Timeline). It opens the summary as a modal-sized sheet, not a tab.

No pill is ever disabled. The `.props` list in the agent line is the same
`thread.actions` drawn vertically with more words: `.p-l` is `op.title`,
`.p-s` is the first sentence of `op.summary`, `.p-tag` is `op.instrument`
(`scribe` and `form` have their own tag colours in the prototype; `device`
and `voice` take `form`'s), or `irr` "irreversible" when it is. First is
`.prop.primary`. Five at most.

`.crow`: `<input placeholder="Ask about this patient">` and a round ink
`.send`. Enter sends. For a workspace thread the placeholder is "Ask about
the facility".

What sending does, honestly:

- There is no route on the kernel for an utterance, and `kernel/contracts.py
  ROUTES` is frozen. The planner exists as `python3 -m agent`, in Python,
  and its client can only propose. The right shape is a small HTTP wrapper
  around `agent.planner.plan()` and `agent.client.Kernel.propose()`, in
  `agent/serve.py`, on its own port, reached by the renderer as
  `VITE_AGENT_BASE`. It takes `{utterance, thread, role}`, returns
  `{proposals: [ids], said: "..."}`, and posts every proposal through the
  kernel's `/propose`, so the machine surface is the machine surface. The
  renderer then re-reads the thread and the pending cards appear. The box
  itself never calls `/commit` or `/confirm`; put that in a check.
- When `VITE_AGENT_BASE` is unset or unreachable, the input stays visible
  and sending posts the user bubble followed by an agent bubble: "No agent
  is connected to this kernel. Start `python3 -m agent.serve` and it will
  answer here. Everything it proposes still lands as a card you confirm."
  That is the honest degraded state, not a hidden input.
- For a workspace thread, questions that name a declared view (its title or
  id words) are answered client-side with no agent at all: the view result
  is rendered as a `.kvbox` (group counts for a queue, metric values for a
  dashboard). That is the generic form of `wsAnswer()`, and its pills are
  one `.cq` per queue and dashboard view the role may open.

---

## 3. The workspace shell

### 3.1 Sidebar `.sb`, top to bottom

| Block | Prototype | Source for us |
|---|---|---|
| `.brand-mark` + `.brand-n` + `.brand-s` | "PHC Yadiki" / "Anantapur · Workspace" | `manifest.title` / `"<manifest.id> · <manifest.version>"` from `/catalogue`. The mark is `#i-mark`, generic. There is no facility name anywhere in the declarations; the bundle title is what we have |
| New chat | `newChat()` | Opens a workspace thread (2.5). Same button, same copy |
| Search with ⌘K `.kbd` | `openSpot()` | Same |
| Nav `.nv` | `NAV` hard-coded six | Home, then one entry per view in `catalogue.views` whose `kind !== "summary"`, in manifest order, label `view.title`, icon by `kind` (list for queue, vitals-line for dashboard). Summaries are not nav; they belong to a thread. The count `.ct` on a queue view is the sum of its `groups[].count` excluding the `null` key, fetched once per minute. No count on a dashboard |
| Recents | `renderThreads()` | The last ten thread ids opened in this browser, with the name shown in the header at the time, in `localStorage`; workspace chats included with the spark icon. Per viewer, not shared: it is a convenience, say so in the code |
| Role switcher `.rolebtn` + `.menu` | `ROLES` hard-coded seven | `/facility` returns `roles` and `/catalogue` returns `bundles` (role to capabilities). Label `human(role)`, subtitle "N capabilities". The menu lists every role with its count and marks the active one. Selecting writes the role to `localStorage`, sets `X-PHC-Role` on every request in `api.ts`, and re-reads everything. Default is `demo`, labelled "Every capability (demo)" so the union is never mistaken for a person |

The prototype's role has an icon (`desk`, `nurse`, `doc`), a subtitle
("Vitals & triage"), a home node and a person behind it (`ROLE_USER`). None
of that is declared. Do not map role ids to icons in the renderer; use the
role's initial in `.rb-av`. If the owner wants labels, the declaration is a
`roles:` block in `bundle.yaml` with `title` and `summary` per role, which
`kernel/declarations.py` would need to compile (LAB-LOG 10 already wants the
default role declared there too). Until then, `lab_incharge` reads "lab
incharge", and that is the honest state.

### 3.2 Topbar `.topbar`, 56px

Left `.tb-title` / `.tb-sub`:

- On a thread: the subject name; sub `"<station humanised> · <label of the
  last done step humanised>"`, or "Complete" once `station` is null. The
  prototype's `stateLabel()` chain is PHC-specific; the last done step's
  `done_when` flag is the generic equivalent and reads "Vitals recorded"
  for the PHC and, per LAB-LOG 2, "Vitals recorded" for a collected specimen
  too, which is a vocab lie the renderer must show rather than paper over.
- On a view: `view.title` / `view.summary`.
- On Home: "Today" / "Your shift at a glance".

Right: the scribe control `#scCtl` (polish), the "Search or ask ⌘K" pill,
the theme toggle, and the API status dot with the "Use demo data" toggle
moved here from the current header, drawn as `.icon-btn`.

### 3.3 Who the actor is

Audit rows carry `actor` as `user:<role>` or `agent`. Draw `user:x` as
`human(x)` and `agent` as "agent" with the spark icon. The API accepts an
`X-PHC-Actor` header; the renderer does not send one because there is no
people directory to pick a name from. Do not invent one.

### 3.4 The command palette

Open on ⌘K, Esc closes, arrows move `.sr.sel`, Enter runs. Same markup and
classes as `renderSpot()`.

Rows, in groups:

1. **Ask the agent**, when `isAsk(q)` (the same regex). Runs 2.5's send in
   a workspace thread.
2. **Patients** (or "Today's queue" when the box is empty). Rows come from
   every queue view the role may open; today that is the station queue with
   `scope: today`. Match on any `columns` value and the thread id. To find a
   patient not seen today, a queue view with `scope: all` and no `group_by`
   has to be declared (5.7); the palette then searches it too, without any
   code change. Row `.sr-n` is the name, `.sr-m` is the other columns and
   the station.
3. **Go to**: Home and every nav view, matching on title.

Preview `.spot-prev` for a patient row: `.pv-top`, then `.pv-rows` of
Station (and last done step), each queue column, each flag styled by the
badges map, then "Quick actions" as a `.qa-grid` of that thread's
`actions`, which needs one `GET /threads/{id}` when the row is highlighted
(debounce 150ms, cache per palette session). "Open thread" is always first.
`.hint` reads "Filtered by your role (<role>)". The prototype hard-codes four
buttons and disables the ones the role lacks; ours draws what the kernel
returned, which is already filtered, and disables nothing.

Empty state when `q` is non-empty and nothing matched:

```
No patient matches "q".
Registering creates a permanent record.
[ Register new patient ]
```

The button is the generic form of `registerNew()`: `POST /threads` (which
exists on the API, opens an empty encounter and writes no clinical fact),
then open the modal for the first operation of the workflow's first step
(`workflows[wf].steps[0].operations[0]`; for the PHC that is
`phc.op.patient-register`, for the lab `lab.op.referral-accession`). The
modal's own irreversibility rules apply. Note the prototype treats
registration as the irreversible class with an un-prefilled gate and our
atom says `correctable`, while `phc.op.abha-link` is `irreversible` and gets
the two-stage confirm we already have. That is a declaration decision, and
the atom is where it changes.

The footer line "Find first · create only on miss" stays, in `.rose-ink`.

---

## 4. The right rail, and why "Capabilities held" is there

Four cards in `.panel`, in this order, each `.card` with a `.card-h`.

**1. Patient state.** Eyebrow `human(thread.workflow)` ("Outpatient line",
"Specimen line"), title "Where this stands", badge the last done step's
label. Body: `Line` as today (done, now, pending, skipped "not this visit").
Then a `.nudge`. The prototype's `NUDGES[role]` are seven doctrine sentences
("Vitals are discrete values... form or device, never ambient scribe"). They
are role-specific and PHC-flavoured; do not hard-code them. Use
`thread.nudge` from the kernel as the nudge and nothing else. If the owner
wants doctrine on screen, the place is the instrument declaration's
`summary` ("Say one number for one field..."), which is generic and already
written: show the summary of every instrument that applies to an action at
the current station, one `.nudge` each. That is a real improvement on the
prototype: the doctrine is attached to the thing it governs.

**2. Care unit.** Eyebrow "This visit", title "Who touched this", badge the
count. Rows from the distinct actors in `thread.audit` with the first
operation they ran, as today. No "Join care unit" button: there is no
operation for it and a button that mutates nothing is a lie. Keep the
prototype's explanatory `.nudge` copy, which is generic: "Membership accrues
as stations touch the patient. It is scoped to this visit, not to the
facility."

**3. Capabilities held.** Title, badge "at <manifest.title>". `.caps` of
every capability in `thread.capabilities` with `.cap.on` for `thread.held`.
This card earns its place, and it is the one the rebuild is most tempted to
drop as debug clutter, so here is the argument. Everything else on the
screen obeys the invisibility rule: an action you cannot take is not there.
Invisibility has a cost: an absent button looks identical to a missing
feature or a bug. This card is the only place the person can see the shape
of what they are not being shown, and read it against the role in the
sidebar foot. When the nudge says "Nobody with your capabilities can act
here", this card is what makes that sentence checkable in two seconds. It is
also the visible half of the permission model the spec calls "the product"
(C, "Replacing master access"). It stays.

**4. Audit trail.** As today. Newest first, `max-height:150px`, `.au` rows.
Denials included, `.b-crit` outcome. The badge is the count.

Drop the shipped "Flags" card: the flags are already on the header as badges
and on the line as done steps, and the card duplicates them in monospace.
Every flag is still reachable in the summary view's "Flags" section.

---

## 5. Where every element comes from

The prototype hard-codes everything. This table is the whole point of the
document: for each restored element, its source in our model, and what
would be a hard-code if you are not careful. "Generic" means the renderer
code names nothing from any bundle.

| Element | Prototype source | Our source | Hard-code trap, and the declaration instead |
|---|---|---|---|
| Facility name and mark | `"PHC Yadiki"`, `"Anantapur"` | `manifest.title`, `manifest.id`, `manifest.version` | No facility name is declared. Do not put one in `index.html`. If wanted: a `facility:` block in `bundle.yaml` |
| Nav items | `NAV` | `catalogue.views` where `kind !== "summary"`, manifest order, plus a fixed Home | Nav keyed by view id ("if id === phc.view.station-queue") is the trap. Key by `kind` only |
| Nav counts | `PATIENTS.filter(today)` | Queue view `groups[].count` sum, `null` key excluded | Generic |
| Home hero sentence | `td.length`, `done` | Same sums: total rows, and the `null` group count as "complete" | Generic. "patients" is the word; use `human(workflow.subject)` pluralised badly or just "threads". Say "N on the <workflow title> today, M complete" |
| Home hero starter chips | `ASKS[role]` | One chip per queue or dashboard view the role may open ("Show <view.title>"), which the workspace chat answers without an agent | The prototype's questions ("How many patients have no ABHA?") are PHC. Do not hard-code them. When the agent wrapper exists, its own suggested questions can come back on `/agent/hello` |
| Session clock `.arc` | "09:00 to 14:00" | Nothing. Drop it. No declaration carries hours | Trap. Do not hard-code 09:00 |
| Shift brief | `brief()` per role, PHC prose | One generic sentence: "N on the line right now, heaviest at <group with max count>", with the group name as a link to that queue tab. Add ", and P proposals await a person" only when a cross-thread proposals route exists (it does not; ROUTES has none) | The per-role prose is PHC. Skip it |
| Patient flow columns | `STATIONS` | The queue view's `groups` in order, with the rows in each; a chip is `.alert` when its `badges` contain a `crit` | Generic. Column labels are `human(group.key)`. For the lab that reads "reception, nurse, lab, doctor", which is LAB-LOG 2 made visible |
| Needs you | `attention()` filtered by caps, PHC rules | Queue rows carrying any `crit` or `warn` badge, newest first, capped at six; each opens the thread | The prototype filters by what the role can do about it. We cannot without a thread read per row; do not fake it. Say "Flagged on today's line" instead of "Needs you" |
| Facility pulse | seen today, ABHA linked | The dashboard view's metrics that have a denominator, as `.split` bars (numerator vs denominator minus numerator), the rest as numbers | Generic |
| Recents | `S.threads` | `localStorage` | Generic |
| Role switcher | `ROLES` | `/facility.roles`, `/catalogue.bundles` | Role labels, icons and subtitles are not declared; use `human(id)` and the initial. Declaration to add: `roles:` in `bundle.yaml` |
| Default role | `frontdesk` | `demo` | LAB-LOG 10 wants a bundle-declared default; until then the union, labelled as such |
| Thread header meta | `p.age`, `p.village`, `p.cat` | The queue view's `columns` applied to `thread.subject` | The plumbing regex in `Thread.tsx` is a guess; the view already says which fields matter |
| Identity badge | `p.abha` | Subject key matching `/abha/` | The one accepted hard-code: ABHA is a national identifier, not a facility concept, and `--abdm` blue is reserved for it by the design rule. Keep the regex, keep the colour |
| Flag badges | `p.v.vitalsFlag` etc. | `thread.flags` styled by the queue view's `badges` | Replace `risky()` regex with the map; keep the regex as fallback when no queue view declares badges |
| State label | `stateLabel()` chain | Last `done` step's `label` | Generic |
| Line steps | `STEPS` | `thread.line` | Already generic |
| Agent line | `agentLine()` per state | Three composed sentences from the newest audit row, `thread.nudge`, and whether `actions` is empty | Nine PHC sentences are the trap. Declaration to add if wanted: `says:` per state in the workflow, which needs the frozen contract to grow |
| Quick actions, props and pills | `actions()`, `cbar()` with caps checks and `off` | `thread.actions` verbatim; the kernel already ordered them by the current station, then line order | Never disable. Cap six pills, five props. Ordering is the kernel's (D.2: a table, not a model) |
| Pill labels and tags | `l`, `s`, `tag` | `op.short`, `op.title`, `op.summary`, `op.instrument`, `op.irreversibility` | Generic |
| Icons on pills | `ic` per action | By `op.instrument` and by `view.kind`, never by station or op id | Station icons (`i-desk`, `i-nurse`) would encode the PHC. Use the first letter of the station in a `.fl-av` instead |
| Primary action | `i===0 && !a.off` | First action at `thread.station` | Generic |
| Scribe pill | `c.includes('encounter.document')` | A `kind: scribe` instrument naming an action in `thread.actions`, and `capture.consented` in flags | `capture.consented` is the one flag name in the renderer; it is already there in `VoiceCapture.tsx` as `CONSENT` and it is the product rule, not a PHC word |
| Voice in the form | `cVoice()` | `mountsFor()` over `catalogue.instruments` | Already generic |
| Doc assist | `docAssist()`, protocol text | Nothing. No declaration. Drop | Trap: the NPCDCS text |
| Timeline | `timeline()` | The summary views declared on this workflow | Generic |
| Hand over | `aHand()` | Nothing. `handover` is a capability in vocab with no operation atom; the station is derived from records, not moved by a person | Declaration to add: an operation that writes something the station derivation reads, or nothing, since the derived station already moves when the previous step's record lands. Do not fake a move |
| Posted card values | hand-written `kvs` | `audit.payload` labelled by the questionnaire, units and critical bands from `styling_metadata.phc` | Generic. `phc` in `styling_metadata.phc` is a namespace name (LAB-LOG 14, cosmetic) |
| Posted card tags | `tag`, `tagc` | outcome, instrument, irreversibility, `flags_raised` via the badge map | Generic |
| Proposal cards | `.prop-card` (admin only) | `thread.proposals` | Already generic; restyle |
| Ask box | `askAgent()` client-side | `agent/serve.py` over HTTP, propose-only; degraded copy when absent | The renderer must have no commit path from this box. Check it |
| Workspace chat answers | `wsAnswer()` regexes | Match the question against view titles and ids; render the view result | Queue, ABHA, stock, NCD regexes are the trap. Views only |
| Palette patient rows | `PATIENTS` | Queue views the role may open | For patients not on today's line, declare a directory view (5.7) |
| Palette preview rows | `p.dx`, `p.meds`, `p.alerts` | Queue `columns`, station, flags, `actions` from one thread read | "Active problem" and "Current meds" are a summary section's job; the summary view is one click away |
| Register on miss | `registerNew()` three-step SDK | `POST /threads` then the first operation of step one | The SDK screens are theatre. The two atoms and their questionnaires are the real thing |
| Directory | `vDir()` | A queue view with `scope: all`, no `group_by`, more `columns`; category chips from the group_by if any | Declare it. Not one line of renderer code |
| Analytics cards | `METRICS` with sparklines | `dashboard` view result | Sparklines need history the API does not return. Draw the one window honestly |
| Metric registry | `METRICS` defs, owner, version | `catalogue.metrics`: `title`, `summary`, `certified_by`, `unit`, `window`, and the numerator's `resource` as "source" | Generic, and currently undrawn |
| "No certified metric" deny box | `UNCERTIFIED` | When the ask box on the Analytics view matches no metric title or summary word | The six PHC excuses are the trap. Generic copy: "No certified metric matches. The agent does not compose from free SQL." |
| Organisation | `ORG`, `PEOPLE`, `ESPEC` | Nothing. No declaration. Drop the screen | Whole screen is a trap |
| Control panel | `FIELDS`, `STOCK`, `ROLES` | A read-only "This bundle" view: manifest, operations (id, short, capability, station, instrument, irreversibility, verified status), roles with capabilities, instruments, metrics, views. All from `/catalogue` | The field proposer and stock are traps. The read-only bundle page is genuinely generic and is what an admin needs to see |
| Toast copy | per action | "<op.title> committed", "<op.title> proposed for review", "Role: <role>" | Generic |
| Theme | `toggleTheme()` | Same, on `<html data-theme>`; `theme.css` already has both palettes | Generic |
| Typeface | Google Fonts Inter | Same `<link>` in `index.html`; system-ui fallback already in `theme.css` | Generic |

### 5.7 Declarations to add, none of them renderer work

- `phc.view.directory` and `lab.view.register`: `kind: queue`, `scope: all`,
  no `group_by`, `columns` with phone and village (or referrer for the lab).
  Nav, palette search and the directory screen all appear from that alone.
- `roles:` in `bundle.yaml` with a title and one line per role, and the
  default role. Needs `kernel/declarations.py` and `contracts.Manifest` to
  grow; contracts are frozen, so file it as a gap.
- `says:` per workflow state, if the owner wants the prototype's agent prose.
  Same frozen-contract caveat.
- Nothing for hand over. The line moves when records land.

### 5.8 What the lab gets from the same code

Point the shell at `:8001` and, with no bundle-specific line in `web/src`:
brand "Diagnostics laboratory · lab · 2026.09.11"; nav Home, "Worklist by
specimen status" (with a count), "Turnaround today"; the role menu lists
`lab`, `lab_incharge`, and the PHC roles too because `vocab.BUNDLES` is one
list (LAB-LOG 2); a thread header showing the token because there is no
patient row; a line reading "reception, nurse, lab, doctor" with a "now"
step; composer pills Accession, Collect, Result, Verify, Release as the
kernel returns them; an agent line saying "Waiting at reception. Nobody with
your capabilities can act here." for the technologist; a "Laboratory report"
summary pill; analyser as a device row in the result modal; a dashboard of
four metrics. Every wrong word on that screen is listed in `LAB-LOG.md` and
every one of them is fixed in `vocab.py` or a declaration, not here. If the
rebuild finds itself adding `if (bundle === "lab")` anywhere, it has gone
wrong.

---

## 6. Build order for one agent, a few hours

Ranked. Do them in order; each step leaves the app runnable and
`sh scripts/check.sh` green. The line between "stops looking like a
prototype" and "polish" is drawn after step 7. Reuse before writing:
`theme.css` already carries most of the prototype's classes verbatim
(`.sb`, `.nv`, `.chatgrid`, `.bubble`, `.kvbox`, `.props`, `.prop`, `.cq`,
`.states`, `.caps`, `.audit`); copy the missing ones (`.sb-*`, `.rolebtn`,
`.menu`, `.mi`, `.topbar` as 56px, `.view`, `.wrap`, `.msg.right`,
`.kv`, `.quote`, `.p-*`, `.ov`, `.spot*`, `.sr*`, `.pv-*`, `.qa-*`, `.mod*`,
`.sheet`, `.toast`, `.home`, `.hero*`, `.flow`, `.fl-*`, `.at*`, `.pulse`,
`.split`, `.leg`, `.cont`, `.cn`) from the prototype's `<style>` into
`theme.css` in one commit before any component work, with the dark
overrides, and delete `renderer.css` rules they supersede.

### Essential

1. **Shell and role.** `App` becomes `.app` with `Sidebar` and `.main`
   (topbar + `.view`). Nav from views, Home route, recents in
   `localStorage`, role switcher reading `/facility` and setting
   `X-PHC-Role` in `api.ts` (`mock.ts` gains `facility()`). Icon sheet as
   `icons.tsx` with a `<use>` helper. Inter in `index.html`. Theme toggle.
   Check: a node script asserting the nav is exactly the non-summary views
   in manifest order and that `api.ts` sends the stored role header.
2. **The thread as a conversation.** Rewrite `Thread.tsx`: one time-sorted
   list of the five message kinds in 2.3, posted cards with labelled
   payloads via `labelled()`, denials muted and collapsed, pending proposals
   as agent cards with stale detection, the composed agent line with
   `.props`. Header meta and badges from the queue view's `columns` and
   `badges`. Check: pure function `messages(thread, catalogue)` asserted on
   a fixture: order, kinds, stale marking, that a denied row never renders
   a Review control.
3. **Composer.** Pills from `thread.actions`, cap six, primary rule,
   scribe pill rule, summary pills, More to palette. The ask row with the
   degraded agent reply. Check: `composer(thread, catalogue)` returns no
   disabled pill ever, at most six action pills, and the module imports no
   commit or confirm symbol.
4. **Modal and sheet.** `OperationPanel` unchanged inside `.ov > .mod`
   with the `.mod-bar`, the footer sentence about the audit log, and Esc
   to close. Summary views open in `.sheet`. After `onDone` the thread
   re-reads and scrolls to the bottom; a toast names the operation.
5. **Right rail.** The four cards of section 4, Flags card removed,
   "at <manifest.title>" badge, instrument summaries as nudges.
6. **Palette.** ⌘K overlay, three row groups, keyboard, preview with a
   debounced thread read, empty state with `POST /threads` then the first
   operation. Check: `rows(q, views)` groups and the miss state on a
   fixture; that the miss button's operation is `steps[0].operations[0]`.
7. **Home.** Hero (no clock), starter chips from views, brief sentence,
   flow columns from queue groups, flagged rows, pulse from the dashboard,
   recents. Every number from one queue read and one dashboard read.

At the end of 7 the app is the prototype's workspace with real data under
it, for both bundles, and the only thing it lacks is the agent answering.

> **Done, 2026.09.13, differently.** There is no `agent/serve.py` and no
> `VITE_AGENT_BASE`. The route is on the kernel itself,
> `POST /api/v1/phc/agent/say` in `api/main.py`, calling `agent/turn.py`. A
> second process would be a second port, a second CORS surface and a second
> copy of the propose path for nothing: the kernel already holds the only
> propose path, and that route takes no `confirmed` argument. `web/src/ask.ts`
> posts there. The degraded copy now applies when the KERNEL is unreachable,
> which is the only way the box can be dead. `scripts/e2e.py` posts an
> utterance, asserts the card, asserts no clinical row, confirms it, and reads
> the row back out of SQLite.

8. **The agent box, wired.** `agent/serve.py`: stdlib `http.server`, one
   POST, calls `plan()` then `Kernel.propose()`, returns ids and one
   sentence. Renderer sends `{utterance, thread, role}` and re-reads the
   thread. Add the e2e line: post an utterance, assert a pending proposal
   appears on the thread and nothing was written. This is essential to the
   owner's "agent-first" and it is last in the essential list only because
   it needs the Python side.

### Polish, in order of payoff

9. Workspace chat answering view questions client-side; starter pills per
   view.
10. Analytics: the metric registry list from `catalogue.metrics`; the
    "no certified metric" box on the Analytics ask.
11. "This bundle" read-only page from `/catalogue` (replaces Control panel).
12. The scribe sheet: drawer, live wave, transcript tab from `dictate()`,
    output tab as the draft in the consult form, "Confirm & post" opening
    the modal. Languages only if the recogniser exposes them; do not draw
    pickers that do nothing.
13. Topbar scribe control with the running timer.
14. Motion: `pop`, `slide`, `fade`, `flow` keyframes; hover lifts on cards
    and pills; `prefers-reduced-motion` off switch.
15. Directory screen once `phc.view.directory` is declared: `.dir-bar`
    search and the table renderer for an ungrouped queue.

### Not to build

Organisation, the field proposer, stock, doc assist, hand over, the ABHA SDK
walkthrough, per-state agent prose, the OPD clock. Each is either
undeclared, PHC-specific, or a fake write. Say so in a comment where a
reader might look for it, and move on.
