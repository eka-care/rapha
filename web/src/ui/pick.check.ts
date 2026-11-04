/** Which shape a closed choice gets, and what survives a search. */
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { LONG, MANY, matches, needsSearch } from "./pick.ts";

const ok = (m: string) => console.log("ok  ", m);
const check = (m: string, f: () => void) => { f(); void m; };

// -- a short list of short words is read, not hunted ----------------------
check("three short options are a menu", () => {
  assert.equal(needsSearch(["Day", "Week", "Month"]), false);
  assert.equal(needsSearch(["Once daily", "Twice a day", "Three times daily"]), false);
});
check("a list longer than a glance gets a search box", () => {
  assert.equal(needsSearch(Array.from({ length: MANY }, (_, i) => `x${i}`)), false);
  assert.equal(needsSearch(Array.from({ length: MANY + 1 }, (_, i) => `x${i}`)), true);
});
check("so does a short list of long names", () => {
  // Seven laboratory analytes. Few enough to fit in a menu, and no human
  // reads seven lines of this and picks the right one by eye.
  assert.equal(needsSearch([
    "Creatinine [Mass/volume] in Serum or Plasma",
    "Glucose [Mass/volume] in Capillary blood by Glucometer",
  ]), true);
  assert.ok("Glucose [Mass/volume] in Capillary blood by Glucometer".length > LONG);
});
check("an empty list is not a search problem", () => {
  assert.equal(needsSearch([]), false);
});
ok("pick: a list is searched when it is long, or when its names are");

// -- the filter finds what a clinician would type -------------------------
const LAB = [
  { value: "a", display: "Glucose [Mass/volume] in Capillary blood by Glucometer" },
  { value: "b", display: "Glucose [Mass/volume] in Serum or Plasma" },
  { value: "c", display: "Haemoglobin [Mass/volume] in Blood" },
];
check("nothing typed shows everything", () => {
  assert.equal(matches(LAB, "").length, 3);
  assert.equal(matches(LAB, "   ").length, 3);
});
check("a word anywhere in the name counts, not only at its start", () => {
  // "capillary" is the sixth word of the option. A prefix match finds
  // nothing, which is how a picker teaches a person it is broken.
  assert.deepEqual(matches(LAB, "capillary").map((o) => o.value), ["a"]);
});
check("two words both have to appear, in any order", () => {
  assert.deepEqual(matches(LAB, "glucose capillary").map((o) => o.value), ["a"]);
  assert.deepEqual(matches(LAB, "capillary glucose").map((o) => o.value), ["a"]);
  assert.deepEqual(matches(LAB, "glucose serum").map((o) => o.value), ["b"]);
});
check("case is not something to hold against anybody", () => {
  assert.equal(matches(LAB, "HAEMOGLOBIN").length, 1);
});
check("a query nothing matches matches nothing, rather than everything", () => {
  assert.equal(matches(LAB, "potassium").length, 0);
});
ok("pick: the filter finds an option by any of its words, in any order");

// -- the stored value is the code, never the word -------------------------
//
// The whole picker exists to show a word and store a code. A component that
// passed the display up would write "Glucose [Mass/volume] in Serum or
// Plasma" into a field whose value set holds a LOINC number, and the kernel
// would refuse it at commit with a message about an unknown code.
{
  const src = readFileSync(new URL("./Picker.tsx", import.meta.url), "utf8");
  assert.ok(!/onChange\(o\.display\)/.test(src) && !/onChange\(.*\.display\)/.test(src),
    "the picker hands a display up as the value; the code is what is stored");
  assert.ok(/onChange\(o\.value\)/.test(src) || /take\(.*\)/.test(src),
    "the picker no longer passes a value up at all");
}
ok("pick: what is drawn is the word and what is stored is the code");
