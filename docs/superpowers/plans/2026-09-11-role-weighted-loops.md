# Role-Weighted Loops, Records Rail, and Deletions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every role one obvious next action, a visible close to each task that offers the next one, and a right rail that shows the documents produced instead of our permission model.

**Architecture:** Almost nothing new is declared. A workflow step already names its `station`, its `done_when` and its `operations`, and an operation already declares what it `emits` and what it needs. Two derivations fall out — the operation that closes a station's loop, and the one that opens a new subject — and the kernel computes both because the kernel is already the authority on which station a thread is at (`applies_when` steps make that non-trivial, and `kernel/state.station()` already handles it). The renderer receives one new field and stops guessing.

**Tech Stack:** Python 3.9 (kernel, no framework, plain `assert` checks run as `python3 -m module`), FastAPI (api/), React + TypeScript + Vite (web/), Go (care_phc_mcp). No test framework anywhere — checks are runnable modules.

**Spec:** `docs/superpowers/specs/2026-09-11-role-weighted-loops-design.md`

## Global Constraints

- **Nothing in `web/src/types.ts` or the renderer names a station, a flag, or a bundle.** The file says so at the top and it is load-bearing: point the renderer at the lab kernel and it must draw the laboratory's words. Every string in this plan that looks like PHC vocabulary comes from a declaration at runtime.
- **`kernel/contracts.py` field names are frozen: add, never rename.**
- **Every check runs without a network, a database server, or CARE.** `sh scripts/check.sh` is the gate. `SKIP_E2E=1` skips only the socket half.
- **The guard's ordering is not to be touched.** Irreversibility denies on `surface != RENDERED` before reading `confirmed`.
- **Nothing on a machine surface may commit.** Propose-only; `commit()` takes no surface argument.
- **Copy rule:** no disclaimer prose, no text restating a card already on screen. The nurse's screen is at 178 visible words; the target is roughly 60.
- **The spoken consent line is exactly:** `May we record this visit to write your notes? You can say no, or stop it any time.`
- **Commit before mutating anything for a mutation test.** A `git checkout <file>` to undo a deliberate mutation has already destroyed uncommitted work in this repo once.

---

### Task 1: The kernel derives both ends of a loop

**Files:**
- Modify: `kernel/state.py` (add two functions after `drawn_by`, around line 133; extend `thread_view` around line 174)
- Modify: `kernel/contracts.py` (add one field to `ThreadView`, around line 395)
- Modify: `web/src/types.ts` (mirror the field on `ThreadView`, around line 149)
- Test: `kernel/tests/test_kernel.py` (append)
- Test: `bundles/lab/check.py` (append — the cross-bundle assertion)

**Interfaces:**
- Consumes: `kernel.state.station(workflow, known)`, `kernel.state.drawn_by(workflow, op_id)`, `contracts.Workflow.steps` (each with `.station`, `.done_when`, `.operations`).
- Produces:
  - `kernel.state.loop_closer(workflow, operations, station) -> Optional[str]` — the operation id at `station` that emits that step's `done_when`.
  - `kernel.state.loop_opener(workflow, operations) -> Optional[str]` — the operation id whose preconditions hold against an empty flag set.
  - `contracts.ThreadView.closes: Optional[str]` — `loop_closer` for the thread's current station, or `None` when the line is complete.

- [ ] **Step 1: Write the failing test**

Append to `kernel/tests/test_kernel.py`, before its `__main__` block:

```python
def test_loop_closer_is_the_operation_that_emits_done_when():
    """A station's loop closes on the operation that satisfies its step.

    Derived, never declared: adding a `loop:` key to every bundle would be a
    second place to state what `done_when` and `emits` already say, and so a
    second place to be wrong.
    """
    assert state.loop_closer(WF, OPS, "reception") == "phc.op.patient-register"
    assert state.loop_closer(WF, OPS, "nurse") == "phc.op.vitals-record"
    # The doctor's step draws four operations and only one of them ends it.
    # rx-prescribe and lab-order live INSIDE the doctor's loop.
    assert state.loop_closer(WF, OPS, "doctor") == "phc.op.consult-document"
    assert state.loop_closer(WF, OPS, "nowhere") is None


def test_loop_opener_is_the_only_operation_that_needs_an_empty_thread():
    """`not registered` is the signature of an operation that starts a subject."""
    assert state.loop_opener(WF, OPS) == "phc.op.patient-register"


def test_thread_view_carries_what_closes_this_station():
    store = Fake()
    ref = c.ThreadRef(id=T, workflow=WF.id, subject={}, station=None, opened_at="")
    caps = set(BUNDLE.roles["frontdesk"])
    view = state.thread_view(store, ref, WF, OPS, caps=caps)
    assert view.station == "reception"
    assert view.closes == "phc.op.patient-register"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python3 -m kernel.tests.test_kernel
```

Expected: `AttributeError: module 'kernel.state' has no attribute 'loop_closer'`.

- [ ] **Step 3: Write the minimal implementation**

In `kernel/state.py`, immediately after `drawn_by` (which ends around line 132):

```python
def loop_closer(workflow, operations, station):
    """The operation at `station` that ends this role's task there.

    A step declares `done_when`, and exactly one of its operations emits that
    flag. That operation is the close of the loop; the rest of the step's
    operations happen inside it. The doctor's step draws four operations and
    `consult.documented` names one of them, which is what keeps rx-prescribe
    and lab-order from reading as ends of the consultation.

    Returns None for a station this workflow has no step for, and for a step
    whose done_when no operation at that station emits — a bundle may declare
    a flag raised somewhere else, and that is a line with no close, not a
    crash.
    """
    for step in workflow.steps:
        if step.station != station:
            continue
        for op_id in step.operations:
            op = operations.get(op_id)
            if op is not None and step.done_when in (op.get("emits") or []):
                return op_id
    return None


def loop_opener(workflow, operations):
    """The operation that starts a new subject: the one whose preconditions
    hold against an empty thread.

    Everything else on the line needs `registered` or something later, so this
    picks out registration without naming it. A bundle with no such operation
    (a laboratory that only ever receives specimens) returns None, and roles
    there loop on their queue instead of on new subjects.
    """
    for step in workflow.steps:
        for op_id in step.operations:
            op = operations.get(op_id)
            if op is None:
                continue
            if guard.preconditions_hold(op.get("preconditions") or [], frozenset()):
                return op_id
    return None
```

If `guard.preconditions_hold` does not exist under that name, find the predicate
`catalogue/guard.py` already uses to evaluate `preconditions` against a flag set
and call that instead; do not write a second evaluator.

Then in `thread_view`, add to the `c.ThreadView(...)` call:

```python
        closes=loop_closer(workflow, operations, station(workflow, known)),
```

And in `kernel/contracts.py`, on `ThreadView`:

```python
    closes: Optional[str] = None    # loop_closer for `station`; None once complete
```

And in `web/src/types.ts`, on `ThreadView`:

