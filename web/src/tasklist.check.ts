/** kind: tasklist has no DOM, so the resolver's proof lives in
 *  kernel/tests/test_kernel.py; this is the renderer's half.
 *
 *  Run: node --experimental-strip-types src/tasklist.check.ts   (from web/)
 *
 *  A `.check.ts` may never import a `.tsx` (that would pull in React and a
 *  DOM this plain-node script does not have), so this reads ViewRenderer.tsx
 *  back as text and asserts against its source, the same technique
 *  shell.check.ts and voice.check.ts use for the files they cannot import.
 *
 *  What this technique cannot cover: it never runs TaskList, so it cannot
 *  prove the `r.operation && ...` guard actually short-circuits at render
 *  time, that clicking Open calls onOpenThread with the right id, or that
 *  the count and title actually land in the DOM in that order. Those are a
 *  browser's job; this was confirmed once by hand (a screenshot of
 *  #/views/phc.view.today-tasks with "Consent never asked" drawing no
 *  button) but that is not a regression check and nothing here repeats it.
 *  What a text check gets right instead: the row is genuinely gated behind
 *  `operation` in the source that ships, so a future edit that renders the
 *  button unconditionally is a byte-for-byte diff this check can see, which
 *  running the component once in a browser would not.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const src = read("web/src/ViewRenderer.tsx");

// -- the dispatch reaches TaskList, the way every other kind does -----------
ok(/result\.kind === "tasklist"/.test(src), "the dispatch tests for kind \"tasklist\"");
ok(/<TaskList\b/.test(src), "the tasklist branch actually renders <TaskList>");

// -- pull out the component body so every assertion below is scoped to it,
// not to some other part of the file that happens to match the same regex --
const start = src.indexOf("function TaskList(");
ok(start >= 0, "TaskList is defined");
const end = src.indexOf("\n}\n", start);
const body = src.slice(start, end);

// -- a row is a title and a count, no prose (the declaration's copy rule) --
ok(/r\.title/.test(body), "a row draws its declared title");
ok(/r\.count/.test(body), "a row draws its declared count");

// -- operation is optional, and the guard is genuinely conditional: the
// button sits behind `r.operation &&`, so a null operation renders no
// button rather than one that would fail on click. A regex that only
// checked for a <button> element anywhere in the body would pass even if
// the guard were deleted, so this anchors the guard immediately in front of
// the button it protects. --
const guarded = /r\.operation\s*&&[^<]*&&[\s\S]{0,80}?<button/.test(body);
ok(guarded, "the Open button is gated behind r.operation, not always rendered");
ok(!/<button[^>]*>\s*Open/.test(body.replace(/r\.operation[\s\S]{0,120}?Open/, "")),
  "no ungated Open button exists elsewhere in the component");

// -- generic renderer: no station, flag or bundle word in the tasklist code -
const BUNDLE_WORDS = ["phc.op", "phc.wf", "phc.view", "lab.op", "lab.wf", "lab.view",
  "lab.ordered", "lab.resulted", "capture.consented", "capture.declined",
  "registered", "specimen.collected", "result.entered"];
for (const w of BUNDLE_WORDS) {
  ok(!body.includes(w), `TaskList names no bundle word ('${w}' absent)`);
}

console.log(`ok   tasklist: ${checks} checks`);
