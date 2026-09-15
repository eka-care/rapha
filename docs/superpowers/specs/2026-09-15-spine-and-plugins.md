# The patient spine and per-user plugin composition

Status: approved design, not yet built. Date: 2026-09-15

Produced by a five-agent workflow: four independent investigations (spine data model, composition model, Glass Health IA, migration risk) and one synthesis.

Supersedes the deferred "Phase 2: the patient spine" section of docs/superpowers/specs/2026-09-11-role-weighted-loops-design.md, which assumed the spine needed a widened Store protocol. It does not — see **The store change**.

## The spine

TWO LEVELS. Patient is the durable spine. Encounter stays the thread. Nothing about `Workflow.subject: encounter` (bundles/phc/phc.wf.outpatient.md:6, bundles/lab/lab.wf.specimen.md:6) changes.

WHY A PATIENT CANNOT BE THE THREAD — three breakages, each verifiable in the repo today:

1. EVERY PRECONDITION INVERTS PERMANENTLY. catalogue/ops/phc.op.vitals-record.md declares `preconditions: [registered, not vitals.recorded]`, and kernel/state.py:22 derives flags by `store.count(resource, thread=...)`. Make the thread a patient and `vitals.recorded` is true forever after visit one, so the nurse's action is absent at visit two — and because catalogue/guard.py:136 `visible()` shares `_preconditions_met` with `evaluate()` at :152, the guard would also DENY the correct action, not merely hide it. Fail-safe direction, unusable from visit two.

2. CONSENT LEAKS. `capture.agreed`, `capture.declined`, `capture.withdrawn` are stored thread flags (bundles/phc/bundle.yaml:52-55, written to the `thread_flag` table keyed on `thread`). phc.wf.outpatient states in prose that consent is scoped to the visit and therefore nothing patient-scoped can leak. A patient-level thread makes a declined visit's consent stand over the next visit's capture.

3. THE QUEUE FLOODS. phc.view.station-queue is over `store.threads()` (kernel/views.py:63, adapters/local/store.py:265 `SELECT * FROM encounter`). Threads are encounters. If a patient is a thread, every patient the facility has ever seen joins today's line.

THE SPINE'S ACTUAL PROBLEM IS NOT HOLES, IT IS LENGTH. `encounter.patient` already exists (adapters/local/store.py:57) and is populated on every registered visit. Measured on the live file /Users/samdennis/code/abdm-ai-sandbox-plan/phc.sqlite3: 7 encounters, 6 with a patient, and `SELECT patient, COUNT(*) FROM encounter GROUP BY patient` returns 1 for every patient id. Every edge exists; every tree is depth one. The reason is adapters/local/store.py:311-316: `write("patient", ...)` looks for an existing patient with `self.select("patient", thread=thread, ...)` — scoped to THIS thread — so a returning patient matches nothing and is issued a new id. There is no lookup by phone, ABHA or name anywhere in kernel/, api/ or adapters/local/ (grepped, zero hits).

SO THE SPINE WORK IS IDENTITY, NOT SCOPE. Three changes, all additive:

(a) A patient lookup read. `GET /api/v1/phc/patients?q=` in api/main.py, requiring `patient.find` server-side (the same capability phc.view.station-queue already declares, so every role holds it). Implementation: `store.select("patient", thread=None, where={}, fields=["id","name","age","sex","phone","village","abha_number"], limit=500)` then an in-process case-insensitive substring filter on name / phone / abha_number, returning at most 20 rows, each with a visit count from `store.count("encounter", thread=None, where={"patient": id})`. ponytail: 500-row in-process scan; the query grammar (adapters/local/store.py:217 `_where`) has equality and gte/lt/gt/lte and no LIKE, and adding LIKE widens the grammar for one screen. Upgrade to a store-side match when the register outgrows one page of a facility's patients.

(b) Registration attaches instead of duplicating. Add one OPTIONAL question `patient_id` (type string) to questionnaires/phc.schema.register-v1.json, and one mapping line to catalogue/ops/phc.op.patient-register.md: `id: {answer: patient_id}`. When the clerk picks a search result the payload carries that id; adapters/local/store.py:310 `if resource == "patient" and "id" not in record` is then skipped, `_put` UPDATEs the existing patient row (created_by and created_date are already excluded from the update at :368, so the original registrar and the original registration date survive), and :319-325 attaches `encounter.patient` because the encounter's patient is null. The workflow, the capability, the precondition `not registered` and the emitted flags are untouched; `registered: {exists: {resource: patient}}` (phc.wf.outpatient.md:26) becomes true from the join exactly as it does for a new patient. When the field is absent the behaviour is byte-for-byte today's.

(c) One adapter bug this exposes. adapters/local/store.py:367 computes `sets = [k for k in record if k not in ("id","created_by","created_date")]` and then emits `UPDATE ... SET <sets> WHERE id = ?`. An update carrying only an id produces `UPDATE patient SET  WHERE id = ?`, which is a SQL error. Add `if not sets: return rid` before the UPDATE. Two lines, fixes every caller, not just this one.

ENCOUNTERS WHOSE PATIENT COLUMN IS NULL. They stay null and that is the correct value: an unregistered walk-in has no patient to point at. `SqliteStore.open_thread` (adapters/local/store.py:380-392) writes {id, status, token, created_by} and no patient by design — POST /api/v1/phc/threads is how reception opens a line before anyone is registered, and bundles/phc/seed.yaml:27-30 ships enc-001 deliberately unregistered ("stands at reception with no patient row at all"), as bundles/lab/seed.yaml:15 does for lab-001. `store.threads()` already guards it (`if row["patient"]:`, adapters/local/store.py:280). Consequence for the new screens: a null-patient thread has no patient page and its row offers no link to one. It is not an error state and must not be drawn as one. Note the adapters disagree here and that is recorded, not resolved: `CareStore.open_thread` (adapters/care/store.py:598-620) refuses to open an encounter without a patient because EncounterCreateSpec requires one.