```ts
  /** The operation whose commit ends this role's task at this station, from
   *  the step's own done_when. The renderer never derives this: `applies_when`
   *  steps mean only the kernel knows which station is current. */
  closes: string | null;
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m kernel.tests.test_kernel && python3 -m kernel.tests.test_contracts
```

Expected: PASS both. `test_contracts` asserts the declarations still drive the line.

- [ ] **Step 5: Prove it is not PHC wiring**

Append to `bundles/lab/check.py`, in the same style as the assertions already there:

```python
# The loop derivations are kernel behaviour, not the health centre's. This
# bundle's line must resolve a closer for every station it declares, from its
# own done_when flags, with no phc.* anywhere in the answer.
wf = BUNDLE.workflow()
for step in wf.steps:
    closer = state.loop_closer(wf, BUNDLE.operations, step.station)
    assert closer is not None, f"{step.station} has no operation emitting {step.done_when}"
    assert not closer.startswith("phc."), f"lab station {step.station} closed by {closer}"
```

Add `from kernel import state` to that file's imports if it is not already there.

- [ ] **Step 6: Run the full gate**

```bash
sh scripts/check.sh
```

Expected: `all checks passed`. Every existing check must still pass — `closes` is an added field with a default, so no frozen name moved.

- [ ] **Step 7: Commit**

```bash
git add kernel/state.py kernel/contracts.py web/src/types.ts kernel/tests/test_kernel.py bundles/lab/check.py
git commit -m "Derive both ends of a station's loop from the declarations"
```

---

### Task 2: One primary action, everything else in overflow

**Files:**
- Create: `web/src/loops.ts`
- Create: `web/src/loops.check.ts`
- Modify: `web/src/Thread.tsx:286-292` (the action list)
- Modify: `scripts/check.sh` (register the new check)

**Interfaces:**
- Consumes: `ThreadView.closes` (Task 1), `ThreadView.actions: Operation[]`.
- Produces: `web/src/loops.ts` exporting
  `weigh(actions: Operation[], closes: string | null): { primary?: Operation; overflow: Operation[] }`.

- [ ] **Step 1: Write the failing check**

Create `web/src/loops.check.ts`:

```ts
/** The loop rules, as pure functions over declarations.
 *
 *  Run: node --experimental-strip-types src/loops.check.ts   (from web/)
 *
 *  Nothing here names a station or a bundle. Every input is built from
 *  catalogue.json, so a rule that only works for the health centre fails.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { weigh } from "./loops.ts";
import type { Operation } from "./types";

const root = fileURLToPath(new URL("../../", import.meta.url));
const cat = JSON.parse(readFileSync(root + "catalogue/catalogue.json", "utf8"));

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const op = (id: string): Operation => cat.operations[id] as Operation;
const doctor = [op("phc.op.consult-document"), op("phc.op.rx-prescribe"),
                op("phc.op.lab-order"), op("phc.op.capture-withdraw")];

// -- the closer is the one filled button -----------------------------------
const w = weigh(doctor, "phc.op.consult-document");
ok(w.primary?.id === "phc.op.consult-document", "the closer is primary");
ok(w.overflow.length === 3, "everything else is overflow");
ok(!w.overflow.some((o) => o.id === w.primary?.id), "primary never repeats in overflow");

// -- no closes, or a closer not offered: fall back to the first action ------
const none = weigh(doctor, null);
ok(none.primary?.id === "phc.op.consult-document", "falls back to the first action");
const gone = weigh(doctor.slice(1), "phc.op.consult-document");
ok(gone.primary?.id === "phc.op.rx-prescribe", "a closer whose precondition is unmet is not primary");

// -- nothing to do is not a crash ------------------------------------------
const empty = weigh([], "phc.op.consult-document");
ok(empty.primary === undefined && empty.overflow.length === 0, "an empty action list is empty");

// -- say a thing once ------------------------------------------------------
const all = [w.primary!.id, ...w.overflow.map((o) => o.id)];
ok(new Set(all).size === all.length, "no operation is offered twice");

console.log(`ok   ${checks} loop checks`);
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ERR_MODULE_NOT_FOUND` for `./loops.ts`.

- [ ] **Step 3: Write the minimal implementation**

Create `web/src/loops.ts`:

```ts
/** The loop rules. Pure, so they are checkable without a browser.
 *
 *  `thread.actions` is already filtered by the kernel: an action whose
 *  precondition is unmet or whose capability is not held is absent, never
 *  disabled. So everything here is a question of weight, not permission.
 */
import type { Operation } from "./types";

/** One filled button, everything else one level down.
 *
 *  Two things of equal visual weight means we have not decided which is the
 *  point. The kernel already says which operation ends this station's task;
 *  when it is not on offer (its precondition is unmet, or the line is
 *  complete) the step's own ordering has put the next thing first.
 */
export function weigh(
  actions: Operation[],
  closes: string | null,
): { primary?: Operation; overflow: Operation[] } {
  const primary = actions.find((op) => op.id === closes) ?? actions[0];
  return { primary, overflow: actions.filter((op) => op.id !== primary?.id) };
}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ok   7 loop checks`.

- [ ] **Step 5: Use it in the renderer**

In `web/src/Thread.tsx`, replace the action list at lines 286-292. The current
block maps every action into an equal pill. Replace with the weighed pair — the
primary as the one filled button, the rest behind a single overflow control that
reuses the palette:

```tsx
      {(() => {
        const { primary, overflow } = weigh(line.actions, thread.closes);
        if (!primary) return null;
        return (
          <div className="acts">
            <button className="act act-primary" title={primary.summary}
                    onClick={() => onAction(primary)}>
              {primary.title}
            </button>
            {overflow.length > 0 && (
              <button className="act act-more" onClick={onMore}>
                {overflow.length} more
              </button>
            )}
          </div>
        );
      })()}
```

Add `import { weigh } from "./loops";` to the file's imports. `onMore` is already
a prop on this component and already opens the palette.

The bottom bar at `Thread.tsx:322-327` currently renders its own pill per
operation, which is where three operations come to be offered twice. Delete the
operation pills from it and leave only the ask input and its send control; the
primary action above is now the only place an operation is offered.

- [ ] **Step 6: Register the check and run the gate**

In `scripts/check.sh`, inside the `if [ -d web/node_modules ]` block, after the
scribe check line:

```sh
  (cd web && node --experimental-strip-types src/loops.check.ts)
```

Then:

```bash
sh scripts/check.sh
```

Expected: `all checks passed`, including `ok   7 loop checks`.

- [ ] **Step 7: Verify in the browser**

Open a thread whose station has more than one operation (the doctor's, with a
consented visit, draws four). Confirm exactly one filled button, an "N more"
control beside it, and no operation name appearing twice anywhere on screen.

- [ ] **Step 8: Commit**

```bash
git add web/src/loops.ts web/src/loops.check.ts web/src/Thread.tsx scripts/check.sh
git commit -m "Give a thread one primary action and put the rest behind one control"
```

---

### Task 3: The close card, and the cue to the next task

