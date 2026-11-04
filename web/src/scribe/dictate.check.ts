/** The dictation rules, checked without a microphone or a browser. */
import assert from "node:assert";
import { readFileSync } from "node:fs";
import {
  DEFAULT_KEY, DOUBLE_MS, HOLD_MS, gesture, insert, isTarget, listening,
} from "./dictate.ts";

const ok = (m: string) => console.log("ok  ", m);
let n = 0;
const check = (m: string, f: () => void) => { f(); n++; void m; };

// -- where the words land -------------------------------------------------
//
// At the cursor, not on the end. Appending looks identical on an empty field
// and is wrong on every other one, which is why it survives a careless test
// and fails the first time somebody dictates a correction.
check("into an empty field, the words are the whole value", () => {
  assert.deepEqual(insert("", 0, 0, "fever since three days"),
    { value: "fever since three days", caret: 22 });
});
check("at the cursor, mid-sentence, with the rest kept after it", () => {
  const r = insert("fever and cough", 6, 6, "headache");
  assert.equal(r.value, "fever headache and cough");
  assert.equal(r.value.slice(0, r.caret), "fever headache",
    "the cursor is left after the words that were just said, not at the end");
});
check("a selection is replaced rather than pushed along", () => {
  assert.equal(insert("fever and cough", 10, 15, "wheeze").value, "fever and wheeze");
});
check("and appending is NOT what happens", () => {
  assert.notEqual(insert("a b", 0, 0, "x").value, "a b x");
  assert.equal(insert("a b", 0, 0, "x").value, "x a b");
});
ok("dictation: the words land at the cursor, replacing a selection, and the "
   + "cursor is left after them");

// -- the spaces, which are the whole difference between this reading as a
//    product and reading as a demo --------------------------------------
check("a space is added between words and not doubled", () => {
  assert.equal(insert("fever", 5, 5, "cough").value, "fever cough");
  assert.equal(insert("fever ", 6, 6, "cough").value, "fever cough");
});
check("no space is invented at the start of a field", () => {
  assert.equal(insert("", 0, 0, "cough").value, "cough");
  assert.ok(!insert("", 0, 0, "cough").value.startsWith(" "));
});
check("no space is pushed in front of punctuation that closes up", () => {
  assert.equal(insert("fever.", 5, 5, "today").value, "fever today.");
  assert.equal(insert("(x)", 1, 1, "y").value, "(y x)");
});
check("the words themselves are trimmed", () => {
  assert.equal(insert("", 0, 0, "  cough  ").value, "cough");
});
check("and saying nothing changes nothing", () => {
  assert.deepEqual(insert("fever", 2, 2, "   "), { value: "fever", caret: 2 });
  assert.deepEqual(insert("fever", 2, 2, ""), { value: "fever", caret: 2 });
});
ok("dictation: spacing is right at the start, the end and against "
   + "punctuation, and silence changes nothing");

// -- the gesture ----------------------------------------------------------
//
// Hold to talk, double press for hands-free. The ordering matters: while
// hands-free is running the key means stop, so the press that ends it must
// not also be read as the first half of starting it again.
const press = (at: number, released?: number) => ({ at, released });

check("a key still down, long enough, is a hold", () => {
  assert.equal(gesture([press(0)], HOLD_MS, null), "hold");
});
check("a key still down but only just is nothing yet", () => {
  assert.equal(gesture([press(0)], HOLD_MS - 1, null), null);
});
check("two quick taps are hands-free", () => {
  assert.equal(gesture([press(0, 50), press(200, 250)], 260, null), "handsfree");
});
check("two taps too far apart are not", () => {
  assert.equal(gesture([press(0, 50), press(DOUBLE_MS + 100, DOUBLE_MS + 150)],
    DOUBLE_MS + 160, null), null);
});
check("a long press followed by a tap is not hands-free", () => {
  assert.equal(gesture([press(0, HOLD_MS + 100), press(300, 350)], 360, null), null,
    "a hold then a tap would otherwise start hands-free by accident every "
    + "time somebody dictated twice in a row");
});
check("any press while hands-free is running stops it", () => {
  assert.equal(gesture([press(0)], 10, "handsfree"), "stop");
  assert.equal(gesture([press(0)], 10_000, "handsfree"), "stop",
    "holding the key to stop must stop it, not start a hold inside it");
});
check("and two taps to stop do not immediately restart it", () => {
  // The press that stops is reported as `stop`; what the caller does after
  // is start nothing. This is the assertion that the stop branch is checked
  // before the hands-free branch.
  const taps = [press(0, 50), press(200, 250)];
  assert.equal(gesture(taps, 260, "handsfree"), null,
    "once released, a stop is spent: it must not fall through into starting "
    + "hands-free again");
});
check("nothing pressed means nothing", () => {
  assert.equal(gesture([], 1000, null), null);
});
ok("dictation: hold to talk, two taps for hands-free, and the key always "
   + "means stop while hands-free is running");

