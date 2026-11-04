/** Field width is decided by the declaration, and only by the declaration. */
import assert from "node:assert";
import { CH, capFor, choiceWeight, UNIT, weightFor } from "./span.ts";

const ok = (m: string) => console.log("ok  ", m);
const check = (m: string, f: () => void) => { f(); void m; };

// -- a number is short ----------------------------------------------------
//
// This is the whole complaint. A dose of 500 was given the width of a drug
// name because the row divided itself evenly. It must not be able to again.
check("a measurement is narrower than prose", () => {
  assert.ok(weightFor("integer") < weightFor("text"));
  assert.ok(weightFor("decimal") < weightFor("text"));
  assert.equal(weightFor("integer"), weightFor("decimal"));
});
check("a measurement is narrower than a plain string", () => {
  assert.ok(weightFor("integer") < weightFor("string"));
});
check("prose is the widest thing there is", () => {
  const every = ["integer", "decimal", "boolean", "date", "choice", "string", "text"];
  const widest = Math.max(...every.map((t) => weightFor(t)));
  assert.equal(weightFor("text"), widest);
});
ok("span: a dose can never again be given the width of a drug name");

// -- a choice is as wide as what it can say -------------------------------
check("a longer option list earns a wider box", () => {
  assert.ok(choiceWeight(6) <= choiceWeight(14));
  assert.ok(choiceWeight(14) <= choiceWeight(24));
  assert.ok(choiceWeight(24) <= choiceWeight(40));
});
check("a choice is measured on its displays, not its codes", () => {
  // Both of these are SNOMED codes nine digits long. What differs is what
  // the terminology calls them, and that is what the person reads.
  const short = weightFor("choice", ["day", "week", "month"]);
  const long = weightFor("choice", ["Respiratory tract route", "Intramuscular route"]);
  assert.ok(short < long);
});
check("no picker is ever as wide as prose", () => {
  // The only control that earns the whole width of a form is one somebody
  // writes sentences in. A picker shows one line whatever its list holds.
  const longest = "a".repeat(200);
  assert.ok(weightFor("choice", [longest]) < weightFor("text"));
});
check("a choice with no options at all is still a usable width", () => {
  assert.ok(weightFor("choice") >= 3);
});
ok("span: a picker is as wide as the longest thing it can show");

// -- a standalone field has a ceiling, not a share ------------------------
//
// In a row the weight divides the line. Alone there is no line, so the same
// weight is a maximum: a number on its own stops being an invitation to
// write a sentence.
check("a standalone number is capped well short of the panel", () => {
  const cap = capFor(weightFor("integer"));
  assert.ok(cap !== null);
  assert.ok((cap as number) <= 12, `a number capped at ${cap}ch is still too wide`);
});
check("a standalone note is not capped at all", () => {
  assert.equal(capFor(weightFor("text")), null);
});
check("a wider weight earns a wider cap", () => {
  assert.ok((capFor(2) as number) < (capFor(6) as number));
  assert.equal(capFor(6), 6 * CH);
});
ok("span: a field alone on its line is as wide as its answer, not as the form");

// -- the weights are relative, and the floor keeps them legible -----------
check("the wrap floor holds at least a few characters", () => {
  assert.ok(UNIT * 2 >= 32, "a weight-2 box must still hold four digits");
});
ok("span: a weighted field wraps rather than shrinking past reading");
