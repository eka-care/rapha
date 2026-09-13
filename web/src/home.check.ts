/** Home: three bands in order, cards draggable by an explicit handle, a
 *  focused handle takes arrow keys, and order is remembered per viewer by
 *  the card's own declaration id (not by anything in the data), which is
 *  what makes it survive a reseed.
 *
 *  Run: node --experimental-strip-types src/home.check.ts   (from web/)
 *
 *  What a text check can prove and what it cannot: it can prove the drag
 *  handle is the only draggable element, that a keydown handler branches on
 *  ArrowUp/ArrowDown, and that the storage key is built from a declaration id
 *  rather than a row field. It cannot press a key in a real DOM and watch two
 *  cards swap, or open two tabs and watch a reorder in one reach the other
 *  after a reload; that was confirmed once by hand, in the browser, against a
 *  running kernel, and is reported alongside this run rather than repeated by
 *  it. What this check would catch that a browser check would not:
 *  reordering logic quietly rebuilt to key off something in the loaded rows
 *  (a subject field, a count) instead of the declaration id, which would
 *  still pass a single manual reload (the data has not changed yet) and only
 *  break on the reseed nobody thinks to retest.
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

// -- three bands, in this order: greeting, data (live line + metrics), tasks -
const iGreet = src.indexOf('className="greet"');
const iLive = src.indexOf('className="flat live"');
const iCards = src.indexOf('className="home-cards"');
ok(iGreet >= 0 && iLive > iGreet, "the greeting is written before the live line");
ok(iCards > iLive, "the cards band (metrics, tasks) is written after the live line");

// -- the live line is not a card: it is the page's subject, drawn flat, and
// is not part of the draggable pool built a few lines later --------------
ok(!/cardIds[\s\S]{0,200}"live"/.test(src), "the live line's id is not added to the reorderable pool");

// -- an explicit drag handle, not the card body --------------------------
const handleFn = src.slice(src.indexOf("const Handle ="), src.indexOf("const Handle =") + 700);
ok(/draggable/.test(handleFn), "the handle itself is the draggable element");
ok(/onDragStart/.test(handleFn), "the handle starts the drag, not some ancestor");
ok(/dataTransfer\.setData/.test(handleFn), "the handle carries its own id on the drag");
// The handle is a bare icon with no visible text, so its aria-label is the
// only thing that tells a screen reader what it does or which card it
// belongs to; losing it is silent to anyone who is not using one.
ok(/aria-label=\{`Reorder \$\{label\}`\}/.test(handleFn), "the handle has a per-card accessible name");

// -- keyboard reorder: a focused handle takes arrow keys, not just a mouse --
ok(/ArrowUp/.test(handleFn) && /ArrowDown/.test(handleFn), "the handle's keydown branches on ArrowUp and ArrowDown");
ok(/onMove\(id,\s*-1\)/.test(handleFn) && /onMove\(id,\s*1\)/.test(handleFn),
  "arrow keys actually call the move function in both directions, not just preventDefault");
// A handler that catches the keys but never calls onMove would still match
// "ArrowUp" and "ArrowDown" above; anchoring the call inside the same handler
// closes that gap.
ok(/preventDefault\(\)/.test(handleFn), "the handler prevents the browser's own scroll-on-arrow-key");

// -- the card body stays a normal drop target, not just the handle --------
const cardFn = src.slice(src.indexOf("function Card("), src.indexOf("function Card(") + 900);
ok(/onDragOver/.test(cardFn) && /onDrop/.test(cardFn), "the whole card is a drop zone, not a sliver at the handle");

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

// -- tasks are drawn by the same generic renderer Task 5 built, not a second,
// parallel tasklist renderer living in Home -------------------------------
ok(/import \{ ViewRenderer \} from "\.\/ViewRenderer"/.test(src), "Home imports the shared ViewRenderer");
ok(!/task-t|task-n|r\.threads\[0\]/.test(stripped), "Home has no tasklist rendering logic of its own");

console.log(`ok   home: ${checks} checks`);