**Files:**
- Create: `web/src/CloseCard.tsx`
- Modify: `web/src/loops.ts` (add `cue`)
- Modify: `web/src/loops.check.ts` (append)
- Modify: `web/src/main.tsx:369-374` and `:437` (the two `onDone` handlers)

**Interfaces:**
- Consumes: `weigh` (Task 2), `ThreadView.closes` (Task 1), `firstOperation(cat, workflow)` which already exists in `web/src/main.tsx`, `QueueRow[]` from the station-queue view result the shell already fetches.
- Produces:
  - `web/src/loops.ts` exporting `type Cue` and
    `cue(a: { station: string | null; opener: Operation | null; queue: QueueRow[]; closed: string }): Cue`
  - `web/src/CloseCard.tsx` exporting
    `CloseCard({ what, wentTo, cue, onCue, onUndo }: { what: string; wentTo: string | null; cue: Cue; onCue: () => void; onUndo?: () => void })` — `onCue` takes no argument; the caller closes over the cue it passed in.

- [ ] **Step 1: Write the failing check**

Append to `web/src/loops.check.ts`, before its `console.log`:

```ts
// -- the cue after a loop closes -------------------------------------------
import { cue } from "./loops.ts";
import type { QueueRow } from "./types";

const row = (thread: string, name: string, station: string): QueueRow => ({
  thread, subject: { name }, station, flags: [], badges: {}, opened_at: "",
});
const register = op("phc.op.patient-register");

// A role that can start a new subject loops on new subjects.
const opened = cue({ station: "reception", opener: register, queue: [], closed: "enc-1" });
ok(opened.kind === "open", "a role holding the opener is cued to start another");

// A role that cannot loops on its own queue, and never on the thread it closed.
const next = cue({
  station: "nurse", opener: null, closed: "enc-1",
  queue: [row("enc-1", "Kamala Devi", "nurse"), row("enc-2", "Iqbal Ahmed", "nurse")],
});
ok(next.kind === "next" && next.thread === "enc-2", "cues the next one, not the one just closed");

// Only this station's queue.
const elsewhere = cue({
  station: "nurse", opener: null, closed: "enc-1",
  queue: [row("enc-3", "Sunita Rao", "pharmacy")],
});
ok(elsewhere.kind === "empty", "another station's queue is not this role's work");

// An empty queue says so and invents nothing.
const quiet = cue({ station: "nurse", opener: null, queue: [], closed: "enc-1" });
ok(quiet.kind === "empty", "an empty queue is an empty cue");
ok(!/\d/.test(quiet.label), "the empty cue states no count it does not have");
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ERR_IMPORT` / `cue is not a function`.

- [ ] **Step 3: Write the minimal implementation**

Append to `web/src/loops.ts`:

```ts
import type { QueueRow } from "./types";

/** What a role is offered once its task at a station is done.
 *
 *  Two shapes, because there are two kinds of role: one that starts new
 *  subjects (it holds the workflow's opener) and one that works a queue. The
 *  difference is derived from the declarations, not from a list of job titles.
 */
export type Cue =
  | { kind: "open"; op: Operation; label: string }
  | { kind: "next"; thread: string; label: string }
  | { kind: "empty"; label: string };

export function cue(a: {
  station: string | null;
  opener: Operation | null;
  queue: QueueRow[];
  /** The thread whose loop just closed. It may still be in the queue result,
   *  which was read before the commit; offering it back is a loop with no
   *  exit. */
  closed: string;
}): Cue {
  if (a.opener) return { kind: "open", op: a.opener, label: a.opener.title };
  const waiting = a.queue.filter((r) => r.station === a.station && r.thread !== a.closed);
  const first = waiting[0];
  if (!first) return { kind: "empty", label: "Nobody waiting" };
  const name = typeof first.subject.name === "string" && first.subject.name
    ? first.subject.name
    : String(first.subject.token ?? first.thread);
  return { kind: "next", thread: first.thread, label: name };
}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ok   12 loop checks`.

- [ ] **Step 5: Write the close card**

Create `web/src/CloseCard.tsx`:

```tsx
/** The end of a task, and the start of the next one.
 *
 *  A loop with no visible close leaves a clerk looking at a patient who is no
 *  longer their problem. This card is that close: what happened, where the
 *  patient went, and the single thing to do next. The undo is quiet and is
 *  present only while the operation is still correctable.
 */
import type { Cue } from "./loops";

export function CloseCard({ what, wentTo, cue, onCue, onUndo }: {
  /** The operation's own title, from its declaration. */
  what: string;
  /** The station the thread is at now, or null once the line is complete. */
  wentTo: string | null;
  cue: Cue;
  onCue: () => void;
  onUndo?: () => void;
}) {
  return (
    <div className="close">
      <div className="close-h">
        {what}{wentTo ? ` → ${wentTo}` : ""}
      </div>
      {cue.kind === "empty" ? (
        <div className="close-e">{cue.label}</div>
      ) : (
        <button className="act act-primary" autoFocus onClick={onCue}>
          {cue.kind === "open" ? cue.label : `Next: ${cue.label}`}
        </button>
      )}
      {onUndo && <button className="close-u" onClick={onUndo}>Undo</button>}
    </div>
  );
}
```

`autoFocus` is what makes Enter continue the loop without a mouse, which is the
whole point for a front desk.

- [ ] **Step 6: Show it when a loop closes**

In `web/src/main.tsx`, both `onDone` handlers (around lines 369 and 437) currently
call `toast(...)` and reload. A commit closes a loop when the operation committed
is the one the kernel named in `thread.closes` **before** the reload, so it must
be read first.

Add the state and one helper near the other `useState` calls:

```tsx
  const [closed, setClosed] = useState<{ what: string; cue: Cue } | null>(null);

  /** Read `closes` before reloading, because the reload is what changes it. */
  const finish = (op: Operation) => {
    const wasClosing = thread.data?.closes === op.id;
    thread.reload();
    loaded.reload();
    if (!wasClosing || !cat.data) return;
    setClosed({
      what: op.title,
      cue: cue({
        station: thread.data?.station ?? null,
        opener: openerFor(cat.data, thread.data?.workflow, facility.data),
        queue: (queues[0]?.result.rows ?? []) as QueueRow[],
        closed: route.id,
      }),
    });
  };
```

In the **proposal** handler (around line 369), replace the `toast`, `thread.reload()`
and `loaded.reload()` lines with:

```tsx
                            finish(proposalOperation(p, cat.data?.operations ?? {}));
                            void offerJourney(route.id, p.operation, thread.data?.workflow, carried);
```

In the **panel** handler (around line 437), replace the same three lines with:

```tsx
              finish(modal.op);
```

Render the card above the thread:

```tsx
  {closed && (
    <CloseCard
      what={closed.what}
      wentTo={thread.data?.station ?? null}
      cue={closed.cue}
      onCue={() => {
        const c = closed.cue;
        setClosed(null);
        if (c.kind === "open") void register();
        else if (c.kind === "next") openThread(c.thread);
      }}
    />
  )}
```