// -- which fields take dictation -----------------------------------------
//
// A node stub, because jsdom for four properties is a dependency this repo
// does not have and this is all `isTarget` reads.
const el = (tag: string, props: Record<string, unknown> = {}) =>
  ({ tagName: tag, isContentEditable: false, disabled: false, readOnly: false,
     type: "text", ...props } as unknown as Element);

check("a text field and a textarea take dictation", () => {
  assert.ok(isTarget(el("INPUT")));
  assert.ok(isTarget(el("INPUT", { type: "search" })));
  assert.ok(isTarget(el("TEXTAREA")));
  assert.ok(isTarget(el("DIV", { isContentEditable: true })));
});
check("a disabled or read-only field does not", () => {
  assert.ok(!isTarget(el("INPUT", { disabled: true })));
  assert.ok(!isTarget(el("INPUT", { readOnly: true })));
  assert.ok(!isTarget(el("TEXTAREA", { disabled: true })));
  assert.ok(!isTarget(el("TEXTAREA", { readOnly: true })));
});
// Each of these is a real problem rather than a missing feature, and the
// comment in dictate.ts says so: words into a closed choice have to be
// matched against the declared options, and "one twenty" into a number
// field would insert those characters rather than that value.
check("a closed choice, a number and a checkbox do not", () => {
  assert.ok(!isTarget(el("SELECT")));
  assert.ok(!isTarget(el("INPUT", { type: "number" })));
  assert.ok(!isTarget(el("INPUT", { type: "checkbox" })));
  assert.ok(!isTarget(el("INPUT", { type: "radio" })));
});
check("and nothing focused is not a target", () => {
  assert.ok(!isTarget(null));
  assert.ok(!isTarget(el("DIV")));
});
ok("dictation: free text takes the words; a closed choice, a number and a "
   + "checkbox are left for the work they each need");

// -- what the person is told ---------------------------------------------
check("the indicator names the field, so a wrong cursor is caught before "
      + "somebody speaks rather than after", () => {
  assert.match(listening("Diagnosis"), /Diagnosis/);
});
check("and with no field it says what will happen to the words instead", () => {
  const said = listening(null);
  assert.ok(!/undefined|null/.test(said), "the sentence leaks a missing value: " + said);
  assert.match(said, /copy/i);
});
ok("dictation: the indicator says where the words are going, by name");

check("the default key is the one the owner chose", () => {
  assert.equal(DEFAULT_KEY, "₹");
});

console.log(`\n${n} dictation checks passed`);

// -- THE KEY MUST NEVER BECOME A CHARACTER ------------------------------
//
// The rules above are pure and the wiring is not, so this reads the wiring.
// Holding the key IS the gesture, a held key repeats, and a repeat that is
// not prevented is typed: a date box came back reading "₹₹₹₹₹₹₹₹₹₹₹". The
// bug was an early return ordered before the prevention, which no pure
// check could ever have seen.
{
  const src = readFileSync(new URL("./useDictation.ts", import.meta.url), "utf8");
  const down = src.slice(src.indexOf("const down ="), src.indexOf("const up ="));
  assert.ok(down.includes("e.preventDefault()"), "the keydown handler prevents nothing");
  assert.ok(down.includes("if (e.repeat)"),
    "the keydown handler no longer tests e.repeat at all, so a held key "
    + "restarts the gesture on every repeat");
  assert.ok(
    down.indexOf("e.preventDefault()") < down.indexOf("if (e.repeat)"),
    "the keydown handler tests e.repeat before it prevents the default, so "
    + "every repeat of a held key types the shortcut into the field",
  );
  assert.ok(src.includes('addEventListener("beforeinput"'),
    "nothing refuses the character on the input path, which is how a composed "
    + "key or an input method editor reaches the field without a keydown");
  assert.ok(src.includes("held.current"),
    "the input guard is not gated on the key being down, so a person could "
    + "never type this character at all");
}
ok("dictate: the shortcut key cannot type itself, held, repeated or composed");
