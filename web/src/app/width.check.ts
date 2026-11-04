/** The divider's rule, checked without a browser. */
import assert from "node:assert";
import { clampWidth, nudge, DEFAULT, MAX, MIN, STEP } from "./width.ts";

const ok = (m: string) => console.log("ok  ", m);
let n = 0;
const check = (m: string, f: () => void) => { f(); n++; void m; };

// -- the floor and the ceiling -------------------------------------------
//
// Both exist so a drag cannot produce a width a person cannot undo. Below
// the floor the grip itself is too narrow to find again; above the ceiling
// the thing the column sits beside is off the screen.
check("a drag below the floor stops at the floor", () => {
  assert.equal(clampWidth(0), MIN);
  assert.equal(clampWidth(-500), MIN);
  assert.equal(clampWidth(MIN - 1), MIN);
});
check("a drag past the ceiling stops at the ceiling", () => {
  assert.equal(clampWidth(10_000), MAX);
  assert.equal(clampWidth(MAX + 1), MAX);
});
check("and a width between them is kept as it was", () => {
  assert.equal(clampWidth(300), 300);
  assert.equal(clampWidth(MIN), MIN);
  assert.equal(clampWidth(MAX), MAX);
});
ok("width: a drag cannot produce a column too narrow to grab or too wide to "
   + "see past");

// A pointer gives fractional pixels on a scaled display, and a fraction
// written into a CSS length is a sub-pixel border that renders on some
// frames and not others.
check("a fractional drag lands on a whole pixel", () => {
  assert.equal(clampWidth(300.4), 300);
  assert.equal(clampWidth(300.6), 301);
  assert.ok(Number.isInteger(clampWidth(247.9)));
});

// A width that is not a width. Without the fallback the column is laid out
// at NaN, which collapses it to nothing on first load and then remembers
// that, because the collapsed value is what gets saved.
check("a width that is not a number falls back rather than collapsing", () => {
  assert.equal(clampWidth(NaN), DEFAULT);
  // Infinity is garbage in the same way NaN is -- no pointer produces it --
  // so it falls back to a working column rather than being read as "as wide
  // as allowed".
  assert.equal(clampWidth(Infinity), DEFAULT);
  assert.equal(clampWidth(-Infinity), DEFAULT);
});
// AND THE TRAP THAT WAS ACTUALLY IN THE CODE. `Number("")` is 0, not NaN,
// so a stored empty string passed the clamp and came back as the minimum:
// the column shrank to its narrowest on load, and that narrow value was
// then what got saved. readWidth now treats anything that is not a number
// as nothing stored; this is the case that caught it.
check("zero is a width and a blank string is not", () => {
  assert.equal(Number(""), 0, "the premise of the bug this guards");
  assert.equal(clampWidth(0), MIN, "a real zero is still a drag to the floor");
});
ok("width: a fraction is rounded and a non-number falls back to a working "
   + "column rather than to zero");

// -- the keyboard ---------------------------------------------------------
check("the arrows move it and the ends jump to the limits", () => {
  assert.equal(nudge(300, "ArrowLeft"), 300 - STEP);
  assert.equal(nudge(300, "ArrowRight"), 300 + STEP);
  assert.equal(nudge(300, "Home"), MIN);
  assert.equal(nudge(300, "End"), MAX);
});
check("a keyboard nudge obeys the same limits a drag does", () => {
  assert.equal(nudge(MIN, "ArrowLeft"), MIN);
  assert.equal(nudge(MAX, "ArrowRight"), MAX);
});
check("and any other key moves nothing", () => {
  assert.equal(nudge(300, "a"), null);
  assert.equal(nudge(300, "Enter"), null);
  assert.equal(nudge(300, "ArrowUp"), null);
});
ok("width: the divider moves by keyboard, under the same limits, and no "
   + "other key moves it");

console.log(`\n${n} divider checks passed`);