`register()` and `openThread()` already exist in this file. Clear the card
whenever the route changes, so it never outlives its thread:

```tsx
  useEffect(() => { setClosed(null); }, [route.id]);
```

Add a helper beside the existing `firstOperation`:

```tsx
/** The workflow's opener, but only for someone who may actually perform it.
 *  A nurse who cannot register must be cued to their queue, not to a button
 *  the guard will refuse. */
function openerFor(cat: Catalogue, workflow: string | undefined, facility?: Facility) {
  const id = firstOperation(cat, workflow);
  const op = id ? cat.operations?.[id] : undefined;
  if (!op) return null;
  return facility?.user?.capabilities?.includes(op.capability) ? op : null;
}
```

- [ ] **Step 7: Style it**

Add to `web/src/theme.css`, using existing tokens only — no new colours:

```css
.close { border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
         display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.close-h { font-weight: 600; flex: 1; }
.close-e { color: var(--muted); }
.close-u { background: none; border: 0; color: var(--muted); cursor: pointer; }
```

- [ ] **Step 8: Verify the front desk loop by keyboard alone**

Run the app. As `frontdesk`, register a patient. Confirm: the close card appears
reading `Register a new patient → nurse`, the cue button holds focus, **Enter**
opens an empty registration form with the cursor in the first field, and the
queue was never visited.

- [ ] **Step 9: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/loops.ts web/src/loops.check.ts web/src/CloseCard.tsx web/src/main.tsx web/src/theme.css
git commit -m "Close every task with a card that offers the next one"
```

---

### Task 4: The instrument opens; nothing offers to open it

**Files:**
- Modify: `web/src/main.tsx` (open the primary action's panel on arrival)
- Modify: `web/src/loops.check.ts` (append)

**Interfaces:**
- Consumes: `weigh` (Task 2), `Operation.instrument`.
- Produces: `web/src/loops.ts` exporting `opensOnArrival(op: Operation | undefined): boolean`.

- [ ] **Step 1: Write the failing check**

Append to `web/src/loops.check.ts`, before its `console.log`:

```ts
// -- how much AI a role touches is declared, never coded --------------------
import { opensOnArrival } from "./loops.ts";

ok(opensOnArrival(register), "registration opens on arrival");
ok(register.instrument === "form", "and it is a form, which is why front desk sees no AI");
ok(op("phc.op.vitals-record").instrument === "device", "vitals declares a device");
ok(op("phc.op.consult-document").instrument === "scribe", "the consultation declares the scribe");
ok(!opensOnArrival(undefined), "nothing to open is not an open");

// Irreversible work is never opened for someone who did not ask for it.
ok(!opensOnArrival(op("phc.op.abha-link")), "an irreversible operation waits to be asked for");
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `opensOnArrival is not a function`.

- [ ] **Step 3: Write the minimal implementation**

Append to `web/src/loops.ts`:

```ts
/** Whether arriving at a thread should open this operation's instrument
 *  straight away, rather than draw a button that offers to.
 *
 *  Everything correctable opens. An irreversible operation does not: opening a
 *  national identity journey over the screen every time someone arrives is how
 *  a person learns to dismiss it, and dismissing is the habit that makes the
 *  confirm step meaningless.
 */
export function opensOnArrival(op: Operation | undefined): boolean {
  return !!op && op.irreversibility !== "irreversible";
}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ok   18 loop checks`.

- [ ] **Step 5: Open it on arrival**

In `web/src/main.tsx`, where the thread route renders, add an effect that opens
the primary action's panel once per thread:

```tsx
  // The instrument is the screen, not a thing a button offers to fetch. Once
  // per thread: reopening after a person closes it is a trap, not a default.
  const openedFor = useRef<string | null>(null);
  useEffect(() => {
    if (route.kind !== "thread" || !thread.data || modal || closed) return;
    if (openedFor.current === route.id) return;
    const { primary } = weigh(thread.data.actions, thread.data.closes);
    if (!opensOnArrival(primary)) return;
    openedFor.current = route.id;
    setModal({ op: primary!, thread: route.id });
  }, [route.kind, route.id, thread.data, modal, closed]);
```

- [ ] **Step 6: Verify each role gets what its operations declare**

Run the app and check three roles. As `frontdesk` on a new thread: a form opens,
focused, and no microphone or scribe control is anywhere on screen. As `nurse` on
a registered thread: the vitals pad opens. As `mo` on a consented thread: the
scribe opens. Confirm closing the panel does not reopen it.

- [ ] **Step 7: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/loops.ts web/src/loops.check.ts web/src/main.tsx
git commit -m "Open the primary action's instrument on arrival instead of offering to"
```

---

### Task 5: Other stations collapse to one line

**Files:**
- Modify: `web/src/Thread.tsx` (the said/card list)

**Interfaces:**
- Consumes: `ThreadView.audit`, `ThreadView.station`, `Operation.station`.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Write the failing check**

Append to `web/src/loops.check.ts`, before its `console.log`:

```ts
// -- a role sees its own work, not the handover log -------------------------
import { mine } from "./loops.ts";

ok(mine(op("phc.op.vitals-record"), "nurse"), "the nurse's own work stays open");
ok(!mine(register, "nurse"), "reception's finished form collapses for the nurse");
ok(mine(register, "reception"), "and stays open for the clerk who filled it");
ok(mine(register, null), "a complete line collapses nothing");
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `mine is not a function`.

- [ ] **Step 3: Write the minimal implementation**

Append to `web/src/loops.ts`:

```ts
/** Whether a committed operation's card belongs open on this screen.
 *
 *  The nurse opening onto reception's six-row registration form is workflow
 *  fragmentation: someone else's completed context, above her own task. It
 *  collapses to one line she can expand. Once the line is complete there is no
 *  current station and nothing collapses, because the whole visit is the
 *  subject then.
 */
export function mine(op: Operation, station: string | null): boolean {
  return station === null || op.station === station;
}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ok   22 loop checks`.

- [ ] **Step 5: Collapse them in the renderer**

In `web/src/Thread.tsx`, each posted operation card is rendered from a `said`
entry that carries its operation id. Wrap any card where
`!mine(cat.operations[opId], thread.station)` in a `<details>` whose `<summary>`
is one line — the operation's `short`, the actor, and the time, all of which the
audit record already carries:

```tsx
  <details className="folded">
    <summary>{op.short} · {a.actor ?? "—"} · {time(a.at)}</summary>
    {card}
  </details>
```

Style it flat in `web/src/theme.css`:

```css
.folded > summary { list-style: none; cursor: pointer; color: var(--muted);
                    padding: 6px 0; font-size: 13px; }
.folded > summary::-webkit-details-marker { display: none; }
```

- [ ] **Step 6: Verify**

Open a thread as `nurse` where reception has registered the patient. Confirm the
registration card is one grey line, that clicking it expands the full card, and
that the vitals pad is the first thing at full size.