MIGRATION: THERE IS NONE, AND NOTHING IS DESTRUCTIVE. `encounter.patient` is already in the CREATE TABLE (adapters/local/store.py:57) and `CREATE TABLE IF NOT EXISTS` (:126-129) is a no-op on an existing file. No ALTER, no rebuild, no backfill — a null patient is the right value, not a missing one, and the only two readers of the column (`threads()` at :281 and `_where`'s downward join at :224) both tolerate null. Existing single-visit patients are simply trees of depth one; the spine grows forward from the first returning patient who is found by search.

MERGING two patient rows already issued for the same person is a separate, DEFERRED tool: one `UPDATE encounter SET patient = ? WHERE id = ?` per merged encounter, because every clinical row joins to the encounter and never to the patient (THREAD_COLUMN, adapters/local/store.py:89-90), plus keeping the superseded patient row as a tombstone so the merge reverses with one UPDATE back. ONE THING MUST BE FIXED BEFORE A MERGE TOOL EXISTS: `roll_seed_forward` (adapters/local/store.py:132-199) rewrites dates on every constructor call and its patient branch is `id IN (SELECT patient FROM encounter WHERE id IN (seed threads))` (:186-187). Merge a seeded demo patient into a real one and that real patient's created_date walks forward with the demo day every time any process opens the file. Add `AND created_by = 'seed'` (SEED_ACTOR, :95) to that UPDATE. One clause, and it is the only place a spine merge turns destructive.

## The store change

CHOSEN: OPTION D — do not widen the protocol. No `subject=` keyword, no polymorphic `thread=`, no kernel-side fan-out. The Store keeps its ten methods and both read signatures keep exactly one scoping argument.

WHAT THE SPINE READS, USING WHAT IS THERE TODAY:
- A patient's visits: `store.select("encounter", thread=None, where={"patient": pid}, fields=["id","token","status","created_date"], limit=50)`. Verified against the live /Users/samdennis/code/abdm-ai-sandbox-plan/phc.sqlite3. This is the same shape `threads()` already runs at adapters/local/store.py:265.
- A patient's identity: `store.select("patient", thread=None, where={}, ...)` filtered in process (see spine (a)).
- A visit's content: unchanged — `phc.view.visit-summary` per encounter, `thread=` as today.
- The patient id itself needs no new read at all. `ref_or_404` (api/main.py:143-153) already does `subject.update(patient[0])` from `SELECT *`, so every thread panel the renderer receives ALREADY carries `subject.id` = the patient id and `subject.encounter` = the thread. The CARE adapter does the same deliberately (adapters/care/store.py:384-390). The patient page is reachable from any open thread with zero backend change.

JUSTIFICATION AGAINST THE PROTOCOL'S STATED SMALLNESS (kernel/contracts.py:374-386). The docstring's value is the sentence "Every read is scoped to a thread", not the method count. Option A (`count/select` gaining `subject=`) keeps the count at ten and spends the sentence; it also forces every adapter to honour a second scoping mode, and adapters/care has never run against an authenticated CARE — an adapter that ignores the keyword returns an empty history, which renders as "this patient has no past visits" and is indistinguishable on screen from the truth. That is the same wrong-but-plausible failure shape as the dropped CSS token that shipped green on this branch. Option D adds no keyword, so there is nothing for an adapter to ignore.

Be honest about the sentence: it is already softer than it reads. `metric()` passes `thread=None` (kernel/views.py:49-50) and `_tasklist` walks every thread (kernel/views.py:104); measured on the live file, `count("patient", thread=None)` is 6 against `count("patient", thread="enc-002")` = 1. `thread=None` unscoped reads are an existing, used part of the protocol. Option D spends only what is already spent.

WHAT OPTION D COSTS, STATED NOT HIDDEN. A genuinely cross-visit query — "every HbA1c this patient has ever had", "is this drug already active on another visit" — is N client-side thread reads, and there is no `count()` over a patient, so no patient-windowed metric exists. The patient page is therefore a LIST of dated visits, each row opening the existing per-encounter summary, and not a collation.

THE UPGRADE AND ITS TRIGGER, NAMED SO NOBODY RE-ARGUES IT. When a real screen needs one value computed ACROSS visits (a trend, a duplicate-therapy check, a patient-scoped metric), do Option A and nothing else: `count(resource, *, thread=None, subject=None, where)` and `select(...)` the same, exactly two signatures; adapters/local/store.py:217 `_where` gains three branches (`subject` + resource=="patient" -> `id = ?`; + resource=="encounter" -> `patient = ?`; + anything else -> `encounter IN (SELECT id FROM encounter WHERE patient = ?)`), the same downward direction as the join already at :224; adapters/care raises NotImplementedError and never falls back to thread scope. The other eight methods do not move — making `proposals` or `audit` patient-scoped IS the consent leak. Land it with no caller, then the caller, and update the ten-name assertion at adapters/care/tests/test_store.py:492-497 and the docstring in the same commit.

KERNEL CHANGES IN THIS SPEC: none to kernel/state.py and none to kernel/views.py. `kernel/state.py:22` keeps `thread=` — that single call site is the whole flag-derivation surface, and it is what check 6 pins.

## Composition

A PLUGIN IS A NAMED GROUP OF ONE BUNDLE'S OWN WORDS. It is manifest data in bundles/<id>/bundle.yaml beside `roles:`, linted by `catalogue/vocab.py Vocabulary.problems()`. It is NOT a sixth declaration type: each of the five costs a REQUIRED manifest entry, a `_lint_*` in kernel/declarations.py, a dataclass in kernel/contracts.py, a compile_json key, a struct in care_phc_mcp/catalogue.go and a type in web/src/types.ts, and a plugin is a grouping of ids — precisely what `roles:` already is. One new field on `Vocabulary` (`__slots__` at catalogue/vocab.py:88), one new key read in `from_manifest` (:122-126), one new field on `contracts.Manifest` (:285-298, which is additive — that dataclass's rule is add, never rename).

THE MOVE THAT MAKES THE REST FREE: the three things with no off switch today (scribe, voice, the agent) are exactly the three things with no CAPABILITY. Give them one. Capability is the only per-caller set that catalogue/guard.py, `visible()`, `kernel/state.actions`, `GET /whoami` and care_phc_mcp/catalogue.go `For()` all already read; anything expressed as a second set has to be taught to five places that then drift.

bundles/phc/bundle.yaml — three capabilities appended to the existing list (:70-86):
    - capture.voice        # may use a voice instrument
    - capture.scribe       # may use an ambient scribe
    - agent.ask            # may use Khoj

and a new top-level key:
    plugins:
      forms:         {title: Forms, always: true,
                      capabilities: [patient.find, patient.register, abha.link, vitals.record,
                                     assessment.record, encounter.document, appointment.book, handover]}
      prescriptions: {title: Prescriptions, capabilities: [rx.prescribe, pharmacy.dispense]}
      orders:        {title: Laboratory orders, capabilities: [lab.order, lab.result.enter, lab.result.validate]}
      voice:         {title: Voice capture, capabilities: [capture.voice],
                      instruments: [phc.inst.vitals-voice, phc.inst.consent-speak]}
      scribe:        {title: Ambient scribe, capabilities: [capture.scribe],
                      instruments: [phc.inst.consult-scribe]}
      agent:         {title: Khoj, capabilities: [agent.ask]}
      outreach:      {title: Household visits, capabilities: [visit.household]}
`always: true` is the floor a composition may not turn off. A bundle declaring no `plugins:` behaves exactly as it does now, which is what keeps bundles/lab a valid second bundle on day one.

TWO LINT RULES, both in `Vocabulary.problems()` beside the existing role-holds-unknown-capability check (catalogue/vocab.py:110-114):
- a plugin naming a capability the bundle does not declare is a build failure;
- a plugin naming an instrument whose declaration carries no `capability:` is a build failure, because such a plugin is decorative.
And the handover rule, which is the one that is not obvious: A PLUGIN THAT OWNS INSTRUMENTS MUST NOT OWN THE CAPABILITY OF ANY OPERATION THOSE INSTRUMENTS DRAFT FOR. Turning off `scribe` must remove the microphone and leave `encounter.document` and `rx.prescribe` intact, so the doctor types instead of dictating and the visit still finishes. Checkable from the declarations alone (plugin.instruments -> instrument.operations -> operation.capability must not intersect plugin.capabilities).

