/** Home: three bands in order (resume/facility, live scale, plate stack),
 *  plates reordered by pointer events plus setPointerCapture -- never HTML5
 *  drag-and-drop, which is why this file asserts its absence rather than its
 *  shape -- and order remembered per viewer by the card's own declaration id
 *  (not by anything in the data), which is what makes it survive a reseed.
 *
 *  Run: node --experimental-strip-types src/home.check.ts   (from web/)
 *
 *  What a text check can prove and what it cannot: it can prove the handle
 *  carries no draggable attribute and no dataTransfer, that pointerdown calls
 *  setPointerCapture, that exactly one function is named move(, and that both
 *  the keyboard branch and the pointer-drop path route through the same
 *  reorder() wrapper that calls it. It cannot press a key or synthesise a
 *  pointer drag in a real DOM and watch two plates swap; that is a browser's
 *  job, confirmed by hand against the running app and reported alongside
 *  this run (forward drag, backward drag, and the keyboard twin, each
 *  producing the identical resulting order) rather than repeated by it. What
 *  this check would catch that a browser check would not: the handle quietly
 *  regaining a draggable attribute, or a second reorder function appearing
 *  that splices differently -- exactly the two-semantics-in-one-component bug
 *  (moveBy swapped, dropOnto spliced) the previous build shipped with.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const src = read("web/src/Home.tsx");
const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
const stripped = strip(src);

// -- three bands, in this order: resume/facility, the live scale, the stack -
const iResume = src.indexOf('<ResumeBand');
const iScale = src.indexOf('<LiveScale');
const iStack = src.indexOf('className="stack"');
ok(iResume >= 0 && iScale > iResume, "the resume band is written before the live scale");
ok(iStack > iScale, "the plate stack is written after the live scale");

// -- the greeting is gone, root and branch: no .greet anywhere, and the
// resume band's own fallback text draws facility/date/role, never a "Good
// morning" clock -----------------------------------------------------------
ok(!/\bgreet\b/.test(stripped), "no .greet class or word survives Home.tsx");
ok(/cat\.manifest\?\.title/.test(src) && /roleLabel/.test(src),
  "the resume band's fallback reads the facility and the role, not a greeting");

// -- HTML5 drag-and-drop is deleted, not fixed: it never fires on touch, and
// dropOnto always spliced the source BEFORE the destination, a silent no-op
// for every forward drag ----------------------------------------------------
ok(!/draggable/.test(src), "no draggable attribute anywhere in Home.tsx");
ok(!/dataTransfer/.test(src), "no dataTransfer anywhere in Home.tsx");
ok(!/onDragStart|onDragEnter|onDragLeave|onDragOver|onDrop\b/.test(src),
  "no HTML5 drag event handler anywhere in Home.tsx");
ok(!/\bmoveBy\b|\bdropOnto\b/.test(stripped), "the old two-semantics functions (moveBy, dropOnto) are gone");

// -- pointer events plus setPointerCapture on the handle, and nothing about
// the gesture lives in useState (a ref plus direct DOM writes instead, so a
// pointer crossing does not re-render every plate body) --------------------
ok(/onPointerDown/.test(src) && /setPointerCapture/.test(src),
  "pointerdown on the handle calls setPointerCapture");
ok(/onPointerMove/.test(src) && /onPointerUp/.test(src) && /onPointerCancel/.test(src),
  "the handle tracks pointermove, pointerup and pointercancel");
const dragStateBlock = src.slice(src.indexOf("const drag = useRef<"), src.indexOf("const drag = useRef<") + 40);
ok(/useRef</.test(dragStateBlock), "drag state lives in a ref, not useState");
ok(!/\[dragging,\s*setDragging\]|\[dragOver,\s*setDragOver\]/.test(src),
  "dragging/dragOver are not useState -- the exact re-render thrash the spec measured");

// -- the handle: a real button, an accessible name per plate, 4px of travel
// before a click becomes a drag is not asserted here (it is a runtime
// threshold, not source shape a text check can see; confirmed by hand) ----
const plateFn = src.slice(src.indexOf("function Plate("), src.indexOf("function Plate(") + 900);
ok(/type="button"/.test(plateFn), "the handle is a real <button type=\"button\">, not a div with a role");
ok(/aria-label=\{`Reorder \$\{plateTitle\}`\}/.test(plateFn), "the handle has a per-plate accessible name");
ok(/plate-handle/.test(plateFn), "the handle carries its own class for the zero-layout-box CSS");

// -- keyboard reorder: ArrowUp/ArrowDown/Home/End/Escape, all routed through
// the same reorder() this file's pointer path also calls -------------------
// Comment-stripped: a mutation's own explanatory comment can otherwise
// mention "reorder(" in prose and satisfy a regex looking for the real call.
const keyFn = stripped.slice(stripped.indexOf("function onKeyDown("), stripped.indexOf("function onKeyDown(") + 900);
ok(/ArrowUp/.test(keyFn) && /ArrowDown/.test(keyFn), "the keyboard branch handles ArrowUp and ArrowDown");
ok(/"Home"/.test(keyFn) && /"End"/.test(keyFn), "the keyboard branch handles Home and End");
ok(/"Escape"/.test(keyFn) && /focusOrigin/.test(keyFn), "Escape restores the index recorded on focus");
ok(/preventDefault\(\)/.test(keyFn), "the handler prevents the browser's own scroll-on-arrow-key");
// Anchored per branch, not just "reorder( appears >=N times somewhere in the
// function": a mutation that gave ArrowDown its own inline splice (the exact
// two-semantics-in-one-component bug) still left enough OTHER branches
// calling reorder() to clear a bare count threshold, so it passed a looser
// version of this check. Requiring each key's own branch to reach reorder(
// before the next branch starts is what actually closes that hole.
for (const key of ["ArrowUp", "ArrowDown", "Home", "End"]) {
  const at = keyFn.indexOf(`"${key}"`);
  ok(at >= 0, `the keyboard branch has a case for ${key}`);
  const branch = keyFn.slice(at, at + 160);
  const nextCase = branch.slice(1).search(/else if \(e\.key ===/);
  const scoped = nextCase === -1 ? branch : branch.slice(0, nextCase + 1);
  ok(/\breorder\(/.test(scoped), `${key} calls reorder(), not a private splice of its own`);
}

// -- ONE move function, shared: today's build has a single splice-out/
// splice-in move(), called from exactly one place (reorder()), which is
// itself the only thing either input path calls. Two semantics in one
// component (a swap here, a splice there) is exactly the bug this closes. -
const moveDefs = stripped.match(/function move[<(]/g) ?? [];
ok(moveDefs.length === 1, `exactly one function named move( exists (found ${moveDefs.length})`);
ok(/next\.splice\(to,\s*0,\s*next\.splice\(from,\s*1\)\[0\]\)/.test(src),
  "move() is the spec's own splice-out/splice-in, not a neighbour swap");
const reorderFn = src.slice(src.indexOf("function reorder("), src.indexOf("function reorder(") + 500);
ok(/persist\(move\(order,\s*from,\s*to\)\)/.test(reorderFn), "reorder() is the one call site for move()");
ok((stripped.match(/\breorder\(/g) ?? []).length >= 3,
  "reorder() itself is called from more than one place (the keyboard branch and the pointer-drop path)");

// -- the FLIP settle: First/Last/Invert/Play on transform only, and reduced
// motion lands in one frame rather than losing the affordance --------------
ok(/useLayoutEffect/.test(src), "the settle runs in useLayoutEffect, before the browser paints the new order");
ok(/getBoundingClientRect/.test(src), "First/Last are read via getBoundingClientRect, the actual FLIP technique");
ok(/requestAnimationFrame/.test(src), "Play is scheduled on the next frame, not applied in the same layout pass");
ok(/prefers-reduced-motion/.test(src), "a reduced-motion path exists");
ok(!/\btransform:\s*(scale|rotate)/.test(stripped), "no scale or rotation anywhere -- an instrument module slides, it does not tilt");

// -- one aria-live region announces a crossing; the current build has none,
// so a screen-reader user cannot tell whether a key did anything -----------
ok(/aria-live="polite"/.test(src), "an aria-live=\"polite\" region exists");
ok(/announceRef/.test(src) && /position \$\{index \+ 1\} of \$\{order\.length\}/.test(stripped),
  "the announcement names the plate's new position out of the total");

// -- order is per viewer (localStorage), keyed so a reseed does not lose it -
//
// `loadOrder()` reading `localStorage.getItem` is necessary but nowhere near
// sufficient: a check that only looked for "getItem or setItem, anywhere in
// the file" was satisfied by the read half alone, so a mutation that gutted
// `persist` down to `setOrder(next)` (dropping the write, the one line that
// actually makes an order survive a reload) still passed. Anchored on the
// `persist` function's own body instead, so the write half is what's tested.
ok(/localStorage\.getItem\(ORDER_KEY/.test(src), "order is read from the localStorage key");
const persistFn = src.slice(src.indexOf("const persist = "), src.indexOf("const persist = ") + 300);
ok(persistFn.length > 20, "the persist function exists to anchor this check on");
ok(/localStorage\.setItem\(ORDER_KEY,\s*JSON\.stringify\(next\)\)/.test(persistFn),
  "persist() actually writes the new order to localStorage, not just to React state");
ok(/setOrder\(next\)/.test(persistFn), "persist() also updates the state that renders, so the reorder is visible immediately");
ok(/ORDER_KEY\s*=\s*"phc\.home\.order\." \+ API_BASE/.test(src),
  "the key is scoped per kernel, the same reason Recents is (two kernels, two facilities)");
// The pool is built from decl.id (and the literal "recent"), never from a
// row's own field: that is what makes it survive a reseed, where the ids
// stay put but every row's content changes.
const poolBlock = src.slice(src.indexOf("const cardIds"), src.indexOf("const cardIds") + 300);
ok(/\.decl\.id/.test(poolBlock), "the reorderable pool is keyed by each view's declaration id");
ok(!/\.result\.rows/.test(poolBlock) && !/\.subject/.test(poolBlock),
  "the pool is not keyed by anything read out of a row's own data");

// -- reconciliation is against the id set, not the data, and is not lost to
// an initial empty render (queues/tasklists load asynchronously) ----------
ok(/function reconcile\(saved: string\[\], ids: string\[\]\)/.test(src),
  "reconcile takes a set of known ids, not a set of rows");
ok(/setOrder\(reconcile\(loadOrder\(\), ids\)\)/.test(src),
  "the reconciling effect re-reads storage rather than trusting a `prev` that can start empty");

// -- generic renderer: no station, flag or bundle word --------------------
const BUNDLE_WORDS = ["phc.op", "phc.wf", "phc.view", "lab.op", "lab.wf", "lab.view",
  "lab.ordered", "lab.resulted", "capture.consented", "capture.declined",
  "registered", "specimen.collected", "result.entered"];
for (const w of BUNDLE_WORDS) {
  ok(!stripped.includes(w), `Home.tsx names no bundle word ('${w}' absent)`);
}

// -- plates are drawn by the same generic renderer Task 5/10 built, not a
// second, parallel renderer living in Home; ViewRenderer.tsx owns the
// colour law's one write site, not this file --------------------------------
ok(/import \{ .*ViewRenderer.* \} from "\.\/ViewRenderer"/.test(src), "Home imports the shared ViewRenderer");
ok(!/task-t|task-n|r\.threads\[0\]/.test(stripped), "Home has no tasklist rendering logic of its own");
// The live scale's segments (band 2) do set [data-over]/[data-act] -- a
// station segment past its declared threshold is required to carry the
// word "over" -- but the elapsed/target/escalate arithmetic itself is not
// reimplemented here a third time (Shell.tsx already carries an independent
// copy for the rail's own DOM, documented there as a deliberate mirror
// rather than a cross-file import). Home imports toneOf from ViewRenderer.tsx
// instead, so there remains exactly one implementation of "what tone is
// this row" for every row a subject appears in, even though more than one
// component has to apply its result to its own elements.
ok(/import \{ .*\btoneOf\b.* \} from "\.\/ViewRenderer"/.test(src),
  "Home imports toneOf from ViewRenderer.tsx rather than reimplementing the colour law's elapsed/target arithmetic");
ok(!/escalate_minutes\s*\?\?/.test(stripped),
  "no second copy of the escalate-defaults-to-2x-target rule lives in Home.tsx");

console.log(`ok   home: ${checks} checks`);