- [ ] **Step 7: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/loops.ts web/src/loops.check.ts web/src/Thread.tsx web/src/theme.css
git commit -m "Collapse other stations' finished work to one line"
```

---

### Task 6: The records rail

**Files:**
- Modify: `web/src/Thread.tsx:361-430` (the right rail)
- Modify: `web/src/ViewRenderer.tsx:125-200` (`Sections`, add a `records` shape)
- Modify: `bundles/phc/phc.view.patient-summary.md` (rename to what it is)
- Modify: `bundles/lab/` equivalent summary view if it declares one

**Interfaces:**
- Consumes: `ViewResult.rows` per section, `SectionResult`.
- Produces: `web/src/loops.ts` exporting
  `records(sections: SectionResult[]): { title: string; count: number }[]`.

- [ ] **Step 1: Write the failing check**

Append to `web/src/loops.check.ts`, before its `console.log`:

```ts
// -- the rail is the declared summary, rendered as a list -------------------
import { records } from "./loops.ts";

const secs = [
  { title: "Visit", show: "line", rows: [] },
  { title: "Vitals", resource: "observation", rows: [{}, {}] },
  { title: "Notes", resource: "notes", rows: [{}] },
  { title: "Prescription", resource: "medication_request", rows: [] },
  { title: "Audit trail", show: "audit", rows: [{}] },
];
const r = records(secs);
ok(r.length === 2, "only sections that read a resource and have rows are records");
ok(r.every((x) => x.title !== "Audit trail"), "audit is events, not documents");
ok(r.every((x) => x.title !== "Visit"), "the line is not a document");
ok(r[0].title === "Vitals" && r[0].count === 2, "a record carries its count");
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `records is not a function`.

- [ ] **Step 3: Write the minimal implementation**

Append to `web/src/loops.ts` (add `SectionResult` to the type import):

```ts
/** The documents a thread produced, from the summary view's own sections.
 *
 *  A section that reads a resource is a kind of document; a section that shows
 *  a kernel structure (the line, the flags, the actions, the audit) is not.
 *  These are also ABDM's units — Prescription, DiagnosticReport,
 *  OPConsultation — so the rail and the ABHA share sheet list the same things.
 *
 *  Audit is deliberately excluded even though it has rows. The guard writes
 *  audit before execute, so there are rows for denials and rejected proposals:
 *  events that produced no document. Those belong in the visit collation. The
 *  rail is what exists; the collation is what happened.
 */
export function records(sections: SectionResult[]): { title: string; count: number }[] {
  return sections
    .filter((s) => s.resource && s.rows.length > 0)
    .map((s) => ({ title: s.title, count: s.rows.length }));
}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `ok   26 loop checks`.

- [ ] **Step 5: Replace four rail panels with two**

In `web/src/Thread.tsx`, in the right rail beginning at line 361:

- Keep the "Where this stands" panel that renders `thread.line`. It is the live
  loop and it is germane.
- **Delete the "Capabilities held" panel entirely** (lines 406-415, the block
  mapping `thread.capabilities` into `cap` spans). It is a permissions debug
  panel. Also delete the now-unused `capabilities` and `held` reads in this file;
  leave the fields on the contract, which other surfaces may use.
- **Delete the "Care unit" panel.**
- **Replace the "Audit trail" panel with Records**, built from `records(...)` over
  the summary view's sections, each row opening that section:

```tsx
  <div className="card">
    <div className="card-t">Records</div>
    {rs.length === 0
      ? <div className="close-e">Nothing yet</div>
      : rs.map((r) => (
          <button key={r.title} className="rec" onClick={() => onSummary(summaryView)}>
            <span>{r.title}</span>
            {r.count > 1 && <span className="rec-n">{r.count}</span>}
          </button>
        ))}
  </div>
```

Audit remains reachable through the summary sheet, which already declares an
`Audit trail` section.

- [ ] **Step 6: Rename the misnamed view**

In `bundles/phc/phc.view.patient-summary.md`, the title is already
`Visit summary` and the summary is already `One visit on one page`, so the prose
is honest and only the id lies. Renaming an atom id changes
`bundles/phc/bundle.yaml`, the manifest, and anything referencing it. Do it in
one commit:

```bash
git mv bundles/phc/phc.view.patient-summary.md bundles/phc/phc.view.visit-summary.md
```

Then update `id:` inside that file, the `views:` list in `bundles/phc/bundle.yaml`,
and grep the tree for the old id:

```bash
grep -rn "phc.view.patient-summary" --exclude-dir=node_modules --exclude-dir=.git .
```

Update every hit, then recompile:

```bash
python3 -m catalogue.build && python3 -m kernel.declarations
```

- [ ] **Step 7: Verify the word count came down**

With the app running, on a nurse's thread, in the browser console:

```js
const v=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0};
[...document.querySelectorAll('*')].filter(e=>v(e)&&!e.children.length&&e.textContent.trim())
  .map(e=>e.textContent.trim().split(/\s+/).length).reduce((a,b)=>a+b,0)
```

Expected: well under the 178 this started at. Record the number in the commit
message. If it is not under 100, something in the deletions was missed.

- [ ] **Step 8: Run the gate and commit**

```bash
sh scripts/check.sh
git add -A
git commit -m "Show the records a thread produced instead of the permission model"
```

---

### Task 7: Consent, spoken by the agent

**Files:**
- Create: `bundles/phc/phc.inst.consent-speak.md`
- Modify: `bundles/phc/bundle.yaml` (add to `instruments:`)
- Modify: `questionnaires/phc.schema.register-v1.json` (the copy)
- Modify: `kernel/declarations.py` (lint the new instrument kind)
- Modify: `bundles/phc/check.py` (append)

**Interfaces:**
- Consumes: the instrument atom shape already used by `phc.inst.vitals-voice`.
- Produces: instrument id `phc.inst.consent-speak` with `kind: spoken-prompt` and a `says` string.

- [ ] **Step 1: Write the failing check**

Append to `bundles/phc/check.py`:

```python
# The consent read-out is the agent's line, not 53 words the clerk performs.
SPOKEN = ("May we record this visit to write your notes? "
          "You can say no, or stop it any time.")

inst = BUNDLE.instruments["phc.inst.consent-speak"]
assert inst["kind"] == "spoken-prompt"
assert inst["says"] == SPOKEN, inst["says"]
# Four things, and shortening further drops one: that it is a recording, what
# for, that refusal is free, that it can be stopped.
for must in ("record", "notes", "say no", "stop"):
    assert must in SPOKEN.lower(), must

schema = json.load(open("questionnaires/phc.schema.register-v1.json"))
consent = [q for q in schema["questions"] if q["link_id"] == "capture_consent"][0]
assert consent["text"] == "Record this visit?", consent["text"]
assert "description" not in consent, "the 53 word read-out moved to the spoken line"
```

Add `import json` to that file if it is not already imported.

- [ ] **Step 2: Run it to verify it fails**

```bash
python3 -m bundles.phc.check
```

Expected: `KeyError: 'phc.inst.consent-speak'`.

- [ ] **Step 3: Write the instrument atom**

Create `bundles/phc/phc.inst.consent-speak.md`:

```markdown
---
id: phc.inst.consent-speak
type: instrument
kind: spoken-prompt
title: Ask for consent aloud
summary: The agent asks; the clerk taps what the patient answered.
operations: [phc.op.patient-register]
fields: [capture_consent, capture_declined]
says: >-
  May we record this visit to write your notes?
  You can say no, or stop it any time.