ONE NEW OPTIONAL FIELD ON THE INSTRUMENT DECLARATION, copying what View already has: `capability:` in bundles/phc/phc.inst.consult-scribe.md and the two voice instruments; `Instrument` gains `capability: Optional[str] = None` (kernel/contracts.py:234-247); `_lint_instrument` (kernel/declarations.py:236) gains the one line `_lint_view` already has — unknown capability fails the build. Absent means ungated means on for everyone, which is what keeps every other bundle's instruments working untouched.

THE SIX PLUGIN TYPES THE OWNER NAMED, STATE BY STATE:
- QUESTIONNAIRES: already declared (questionnaires/*.json, named by an operation's `input:`, compiled into Operation.fields, the one validator every surface shares). Not independently addressable and DELIBERATELY NOT MADE SO: a questionnaire is an operation's schema, bound 1:1, and "turn questionnaires off" can only mean "turn the operation off", which is what a plugin owning that operation's capability already does. No work.
- PERSONAS: today hard-coded across three unrelated places — `roles:` in bundle.yaml, `instrument:` on each operation atom (a facility-wide default), and each instrument's own `operations:` list. The strongest persona statement in the repo is an assertion in a test (web/src/loops.check.ts:105, `register.instrument === "form"`, commented "which is why front desk sees no AI"). A persona is a composition with a name, and a named composition is what a role preset already is, so personas land as three capability names in the presets that exist: frontdesk gets none of capture.voice / capture.scribe / agent.ask; nurse gets capture.voice; mo and cho get capture.scribe and agent.ask. That comment becomes a fact the guard enforces. No new type.
- TEMPLATES: absent, and DEFERRED entirely. The only template in the runtime is the vendor parameter in api/scribe.py (`output_template: [{template_id: ...}]`) — Eka's ids, not the facility's. Composition answers on/off per user and nothing else; the moment it answers "with which template" it is a second config system.
- PRESCRIPTIONS: the ACTION is fully declared (phc.op.rx-prescribe, capability rx.prescribe, questionnaires/phc.schema.rx-v1.json). The CONTENT is not declarable — formulary, dose patterns, the picker live in web/src/structured.ts. The `prescriptions` plugin gates the capability only. Content stays code, and that is stated, not hidden.
- SCRIBE: declared (kind, operations, readback: required, commit: tap, fallback: form, with the ambient-speech rule made unwritable by kernel/declarations.py:239-245). Gains `capability: capture.scribe`. That is the whole hole.
- AGENTIC (Khoj): a manifest constant (`KHOJ` in kernel/contracts.py), deliberately not a declaration type, and the least gated thing in the product — POST /khoj (api/main.py:372) checks NO capability at all today. The `khoj` manifest dict gains `capability: agent.ask`, and the route checks it. Its writes were already guard-checked on guard.MCP so it could never commit; what it lacked was an off switch and a name.

THE USER-LEVEL MAPPING, WHICH IS THE THIN PART. Sparse and NEGATIVE: it records what is OFF, never what is on. A user with no record has every plugin, so a new plugin ships enabled for every existing user with no migration and the table is empty on day one — the owner's "the default can be with all of this inbuilt for now" made structural instead of remembered.

    # api/main.py, beside OVERRIDES (:85)
    PLUGINS = BUNDLE.manifest.plugins
    # ponytail: in-process, one facility per kernel, same ceiling as OVERRIDES.
    # Sparse and negative: a user absent here holds every plugin.
    OFF: dict[str, set[str]] = {}          # actor id -> plugin ids

It does NOT go in the Store: every Store read takes a thread or None-across-threads, and a per-user composition is facility configuration of exactly the same class as OVERRIDES, which is already a module dict with a stated ceiling.

THE ADMIN ROUTE, copy-and-narrow from `set_role` (api/main.py:222-234):
    PUT /api/v1/phc/users/{user}/plugins    body {"off": ["scribe"]}
    - requires facility.admin server-side, the same 403 line as set_role;
    - rejects a plugin id the bundle does not declare, the same 400 as set_role's unknown-capability check;
    - refuses to turn off a plugin declared `always: true` (400);
    - appends an audit line via `store.append_audit` against the reserved thread id "facility", with operation "composition.set", actor = the admin, surface = RENDERED, payload = {user, off}, outcome = "allowed". PUT /roles must start doing this in the same commit: it records nothing today, so "who turned scribe off for Dr Rao, and when" currently has no answer anywhere.
    GET /api/v1/phc/users/{user}/plugins returns {declared: PLUGINS, off: [...], effective_capabilities: [...]}.

THREE LAYERS, PRESENTED AS THREE BECAUSE THEY ARE THREE DECISIONS: preset (bundle.yaml `roles:`, read-only, ships, carries the 70%), facility role override (PUT /roles/{role}, exists, unchanged), user composition (PUT /users/{user}/plugins, new). WHAT SHIPS ON: everything. OFF is empty, every preset keeps every capability it has today plus the new capture.*/agent.ask ones where the persona warrants them, and the demo role is `sorted(vocab.CAPABILITIES)` (api/main.py:75) so the browser account — the only account with no login — is unchanged in every respect.

## The safety rule

THE RULE: A PLUGIN THAT IS OFF IS A CAPABILITY THE CALLER DOES NOT HOLD. It is subtracted once, before anything reads it, so there is no render-time hide to implement and nothing to forget.

WHERE THE SUBTRACTION HAPPENS — one function, api/main.py `caller()` (:123-133), which every surface already passes through (/whoami, /facility, panel, /views, propose, commit, confirm, /khoj, /scribe/*):

    def caller(request: Request) -> dict:
        ...
        caps = OVERRIDES.get(role, ROLES[role])
        off = OFF.get(actor_id, frozenset())              # sparse: absent = all on
        withheld = {c: p for p in off if not PLUGINS[p].get("always")
                    for c in PLUGINS[p].get("capabilities") or []}
        held = [c for c in caps if c not in withheld]
        return {"id": actor_id, "role": role, "capabilities": held,
                "withheld": withheld, "scopes": sorted(held)}

That single subtraction buys, with no further code: `guard.visible()` narrows (the button is ABSENT, not greyed, and it still shares `_preconditions_met` with `evaluate()`); `kernel/state.actions()` narrows because it passes caps to visible(); `GET /whoami` narrows, so care_phc_mcp/main.go:195 builds a smaller tool list and catalogue.go `For()` needs no change at all; `GET /views/{id}` 403s on a view whose declared capability is withheld.

WHERE AN OFF PLUGIN REFUSES: GUARD STEP 2, catalogue/guard.py:181-186, inside the existing capability check. Not a new step, not a new set. Four lines:

    def evaluate(op, *, caps, state, payload, surface, confirmed=False,
                 scopes=None, validate=None, actor=None, performers=None,
                 withheld=None):
        ...
        # 2. capability, then its scope qualifier.
        if op["capability"] not in caps:
            plugin = (withheld or {}).get(op["capability"])
            if plugin:
                return deny("capability %s withheld by plugin '%s': not enabled "
                            "for this user" % (op["capability"], plugin))
            return deny("missing capability %s" % op["capability"])

`withheld` is an optional keyword, so every existing call site and test is unaffected. It threads through kernel/proposals.py `propose` (:106), `commit` (:130), `confirm` (:146) into `_decide` (:65) and on to `guard.evaluate` (:76) — six lines of `withheld=withheld` — and api/main.py passes `user["withheld"]` at each of the three call sites.

WHAT THE AUDIT RECORD SAYS. No schema change: `contracts.AuditRecord` keeps its nine fields and no adapter gains a column. The `outcome` string gains one form, and it names BOTH the capability and the plugin:
    denied: capability rx.prescribe withheld by plugin 'prescriptions': not enabled for this user
Naming only the plugin would produce a line an admin cannot reconstruct six months later; naming only the capability would lie to a clinician whose role plainly holds rx.prescribe. The audit is written by the same `deny()` path as every other denial (guard.py:168-170), so it is written BEFORE execute, like everything else.

ORDERING, DELIBERATELY LEFT ALONE: because the check sits inside step 2, a malformed payload sent to a disabled plugin still reports the payload problem first (step 1 is schema). That is already true for a plain missing capability, so it is not a regression; reordering steps 1 and 2 is a separate decision.

THE MUTATION THAT PROVES IT — and it is the one the task names. In bundles/phc/check.py, `check_plugin_off_denies_the_machine_surface`:
    1. OFF["user:rao"] = {"prescriptions"}; role mo (which holds rx.prescribe).
    2. GET /whoami with X-PHC-Actor: user:rao -> "rx.prescribe" not in capabilities. (Tool list narrowed.)
    3. POST /api/v1/phc/propose {"operation": "phc.op.rx-prescribe", ...} with surface MCP, the same headers — i.e. an agent calling the tool name it remembered from before the switch was thrown. ASSERT: 422, and the reason string contains both "rx.prescribe" and "prescriptions".
    4. ASSERT the thread's audit trail gained a row whose outcome starts "denied: capability rx.prescribe withheld by plugin".
    5. ASSERT the same call with OFF cleared returns a proposal id. (Non-vacuity: the check would otherwise pass against an endpoint that denies everything.)
  THE MUTATION THAT MUST MAKE THIS CHECK FAIL: change `caller()` to return the full `caps` and only report `withheld` alongside — i.e. implement the feature as a render-time hide. Step 2 still passes (whoami is computed from `held`... so also remove the subtraction there), and step 3 then RETURNS A PROPOSAL, so the check fails. Hidden AND refused, never hidden instead of refused.

A SECOND MUTATION, for the message: drop `op['capability']` from the withheld deny string and check 2 (catalogue/tests/test_guard.py) fails, because an audit line that names a plugin but not the capability cannot be reconstructed against a bundle.yaml that has since been edited.

TWO EXISTING HOLES THIS RULE WOULD OTHERWISE LEAVE OPEN, both closed in the same commit:
- POST /khoj (api/main.py:372) checks no capability whatsoever. It must check `BUNDLE.manifest.khoj["capability"]` against the caller's held caps and 403 otherwise. Without this, turning the agent plugin off removes the box from the screen and leaves the endpoint open.
- `scribe_status` (api/main.py) calls `caller(request)` and DISCARDS the result, and GET /scribe/sessions/{id} returns the draft to anyone holding a session id, while api/scribe.begin() records the session's actor. So a nurse with scribe on could start a capture and a doctor with scribe off could collect the draft, and the capability check would have applied only at scribe_start. Both `scribe_status` and `scribe_withdraw` must compare the session's recorded actor to the caller and re-read the instrument capability, exactly the way consent is already re-read by `collect_if_consent_stands`.

## Handover under composition

Handover is where composition does its damage, because every failure below is one person's switch becoming another person's dead end.

1. THE STALLED THREAD — the leading failure, and specific to per-user composition. api/main.py `_nudge()` (:166-173) already says "Waiting at nurse. Nobody with your capabilities can act here." With composition that sentence can be true for every person on shift while the facility's role table says the station is staffed. Nothing in kernel/state.station() or kernel/views.py has any concept of who is on shift, so the thread is invisible: the queue shows the row, the tasklist shows the task, and nobody is told the line is dead.
ANSWER: compute it at the moment of the change, not by monitoring. `PUT /users/{user}/plugins` returns `strands: [station, ...]` — for each step of each workflow, the union over every known composition (ROLES/OVERRIDES minus each user's OFF) of the capabilities of that step's operations; a step no composition can reach is named in the response and drawn on the admin screen beside the switch that caused it. One derived list from declarations already in memory, no new machinery, no monitoring system. It warns; it does not refuse, because staff come and go and refusing would make the editor unusable at shift change.

2. SEPARATION-OF-DUTIES DEADLOCK. catalogue/ops/lab.op.result-verify.md declares `not actor of lab.op.result-enter`. Turn a plugin off for the only other lab user and the incharge must both enter and validate, and that precondition refuses — correctly and permanently. The guard's denial ("Already performed lab op result enter") gives an admin no hint that a switch three screens away is the cause; the two rules are enforced in the same function and neither knows about the other.
ANSWER: extend the `strands` computation. For any step whose operations carry an `actor of` / `not actor of` precondition, require at least TWO distinct holders, and name the station when the count falls to one. Same derived list, one different threshold. The guard is not changed — a deadlock must still deny — the admin is simply told before they create it.

3. PROVENANCE IS LOST AT THE HANDOVER. `contracts.Proposal` carries surface (RENDERED or MCP) and no instrument; `contracts.Draft` carries `instrument` but a Draft is never stored; `AuditRecord` has no instrument field. So nothing records that the nurse's vitals-voice produced a BP rather than a keyboard. The confidence markers web/src/Form.tsx draws die with the browser state.
ANSWER: DEFERRED, with the trigger named. The day a facility turns an instrument off because it misheard, "which values did that instrument produce" is unanswerable, and that is the day to add `instrument` to Proposal and to the proposal table in both adapters. Not before: it is a column in two adapters and a field in a frozen-by-convention dataclass, bought for a question nobody has asked yet.

4. A MID-CAPTURE HANDOVER LOSES THE WORK. A Draft lives only in the browser. The nurse dictates three of five vitals, the patient moves, the doctor opens the thread: nothing carries over. Composition removes the workaround of handing the tablet over, because the doctor may not hold capture.voice.
ANSWER: the structural rule in the composition section is what keeps this survivable — a plugin owning instruments may not own the operation's capability, so the OPERATION is always still there and the instrument declaration's own `fallback` (`fallback: form` on consult-scribe, `keypad` on the voice instruments) is what the renderer draws instead. The three dictated vitals are still lost; that is unchanged and deliberate (a draft is never stored), and it is listed under known limits rather than fixed here.

5. SCRIBE SESSIONS ARE COLLECTABLE BY THE WRONG USER, TODAY. See the safety rule: `scribe_status` calls `caller()` and discards it, and api/scribe.begin() records the session's actor. ANSWER: compare them in `scribe_status` and `scribe_withdraw`, and re-read the instrument's capability in both, in the same commit that gives the instrument a capability. Without this the off switch applies only at scribe_start.

6. AN AGENT'S PROPOSAL OUTLIVES THE PLUGIN THAT MADE IT. `kernel.proposals.confirm()` re-judges against thread state and the CONFIRMING user's capabilities. A card Khoj queued while the agent plugin was on is therefore confirmable by a doctor who has the agent plugin off.
ANSWER, decided rather than left to accident: THAT IS CORRECT AND STAYS. `agent.ask` gates ASKING, not writing. The write is the doctor's own, on the rendered surface, re-judged by the full guard against their own capabilities; the operation's capability (rx.prescribe, encounter.document) is what gates it, and if that is withheld the confirm denies with the plugin-named reason. Nothing is added to confirm().

7. THE POST-HOC COMPOSITION CHANGE. Turn prescriptions off for a user and their pending rx cards deny at confirm with the plugin-named reason — readable and correct — but the cards stay pending on the thread forever, because nothing expires them. `PROPOSAL_STATUSES` has an `expired` value that nothing ever writes.
ANSWER: the composition save does NOT touch proposals (that would be a cross-thread write from a config endpoint, which is the wrong shape entirely). The card denies, names the plugin, and stays. Writing `expired` is deferred and belongs to whoever builds proposal expiry generally, since a proposal that outlived its BUNDLE (which `confirm()` already handles with "is not an operation this facility declares") has the identical problem and predates composition.

ONE MORE, CREATED BY THE SPINE RATHER THAN BY COMPOSITION: attaching a returning patient at reception changes who the visit is about after the thread is already open. This is safe because `write("patient")` only attaches when `encounter.patient` is null (adapters/local/store.py:322-325) — a visit already joined to a person cannot be silently re-pointed at another one by a second registration.

## The screens

THE ONE RULE THAT REPLACES HAND-DECIDING PER PERSONA: THE CENTRE OF THE PAGE IS CHOSEN BY THE CALLER'S EFFECTIVE CAPABILITIES, NOT BY A ROLE NAME IN THE RENDERER.

    centre = caps.includes(catalogue.manifest.khoj.capability) && threadIsOpen
             ? prompt-first
             : the form for the next operation at this user's station

Two properties matter and both are structural. First, the renderer names no bundle word: it reads `manifest.khoj.capability` and the instruments' own `capability:` fields, exactly as it already reads `manifest.views` for the nav, so the portability rule (nothing in web/src outside a .check.ts may name a station, a flag or a bundle) still holds and bundles/lab still renders on the same renderer. Second, an admin turning the `agent` plugin off for one doctor moves that doctor's centre back to the form with no code change and no role edit — which is what "falls out of composition" has to mean to be worth anything.

Instruments follow the same rule: `mountsFor` filters by `inst.capability` absent or held. Withheld -> the instrument's declared `fallback` renders instead (`form` for the scribe, `keypad` for the voice instruments). The chip row is GENERATED, never authored: for the open thread and this caller, draw the instruments whose `operations` intersect the operations `visible()` returns, labelled by the artefact they produce ("Draft note", "Draft prescription") rather than by the act. It cannot drift from the guard, because visible() and evaluate() share the precondition predicate, and a chip for an unmet precondition is ABSENT, not greyed.

WHAT EACH PERSONA GETS, AND FROM WHICH DECLARED FACT:
- FRONT DESK CLERK (preset `frontdesk`: patient.find, patient.register, abha.link, appointment.book, handover — no capture.*, no agent.ask). FORM CENTRE. 40-80 registrations a day, keyboard-only, patient at the counter: a prompt box would make a deterministic act nondeterministic and charge a sentence where Tab sufficed. Concretely: find-first search input focused on load, exact/substring on phone, ABHA or name; Enter selects the top match and carries its `patient_id` into the register payload; no match -> the register form, first field focused, tab order = questionnaire order, Enter submits. No prompt box anywhere on this centre. Note the comparable product agrees: even there, "Create a Patient" is a rail button and not a prompt.
- NURSE (preset `nurse` + capture.voice). FORM CENTRE WITH THE VOICE INSTRUMENT MOUNTED. Hands busy is an argument for speech, not for an open sentence: vitals are short numeric utterances, which is exactly what ambient recognition gets wrong, and phc.inst.consult-scribe's own body says so and deliberately excludes vitals from its operations list. Constrained voice into a named field, readback required, tap commits.
- DOCTOR / MO and CHO (preset + capture.scribe + agent.ask). PROMPT-FIRST CENTRE, WITHIN A THREAD. 3-8 minutes, genuinely unbounded intent, payload is language. The ask box sits in the centre with the generated chip row beneath it and the scribe banner above; the thread supplies the subject.
- PHARMACIST and LAB (presets `pharmacist`, `lab`, `lab_incharge`: no capture.*, no agent.ask). FORM CENTRE, match-and-confirm: the order beside the thing in hand, one confirm. The work is comparison, not composition, and a prompt box here quietly opens a free-text path around a structured one.

So one declared capability per preset decides four centres, and the admin can move any individual user across that line without touching code.

NAVIGATION — the nesting is worth copying, the identity is not. Rail, top to bottom: the declared views (as today, from `manifest.views`, station-queue first), then Patients, then the organisation line is NOT included (see below). The patient level is new and is navigation only:
- PATIENT PAGE: header carries name, age, sex, village, ABHA number and "N visits"; body is a list of dated visit rows, newest first, each row opening the existing phc.view.visit-summary for THAT encounter. No new view kind, no `No renderer for a <kind> view` fallback reachable. Reached from any thread panel (subject.id is already the patient id there) and from the find-first search results.
- The queue stays primary and stays grouped by station with the wait rule intact. A flat all-encounters list is at most secondary; a facility needs today's line, not one clinician's recency log.
- A thread whose patient column is null shows no patient link at all. Not an error, not an empty state with a name.

WHAT WE DO NOT COPY, EACH WITH ITS REASON (and note the comparable product is known to us only through one screenshot the owner supplied — nobody could log in, so every claim about it is INFERRED from that image plus vendor marketing, not observed):
- "Add Context" inside the prompt box. INFERRED reason for its existence: a prompt-first page has no default subject. We have a queue, so context arrives from the line. Copying the button imports a per-turn click we do not pay today.
- A subject-free global prompt. web/src/ask.ts returns "Open a thread first." because every Store read is thread-scoped. Making the ask work with no thread is the deferred Option A, not a UI change.
- The document-type library as a menu of templates. Our artefacts are the residue of operations the guard permitted, and the artefact list is already declared as phc.view.visit-summary's sections, which are also ABDM's health-information types. Letting a user pick a template severs the artefact from the transition that produced it, and with it the audit trail and the emits.
- Letting a chip write. A chip produces a proposal; the tap on the resulting card writes, through the guard, with audit-before-execute and the irreversibility rule that denies on surface != RENDERED before it even looks at `confirmed`.
- The organisation switcher as a tenancy answer. Our scoping is role x capability x per-user composition; a corner dropdown would imply tenancy is a view.
- Plan tiers as the model for plugins. Their gating is by price (INFERRED from vendor pages); ours is by role and preference with presets carrying the 70%. Same switch, opposite reason — build it capability-shaped, never plan-shaped.
- Flattening patient over encounter, for the three reasons in the spine section.

THE ADMIN SCREEN. web/src/Roles.tsx keeps its capability grid and gains one axis: `groupsFor()` regroups by the plugin that owns the capability instead of by the operation it unlocks — same function, different key — and the group header becomes the plugin's own switch, with the capability rows underneath as the advanced view. A capability no plugin claims keeps its own ungrouped row and is always on, which is the default-on rule showing through the UI rather than asserted in a doc. Three layers shown as three: preset (read-only), facility role override (exists), user composition (new). Beside the switches, two read-only facts: which plugins each preset implies, and the `strands` list from the handover section. ONE SENTENCE OF COPY EARNS ITS PLACE, in the header and not per row: "Turning a plugin off removes the ability, not just the button." Everything else on the screen stays text-light. That sentence is the difference between a preference screen and a permission screen, and the whole design rests on it being the second.

## Sequencing

PRINCIPLE: at every point between steps the product is either exactly what it was, or what it was plus one page. There is no state in which the old path is gone and the new one is unproven. The previous redesign started at the visual layer while the invariants underneath were unasserted; this order is the reverse of that.

STEP 0 — DETECTORS, BEFORE ANY PRODUCT CHANGE. The CSS custom-property scan converted from a hardcoded file list to a directory scan; the rank-distinctness and contrast arithmetic; seed non-vacuity per declared threshold; referential closure over the declaration graph including the ViewRenderer dispatch; the browser geometry smoke behind CHECK_BROWSER=1, WRITTEN AGAINST THE CURRENT SHELL so it carries a known-good baseline instead of blessing whatever the new screen happens to do. Nothing here changes the product. Prove each by mutation before moving on.

STEP 1 — PLUGINS DECLARED, DEFAULT ALL-ON, NO UI, NO OFF MAP. `plugins:` in both bundle.yaml files (lab may declare none), the two lint rules, `Manifest.plugins`, `Vocabulary.plugins`. Assert: for every role in bundle.yaml, the effective capability set with OFF empty is byte-identical to `vocab.BUNDLES[role]` today. The toggle exists in the model and nowhere on screen.

STEP 2 — THE THREE CAPABILITIES AND THE INSTRUMENT FIELD. capture.voice, capture.scribe, agent.ask added to `capabilities:` and to the presets that warrant them; `capability:` on the three instrument declarations plus its lint line; `khoj.capability` in the manifest and the check in POST /khoj; the scribe_status / scribe_withdraw actor comparison. VISIBLE CHANGE IN THE BROWSER: none — the only account the browser can be is `demo`, which is `sorted(vocab.CAPABILITIES)` (api/main.py:75) and therefore holds all three the moment they are declared. Do ONE plugin's worth of this first (scribe: most self-contained, already owns its own check and stylesheet), prove it, then the other two.

STEP 3 — THE OFF MAP AND THE GUARD REASON. `OFF`, the subtraction in `caller()`, `withheld` threaded through proposals into guard step 2, `PUT/GET /users/{user}/plugins` with the facility.admin gate and the audit line against thread "facility", and the audit line added to PUT /roles in the same commit. Still no UI. The proof is the MCP mutation check, not a screen.

STEP 4 — THE SPINE GETS LENGTH. `GET /patients?q=` with its patient.find gate; the optional `patient_id` question and its one mapping line; the `_put` empty-update guard; the `roll_seed_forward` seed-only clause. Product gain: find-first at reception. Land the two-visit isolation proof and the pinned queue count in the same commit — they are the commit's reason to exist.

STEP 5 — THE PATIENT PAGE. Read-only, N per-encounter reads, reached from the thread panel and from search. The product gains a page and loses nothing.

STEP 6 — THE ADMIN SCREEN. Roles.tsx regrouped by plugin, the per-user switches, the `strands` list, the one sentence of header copy.

STEP 7 — THE CENTRE RULE AND THE NEW SHELL, LAST, BESIDE THE LIVE ONE. Behind a route (#/next), not a build flag, so both shells are live in the same binary and going back is a URL rather than a revert. Per-persona entry points first, each acceptance-tested on its own: clerk keyboard-only registration, nurse voice capture, doctor scribe and prompt, pharmacist/lab match-and-confirm, and one handover between two of them. The old shell is deleted in its own later commit, after the owner has used the new one.

WHAT IS FLAGGED: the new shell, by route (#/next or PHC_SHELL=next), because that is where both previous regressions were visible; the geometry smoke, behind CHECK_BROWSER=1 so a machine without a browser still runs the suite, but NAMED in an explicit SKIPPED summary printed at the end of scripts/check.sh so "all checks passed" never again means "half of them were skipped"; per-user composition, flagged by being empty — OFF is `{}` on day one and the empty-map identity is a check, not a config.

WHAT IS FAIL-CLOSED RATHER THAN FLAGGED (a flag implies a working alternative; these have none): anything the CARE adapter cannot do raises rather than falling back, because a silent fallback returns an empty history that reads as a true one; adapters/care/tests/test_live stays skipped until there is an authenticated CARE and appears by name in the skip summary.

COMMITS THAT MUST NOT BE COMBINED:
- A commit that touches theme.css or a .tsx touches no .py, and the reverse. Two of the last three regressions were visual; separating them makes a bisect mean something.
- The phc.view.patient-summary -> visit-summary rename (already done on this branch) and any new patient-level view: a rename plus an addition in one diff makes "is this reference dangling or newly added" unanswerable to referential closure and to a human.
- Plugin enablement and per-user composition (steps 1-2 vs step 3). Both answer "why can I not see this?". Shipped together, a missing action has two possible causes and neither the user, the admin nor a check can tell which.
- The prompt box and the front desk route. The clerk has the least use for AI in the product; the prompt box goes on the doctor's route first and earns its way outward, or not.
- All six plugin types at once. Scribe alone proves the mechanism; the rest follow in whatever order is convenient.
- Option A (`subject=`) and the first authenticated CARE run, if Option A is ever reached: two unproven things at once means every failure has two candidate causes.

## Checks

- **web/src/design.check.ts — "no stylesheet spends a token :root never declares" (EXISTS at :71-96; this spec converts its hardcoded five-file list into a scan of every *.css under web/src, recursively). Strips comments from theme.css before building the defined set, because theme.css's own prose contains strings like "16.0:1 on --dial" that otherwise satisfy /--([\w-]+)\s*:/ and paper over a deleted token. Keeps `definedTokens.size > 40` so the scan cannot go vacuous.**
  - Mutation that proves it: Two, both must FAIL the suite: (a) comment out any token in theme.css's :root — every call site fires; (b) add web/src/next/next.css spending var(--nope) — the new file must be scanned, which the old hardcoded list would have missed silently. Passes again on revert.

- **web/src/renders.check.ts — "a declared feature is actually rendered", browser-free half. For every plugin in catalogue.json and every instrument carrying a `capability:`, assert a renderer code path is keyed off that declaration: mountsFor(thread, caps) returns a non-empty mount for a consented thread whose caps include the instrument's capability, and an empty one when the capability is absent; and the centre rule resolves to prompt-first exactly when manifest.khoj.capability is held. Imports the real rule modules (no .tsx), so it runs the logic rather than grepping for it.**
  - Mutation that proves it: Replace mountsFor's body with `() => []` (the shape of the regression where a declaration shipped that no renderer ever read) — FAIL. Separately, hardcode the centre to "form" — FAIL. Both pass on revert.

- **CHECK_BROWSER=1 DOM half of the same: boot the API on a free port (reuse scripts/e2e.py's boot), load the doctor's thread with the scribe plugin ON and assert a node carrying the instrument's declared id exists; set OFF={"user:demo":{"scribe"}}, reload, assert that node is ABSENT and the declared fallback (the form) is PRESENT. Named in the suite's SKIPPED summary when the flag is unset.**
  - Mutation that proves it: Delete the scribe mount branch from the renderer while leaving the declaration in place — the ON half FAILs. Then remove the fallback render — the OFF half FAILs. This is the exact pair that shipped green before: a declaration nothing renders, and a check that pinned the deletion.

- **bundles/phc/check.py — check_plugin_off_denies_the_machine_surface. OFF={"user:rao":{"prescriptions"}}, role mo: (1) /whoami omits rx.prescribe; (2) POST /propose for phc.op.rx-prescribe on surface MCP returns 422 whose reason contains both "rx.prescribe" and "prescriptions"; (3) the thread's audit gains a row whose outcome starts "denied: capability rx.prescribe withheld by plugin"; (4) with OFF cleared the same call returns a proposal id.**
  - Mutation that proves it: Make caller() return unsubtracted caps and report `withheld` alongside — i.e. implement composition as a render-time hide. Step (2) returns a proposal instead of 422 and the check FAILs. This is the mutation that proves the rule cannot be satisfied by hiding a button.

- **catalogue/tests/test_guard.py — check_withheld_denial_names_capability_and_plugin. evaluate(op, caps=caps_without_rx, withheld={"rx.prescribe":"prescriptions"}) produces a denial string containing both names, and evaluate with withheld=None (every existing call site) still produces exactly "missing capability rx.prescribe".**
  - Mutation that proves it: Drop op['capability'] from the withheld branch's string — FAIL. Drop the withheld branch entirely so both cases read "missing capability" — FAIL on the first assertion.

- **kernel/tests/test_contracts.py — check_default_composition_changes_nothing. With OFF empty, the effective capability list for every role in bundles/phc/bundle.yaml equals vocab.BUNDLES[role] exactly (set and order), and compile_json(BUNDLE) differs from the pre-plugin compile only by the added `plugins` key and the three new capability names.**
  - Mutation that proves it: Pre-populate OFF with any plugin, or mark a plugin `always: false` and have caller() subtract it by default — FAIL. This is what makes "everything ships inbuilt" provable rather than remembered.

- **catalogue/vocab.py Vocabulary.problems() — check_plugin_owns_only_declared_words: a plugin naming a capability the bundle does not declare, or an instrument whose declaration carries no `capability:`, is a build failure before anything reads the vocabulary.**
  - Mutation that proves it: Add `capabilities: [rx.prescribeX]` to a plugin — `python3 -m kernel.declarations` must exit non-zero. Remove `capability:` from phc.inst.consult-scribe.md while the scribe plugin still lists it — must exit non-zero.

- **kernel/tests/test_contracts.py — check_instrument_plugin_does_not_own_its_operations_capability. For every plugin with `instruments:`, the capabilities of the operations those instruments name must not intersect that plugin's own `capabilities:`. This is the rule that keeps a handover survivable: turning off the scribe removes the microphone, never the ability to document.**
  - Mutation that proves it: Add rx.prescribe to the scribe plugin's capabilities — FAIL. (Without this check the mutation would ship a switch that silently removes a doctor's ability to prescribe at all.)

- **bundles/phc/check.py — check_two_visits_reoffer_vitals_and_consent_does_not_cross. Register a patient, walk visit one to completion, open a SECOND encounter and attach the same patient_id, then assert: phc.op.vitals-record is in visible() for visit two; capture.consented is false on visit two after visit one agreed; the visit-two audit and proposals lists are empty.**
  - Mutation that proves it: Change kernel/state.py:22's count call to derive over the patient instead of the thread — both halves FAIL (vitals absent, consent carried). This one test protects breakage (1) and breakage (2) and the only legal property in the product.

- **bundles/phc/check.py — check_todays_queue_is_still_encounters. store.threads(workflow=..., scope='today') returns a pinned integer against the shipped seed, asserted before and after the patient page exists.**
  - Mutation that proves it: Feed the patient page's encounter list into threads(), or add a patient-derived row to the queue — the pinned count changes and FAILs. A pinned integer is uglier than a property and catches breakage (3) absolutely.

- **adapters/local/tests/test_store.py — check_register_attaches_instead_of_duplicating. Register patient P on encounter A; open encounter B; register with payload carrying patient_id=P. Assert: exactly one patient row exists, both encounters point at it, P.created_by and P.created_date are unchanged from the first registration, and `registered` is true on B.**
  - Mutation that proves it: Ignore patient_id in the mapping — two patient rows, FAIL. Remove the `if not sets: return rid` guard in _put and pass a record of only {id} — sqlite3.OperationalError, FAIL. Remove the created_date exclusion at store.py:368 — the created_date assertion FAILs.

- **api/tests/test_api.py — check_patient_lookup_requires_patient_find. GET /patients?q= with a role holding patient.find returns rows; with a role from which patient.find has been withheld by composition returns 403 naming the plugin; with no q returns [] rather than the whole register.**
  - Mutation that proves it: Delete the capability check on the route — the 403 case FAILs. Return all rows on an empty q — the third assertion FAILs.

- **api/tests/test_api.py — check_scribe_session_belongs_to_its_actor. begin() a session as user:nurse; GET /scribe/sessions/{id} as user:rao returns 403; as user:nurse returns the draft; as user:nurse with the scribe plugin off returns 403.**
  - Mutation that proves it: Remove the actor comparison in scribe_status (which is today's behaviour: caller() is called and discarded) — the first case FAILs. Remove the capability re-read — the third FAILs.

- **bundles/phc/check.py and bundles/lab/check.py — check_seed_exercises_every_outcome_class. For each threshold a view declares (target_minutes 30, escalate_minutes), the seeded store yields at least one row in each outcome class: none, over, act. Keeps the existing non-vacuity idiom mandatory on every loop over a discovered set.**
  - Mutation that proves it: Reset enc-002's minutes_ago to 0 in bundles/phc/seed.yaml — FAIL. Without this, a correct wait rule and a broken one produce identical screens, which is how 527 green checks sat over a rule returning 0m for every row.

- **scripts/check.sh — check_counts_do_not_drop. Every .check.ts already prints `ok <name>: N checks`; collect them and compare against a committed counts file, failing when a count drops without that file being edited in the same commit. Plus an explicit SKIPPED summary listing every guard that did not run.**
  - Mutation that proves it: Delete any assertion from any .check.ts without touching the counts file — FAIL. Comment out `python3 -m bundles.phc.check` — it appears in the SKIPPED summary instead of vanishing into a green run.


## Known limits
- NO AUTHENTICATION. api/main.py caller() takes the role from an X-PHC-Role header or a query parameter and the actor from X-PHC-Actor, with DEMO_ROLE as the default. Per-user composition is therefore configuration, not security: anyone who can reach the port can pick an actor id with no OFF entry. The demo role is sorted(vocab.CAPABILITIES) and holds facility.admin, so it can edit its own composition. This is stated in the code today and this spec does not change it. Everything here is exactly as strong as the day a login lands and no stronger.
- OFF and OVERRIDES are module-level dicts, in-process, one facility per kernel, lost on restart. The composition audit lines go to the reserved thread id 'facility', which no declared view renders, so they are readable only by reading the audit table directly. The plugin-to-capability map is recoverable because bundle.yaml is version-controlled and the manifest carries a version; the per-user OFF list is not.
- OPTION D's CEILING: a genuinely cross-visit query is N client-side thread reads, and there is no count() over a patient, so no patient-windowed metric can exist. phc.metric.abha-coverage stays a facility count. The patient page is a list of dated visits, not a collation.
- The patient lookup is an in-process substring filter over the first 500 patient rows, because the query grammar (adapters/local/store.py _where) has equality and gte/lt/gt/lte and no LIKE. Exact on phone and ABHA number is reliable; name matching is naive and has no phonetic or transliteration handling, which for Indian names read aloud at a counter is a real limitation, not a theoretical one.
- Attaching a returning patient trusts the patient_id in the register payload. A wrong id joins the wrong person to the visit. It is correctable (the operation's irreversibility is 'correctable'), it is audited with the id in the payload, and via MCP it is a proposal a human must confirm — but there is no check that the id came from a search the same user ran.
- A mid-capture draft is still lost on handover: a Draft lives only in the browser and contracts.Draft is never stored. Composition removes the workaround of handing the tablet over.
- No provenance: nothing records which instrument produced a committed value. Proposal carries only surface (RENDERED or MCP), Draft carries instrument but is never stored, AuditRecord has no such field. The day an instrument is switched off for misrecognising, 'which values did it produce' has no answer.
- A pending proposal whose plugin was later switched off denies at confirm with the plugin-named reason and stays pending forever. PROPOSAL_STATUSES has an 'expired' value nothing writes.
- adapters/care has NEVER run against an authenticated CARE. Everything in this spec is specified against adapters/local; the CARE adapter's own gaps recorded during investigation (service_request is facility-pathed with no patient field, medication_dispense is global-pathed with no patient field, encounter.patient exists as a Field but carries no `param` so filtering encounters by patient pages the whole facility list through _matches) are UNVERIFIED claims from reading adapters/care/map.py, not observations against a server.
- The adapters disagree about unregistered visits and this spec does not resolve it: SqliteStore.open_thread creates an encounter with a null patient by design, CareStore.open_thread refuses because EncounterCreateSpec requires a patient. A CARE-backed deployment has no walk-in-before-registration state.
- GET /threads/{id} still applies NO capability check of any kind, and views._summary applies one capability for all nine sections of phc.view.visit-summary, declared as patient.find, which every role holds. Composition narrows what a user can DO; it does not add per-section read authorization, and this spec does not add any. There is no per-thread read authorization to widen, which is why Option D crosses no boundary — but it is also a hole that predates this work and outlives it.
- EVIDENCE FLAGS ON THE COMPARABLE PRODUCT, carried forward rather than laundered: the entire description of Glass Health is one screenshot the owner supplied. Nobody could log in and nobody tried. INFERRED, not observed: that its chips are output schemas rather than canned prompt strings; that 'Add Context' attaches a patient or encounter rather than a knowledge source, and exists because the prompt box has no default subject (if it pre-fills from the selected encounter, the argument against copying it weakens considerably); that 'Patient List' is a user-made saved set rather than a smart or shared list; that 'All Encounters' is sorted by recency; that its 'modes' are configuration of one product rather than separate bundles. ABSENCE OF EVIDENCE, NOT EVIDENCE OF ABSENCE: every statement that it has no queue, no station, no handover, no role-gated capability, no precondition system and no consent handling should be read as 'nothing public describes one'. Most sourcing is the vendor's own /resources and /compare pages, which are marketing and adversarial by construction.
- THE PERSONA FACTS ARE THE OWNER'S, NOT MEASURED. 40-80 registrations a day keyboard-only, nurse hands-busy, doctor 3-8 minutes per patient, pharmacist and lab match-and-confirm. This spec reasons from them and treats them as requirements; none was observed in a facility by anyone who wrote this.
- phc.view.station-queue's target_minutes: 30 is documented in its own declaration as a placeholder, not a value the spec measured, and the new screens inherit it unchanged.
- grants.ts inert() reasons over the FIRST workflow only (its own ponytail comment says so). A second workflow in a bundle would mark every capability the first draws as inert for the second, and the plugin grouping in the admin screen inherits that limitation.


## Deliberately deferred
- OPTION A — widening count() and select() with `subject=`. Trigger: the first real screen that needs one value computed ACROSS visits (a trend, a duplicate-therapy check, a patient-scoped metric). Then two signatures, three SQL branches in adapters/local _where, NotImplementedError in adapters/care, a conformance harness imported by both adapters' tests asserting that exactly one of thread=/subject= may be passed and that an adapter which has not implemented subject= raises rather than falling back, and the ten-name assertion at adapters/care/tests/test_store.py:492-497 updated in the same commit.
- THE PATIENT MERGE TOOL — deciding two patient rows are one person. One UPDATE per merged encounter plus a tombstone patient row; nothing else needs rewriting because every clinical row joins to the encounter. Not needed until two rows for one person actually exist, which find-first is designed to prevent. Prerequisite, to be fixed BEFORE any merge tool exists: the AND created_by = 'seed' clause on roll_seed_forward's patient branch.
- TEMPLATES as a declaration — note templates, order sets, favourite prescriptions. No declaration type can hold one today and composition deliberately answers on/off per user and nothing else. Trigger: a facility asks for its own note shape. It is the next declaration, not this one.
- PRESCRIPTION CONTENT as declaration — formulary, dose patterns, the picker, currently in web/src/structured.ts and the vendor's scribe JSON. The plugin gates the capability only.
- PROVENANCE: `instrument` on contracts.Proposal and the proposal table in both adapters. Trigger: a facility turns an instrument off because it misheard and asks which values it produced.
- PROPOSAL EXPIRY: writing the `expired` status that PROPOSAL_STATUSES already declares. Belongs to whoever builds expiry generally, since a proposal that outlived its BUNDLE has the identical problem and predates composition.
- PER-SECTION READ CAPABILITIES on a summary view, and any capability check on GET /threads/{id}. Both are real holes and both predate this work; adding them is its own change with its own blast radius and does not gate the spine.
- A 'patient list' as a user-authored saved set (the one object in the comparable product's IA we genuinely lack, INFERRED to be user-made). A declared view is authored by the facility; a patient list would be authored by the user, which is a new ownership axis. Not needed for the spine.
- A FLAT ALL-ENCOUNTERS VIEW. One clinician's recency log; the facility needs today's line grouped by station. Add as a secondary declared view if someone asks.
- THE ORGANISATION SWITCHER and anything multi-tenant. OVERRIDES and OFF are one facility per kernel, stated as a ceiling in the code today.
- STORE-SIDE PATIENT MATCHING (a LIKE or a phonetic index) to replace the 500-row in-process filter. Trigger: the register outgrows one page, or name matching is shown to miss real patients at a counter.
- DELETING THE OLD SHELL. Its own commit, after the owner has used the new one, and never in the commit that adds the new route.
