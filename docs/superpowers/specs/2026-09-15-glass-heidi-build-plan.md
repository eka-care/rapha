# Glass and Heidi, understood — the build plan

Status: understanding complete, approved to build. Date: 2026-09-15

Design system: Eka functional luxury (Inter, #215FFF for functional controls, rose gradient at most twice per screen, radii 6/8/12/16).

Produced by a four-agent workflow studying the owner's seven screenshots against our kernel.

The owner named three things he likes: patient lists, patients clubbed as encounters, chat taking precedence. Each is answered below, and several are answered by declarations we already have.

## The rail, resolved

TWO LEVELS, FOUR ENTRIES, ONE DELETION. Final order, top to bottom:

1. THE PRIMARY VERB BUTTON — exists today (web/src/Shell.tsx:434, Alt+N), derived from workflow.steps[0].operations[0]. "Register patient" at a PHC, "Accession referral" in the laboratory. Unchanged.
2. HOME (Alt+1) — exists.
3. THE DECLARED VIEWS from manifest.views, in manifest order, Lines first (Alt+2..9, already wired at Shell.tsx:296-341). THIS IS WHERE EVERY PATIENT LIST LIVES. A list is a queue declaration, so it arrives as a nav entry the rail already draws and already keyboard-binds: zero new rail machinery.
4. PATIENTS — one route, #/patients, the find-first register from the spine spec. FOR: identity, durable, "has this person been here before".
5. THE ROLE FOOTER — exists.

WHAT EACH LEVEL IS FOR, stated so they cannot be confused: level 3 is TODAY'S LINE (encounters, derived per request, authoritative about right now). Level 4 is THE REGISTER (patients, durable, authoritative about identity). The two never contain the same row twice, because one is scoped to today and the other to a person. Glass shows three parallel enumerations of the same rows (lists, patients-nested, encounters-flat) and makes the user work out which is authoritative.

REMOVED — RECENTS (web/src/Shell.tsx:475-556, the "Recents" section header, the sort menu, the filter menu, the rail-list, recentRow at :258, the localStorage key at :29-48, plus loops.ts sortOptions/filterOptions/filterRows and Home.tsx:168's "Recent" plate). ~150 lines out. Three reasons, each in the code:
(a) It is localStorage["phc.recents." + API_BASE], ten items, per browser. Its own docstring says "Per viewer, not shared, and a convenience rather than a record". It survives no handover, no shift change and no second device.
(b) IT FABRICATES ROWS. recentRow() (Shell.tsx:258) synthesises { station: null, flags: [], badges: {}, opened_at: "" } for any recent not on today's queue read. So the rail can show a patient with no badge who carries lab.critical. That is a wrong-but-plausible render, the exact class this branch has shipped green twice.
(c) Its job is already served: the thread you just had is still on the line, at a station, in the queue, plus the browser back button.

NOT ADDED — PATIENT-NESTED TREES. Glass's expanded "Patient" rows with "Show 1 more encounter" underneath are a page trying to happen inside a sidebar. RULE, written down: NO RAIL ROW EVER EXPANDS. The nesting is the patient page's body, where a date, a token, a status and what the visit contained all have room.

NOT ADDED — ENCOUNTER-FLAT. Every queue row already IS an encounter: Workflow.subject: encounter, and QueueRow.thread is the encounter id. Glass's "All Encounters" is our queue with group_by removed; that is one declaration if anyone ever asks, and nobody will.

VISUAL (Eka functional luxury): rail 248px; nav row 34px high, radius 8, label Inter 12.5px/600 #141815; active row background #215FFF at 8% with a 2px #215FFF left rule; the count numeral right-aligned, tabular-nums, 11px, #5E665C. The primary verb button is the one solid #215FFF fill on the rail. The rose gradient does not appear in the rail at all — it is spent once per screen elsewhere.

ONE BUG THIS WORK MUST FIX WHILE IT IS IN HERE: .rail-altkey (Shell.tsx:449 and :468, the Alt-digit hint on every rail row) has NO rule in any stylesheet. It renders unstyled today and the gate is green.

## Patient lists

A PATIENT LIST IS A VIEW OF kind: queue, DECLARED, WITH MEMBERSHIP DERIVED. Not a new declaration type, not a new view kind, not per-viewer state, not a table.

READ GLASS'S OWN DIALOG AGAINST OUR OWN DECLARATION. "A patient list organizes patients by shift, service, or team." bundles/phc/phc.view.station-queue.md already declares scope: today (the shift) and group_by: station (the service, the team). We have the feature. Glass hand-picks because it has no line, so membership there is TYPED and goes stale silently: the patient is discharged, the row stays, nobody is told. Ours is derived at read time (kernel/views.py:135 stamps generated_at per request), so it cannot go stale. The dropzone is a workaround for the absence of a queue.

WHY NOT A SIXTH DECLARATION TYPE: each costs a required manifest entry, a _lint_* in kernel/declarations.py, a dataclass in kernel/contracts.py, a compile_json key, a struct in care_phc_mcp/catalogue.go and a type in web/src/types.ts. And one thing kills it outright: a hand-picked list is authored at 9am by a nurse, and a declaration is a linted markdown file in the repo.

WHY NOT A NEW VIEW KIND: web/src/ViewRenderer.tsx:57 is a live "No renderer for a <kind> view" fallback. A new kind is a VIEW_KINDS entry, a resolve() branch, a _kind() in kernel/views.py, a renderer branch and a new rows shape. A list of patients carrying badges renders as rows carrying badges. That is a queue.

SHIPS NOW — TWO DECLARATIONS.

1. THE WARD ROUND. Free today, zero code: scope: open is already in VIEW_SCOPES and already implemented (adapters/local/store.py:270, status != 'completed').

---
id: phc.view.round
type: view
kind: queue
title: Round
summary: Everyone still on the line, wherever they are standing.
capability: patient.find
workflow: phc.wf.outpatient
scope: open
group_by: station
target_minutes: 30
columns: [name, age, sex, village, token]
badges:
  vitals.flagged: crit
  lab.critical: crit
  abha.pending: warn
---

2. THE SUB-CENTRE ROUND. The one thing that needs a change, and it is three lines. Catchment is patient.village, a column that already exists (adapters/local/store.py:52) and already reaches the view (store.threads() builds subject from the full patient row, :282). Deliberately NO group_by: an ASHA's round is not a line, and leaving group_by off is what makes the per-row station chip (see badges) carry real information instead of repeating a heading.

---
id: phc.view.kadapur-round
type: view
kind: queue
title: Kadapur
summary: Open visits from one sub-centre area.
capability: visit.household
workflow: phc.wf.outpatient
scope: open
where: {village: Kadapur}
columns: [name, age, sex, village]
badges:
  vitals.flagged: crit
---

THE WHOLE DIFF: where: dict = field(default_factory=dict) on View (kernel/contracts.py, additive to a frozen dataclass whose rule is add-never-rename), and in _queue (kernel/views.py:63) filter the REF, not the row — row.subject is already narrowed to view.columns at :47, so filtering there would forbid filtering on a field you do not display:

  for ref in store.threads(workflow=view.workflow, scope=view.scope):
      if any(ref.subject.get(k) != v for k, v in (view.where or {}).items()):
          continue

Equality only. The Query grammar has gte/lt, but where: here reads a plain dict, not a table; it covers village, sex, category, and widens the day a date filter is actually needed. No Store change, no protocol change, no new kind, no renderer change — the API still returns kind: queue and QueueRow.

ONE LINT RULE THAT EARNS ITSELF, beside the group_by check at kernel/declarations.py:197-199: a queue whose where names a key absent from columns fails the build. columns is itself unlinted (field names are adapter knowledge, no closed vocabulary), so where is exactly as closeable as columns — but the failure modes differ. A typo'd columns key renders a blank cell; a typo'd where key renders an EMPTY QUEUE, which reads as "nobody is waiting". It is also the right UI: a list filtered by village shows village.

OWNERSHIP: SHARED, ADDRESSED BY CAPABILITY, NEVER OWNED BY A PERSON. View.capability is checked server-side at the route (api/main.py:282 get_view). phc.view.round declares patient.find, which all nine roles hold. phc.view.kadapur-round declares visit.household, so it is visible to asha, anm and cho and to nobody else — from one line of YAML, enforced at the route, not hidden in the renderer.

THE RULE, WRITTEN DOWN NOW SO A LATER MIGRATION CANNOT SMUGGLE IT BACK: membership rows carry no owner column; the declaration carries a capability. An owner column is precisely the thing that strands a list at 5pm, and it will look harmless in the diff that adds it.

AT HANDOVER: NOTHING HAPPENS, AND THE QUESTION DISSOLVES. handover is a capability in bundles/phc/bundle.yaml:85 held by six of nine roles, and there is no operation for it, deliberately: web/RESTORATION.md:574 says the station is derived from records, not moved by a person — "Do not fake a move." kernel/state.py:84 station() walks the steps and returns the first whose done_when flag is absent. The nurse records vitals, vitals.recorded becomes true, the thread IS at the doctor. Nobody handed anything to anybody. A list with an owner would be the only object in the product needing custody transferred, and we would have to build the transfer mechanism we deliberately do not have — for a bookmark.

AT SHIFT END: NOTHING HAPPENS, BECAUSE SHE DID NOT BUILD IT, SHE OPENED IT. Membership is recomputed on every request. The next nurse holds vitals.record, opens the same declaration, sees the line as it now is. Glass's hand-picked list would still be holding the 4pm patients at 8pm with no way to tell which rows are stale — the exact failure the queue exists to prevent, reintroduced through a side door. Stated plainly for a PHC: a per-user hand-picked list is a second, unaudited patient register drifting from the queue, and the one that is wrong will be the one that is not on the wall.

THE ONE REAL COST, ACCEPTED NOT HIDDEN: a shared list cannot be a private worklist, and somebody will want "my patients". "Mine" in a PHC is a station, not a person, and that worklist already exists as phc.view.today-tasks narrowed by the caller's capabilities (kernel/state.actions() passes caps to guard.visible(), and an action the caller cannot perform is ABSENT). If somebody genuinely means "the four I am personally carrying", that is separation of duties (actor of / not actor of, already in the precondition grammar and already used by catalogue/ops/lab.op.result-verify.md), not a list.

DEFERRED, WITH THE TRIGGER NAMED: a genuinely hand-picked list. Its cost is not a table — adding a patient to a list is A WRITE ABOUT A PATIENT, so it arrives as an operation with a capability, preconditions, an irreversibility, audit-before-execute and a proposal path on the MCP surface: the whole 7-step guard, bought for a bookmark. Trigger: the first real grouping a PHC user cannot state as a filter over station, flag, village or scope.

ALSO DEFERRED, AND I WILL NOT FAKE IT: the follow-up cohort. followup.booked is exists: {resource: token_booking, where: {status: booked}} and nothing anywhere ever writes a different status, so the flag never clears. The cohort question is date-relative ("booked to come back and has not"), which neither the state-rule grammar nor an equality filter can ask. Do not ship a row that only grows.

## The patient spine

TWO SCREENS. THE ENCOUNTER SCREEN IS THE COLLATION; THE PATIENT SCREEN IS THE INDEX. A spine carries no organs.

ENCOUNTER (unchanged). bundles/phc/phc.view.visit-summary.md already declares nine sections: four ABDM health-information types (Notes/OPConsultation, Prescription, Results/DiagnosticReport, Vitals/WellnessRecord), one order (Investigations/service_request), and four kernel structures the renderer draws identically for every bundle (line, flags, proposals, actions, audit). That view stays exactly as it is.

PATIENT (#/patients/:id) HOLDS FOUR THINGS AND NOTHING ELSE:
1. DURABLE IDENTITY — name, age, sex, village, phone, abha_number. The patient row, not the encounter. These are already smuggled onto the thread panel as subject (api/main.py:143-153 does subject.update(patient[0]); adapters/care/store.py:384-390 does the same deliberately), so every open thread already carries subject.id = the patient id. The page is reachable with ZERO backend change beyond the search route.
2. THE VISIT INDEX — N dated rows, newest first, each opening phc.view.visit-summary for THAT encounter. That is the nesting, rendered where it has room.
3. "42 visits", ONCE, in the header, right-aligned, Inter 34px/800 tabular-nums #141815 with the label beneath at 11px/600 #8A928A. Never mid-sentence, never as a suffix on a disclosure control.
4. Nothing else.

WHAT MUST NOT BE ON IT, EACH WITH ITS CODE REASON:
- NO FLAGS. flags(store, thread, workflow) (kernel/state.py:48) takes a thread. A patient-level flag strip has to pick an encounter, and picking the latest silently is how March's vitals.flagged renders as today's alarm.
- NO ACTIONS. actions() needs known flags, which need a thread. The block would be empty on every patient and drawn as an empty state.
- NO AUDIT, NO PROPOSALS. Making either patient-scoped IS the consent leak.
- NO CONSENT CHIP. capture.agreed/declined/withdrawn are STORED THREAD flags (bundles/phc/bundle.yaml:52-55) and phc.wf.outpatient states in prose that consent is scoped to the visit. A patient-level consent chip creates the leak the workflow promises does not exist.
- NO TREND, NO "every HbA1c". That is the deferred Option A store widening.

NO WRITES AT ALL, AND THIS IS STRUCTURAL RATHER THAN POLICY. Store.write(self, resource, record, *, thread) (kernel/contracts.py:397) has no non-thread signature. A page with no thread has no write path: there is nothing to gate because there is nothing to call. ABHA linking is the one identity-shaped write and it STAYS on the thread, where phc.op.abha-link's precondition registered can actually be evaluated. Say this out loud, because it is why the patient page is a day's work and not a fortnight's: IT NEEDS NO GUARD SURFACE.

IT IS A ROUTE, NOT A VIEW. resolve() raises ValueError(f"{view_id} is a summary and needs ?thread=") (kernel/views.py:141-143) and every _summary branch either calls store.select(..., thread=thread) or reads a kernel structure needing a thread. Keeping it a route also keeps ViewRenderer.tsx:57's live "No renderer for a <kind> view" fallback unreachable.

THE RULE AT 40 ENCOUNTERS — and it starts with a bug in the approved spec.

1. THE SPEC'S OWN PATIENT-HISTORY READ TRUNCATES BACKWARDS. Spec line 42 proposes store.select("encounter", thread=None, where={"patient": pid}, fields=[...], limit=50). SqliteStore.select ends ORDER BY created_date, id LIMIT ? — ASCENDING (adapters/local/store.py:259). At 51 visits the patient page silently shows the OLDEST 50 and DROPS LAST WEEK'S VISIT. A chronic patient's page would show 2019-2023 and hide the visit the clinician is asking about. Note the asymmetry that sets the trap: threads() orders created_date DESC (:275) while select() orders ascending, so one file answers two reads in opposite directions and the patient page uses the wrong one.
   FIX, laziest that holds: sort in the route, not in the store.
     rows = sorted(store.select("encounter", thread=None, where={"patient": pid},
                                fields=["id","token","status","created_date"], limit=500),
                   key=lambda r: r["created_date"], reverse=True)
     # ponytail: 500-row in-process ceiling and a route-side sort, the same ceiling
     # the patient search already accepts. Add order= to select() the day a facility
     # has a patient past 500 visits, not before.
   Adding order= to select() is two adapters, one of which (adapters/care) has never run against an authenticated CARE, for a screen that shows ten rows.

2. ONE READ FOR THE LIST, ZERO PER ROW. The index row renders from the encounter row ALONE: date, token, status. No station, no flag strip. flags(store, thread, wf) per row costs roughly fifteen store.count queries (phc.wf.outpatient declares eighteen states, most exists over a count); at 40 visits that is ~600 queries on thread-local sqlite connections to draw a list.

3. THE HEADER STATES THE TOTAL ONCE; THE BODY SHOWS THE TEN MOST RECENT, NEWEST FIRST; ONE CONTROL REVEALS THE REST; NOTHING IS EVER TRUNCATED SILENTLY. "42 visits" right-aligned in the header, ten rows, then "Show all". The number appears exactly once on the screen and never on the control. Glass's "Show 1 more encounter" puts a computed count on a disclosure control, is wrong the moment a visit opens, and makes the reader do arithmetic to learn the total.
   WHY TEN: an OPD follow-up conversation reaches back about three months, which at a PHC re-visit rate is under ten visits. It is a placeholder for whoever owns this facility's number, exactly as target_minutes: 30 in phc.view.station-queue.md is already commented to be. It lives as a constant in the route with that comment attached, NOT as a config system — the patient page is a route and has nowhere to declare a field.

4. THE QUEUE DOES NOT BREAK AT 40, and it is worth saying so nobody re-derives it. scope: today means today's encounters, not this patient's. A 40-visit patient contributes at most one row to the line. The spec's breakage #3 (the queue floods) is a consequence of making the patient the thread, which we explicitly do not do.

5. THE MERGE HAZARD, because the 40-encounter patient is exactly the one someone will want to merge duplicates into. roll_seed_forward's patient branch (adapters/local/store.py:186-187) is id IN (SELECT patient FROM encounter WHERE id IN (seed threads)) and runs on EVERY constructor call. Merge a seeded demo patient into a real one and that real patient's created_date walks forward with the demo day every time any process opens the file. The AND created_by = 'seed' clause must land BEFORE a merge tool exists, not alongside it.

6. A THREAD WHOSE patient COLUMN IS NULL SHOWS NO PATIENT LINK AT ALL. Not an error, not a named empty state. bundles/phc/seed.yaml ships enc-001 deliberately unregistered, open_thread writes no patient by design (adapters/local/store.py:380-392), and store.threads() already guards it with if row["patient"]: at :280.

THE THREE BACKEND CHANGES, all from the approved spec, all additive: GET /api/v1/phc/patients?q= requiring patient.find; one OPTIONAL patient_id question on questionnaires/phc.schema.register-v1.json plus one mapping line id: {answer: patient_id} on catalogue/ops/phc.op.patient-register.md; and the two-line adapter fix if not sets: return rid before adapters/local/store.py:367's UPDATE, which today produces UPDATE patient SET  WHERE id = ? for an update carrying only an id.

## Chat-first, under the guard

CHAT TAKES THE PRECEDENCE OF PLACE, NEVER OF AUTHORITY. On a thread it is already the whole screen (web/src/Thread.tsx) and that is correct and stays. What must never move is the confirm.

WHAT CHAT MAY DO, each traced:
1. NARRATE DECLARED STATE. api/main.py:409 khoj() calls panel(thread, user) and hands it to turn.take as view, so the agent sees exactly the ThreadView the person sees — subject, flags, station, line, pending proposals, audit, and actions already narrowed by capability + precondition + actor + drawn_by (kernel/state.py actions()).
2. FILL A PAYLOAD AND PUT IT IN FRONT OF A PERSON AS A PROPOSAL CARD. kernel/proposals.propose() has no confirmed parameter and defaults surface=guard.MCP; catalogue/guard.py evaluate() returns outcome "proposed" for (MCP, write). That is the ceiling.
3. QUOTE A REFUSAL IN THE GUARD'S OWN WORDS, unedited, plus a next step keyed on precondition_kind() — machine-stable, never on the clerk sentence.
4. OPEN A READ: a declared view, a form. No write.

WHAT IT MAY NOT DO:
1. COMMIT. kernel/proposals.commit() hard-codes guard.RENDERED and takes no surface argument, "because a surface argument is a hole". khoj() is given only propose_one (api/main.py:396).
2. PROPOSE AN IRREVERSIBLE OPERATION AT ALL. Guard step 4 denies on surface BEFORE it reads confirmed, so phc.op.abha-link and lab.op.report-release cannot even become cards. Nobody talks a national health account into existence. This is stronger than "a human confirms" and it is already true — put it in the product copy.
3. LAUNDER SEPARATION OF DUTIES. guard.person() strips the agent: prefix, so the agent acting for Rao IS Rao for every actor of precondition.
4. PROPOSE AN OPERATION THE WORKFLOW DOES NOT DRAW. kernel/proposals._decide checks drawn_by() before the guard runs (kernel/state.py:120-132; phc.op.household-visit is the atom that taught this).
5. HOLD CLINICAL CONTENT. Utterances live in localStorage only (main.tsx:73 SAID). A doctor typing a finding into the composer and assuming it is in the note is the worst failure available on this screen.

WHERE THE CONFIRM LIVES: exactly one place, the rendered proposal bubble inside the thread. Thread.tsx does not build it — the shell passes renderProposal, which mounts OperationPanel inline. Tapping it runs proposals.confirm(), a SECOND full guard pass on guard.RENDERED against the payload AS EDITED and thread state AS IT IS NOW, so a proposal made when a precondition held is denied at confirm if it has since gone. The composer never gets an OK button, and no chip anywhere may be a commit.
NOTE, and fix it in this work: the div that wraps that confirm — Thread.tsx:192 className="inlinepanel" — HAS NO CSS RULE IN ANY STYLESHEET. The single most important container in the product is unstyled and the gate is green.

SCOPE, PER SCREEN.

ON A THREAD: subject = the thread id, full stop. main.tsx:493 passes onSay={(t) => say(route.id, t, route.id)}. Three lines under the composer, all from data already loaded:
  WHO — the subject named from the queue view's own declared columns (messages.header already does this; Thread.tsx's "Ask about {name}" placeholder is the start of it).
  WHAT IS OPEN TO YOU HERE — the titles from thread.actions, i.e. agent/turn.py waiting_for()'s sentence, shown AT REST rather than only after a reply. An action absent from that list is one the agent cannot propose and the guard would refuse.
  WHAT IT CANNOT KEEP — "Nothing typed here is recorded. A card you confirm is."

ON A PATIENT: NO COMPOSER IN V1. propose() takes a thread, so a patient-scoped chat could not write anyway; capture.* are thread flags, so anything patient-scoped over proposals or audit IS the consent leak; and an adapter that returns nothing renders as "this patient has no past visits", indistinguishable on screen from the truth. If a composer ever appears there its subject line reads "this visit list" and every clinical question routes by opening the encounter.

ON HOME: subject = the declared views this role may open, and nothing else. This is already what the code does — Workspace receives loaded (one read per nav view, 403s filtered), answerFor() matches on each view's own title and id words, and ask.ts returns "Open a thread first." for anything else. Stop treating that last line as a fallback and state it as the rule: THE HOME CHAT IS READ-ONLY BECAUSE IT HAS NO THREAD, AND THE WRITE PATH REQUIRES ONE. One line above the box: "Reading: Lines, Needs you, Facility dashboard" — the titles of the views actually loaded, so the laboratory's line reads the laboratory's words with no change here.

DO NOT BUILD "ADD CONTEXT". Glass needs it because it has no queue; our subject is the route and there is nothing to attach. A chat that can attach a second thread is a chat that can propose against a thread the screen is not showing, and every precondition in the guard is per thread.

WHICH PERSONAS GET IT — DERIVED FROM COMPOSITION, NOT HAND-DECIDED. The renderer rule is ONE CONDITION: the composer renders iff agent.ask is in facility.user.capabilities, read from the same object main.tsx:107 already passes to navViews(cat.data, fac.data?.user?.capabilities). The chip row renders iff at least one instrumented action survives the subtraction. NO if (role === "frontdesk") anywhere — that would leak a persona name into web/src and break the laboratory.
Presets (the personas ARE the presets): frontdesk none of the three; nurse capture.voice; lab/pharmacist none; mo and cho capture.scribe + agent.ask.

DOCTOR: yes, and it already is. 3-8 minutes, the consultation is language, phc.inst.consult-scribe drafts two operations, Thread.tsx is a conversation.
NURSE: voice is not chat. phc.inst.vitals-voice is grammar: number over [systolic, diastolic, pulse, spo2, weight, temperature], and its atom explains why: "'One fourteen' misheard for 'one forty' is silent and plausible." She gets the form with a mic per field, which mountsFor already builds. A centred open prompt invites a sentence; her declared instrument is one number into one named field.
PHARMACIST / LAB: match and confirm. lab.op.result-verify carries not actor of lab.op.result-enter. A verifier's job is to READ; a prompt box invites them to generate. Their landing surface is the tasklist, which already exists and is already cross-thread.
FRONT DESK: HARMFUL, AND THE REPO ALREADY SAYS SO. web/src/loops.check.ts:105 asserts register.instrument === "form" with the comment "which is why front desk sees no AI". Khoj.tsx is keyboard-first by construction (autofocused input, ArrowUp/Down, Enter, Escape, create only at the bottom of an EMPTY result); search.ts rows() is pure string matching over queue reads already done, with no model in the path at all. A centred prompt box replaces a deterministic keystroke path with one where the same ten digits can produce a different screen twice — at a counter, 40-80 times a day, with a queue behind them. And it inverts the rule the spine spec is built on: a box that answers "Sunita Devi" with "shall I register Sunita Devi?" makes CREATE the default and SEARCH the exception, which is exactly how you manufacture duplicate patients and duplicate ABHAs.
The clerk gets Khoj unchanged — a search field, not a prompt — plus patient rows in the results so picking one attaches instead of duplicating. Note that today the clerk already gets no centred prompt box. THE WORK IS TO NOT ADD ONE, AND TO MAKE THE ABSENCE ENFORCED RATHER THAN MERELY CURRENT: POST /khoj checks no capability whatsoever today, and gains agent.ask.

THE DIFFERENCE FROM GLASS, STATED: Glass's chat drafts into a note a human carries elsewhere — a drafting pane beside the record. Ours has no elsewhere: messages.ts composes the audit trail and the committed rows INTO the message list, so the chat IS the record's presentation, not a scratchpad next to it. That is why chat-first is cheap for us on a thread and expensive on home.

## The chip row

SOURCED FROM THE INSTRUMENT DECLARATIONS, CROSSED WITH THE THREAD'S OWN ACTION LIST. Not from operations alone, and not from views.

  chips = thread.actions.filter(op =>
            mountsFor(cat.instruments, op, questionnaire(op.input))
              .some(m => m.kind !== "spoken-prompt"))

WHY THIS SHAPE: Glass's row is four "Draft <document>" plus one "Ask a question". A Draft chip promises that one tap or one sentence produces a payload — that is precisely what an Instrument is. An operation with no instrument cannot honour that promise; it can only open a form, and it is already in the action list.

REUSE, WRITE NO NEW RESOLVER. web/src/voice/instruments.ts:50 mountsFor() already exists and is already the double gate (commit must be "tap", readback "required", grammar must be implemented — lines 60-62). OperationPanel.tsx:178 uses it for the same question.

THE TRAP THAT MATTERS: DO NOT source this from the operation atom's instrument: field. catalogue/ops/phc.op.rx-prescribe.md declares instrument: form and yet phc.inst.consult-scribe lists phc.op.rx-prescribe in its operations:. Same for lab.op.result-enter (instrument: form) and lab.inst.analyser. The atom field is the DEFAULT; the Instrument declaration is the ACCELERATOR. Read the wrong one and the doctor loses the prescription chip while the front desk gains nothing.

ORDERING IS ALREADY SOLVED. kernel/state.py actions() sorts current station first, then declared step order, then the step's own operation order — never alphabetically, and its docstring explains what alphabetical cost last time (capture-withdraw sorted ahead of consult-document at every consented visit). Take the list as given.

CONSENT: the chip is the OPERATION, not the microphone. Tapping it opens OperationPanel, which decides whether the mic mounts (flags.includes(CONSENT), messages.ts:248 — the one flag name deliberately allowed in web/src, as a product rule). One gate in one place; do not add a second in the chip row.

THE FIFTH CHIP, "Ask a question", IS THE COMPOSER ITSELF and it is also declared: it renders iff agent.ask is in facility.user.capabilities. Even the free-text chip is capability-derived, not hard-coded.

SHOWN WORKING FOR BOTH BUNDLES, computed against the real declarations:

PHC (bundles/phc)
- mo at station doctor. Step operations: [consult-document, rx-prescribe, lab-order, capture-withdraw]. Only phc.inst.consult-scribe names any of them, and after this plan's handover atom it names three -> THREE CHIPS: "Consult", "Rx", "Hand over". lab-order and capture-withdraw stay in the action list with no chip, which is right: nobody dictates an order form.
- nurse at station nurse. phc.inst.vitals-voice AND phc.inst.vitals-device both name phc.op.vitals-record -> ONE CHIP, two instruments behind it inside the panel.
- frontdesk at station reception. phc.op.patient-register's only instrument is phc.inst.consent-speak, kind spoken-prompt (the agent speaking TO the patient inside the form, not a draft affordance) -> ZERO CHIPS. With agent.ask withheld: zero chips and no composer.

LAB (bundles/lab)
- technologist at station processing. lab.inst.analyser names lab.op.result-enter -> ONE CHIP.
- phlebotomist (accession, phlebotomy). No instrument declaration names lab.op.referral-accession or lab.op.specimen-collect -> ZERO CHIPS.
- pathologist (verification, release). No instrument names lab.op.result-verify or lab.op.report-release -> ZERO CHIPS.

3 / 1 / 0 / 1 / 0 / 0, from the same code, with no bundle word anywhere in web/src. Glass shows the same five chips on home and on an encounter because its list is hard-coded.

ZERO MUST RENDER AS NO ROW, never an empty row with a placeholder. That is a separate assertion from the count, because "render an empty row" is the lazy regression.

ON HOME the chips are a DIFFERENT SET and already exist: main.tsx:779 Workspace's .cbar maps loaded (the views this role may open, already 403-filtered) to "Show <title>". That is the correct home row — what it can SEE, because home has no thread and can therefore propose nothing. Same pattern, different source, falling out of scope rather than from a list.

GLASS'S FOUR DRAFTS (HPI, A&P, DDx, Clinic Note) are four document types inside one note. We have no document types; we have operations with questionnaires. Anyone wanting "Draft HPI" separately from "Draft Clinic Note" is asking for a second operation or a second questionnaire. That is a declaration to write, not a chip to add.

VISUAL: chips 28px high, radius 8, 1px #E4E7E3, label Inter 12px/600 #141815, 10px horizontal gap, hover border #215FFF and label #215FFF. Row wraps, never scrolls horizontally. Sits directly above the composer on a thread, matching Glass's placement — that part of Glass is right and costs nothing.

## Per-section Generate, and Handoff

THREE OF GLASS'S FOUR SECTIONS ARE NOT ONE FEATURE, AND SPLITTING THEM IS WHAT KILLS MOST OF THE WORK.

NOT AN INSTRUMENT KIND. catalogue/vocab.py:70 INSTRUMENTS is closed with the comment "the renderer implements these and no more, so a bundle cannot invent a fifth without renderer code" — a new kind costs a mount branch in web/src/voice/instruments.ts, a lint branch in kernel/declarations.py and a contracts constant. Worse, it does not fit: kernel/contracts.py Instrument is "an accelerator on top of an operation's default form... never changes what is valid, only how a value arrives", bound by operations: and producing a Draft of link_id -> value. Timeline, Summary and Insights are READS. They have no questionnaire, no payload and no validator for an instrument to arrive into.

NOT A VIEW AFFORDANCE, because for three of the four there is nothing to generate:
- TIMELINE is show: audit, already a declared section of phc.view.visit-summary, evaluated on every read by kernel/views._summary. Glass's "No activity yet" is our audit trail with zero rows. A Generate button over it is a button that says "do the thing this page already did". SKIP.
- SUMMARY is the summary view itself. Same argument. SKIP.
- INSIGHTS has no declared referent at all. Rung 1 of the ladder: skip it. If it is only prose it belongs in the agent's bubble, where prose already lives and is honestly not part of the record; if it must persist it has to land through an operation with a questionnaire, i.e. a proposal like every other. SKIP.

HANDOFF IS THE REAL ONE, AND IT IS AN OPERATION-SHAPED HOLE WE ALREADY DOCUMENTED. handover is a capability in bundles/phc/bundle.yaml:85, held by six of nine roles, with NO operation atom — web/RESTORATION.md:153 and :574 say so in as many words. Glass putting a Generate on Handoff is the signal: a handoff note is a PRODUCED artefact, not a derived one. It is the one section of the four whose output is a record another person reads.

BUT NOTE WHAT WE ALREADY HAVE THAT GLASS DOES NOT, so the note is the only missing half: the queue row IS the handoff (name, derived station, declared badges, wait tone), and phc.view.visit-summary already carries a "What you can do / show: actions" section listing exactly what the next person may do. Glass needs a generated handoff paragraph because it has no line to read.

THE BUILD — ONE ATOM, ONE SCHEMA, ONE LINE IN AN EXISTING INSTRUMENT. Zero renderer code, zero kernel code.

catalogue/ops/phc.op.handover.md
---
id: phc.op.handover
type: operation
kind: write
short: Hand over
title: Hand over this visit
summary: What the next person needs to know that no record carries.
capability: handover
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - registered
irreversibility: correctable
input: phc.schema.handover-v1
writes: [notes]
emits: []
mapping:
  records:
    - resource: notes
      fields:
        created_by: {actor: id}
        category: {const: handover}
        text: {answer: what_the_next_person_needs}
---

Then one line in bundles/phc/phc.wf.outpatient.md's doctor step: operations: [..., phc.op.handover], and one line in phc.inst.consult-scribe's operations: so the scribe drafts it. THAT IS GLASS'S "GENERATE" — with readback: required, commit: tap and an audit line, which Glass does not have. The button then appears in three places at once because all three read the same declaration: kernel/state.actions() puts it in the thread's action list, phc.view.visit-summary's existing "What you can do" section draws it inside the summary exactly where Glass draws Generate, and care_phc_mcp exposes it as propose_* only.

WHY ONE STATION AND NOT FIVE, STATED RATHER THAN GLOSSED. kernel/declarations.py:162 refuses an operation drawn at a step whose station it does not declare: "'{oid}' is drawn at {station} but declares station {...}". So one atom is bound to one station. Widening station: to a list costs SIX verified sites — declarations.py:162, declarations.py:397, kernel/state.py:216 (the actions sort key does op["station"] != here and order.get(op["station"], 99), both scalar), catalogue/build.py's REQUIRED tuple, web/src/loops.ts:69 mine() (op.station === station), and care_phc_mcp/catalogue.go:35 (Station string). Five near-identical atoms is 200 lines of duplicated YAML and five audit identities for one act. So: ONE atom at doctor, because the doctor's step is the only one that already draws four operations (so the handover joins an existing overflow rather than creating a second button at a one-button station) and the doctor is the only persona whose declared instrument can draft it. ponytail comment on the atom naming the six sites and the trigger: the first station other than doctor that actually asks.

TWO THINGS THAT FALL OUT AND ARE WORTH SAYING:
- IT DOES NOT BECOME THE LOOP CLOSER. kernel/state.loop_closer picks the operation whose emits contains the step's done_when (consult.documented). phc.op.handover emits nothing, so it cannot displace "Document a consultation" as the end of the doctor's task.
- IT CLAIMS NO MOVE. web/RESTORATION.md:574: "Do not fake a move." Station is derived from records (kernel/state.station over the workflow's states), so a handover operation must either write something a declared state rule reads, or claim nothing. It claims nothing: the station already moves when the previous step's record lands. Handover records what the next station needs to know, and that is all.

SKIPPED: per-section Generate as a generic mechanism, and Insights entirely. Add when a SECOND section turns out to produce a record rather than read one — at which point it is a second operation atom, not a new kind.

## The plugin catalogue

HEIDI LABS IS A PREFERENCE SCREEN. OURS IS A PERMISSION SCREEN. That difference decides everything below.

Heidi's two switches describe generation behaviour ("Heidi learns from your edits... generation may take slightly longer"). A switch that changes what a generator produces has no capability semantics by construction: no subject, no verb, nothing for a server to refuse, and nothing to write an audit line about. Their own IA puts Heidi Labs under "Personal" between Display controls and Notifications, not beside EMR integrations, which is where a real access boundary would live. (Flagged as inference: I have not seen their API.) Ours refuses at guard step 2 because the subtraction happens in caller() (api/main.py:123-133) BEFORE anything reads caps, so /whoami, panel, propose, commit, confirm and the MCP surface all see a caller who simply does not hold rx.prescribe, and the denial names both the capability and the plugin and is written to audit BEFORE execute.

SHIPS NOW — COMPOSITION, steps 1 to 3 of the approved spec, unchanged:
- three capabilities appended to bundles/phc/bundle.yaml's list: capture.voice, capture.scribe, agent.ask. The three things with no off switch today are exactly the three with no capability; give them one, because capability is the only per-caller set that guard.py, visible(), kernel/state.actions, GET /whoami and care_phc_mcp's For() ALL already read.
- a plugins: key beside roles:, with title, capabilities, instruments, always.
- the OFF map, DEFAULT-ON RECORDED NEGATIVELY: a user absent from OFF holds every plugin, so a new plugin ships enabled with no migration. Heidi's two switches are both OFF in the screenshot: their new features ship dark and every user must go find them. Opposite defaults, and ours is right for a shift where the person who configures is not the person who works.
- subtraction ONCE, in caller().
- guard step 2's reason naming both the capability and the plugin.
- POST /khoj gains agent.ask. It checks no capability whatsoever today, and the only reason we can close it is that the off switch IS a capability — a preference flag would have hidden the box and left the endpoint open.
- THE HANDOVER RULE, which is what makes the off switch safe and has no analogue in a preference screen: a plugin owning instruments must not own the capability of the operations those instruments draft for. Turn the scribe off for a doctor and the mic and the chips vanish; encounter.document and rx.prescribe stay; the visit still finishes by typing. Heidi hands nobody to a next station, so their toggle can only cost the person who flipped it.

SHIPS NOW — TWO THINGS THE HEIDI SCREENSHOTS EARN:
1. OFF-FOR-SELF WITHOUT facility.admin. Two lines in the PUT /users/{user}/plugins gate: turning your OWN plugin OFF requires no capability; turning one ON, or touching another user, stays facility.admin. As specced, a doctor cannot mute his own microphone without finding an administrator, which is absurd for a preference-shaped ability. Off-for-self can never widen access, so it is not a security decision and must not be gated like one. This is the one behaviour Heidi Labs has and our spec does not.
2. added: and experimental: as OPTIONAL manifest keys on a plugin entry, one lint line each. Heidi dates every feature ("Added July 2026"), badges the new one and separates experimental from the stable bundle; our specced entry has no lifecycle at all. The PER-ROW CONSEQUENCE LINE needs no prose written, because it is already declared: read the instrument's own fallback: (phc.inst.consult-scribe declares fallback: form, the voice instruments declare fallback: keypad) and render "Without it: the form, typed." That cannot drift from what the renderer draws, which is better than Heidi's hand-written sentence.

THE CHOOSER SCREEN reuses web/src/Roles.tsx wholesale — 150 lines that are already a list of switches per subject read from /facility, with a "reset to preset" control and a save. The plugin chooser is that screen with a different list. One new file is one file too many here.

DO NOT COPY Heidi's rolling "Latest feature bundle" (many features, one switch, auto-updating). That is vendor release management shaped like a user setting; a clinic wants to know what changed, not to opt into a stream.

TEMPLATES — DEFERRED, WITH THE REAL BLOCKER NAMED. A template IS a questionnaire. questionnaires/phc.schema.consult-v1.json is already a SOAP note (history, examination, assessment, diagnosis, plan) — the same artefact as the first row of Heidi's table — and already declares which operation it answers in styling_metadata.phc. Ours is a template with one instance.
The blocker is not the schema. input: on the operation atom is 1:1 and FIVE things key on that binding: Operation.fields is compiled from it, validate(op, payload) validates against it, kernel/mapping.py maps its link_ids to columns and is linted against writes:, the seed lint checks payload keys against its link_ids, and _lint_instrument requires an instrument's fields: to be link_ids on its operations. A second note shape is input: -> inputs: [...] plus ONE new lint rule: every listed questionnaire's link_ids are either mapped or explicitly in mapping.ignored. Without that rule a template ships a question whose answer maps to no column and the value is SILENTLY DROPPED — the exact failure mapping.py was written to make impossible. Trigger: a second note shape actually existing. There is one today.
THE TYPED TABS map onto things we already have: NOTE = a questionnaire whose operation writes notes (phc.op.consult-document, one today). FORM = every other one (register, vitals, abha-link, rx, lab-order, lab-result, dispense, household-visit, handover — nine). DOC = NOT A QUESTIONNAIRE: "Patient Explainer Letter", "Board Meeting Minutes" are OUTPUTS, renderings of what is already stored with nothing being answered. For us that is a kind: summary view over resources (which kernel/views._summary already resolves) plus a print target. Treating it as a template would put an output through the questionnaire validator for no reason.
So the type is real in the declaration and already there — it falls out of kind: and writes:. Nothing to add, and no badge: type in the declaration, placement on screen, no word.
NEVER COPY: Visibility ("Just me"). A per-object ACL is a second permission system running beside the guard, able to disagree with it, and only one of the two writes an audit line. A template's audience is already computed: whoever holds the capability of the operation it answers. NEVER COPY: Browse community — unvetted clinical note shapes, no citation, no lint, arriving outside the build. If shared templates ever ship they ship as atoms through catalogue/build.py.

CALCULATORS — DEFERRED UNTIL AFTER THE SPINE, and specifically after it, because eGFR needs age and sex off the patient record and BMI needs a height question added to the vitals questionnaire, and today a returning patient is a new id. A calculator is worth little against a patient with no history.
When it lands it is AN INSTRUMENT, a sixth INSTRUMENT_KIND. Not a metric (a metric is a facility-wide count or ratio over a window bound to window.start; BMI for this patient now is neither counted nor windowed). Not an operation (kind: read exists in vocab.KINDS and nothing uses it; a read operation would pass the guard and then have nowhere to put its answer — an action that does not act). The propose-never-commit shape is FREE, not something we add: kernel/declarations.py _lint_instrument already REFUSES any instrument whose readback is not "required" and whose commit is not "tap", so a calculator physically cannot auto-write. It produces a contracts.Draft, the renderer shows it in an editable field, a person taps, and the tap goes through guard.evaluate() like every other commit.

    id: phc.inst.egfr
    type: instrument
    kind: calculator                    # sixth INSTRUMENT_KIND
    title: eGFR (CKD-EPI)
    summary: Kidney function from creatinine, age and sex.
    operations: [phc.op.lab-result-enter]
    fields: [egfr]
    inputs:
      creatinine: {question: creatinine}
      age:  {resource: patient, field: age}
      sex:  {resource: patient, field: sex}
    formula: ckd_epi_2021               # names a kernel function; lint fails if it does not resolve
    citation: "Inker LA, et al. N Engl J Med 2021;385:1737-1749"
    capability: capture.calculate
    readback: required
    commit: tap
    fallback: keypad

Cost: three optional fields on a frozen dataclass whose rule is add-never-rename, one INSTRUMENT_KINDS entry, one _lint_instrument branch, one renderer branch. spoken-prompt was added exactly this way. inputs: reuses the Query grammar that state rules, views and metrics already share, so no adapter implements anything new. formula: names a function rather than defining one, because declaring arithmetic in YAML is a small expression language nobody asked for — stated, not hidden, the same honesty the spec applies to the formulary.
CITATION IS FIRST-CLASS AND REQUIRED, four reasons: (1) the number leaves the building — an eGFR decides a metformin dose, becomes an observation and goes into an ABDM FHIR bundle, and body prose is not readable by the MCP surface, the renderer or the audit payload; (2) a citation is a version number for arithmetic — CKD-EPI 2009 and 2021 share a name and disagree, because the 2021 revision removed the race coefficient; (3) presence is lintable, so an unattributable clinical number is a build failure in the same clause that refuses readback != required; (4) it goes in the audit, so "which equation said 43" has an answer six months later.
NOT GLASS'S LIBRARY. Sixteen cards, a search box, Popular and Cardiac groupings — nobody in a three-to-eight minute consult goes shopping for a calculator. Glass needs the page because its calculators write nothing and connect to nothing; ours surface inline at the station whose operation needs them, two or three per operation, drafting into the form that is already open.

RETENTION — the legitimate half of Heidi's Data management, LATER and FACILITY-LEVEL: transcript and audio days, admin-set, audited against the reserved thread "facility", as a ceiling a user may shorten but never lengthen. Ships when scribe audio is actually being stored. Safe per user: whether the scribe keeps the audio after the note is confirmed (default off; nothing is lost, because a Draft is never stored anyway), and per-user UI state. Heidi's "Automatically extract patient details for you to review and add" is already our architecture: it PROPOSES, a human confirms, it never writes.

## Sequencing

TEN COMMITS. THE RULE THAT PREVENTS A VISIBLY-BROKEN MIDDLE: NO COMMIT BOTH DELETES A SURFACE AND ADDS ONE. Every removal lands only after its replacement is already on screen in a previous commit.

THE LESSON FROM THE TWO REGRESSIONS, named so it is fixed and not just regretted: the gate was green because the checks were SNAPSHOTS, not RULES. web/src/layout.check.ts:317 is a literal array of 21 class names — DEAD_CLASSES = [".hgrid", ".att", ".at", ...] — which catches exactly the 21 things someone remembered. Anything deleted afterwards is invisible to it. So commit 0 replaces the snapshot with a rule, and it fails on today's tree.

C0 — THE CENSUS. No user-visible change. Replace DEAD_CLASSES with a bidirectional class census over web/src: every className token in a .tsx/.ts has a rule in some .css, and every class rule in some .css is used by a .tsx/.ts. IT FAILS TODAY, on real defects: 12 className tokens with no rule (including .rail-altkey, rendered on every rail row while Alt is held, and .inlinepanel, the div that wraps the only confirm in the product) and 38 class rules with no call site (including the five .p-tag* rules). Fix those in this commit. From here on, every commit that drops a class is caught by a rule rather than by memory.

C1 — BADGES OUT. Removal only; nothing new appears. Items marked REMOVE / REPLACE-with-existing-behaviour in the badge list: op.instrument, irreversible, the two f-req markers, the refusal pills, 'over {surface}', the workflow eyebrow, the duplicated role in the resume band, the .p-tag CSS, the ui.tsx STYLE map. The census from C0 catches whatever CSS is orphaned by it. Nothing this commit removes is the only route to anything.

C2 — SPINE BACKEND. No UI change. GET /api/v1/phc/patients?q= (requires patient.find, 500-row in-process scan with the ponytail ceiling comment, at most 20 rows returned, a visit count per row); the optional patient_id question on phc.schema.register-v1.json and the one mapping line on phc.op.patient-register; the two-line if not sets: return rid fix at adapters/local/store.py:367; the AND created_by = 'seed' clause on roll_seed_forward's patient branch (:186-187), which must land before any merge tool exists. Every change additive; behaviour with patient_id absent is byte-for-byte today's.

C3 — THE PATIENT PAGE AND THE PATIENTS RAIL ENTRY. Additive. Route #/patients and #/patients/:id, the reverse=True ordering fix, the ten-row rule with its placeholder comment, "N visits" once in the header. Rail gains entry 4. Recents is still there and still works. Khoj's results gain patient rows so picking one attaches.

C4 — RECENTS OUT. Removal only, and its replacement shipped in C3. Shell.tsx:475-556, recentRow, the localStorage key, loops.ts sortOptions/filterOptions/filterRows, Home.tsx's "Recent" plate. ~150 lines. The census catches the CSS.

C5 — COMPOSITION. The three capabilities, plugins: in bundle.yaml, the OFF map, the subtraction in caller(), the guard step 2 reason, the agent.ask gate on POST /khoj, off-for-self in the PUT gate, added:/experimental:. Plus exactly two renderer conditions: the composer renders iff agent.ask is held, the chip row iff an instrumented action survives. THIS COMMIT IS INVISIBLE UNTIL SOMEONE FLIPS A SWITCH, because default-on is recorded negatively: a user with no OFF record holds everything and sees precisely today's screen. That property is what makes it safe to ship mid-stream.

C6 — THE CHIP ROW AND THE COMPOSER FOOTER. Additive. chips from mountsFor over thread.actions; zero chips renders no row. Two lines under the composer: what is open to you here, and "Nothing typed here is recorded. A card you confirm is." One line above the home box: "Reading: <the loaded views' own titles>".

C7 — HANDOVER. catalogue/ops/phc.op.handover.md, questionnaires/phc.schema.handover-v1.json, one line in the doctor step's operations:, one line in phc.inst.consult-scribe's operations:. Additive, zero renderer code, zero kernel code. The doctor's chip count goes 2 -> 3 and the MCP surface gains propose_phc_op_handover and no commit tool.

C8 — PATIENT LISTS. phc.view.round first (zero code at all). Then where: on View, the three-line filter in _queue, the one lint rule, and phc.view.kadapur-round. Each is a nav entry the rail already draws and already keyboard-binds.

C9 — THE PLUGIN CHOOSER SCREEN, on the Roles.tsx pattern, with the per-row consequence line read from each instrument's own fallback:.

THE EKA FUNCTIONAL LUXURY RETHEME IS NOT ONE OF THESE COMMITS AND IS NOT BUNDLED INTO ANY OF THEM. State the conflict honestly: web/src/theme.css:80-95 currently aliases --r-sm/md/lg/xl ALL to 4px, --sh-card and --sh-hover to none, and --eka-blue to var(--hand). Restoring 6/8/12/16, whisper shadows (0 1px 2px rgba(20,24,20,.04), 0 6px 16px rgba(20,24,20,.05)) and #215FFF touches roughly 200 call sites through those aliases. That is exactly the shape of the last two regressions. So it ships LAST, ALONE, behind the C0 census and the existing design.check.ts colour gate, and it edits ONLY the token block at theme.css:60-95 — NO .tsx file is touched in that commit. If a token cannot be restored by editing the :root block alone, it does not get restored in that commit. The rose gradient is spent once per screen and is declared in exactly one rule (the Home "Needs you" plate's leading rule); #215FFF carries the primary verb button, the focus ring, the chip hover and the link, and nothing else.

WHAT IS NOT IN THIS PLAN AT ALL: templates (inputs: widening, one lint rule) — when a second note shape exists. Calculators — after the spine, because eGFR needs age and sex and BMI needs a height question. Facility retention — when scribe audio is actually stored. A Doc output (a summary view with a print or share target) — standalone, and genuinely the one Heidi tab we lack.

## Badges — every one currently rendered

- **`OperationPanel.tsx:244 <Badge>{op.instrument}</Badge> — renders "form" / "scribe" / "device" at the top-right of every operation panel`**
  - REMOVE. This is the owner's badge, literally. Placement already says it: the mic is either on the panel or it is not, and the panel is titled with the operation. Taxonomy naming its own container.

- **`OperationPanel.tsx:245 <Badge style="crit">irreversible</Badge>`**
  - REPLACE with the two-stage confirm that already exists (OperationPanel.tsx:183, stage === 'confirm' with an empty-by-default button). Making someone do it twice states it better than a word. Note the badge is already inert: .b-crit with no [data-act] renders as the plain neutral badge (theme.css:349-357), so today it is grey text reading 'irreversible' beside a title.

- **`Form.tsx:236 <span className="f-req">required</span> on every required question`**
  - REMOVE. The validator refuses the write and OperationPanel.tsx:219 already surfaces 'is required' on the specific field at commit. A marker before you have done anything wrong is a second, weaker copy of a rule the guard enforces. If anything is marked, mark the optional ones.

- **`Form.tsx:266 'required' on the out-of-range override reason`**
  - REMOVE, same reason, and it is doubly redundant: the field only appears at all when a value is outside its declared range.

- **`Form.tsx:252 <span className="badge b-crit" data-act="">Outside range · {flags}</span>`**
  - KEEP, unchanged. The one badge in the product that holds a signal colour, gated on [data-act] from a declared range. This is the exception the colour law was written for, and design.check.ts's colour gate depends on it existing.

- **`ViewRenderer.tsx:262 and Khoj.tsx:217 and Thread.tsx:84/:204 — declared flag badges, from the queue view's own badges: map`**
  - KEEP, unchanged. This IS the mechanism: phc.view.station-queue declares five, the laboratory declares its own, and web/src names none of them. Removing these would remove the feature.

- **`ViewRenderer.tsx:260 <Badge style="blue">{row.station ? human(row.station) : "Complete"}</Badge> on every queue row`**
  - KEEP CONDITIONALLY: render it only when the view has no group_by. Both queues that exist today are group_by: station (phc.view.station-queue, lab.view.worklist), so the chip repeats the group heading on every single row. On phc.view.kadapur-round, which deliberately declares no group_by, it is the only thing that says where the person is standing. One condition: {!result.groups?.length && <Badge…>}.

- **`ViewRenderer.tsx:284 <span className="badge b-mute">{s.rows?.length ?? 0}</span> — a summary section's row count`**
  - KEEP AS A NUMBER, NOT A PILL. Strip the .badge wrapper; render right-aligned, tabular-nums, 12px, #5E665C, per the design system's key-value rule. A count is data, a pill is chrome.

- **`ViewRenderer.tsx:383 <Badge style={…}>{a.outcome}</Badge> — 'allowed' / 'denied' / 'proposed' in the audit section`**
  - KEEP, de-pilled. This is the one place guard vocabulary is legitimately the SUBJECT: the audit row's content is the outcome. Render as a word in the row, not a pill, and leave it neutral — a denial is not a per-shift clinical escalation and the colour law forbids it holding --act.

- **`Thread.tsx:157 <Badge>{m.actor}</Badge> <Badge>refused</Badge> on a refusal card`**
  - REPLACE with the guard's own sentence, which the card already carries in its body. Two grey pills reading 'user:rao' and 'refused' sit above a line that says the same thing in words the clinician can act on.

- **`Thread.tsx:170 <Badge>over {m.surface}</Badge> — renders 'over mcp' / 'over rendered'`**
  - REMOVE. Surface is guard vocabulary, not a clinician's, and the card is already visibly an agent bubble. The surface rule that matters (a machine can only propose) is enforced in kernel/proposals, stated once in the composer footer, and does not need reprinting on each bubble.

- **`Thread.tsx:172 <Badge>superseded</Badge>`**
  - KEEP THE FACT, LOSE THE PILL. It changes what the card does — there is no confirm on a superseded proposal — so it must be on screen. Render as the card's disabled state plus one line: 'A newer card replaced this.'

- **`Thread.tsx:173 and ViewRenderer.tsx:368 <Badge style="warn">awaiting a person</Badge>`**
  - KEEP THE FACT, LOSE THE PILL. In the thread, the confirm button IS the statement — a card with a live confirm is self-evidently awaiting a person. In the summary view (ViewRenderer:368) there is no button, so keep one line of text: 'Waiting for someone to confirm.'

- **`Thread.tsx:370 <span className="badge b-mute">{done ? human(done.label) : "Not started"}</span> — the last completed step, in the 'Where this stands' card header`**
  - KEEP AS TEXT. It is the literal answer to the card's own title; de-badge it to 12px #5E665C right-aligned in the header row.

- **`Thread.tsx:367 <div className="eyebrow">{human(thread.workflow)}</div> — renders 'Outpatient line'`**
  - REMOVE. A workflow name printed over a card titled 'Where this stands', on a screen that only ever shows one workflow. Pure taxonomy in chrome.

- **`Thread.tsx:78 .id-badge — the ABHA number`**
  - KEEP. An identifier the patient owns, not a tag we applied. It is the one thing on that row a person might read aloud.

- **`Shell.tsx rail-role footer — avatar initial plus human(role), e.g. 'F' / 'Frontdesk' / 'Every capability (demo)'`**
  - KEEP, ONCE. It is the identity line of the account switcher, not a label on content: the answer to 'who am I signed in as', and the only way to change role. Keep it here and remove its duplicate below.

- **`Home.tsx:232-238 ResumeBand roleLabel — 'Primary health centre · Mon 15 Sep · Frontdesk'`**
  - REMOVE THE ROLE HALF. The rail footer carries it 200px to the left; this is the second printing of the persona name on the same screen. Band becomes 'Primary health centre · Mon 15 Sep'.

- **`Shell.tsx:656 .rail-badge (collapsed-toggle count), Shell.tsx:470 .ct (nav count), Home.tsx:347 .plate-n (plate row count)`**
  - KEEP, all three. Numbers, not taxonomy. Restyle to tabular-nums, right-aligned, per the design system; the tone attributes on .rail-badge stay because they are the declared wait rule, gated on [data-over]/[data-act].

- **`theme.css:416-424 .p-tag, .p-tag.scribe, .p-tag.form, .p-tag.irr, .p-tag.hand — five rules with a comment reading 'An instrument tag names how a value was captured'`**
  - DELETE THE CSS, 9 lines. No .tsx renders p-tag anywhere in the repo. This is exactly the badge the owner is describing, still sitting in the stylesheet after its call site was removed, and the gate is green.

- **`ui.tsx:29 const STYLE = { warn: 'b-warn', crit: 'b-crit', ok: 'b-ok', mute: 'b-mute', blue: 'b-blue' } and the style prop on Badge`**
  - DELETE THE MAP. Four of the five class names have NO rule in any stylesheet — only .b-crit[data-act] does (theme.css:357). The style prop is already inert for every value but crit, so every badge on every screen already renders identically neutral. Keep Badge as a one-class component plus the single [data-act] exception, and let the census check (see checks) stop this recurring.

- **`OperationPanel.tsx ~292 <span className="v-off">Scribe off</span> with 'No capture consent.'`**
  - KEEP. It is a reason, not a tag — the guard speaking in words about why a control is absent. Removing it would make an absent microphone unexplained, which is the failure the line exists to prevent.


## Checks

- **THE CLASS CENSUS (replaces layout.check.ts's hard-coded DEAD_CLASSES array). Over every .css and every non-.check .tsx/.ts in web/src: every className token has a rule in some stylesheet, and every class rule has at least one call site. Run under node --experimental-strip-types from scripts/check.sh, where the other web checks already run.**
  - Mutation: Delete the .inlinepanel rule from theme.css (or re-add a .p-tag rule with no call site) — the check names the file and the class and fails. NON-VACUITY: it fails on the tree as it stands today with 50 findings, 12 unstyled tokens (.rail-altkey and .inlinepanel among them) and 38 orphan rules (the five .p-tag* among them), all of which currently pass a fully green gate.

- **NO TAXONOMY WORD REACHES A RENDERED STRING (new assertions in design.check.ts, same read-the-source-as-text technique the file already uses). Assert OperationPanel.tsx contains no {op.instrument} and no {op.irreversibility} inside JSX, Thread.tsx contains no {m.surface}, Form.tsx contains no >required< text node, and no .tsx contains the literal string 'frontdesk'.**
  - Mutation: Put <Badge>{op.instrument}</Badge> back at OperationPanel.tsx:244 — fails on the first assertion. Second mutation: add if (role === 'frontdesk') anywhere in web/src — fails on the last, which is also the assertion that keeps the laboratory working.

- **THE PATIENT PAGE ORDERS NEWEST FIRST AND NEVER TRUNCATES SILENTLY. Seed one patient with 60 encounters across 60 days. Assert (a) the route's first row is the NEWEST encounter, (b) the header count reads 60, (c) exactly 10 rows render, (d) a reveal control exists. Then, the non-vacuity half: a patient with 3 encounters renders 3 rows and NO reveal control.**
  - Mutation: Drop reverse=True from the route's sorted(...) — (a) fails with the 2019 visit first. That is precisely the bug sitting in the approved spec today, because SqliteStore.select ends ORDER BY created_date, id ASC (adapters/local/store.py:259) while threads() orders DESC (:275). The 3-encounter half is what stops the check passing against a page that renders nothing.

- **ONE READ FOR THE LIST, ZERO PER ROW. Wrap the store in a counting proxy for the duration of the patient route against the 60-encounter patient; assert total select+count calls <= 2 (identity, list).**
  - Mutation: Add a station chip or a flag strip to each index row, i.e. call kernel.state.flags(store, thread, wf) per row — phc.wf.outpatient declares 18 states, most of them exists over a count, so the counter goes to roughly 900 and the check fails. This is the cheapest thing anyone will be tempted to add to that page.

- **REGISTRATION ATTACHES INSTEAD OF DUPLICATING. Register 'Sunita Devi'; open a second encounter; search; pick the result; register with patient_id in the payload. Assert count('patient', thread=None) is unchanged at 1, the second encounter's patient equals the first's, and the original created_by and created_date survive the UPDATE.**
  - Mutation: Remove the id: {answer: patient_id} mapping line from catalogue/ops/phc.op.patient-register.md — adapters/local/store.py:310's 'id not in record' branch fires, a second patient row is issued, the count goes 1 -> 2 and the check fails. Second mutation: revert the two-line if not sets: return rid fix and register with ONLY a patient_id and no changed field — sqlite raises on UPDATE patient SET  WHERE id = ?.

- **THE OFF SWITCH IS A CAPABILITY, NOT A RENDER-TIME HIDE (bundles/phc/check.py, alongside the capture-consent half already there). With OFF = {'user:rao': {'prescriptions'}}, POST /khoj proposing phc.op.rx-prescribe returns 422 whose body names BOTH the capability rx.prescribe AND the plugin 'prescriptions', and the thread's audit gains a denial row written before any execute.**
  - Mutation: Implement composition as a render-time hide (subtract in the renderer instead of in api/main.py caller()) — propose returns a pending proposal instead of 422 and the audit has NO denial row. This is the mutation the approved spec already names, and it is the one Heidi's screen has no equivalent for, because there is no second surface for their switch to fail on.

- **OFF-FOR-SELF NEVER WIDENS. As rao with no facility.admin: PUT /users/rao/plugins removing 'prescriptions' succeeds; the same call adding it back returns 403; the same call against user:devi returns 403 whichever direction it moves.**
  - Mutation: Invert the subset test in the gate (accept off ⊆ current_off instead of off ⊇ current_off) — the add-back succeeds and the check fails. Without this check the two-line asymmetry is exactly the kind of gate someone simplifies to 'self can edit self'.

- **THE CHIP ROW IS SOURCED FROM INSTRUMENTS AND IS BOTH-BUNDLE. Against compiled catalogue.json for BOTH bundles, with no browser: PHC mo at doctor -> exactly 3 chips, including phc.op.rx-prescribe; PHC nurse at nurse -> exactly 1; PHC frontdesk at reception -> 0 chips AND no row element rendered; LAB technologist at processing -> exactly 1; LAB phlebotomist -> 0.**
  - Mutation: Source the row from the atom's own instrument: field instead of from mountsFor over the instrument declarations — phc.op.rx-prescribe declares instrument: form while phc.inst.consult-scribe lists it in operations:, so the doctor's count drops 3 -> 2 and the check fails. Second mutation: render an empty row when the list is zero-length — the frontdesk 'no row element' assertion fails.

- **NOTHING ON THE COMPOSER PATH CAN COMMIT, AND AN IRREVERSIBLE OPERATION NEVER BECOMES A CARD. Extend api/tests/test_api.py, which already makes confirm and commit explode for the duration of a turn: additionally assert that proposing phc.op.abha-link over /khoj returns no proposal id and a guard reason naming the surface.**
  - Mutation: Move guard step 4's surface test to AFTER it reads `confirmed` — abha-link becomes a pending card on the thread and the check fails. The ordering (surface denied before confirmed is read) is what lets the product copy say 'nobody talks a national health account into existence', so the copy and the check fail together.

- **A VIEW'S where: FILTERS, AND A TYPO IS A BUILD FAILURE RATHER THAN AN EMPTY QUEUE. Assert phc.view.kadapur-round's rows are exactly the open threads whose ref.subject['village'] == 'Kadapur', and that a view declaring where: {villag: Kadapur} (a key absent from columns) fails kernel.declarations with a message naming the key.**
  - Mutation: Remove the where-keys-subset-of-columns lint rule and typo the key — the queue renders zero rows, which on screen reads as 'nobody is waiting', the failure mode the lint exists for. Second mutation: filter row.subject instead of ref.subject in _queue — row.subject is already narrowed to view.columns at kernel/views.py:47, so any where on a field not displayed silently matches nothing.

- **HANDOVER IS DRAWN IN THREE PLACES FROM ONE DECLARATION, AND IS PROPOSE-ONLY ON THE MACHINE SURFACE. Assert phc.op.handover appears in kernel.state.actions() for a role holding `handover` at the doctor's station; appears in phc.view.visit-summary's 'What you can do' section rows; appears in care_phc_mcp's tool list as propose_phc_op_handover; and does NOT appear as any commit tool. Also assert it is not the doctor step's loop_closer.**
  - Mutation: Add a commit tool for it in care_phc_mcp/catalogue.go — the propose-only MCP assertion fails (the laboratory's version of that assertion already exists; commit 99303b8 carved khoj out of it). Second mutation: add consult.documented to the atom's emits: — loop_closer returns phc.op.handover and 'Hand over' silently becomes the end of the consultation.

- **THE RAIL HAS TWO LEVELS AND NO ROW EXPANDS. Assert Shell.tsx contains no 'Recents' string and no 'phc.recents.' key; that no element with className containing 'rail-row' carries aria-expanded; and that the nav list resolves to exactly [Home, ...manifest.views, Patients] for both bundles, with the laboratory's entries reading the laboratory's own titles.**
  - Mutation: Re-add the Recents section — the string assertion fails. Second mutation: add an expander to a rail row so a patient's encounters nest in the sidebar — the aria-expanded assertion fails, which is the rule 'no rail row ever expands' made mechanical. Third mutation: hard-code 'Lines' as a nav label — the both-bundles assertion fails against the laboratory.


## Deliberately NOT built

- Glass's 'Create a patient list' dropzone and hand-picked membership. It is a workaround for the absence of a queue: their membership is typed so it goes stale silently, ours is derived per request (kernel/views.py:135) so it cannot. Do not import a workaround for a problem we do not have.
- A sixth declaration type for lists. Each costs a manifest entry, a _lint_*, a contracts dataclass, a compile_json key, a Go struct and a TS type — and one thing kills it outright: a hand-picked list is authored at 9am by a nurse, and a declaration is a linted markdown file in the repo.
- A new view kind for lists. ViewRenderer.tsx:57 is a live 'No renderer for a <kind> view' fallback. A list of patients carrying badges renders as rows carrying badges. That is a queue.
- An owner column on a list. It would be the only object in the product needing custody transferred, and we deliberately have no transfer mechanism (RESTORATION.md:574, 'Do not fake a move'). It is also precisely what strands a list at 5pm, and it will look harmless in the migration that adds it.
- A hand-picked list of any kind, for now. Adding a patient to a list is A WRITE ABOUT A PATIENT, so it arrives with a capability, preconditions, an irreversibility, audit-before-execute and a proposal path on the MCP surface — the whole 7-step guard, bought for a bookmark. Trigger to revisit: the first grouping a PHC user cannot state as a filter over station, flag, village or scope.
- A follow-up cohort list. followup.booked is exists:{resource: token_booking, where:{status: booked}} and nothing ever writes a different status, so the flag never clears. The question is date-relative and neither the state-rule grammar nor an equality filter can ask it. Do not ship a row that only grows.
- Glass's 'All Patients' nested tree in the rail. Those expanded rows with 'Show 1 more encounter' underneath are a page trying to happen inside a sidebar. RULE: no rail row ever expands.
- Glass's 'All Encounters' flat rail section. Every queue row already IS an encounter — Workflow.subject: encounter, and QueueRow.thread is the encounter id. It is our queue with group_by removed, which is one declaration if anyone ever asks.
- Recents. localStorage per browser, ten items, surviving no handover and no second device — and recentRow() (Shell.tsx:258) FABRICATES station:null, flags:[], badges:{} for any recent not on today's queue read, so it can show a patient with no badge who carries lab.critical.
- 'Add Context' on the composer. Glass needs it because it has no queue; our subject is the route. A chat that can attach a second thread can propose against a thread the screen is not showing, and every precondition in the guard is per thread.
- A centred prompt box on the front desk's home. It replaces a deterministic keystroke path (Cmd-K, type, arrow, Enter, all pure string matching in search.ts with no model in the path) with one where the same ten digits can produce a different screen twice — 40-80 times a day with a queue waiting. And it makes CREATE the default and SEARCH the exception, which is how you manufacture duplicate patients and duplicate ABHAs. loops.check.ts:105 already asserts the opposite.
- A composer on the patient page. propose() takes a thread, so it could not write; capture.* are thread flags, so anything patient-scoped over proposals or audit is the consent leak; and an adapter returning nothing renders as 'this patient has no past visits', indistinguishable on screen from the truth.
- Per-section Generate as a generic mechanism, and Insights entirely. Timeline is show: audit and Summary is the summary view — both already evaluate on every read, so a Generate over them is a button saying 'do the thing this page already did'. Insights has no declared referent at all.
- Glass's encounter screen pattern of five panels each carrying its own ungated Generate, all reading 'No data yet'. Each button is a machine write with no precondition, no capability and no confirm, and five empty panels is the opposite of text-light. Our equivalent of every one of them is a declared view section over resources that either has rows or does not.
- Heidi's 'Automatically delete patients' (30-365 days), and per-user auto-delete of sessions or transcripts. Deleting a patient turns a live ABDM consent artefact into a dangling reference, so a patient's own consent to their own doctor fails silently months later at the other end of the network; it gives the same patient different record lifetimes depending on who saw them; and it cascades toward the audit trail that is the guard's only evidence that any of the other six steps ran. Heidi's own note admits the cascade: 'Sessions linked to a deleted patient will remain in your session list' — that is an orphan, not a policy.
- Audit-trail retention as a setting, at any level, for anyone. It is the guard's only evidence. No switch, no days field, no danger zone.
- 'Automatically include past sessions' as a toggle. The question splits and neither half is a preference: within this facility, reading the patient's own prior encounters is ordinary practice and is the spine, blocked today only because write('patient') is thread-scoped; across facilities it is an ABDM consent artefact with a purpose, a scope and an expiry, and no checkbox stands in for one. The spec already refuses the adjacent version of this leak.
- Deletion offered as the consent-withdrawal path. Withdrawal must stop future capture, not erase what was lawfully recorded — capture.withdrawn is a stored thread flag with an operation behind it, and a 'delete my data' button would quietly replace a guard precondition with a destructive one.
- Heidi's rolling 'Latest feature bundle' switch. Many features, one toggle, auto-updating: that is vendor release management shaped like a user setting. A clinic wants to know what changed.
- Per-object template visibility ('Just me', Creator, share). A second permission system running beside the guard, able to disagree with it, and only one of the two writes an audit line. A template's audience is already computed: whoever holds the capability of the operation it answers.
- 'Browse community' templates. Unvetted clinical note shapes with no citation and no lint arriving outside the build. If shared shapes ever ship, they ship as atoms through catalogue/build.py like everything else.
- Templates as a feature right now. A template is a questionnaire and consult-v1 is already a SOAP note; the cost is that input: is 1:1 and five things key on that binding, so a second shape needs inputs: plus one lint rule that every listed questionnaire's link_ids are mapped or explicitly ignored. Build it when a second note shape exists, not before — today there is one.
- Glass's browsable calculator library: sixteen cards, a search box, Popular and Cardiac groupings. Nobody in a three-to-eight minute consult goes shopping for a calculator. Glass needs the page because its calculators write nothing and connect to nothing; ours draft into the form that is already open.
- Calculators at all before the patient spine lands. eGFR needs age and sex off the patient record and BMI needs a height question added to the vitals questionnaire — and today a returning patient is issued a new id, so there is no record to read.
- Glass's plan-tier badge ('Lite') and corner org switcher. Their gating is by price, ours by role and capability with presets carrying the common case: same switch, opposite reason. A corner org dropdown would also imply tenancy is a view, when our scoping is role x capability x per-user composition.
- A subject= keyword on the Store (Option A). Both read signatures keep exactly one scoping argument until a real screen needs ONE value computed across visits — a trend, a duplicate-therapy check, a patient-scoped metric. An adapter that silently ignores a new keyword returns an empty history, which renders as 'no past visits' and is indistinguishable from the truth.
- An order= parameter on select(). Two adapters, one of which has never run against an authenticated CARE, for a screen that shows ten rows. Sort in the route.
- A persona config screen separate from the plugin chooser. PUT /users/{user}/plugins already is it, and a second per-user mechanism beside capability subtraction is the 'taught to five places that then drift' failure the spec already names.
- A 'chat mode' toggle and a second propose endpoint. /agent/say is already a deprecated alias for /khoj; add a second surface the day one genuinely needs different semantics, which none does.
- A retheme commit that touches both tokens and call sites. theme.css currently aliases all four radii to 4px, both shadows to none and --eka-blue to --hand; restoring 6/8/12/16, whisper shadows and #215FFF through those aliases reaches ~200 sites. Restore the :root block alone, in its own commit, or do not restore that token.