language: facility
spoken: true
commit: tap
fallback: text
---

## In plain words

The clerk used to read fifty-three words off the screen to every patient, at a
counter, with a queue behind them. Nobody reads fifty-three words the fortieth
time, so the consent became a tick. The agent says the line instead, in the
facility's language, and the clerk taps what the patient answered.

Seventeen words carrying four things: that it is a recording, what it is for,
that saying no is free, and that it can be stopped. Dropping any one of them
makes it not a consent, which is why the linter checks the sentence rather
than trusting a later edit.

## Where this is asked

At reception, on the registration form, not in the consulting room. The
recording it authorises happens later at the doctor. That costs the doctor no
consultation time, and by the time the scribe is available the answer is
already a thread flag.

## The off switch

`spoken` on this atom is the default; a facility setting overrides it. When it
resolves false the sentence renders on screen for a person to read and nothing
else changes. The linter refuses a `spoken-prompt` with an empty `says`,
because the off switch must always have something to fall back to.

## What this cannot do

It cannot commit. It sets no flag. The clerk's tap is what raises
`capture.agreed` or `capture.declined`, through the same form validation every
other answer goes through. A prompt that recorded its own answer would be a
consent nobody gave.

## Withdrawal

`phc.op.capture-withdraw` is the doctor's, asks one question, and is absent
unless there is a consent to withdraw. A consent that cannot be withdrawn is
not a consent.
```

Add `phc.inst.consent-speak` to the `instruments:` list in `bundles/phc/bundle.yaml`.

- [ ] **Step 4: Lint the new kind**

In `kernel/declarations.py`, find where instrument `kind` values are validated and
add `spoken-prompt`, with the rule the atom's prose promises:

```python
        if kind == "spoken-prompt":
            if not (decl.get("says") or "").strip():
                fail(f"{iid}: a spoken-prompt with no `says` has nothing to fall "
                     f"back to when a facility turns the voice off")
```

- [ ] **Step 5: Cut the copy**

In `questionnaires/phc.schema.register-v1.json`, on `capture_consent`: set
`"text": "Record this visit?"` and **delete the `description` key entirely**.
Leave `styling_metadata` untouched — the `flags` and `short` there are load-bearing.

- [ ] **Step 6: Run the checks to verify they pass**

```bash
python3 -m catalogue.build && python3 -m kernel.declarations && python3 -m bundles.phc.check
```

Expected: PASS. `bundles/phc/check.py` already asserts consent is raised,
declined, scoped to the visit and withdrawable; all four must still pass.

- [ ] **Step 7: Prove the linter bites**

Commit first, because this step deliberately breaks a file:

```bash
git add -A && git commit -m "Speak the consent line instead of making the clerk read it"
```

Then blank the `says:` value in the atom, run `python3 -m kernel.declarations`,
confirm it fails with the new message, and restore:

```bash
git checkout bundles/phc/phc.inst.consent-speak.md
```

- [ ] **Step 8: Run the gate**

```bash
sh scripts/check.sh
```

Expected: `all checks passed`.

---

### Task 8: The deletions

**Files:**
- Modify: `web/src/Home.tsx` (hero, second search box, the two chips)
- Modify: `web/src/main.tsx` (the topbar's API URL)
- Modify: `web/src/Thread.tsx` (badges, duplicated identity)
- Modify: `web/src/messages.ts` (agent narration of on-screen cards)
- Modify: `web/src/messages.check.ts` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing check**

Append to `web/src/messages.check.ts`, before its summary line:

```ts
// -- the agent narrates nothing already on screen ---------------------------
// Prose restating a card is the most common fluff, and it is written here, so
// it is refusable here. The card carries the operation's own title; a sentence
// that repeats it is a sentence with no reader.
const lines = Object.values(MESSAGES).filter((m) => typeof m === "string") as string[];
for (const line of lines) {
  assert.ok(!/was confirmed by .* at \d/.test(line),
    `FAIL narration restates a posted card: ${line}`);
  assert.ok(!/I have no way to do that/.test(line),
    `FAIL a refusal that offers nothing is a dead end: ${line}`);
}
```

`web/src/messages.ts` is the only place this prose is written. Import whatever it
exports as its message table; if it exports named constants rather than one
object, collect them with
`const lines = Object.values(await import("./messages.ts")).filter((m) => typeof m === "string") as string[];`
so the check covers every line the module can produce, not a list that drifts.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/messages.check.ts
```

Expected: FAIL naming the narration line.

- [ ] **Step 3: Make the deletions**

`web/src/Home.tsx`:
- Delete the `hero-h` greeting (`Good morning/afternoon/evening` and the `hour`
  computation feeding it). No declaration carries opening hours and it is a third
  of the fold for no work value.
- Delete the `hero-ask` block. The topbar search is the same control.
- Delete the `chips` block. Both chips duplicate sidebar nav items directly above.
- Keep the `hero-eye` role and facility line, and keep the live board — promote
  the board to the top of the page.

`web/src/main.tsx`: delete the `API_BASE` text node from the topbar. A developer
who needs it has the network tab.

`web/src/Thread.tsx`:
- Delete the `DEVICE` / `IRREVERSIBLE` / `SCRIBE` badges from the action rows.
  Irreversibility is already confirm behaviour in `OperationPanel`; a red label
  on a button is decoration on top of a control that already stops.
- Delete the `frontdesk` / `form` badges from posted cards. The collapsed summary
  from Task 5 already names the actor and the instrument.
- Delete the identity block that repeats what the topbar shows. Keep one: the
  topbar keeps name and station, the card keeps age, sex and village.

`web/src/messages.ts`: delete the narration template that restates a posted card,
and the `I have no way to do that` line. Where the agent has proposed something,
the proposal's own confirm control is the answer; a sentence saying it cannot
confirm is a dead end in prose.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/messages.check.ts && npm run check
```

Expected: PASS, and no unused-variable errors from the deletions.

- [ ] **Step 5: Verify the count**

With the app running, on the nurse's thread, in the console:

```js
const v=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0};
JSON.stringify({
  interactive: [...document.querySelectorAll('button,a,input,select,textarea,[role=button]')].filter(v).length,
  words: [...document.querySelectorAll('*')].filter(e=>v(e)&&!e.children.length&&e.textContent.trim())
    .map(e=>e.textContent.trim().split(/\s+/).length).reduce((a,b)=>a+b,0),
})
```

Baseline was `{interactive: 28, words: 178}`. Record the new numbers in the commit
message.

- [ ] **Step 6: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/Home.tsx web/src/main.tsx web/src/Thread.tsx web/src/messages.ts web/src/messages.check.ts
git commit -m "Delete the chrome, the duplicate controls, and the narration"
```

