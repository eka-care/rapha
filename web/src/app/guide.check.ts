/** Run: node --experimental-strip-types src/app/guide.check.ts   (from web/)
 *
 *  The two rules the tour cannot be allowed to break: it points at nothing,
 *  and its card leaves the screen.
 */
import assert from "node:assert/strict";
import { applicable, place, STEPS } from "./guide.ts";

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

ok(STEPS.length >= 3 && STEPS.length <= 6,
   "a tour nobody finishes taught nobody anything: it stays short");
ok(new Set(STEPS.map((s) => s.id)).size === STEPS.length, "every step has its own id");
ok(STEPS.every((s) => s.at.startsWith(".")), "every step names an element by class");
ok(STEPS.every((s) => s.body.length < 120), "a step is a sentence, not a paragraph");

// -- a step with nothing to point at is dropped -----------------------------
const none = applicable(STEPS, () => false);
ok(none.length === 0, "a screen with none of them draws no tour at all");
const some = applicable(STEPS, (sel) => sel === ".sb-list" || sel === ".flow");
assert.deepEqual(some.map((s) => s.id), ["line", "flow"]);
checks++;
ok(applicable(STEPS, () => true).map((s) => s.id).join() === STEPS.map((s) => s.id).join(),
   "and the order is the declared one, never the order they were found in");

// -- the card stays on the screen -------------------------------------------
const screen = { width: 1200, height: 800 };
const card = { width: 300, height: 140 };

const under = place({ top: 100, left: 500, width: 200, height: 40 }, screen, card);
ok(under.top === 152, "the card sits under its target when there is room");
ok(under.left === 450, "and centres on it");

const low = place({ top: 740, left: 500, width: 200, height: 40 }, screen, card);
ok(low.top < 740, "a target near the bottom gets its card ABOVE, not off screen");
ok(low.top >= 12, "and never above the top edge");

const right = place({ top: 100, left: 1150, width: 40, height: 40 }, screen, card);
ok(right.left + card.width <= screen.width - 12,
   "a target at the right edge pulls its card back inside");
const left = place({ top: 100, left: 0, width: 40, height: 40 }, screen, card);
ok(left.left >= 12, "and one at the left edge does too");

// The case a phone makes: a card as tall as the screen has nowhere good, and
// the top is still better than off the bottom.
const tall = place({ top: 300, left: 10, width: 100, height: 40 },
                   { width: 380, height: 300 }, { width: 340, height: 280 });
ok(tall.top >= 12 && tall.left >= 12, "a screen smaller than the card still lands on it");

console.log(`ok   tour: ${checks} checks`);