---

### Task 9: The three defects found while measuring

**Files:**
- Modify: `web/src/Home.tsx` (the board's row click)
- Modify: `web/src/main.tsx` (the error boundary's recovery)
- Modify: `web/src/Shell.tsx:30-45` (`recents`)
- Modify: `.claude/launch.json`

**Interfaces:**
- Consumes: `recents()`, `remember()` from `web/src/Shell.tsx`.
- Produces: `web/src/Shell.tsx` exporting `keep(rs: Recent[], live: string[]): Recent[]`.

- [ ] **Step 1: Write the failing check**

Append to `web/src/loops.check.ts`, before its `console.log`:

```ts
// -- recents point at threads that still exist ------------------------------
import { keep } from "./Shell.tsx";

const rs = [{ id: "enc-1", name: "Kamala Devi" }, { id: "962", name: "962" }];
ok(keep(rs, ["enc-1"]).length === 1, "a recent the kernel no longer serves is dropped");
ok(keep(rs, ["enc-1"])[0].id === "enc-1", "and the live one is kept");
ok(keep(rs, []).length === 0, "nothing live means no recents");
// A reseed changes every id, which is how eight dead tokens came to be nav.
ok(keep(rs, ["enc-9"]).length === 0, "a reseed clears them rather than leaving 404s");
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/loops.check.ts
```

Expected: `keep is not a function`.

- [ ] **Step 3: Fix the three defects**

**Recents.** In `web/src/Shell.tsx`, add beside `recents()`:

```ts
/** Recents the kernel still serves. A reseed changes every thread id, and the
 *  list survives it in localStorage, so the sidebar filled with dead tokens
 *  that 404 on click. Filtering on read is cheaper than any bookkeeping. */
export function keep(rs: Recent[], live: string[]): Recent[] {
  const known = new Set(live);
  return rs.filter((r) => known.has(r.id));
}
```

Call it where the shell has the queue result, passing `rows.map(r => r.thread)`.

**The board's dead click.** In `web/src/Home.tsx`, the `fl-p` row calls
`onOpenThread(r.thread)`, which reaches `remember()` but not navigation. Trace
`onOpenThread` from `Home` through `main.tsx` and confirm it is the handler that
calls `go()`; the board is currently wired to a different prop than the one that
navigates. Wire it to the same `openThread` the sidebar uses.

**The stuck error state.** In `web/src/main.tsx`, `Boundary` is keyed on
`${route.kind}-${route.id}-${demo}-${role}`, which should remount on a hash
change — but `parse()` at line 38-39 splits on `/` and the thread route is
`#/threads/<id>`, so a hash of `#/thread/<id>` yields an empty id and the boundary
renders `Nothing at /views/thread/.`. Make `parse` return a route the app can
recognise as unroutable, and have the error state's **Try again** button navigate
Home rather than retry a fetch that cannot succeed.

**The launch config.** In `.claude/launch.json`, `web-lab` runs `dev:lab` but
there is no way to point it at the laboratory API, so it starts against the PHC
on :8000 and the name is a lie. Add the env the lab kernel needs, or rename the
configuration to what it actually starts.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/loops.check.ts && npm run check
```

Expected: `ok   30 loop checks` and a clean typecheck.

- [ ] **Step 5: Verify in the browser**

Clear `localStorage`, reseed, and reload. Confirm: the sidebar shows no dead
tokens; clicking a patient on the home board opens that thread; navigating to a
bad thread id and then clicking **Try again** reaches Home instead of staying
stuck.

- [ ] **Step 6: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/Shell.tsx web/src/Home.tsx web/src/main.tsx web/src/loops.check.ts .claude/launch.json
git commit -m "Fix the dead board click, the stuck error state, and stale recents"
```

---

### Task 10: The keyboard, because front desk is a typist

**Files:**
- Modify: `web/src/Form.tsx`
- Modify: `web/src/OperationPanel.tsx`
- Create: `web/src/keys.check.ts`
- Modify: `scripts/check.sh`

**Interfaces:**
- Consumes: `Questionnaire.questions` (ordered), `OperationPanel`'s commit handler.
- Produces: nothing later tasks depend on.

Principle 9 of the spec: Enter commits, Escape cancels, Tab never traps. For a
clerk registering 40-80 patients a day with a queue at the counter, the mouse is
a failure mode, not a fallback.

- [ ] **Step 1: Write the failing check**

Create `web/src/keys.check.ts`:

```ts
/** The keyboard contract for a form-instrument operation.
 *
 *  Run: node --experimental-strip-types src/keys.check.ts   (from web/)
 *
 *  Asserted against the source rather than a rendered DOM, because the thing
 *  that breaks is someone adding a control without a tabIndex, not a runtime
 *  bug. No mic, no browser, no server.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const panel = read("src/OperationPanel.tsx");
ok(/onKeyDown/.test(panel), "the panel handles keys at all");
ok(/key === "Escape"/.test(panel), "Escape is handled");
ok(/key === "Enter"/.test(panel), "Enter is handled");
// Enter inside a textarea is a newline, not a commit. Committing a
// consultation note because someone pressed return mid-sentence is the bug
// this line exists to stop.
ok(/textarea/i.test(panel), "Enter is not a commit inside a textarea");

const form = read("src/Form.tsx");
ok(!/tabIndex={-1}/.test(form), "no field is removed from the tab order");
ok(/autoFocus/.test(form), "the first field takes focus without a click");

console.log(`ok   ${checks} keyboard checks`);
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && node --experimental-strip-types src/keys.check.ts
```

Expected: FAIL on the first assertion the source does not yet satisfy.

- [ ] **Step 3: Write the minimal implementation**

In `web/src/OperationPanel.tsx`, on the panel's root element:

```tsx
      onKeyDown={(e) => {
        if (e.key === "Escape") { e.preventDefault(); onCancel(); return; }
        // Enter commits, except inside a textarea, where it is a newline. A
        // consultation note committed because someone pressed return
        // mid-sentence is worse than one extra tap.
        const inText = (e.target as HTMLElement)?.tagName?.toLowerCase() === "textarea";
        if (e.key === "Enter" && !inText && !busy) { e.preventDefault(); void submit(); }
      }}
```

Use the existing names for the cancel handler, the busy flag and the commit
function in that file; do not introduce new ones.

In `web/src/Form.tsx`, give the first rendered question `autoFocus`, and render
fields in `questions` order so tab order follows the schema's own `link_id`
order:

```tsx
  {questions.map((q, i) => (
    <Field key={q.link_id} q={q} autoFocus={i === 0} ... />
  ))}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd web && node --experimental-strip-types src/keys.check.ts && npm run check
```

Expected: `ok   6 keyboard checks` and a clean typecheck.

- [ ] **Step 5: Register the check**

In `scripts/check.sh`, beside the loops check:

```sh
  (cd web && node --experimental-strip-types src/keys.check.ts)
```

- [ ] **Step 6: Walk the whole front desk loop with no mouse**

Run the app as `frontdesk`. From the close card, press **Enter**, type a name,
**Tab** through every field, press **Enter** to commit, and confirm the next
empty form opens focused. The mouse must not be touched once. Any field that
needs a click is a defect in this task, not a later one.

- [ ] **Step 7: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/Form.tsx web/src/OperationPanel.tsx web/src/keys.check.ts scripts/check.sh
git commit -m "Make the front desk loop reachable without a mouse"
```

---

### Task 11: Role presets, and editing away from them

**Files:**
- Create: `web/src/Roles.tsx`
- Modify: `web/src/Shell.tsx` (the role menu opens it)
- Modify: `api/main.py` (one read, one write)
- Modify: `api/tests/test_api.py` (append)

**Interfaces:**
- Consumes: `Catalogue.bundles` (role id to capability list — already served),
  `Catalogue.operations[].capability`, `Facility.roles`.
- Produces:
  - `GET /api/v1/phc/roles` -> `{ presets: Record<string, string[]>, current: string }`
  - `PUT /api/v1/phc/roles/{role}` with body `{ capabilities: string[] }` -> the saved set.
  - `web/src/Roles.tsx` exporting `inert(cap: string, cat: Catalogue): boolean`.

The spec's claim is that configuration is a consequence, not a feature: grant
`vitals.record` to frontdesk and they get the vitals pad and the loop, with no UI
work per grant. `kernel/proposals._decide` gates on `drawn_by` then capability
then preconditions and never on the actor's station, so this already holds. What
is missing is only a place to edit the set — and an honest signal when a grant
will do nothing.

- [ ] **Step 1: Write the failing check**

Append to `api/tests/test_api.py`:

```python
def test_roles_lists_presets_and_saves_a_deviation():
    c = client()
    got = c.get("/api/v1/phc/roles").json()
    # The nine in bundle.yaml are the presets, and they are the 70%.
    assert "frontdesk" in got["presets"] and "nurse" in got["presets"]
    assert "patient.register" in got["presets"]["frontdesk"]
    assert "vitals.record" not in got["presets"]["frontdesk"]

    # Enabling a function for a role is a capability grant and nothing else.
    body = {"capabilities": got["presets"]["frontdesk"] + ["vitals.record"]}
    saved = c.put("/api/v1/phc/roles/frontdesk", json=body).json()
    assert "vitals.record" in saved["capabilities"]

    # And the preset is untouched: a facility's own combination never edits
    # the shipped role.
    again = c.get("/api/v1/phc/roles").json()
    assert "vitals.record" not in again["presets"]["frontdesk"]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python3 -m api.tests.test_api
```

Expected: 404 on `/api/v1/phc/roles`.

- [ ] **Step 3: Write the minimal implementation**

In `api/main.py`, beside the other catalogue reads:

```python
@app.get(_p("/roles"))
def roles(request: Request):
    """The shipped presets, and who is asking.

    Presets are bundle.yaml's `roles:` and are read only here. A facility's own
    combination is saved separately, which is what CARE's sync_permissions_roles
    deliberately does not touch.
    """
    return {"presets": dict(BUNDLE.roles), "current": caller(request)["role"]}


@app.put(_p("/roles/{role}"))
def set_role(role: str, body: dict, request: Request):
    require(caller(request), "facility.admin")
    caps = sorted(set(body.get("capabilities") or []))
    unknown = [c for c in caps if c not in BUNDLE.capabilities]
    if unknown:
        raise HTTPException(400, f"not capabilities of this bundle: {unknown}")
    OVERRIDES[role] = caps          # facility role, never the preset
    return {"role": role, "capabilities": caps}
```

Use this file's existing helpers for the path prefix, the caller and the
capability assertion rather than the names above if they differ. `OVERRIDES` is a
module-level dict for now.

```python
# ponytail: in-process overrides, one facility per kernel. Persist to the store
# when a second facility shares a process.
OVERRIDES: dict[str, list[str]] = {}
```

Have whatever builds the caller's capability set prefer `OVERRIDES.get(role)`
over `BUNDLE.roles[role]`, so a grant takes effect on the next request.

- [ ] **Step 4: Run it to verify it passes**

```bash
python3 -m api.tests.test_api
```

Expected: PASS.

- [ ] **Step 5: Build the editor, and say when a grant is inert**

Create `web/src/Roles.tsx`. A role, its capabilities as checkboxes grouped by the
operation each one unlocks, a **Reset to preset** control, and one honest signal:

```tsx
/** A capability the workflow gives no way to exercise.
 *
 *  `drawn_by` refuses any operation this workflow has no step for, so granting
 *  visit.household to a clinic role does nothing at all — phc.op.household-visit
 *  stands at `community` and the outpatient line has no such station. That is
 *  the guard that stopped it appearing as a button on every clinic encounter.
 *  A switch that silently does nothing is worse than one that explains itself.
 */
export function inert(cap: string, cat: Catalogue): boolean {
  const wf = Object.values(cat.workflows ?? {})[0];
  const drawn = new Set((wf?.steps ?? []).flatMap((s) => s.operations));
  return !Object.values(cat.operations ?? {})
    .some((op) => op.capability === cap && drawn.has(op.id));
}
```

Render an inert capability disabled, with the reason beside it: *"The outpatient
line has no community station."* Build that sentence from the operation's own
`station` and the workflow's title — never a hard-coded string.

- [ ] **Step 6: Prove the claim end to end**

Run the app. As an admin, grant `vitals.record` to `frontdesk` and save. Switch
to `frontdesk`, open a registered thread, and confirm **the vitals pad is there
and folds into the loop with no other change** — that is the whole claim. Then
remove `assessment.record` from `nurse` and confirm it disappears. Then try to
grant `visit.household` and confirm the switch is disabled with its reason shown,
rather than granting something the guard will refuse.

- [ ] **Step 7: Run the gate and commit**

```bash
sh scripts/check.sh
git add web/src/Roles.tsx web/src/Shell.tsx api/main.py api/tests/test_api.py
git commit -m "Let a facility grant and remove functions per role, away from the presets"
```

---

## Phase 2 (not in this plan)

The patient spine is specified in the design doc and deliberately excluded here.
It needs a patient-scoped read — `select` and `count` taking either `thread=` or
`subject=` — which widens the Store protocol and obliges the CARE adapter, which
has never run against an authenticated CARE. Nothing in Tasks 1-9 forecloses it:
the records rail groups by nothing today and gains visit groups when the spine
lands.

## Known limits carried forward

- Scope qualifiers remain unexpressible per role, so "record vitals only for
  patients at my own station" still needs a `scope_qualifier` on the operation.
- A capability grant for an operation the workflow does not draw is inert, by
  `drawn_by`. Task 1 does not change this; the admin surface that explains it is
  not in this plan.
- Browser speech accuracy for the spoken consent prompt is untested and needs a
  microphone, so no check here covers it.
- `kernel/contracts.py` says the Store has nine methods; it declares ten.
