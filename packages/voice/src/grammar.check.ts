/**
 * Run: node packages/voice/src/grammar.check.ts     (Node 22.6+, strips types)
 *
 * Asserts the two properties the module exists for: it reads the shapes people
 * actually say, and it refuses everything it cannot read one way. A parser that
 * guesses would pass a looser check than this one, which is why the refusals
 * are asserted as hard as the successes.
 */
// @ts-ignore node built in module. @types/node is not a dependency of this
// package and the browser build never imports this file.
import { readFileSync } from "node:fs";
import { fieldsFrom, parse, parseNumberPhrase, tokens, type FieldSpec } from "./grammar.ts";
import { FAIL_CLOSED_BELOW, toDraft } from "./v2dd.ts";

const schema = JSON.parse(
  readFileSync(new URL("../../../questionnaires/phc.schema.vitals-v1.json", import.meta.url), "utf8"),
);
const FIELDS: FieldSpec[] = fieldsFrom(schema);
const META = { instrument: "phc.inst.vitals-voice", operation: "phc.op.vitals-record" };
const one = (id: string) => FIELDS.filter((f) => f.linkId === id);

let checks = 0;
function ok(cond: unknown, what: string) {
  checks++;
  if (!cond) throw new Error(`FAIL ${what}`);
}
const num = (words: string) => parseNumberPhrase(tokens(words));

// -- numbers ---------------------------------------------------------------
ok(num("one hundred forty")?.value === 140, "one hundred forty is 140");
ok(num("one hundred and forty")?.value === 140, "'and' is filler");
ok(num("one forty")?.value === 140, "the colloquial compound reads as 140");
ok(num("one fourteen")?.value === 114, "one fourteen is 114, not 140");
ok(num("one oh five")?.value === 105, "one oh five is 105");
ok(num("ninety")?.value === 90, "a bare tens word");
ok(num("sixty two")?.value === 62, "tens plus ones");
ok(num("140")?.value === 140, "digits from the recogniser");
ok(num("two hundred")?.value === 200, "a round hundred");

// The compound is the risky shape, so it must read back louder than an
// explicit one. Both stay under 0.9, which is the renderer's highlight line:
// no voice value is ever drawn as trusted.
ok(num("one forty")!.confidence < num("one hundred forty")!.confidence, "compound is less certain");
ok(num("one hundred forty")!.confidence < 0.9, "no voice value is trusted");

// -- decimals --------------------------------------------------------------
ok(num("sixty two point five")?.value === 62.5, "decimal by words");
ok(num("thirty seven point two")?.value === 37.2, "decimal on a temperature");
ok(num("62.5")?.value === 62.5, "decimal from the recogniser");
ok(num("one hundred point two five")?.value === 100.25, "two fraction digits");

// -- ambiguity is refused, never guessed -----------------------------------
ok(num("sixty two five") === null, "'sixty two five' has no single reading");
ok(num("one forty five sixty") === null, "too many parts");
ok(num("point twenty five") === null, "fraction digits are digits, 'point twenty five' is not");
ok(num("point five") === null, "a bare fraction with no whole part is refused");
ok(num("zero point five")?.value === 0.5, "the whole part may be zero, said aloud");
ok(num("hundred") === null, "a bare hundred is not a number");
ok(num("one forty seven three") === null, "trailing junk is refused");
ok(num("one fortty") === null, "an unrecognised word fails the phrase");
ok(num("") === null, "silence is not zero");

// -- fields, pairs and units ----------------------------------------------
const bp = parse("systolic one forty over ninety", FIELDS);
ok(bp.ok && bp.values.systolic === 140 && bp.values.diastolic === 90, "'over' fills the pair");
const slash = parse("blood pressure 140/90", FIELDS);
ok(slash.ok && slash.values.diastolic === 90, "140/90 is the same utterance");
const wt = parse("weight sixty two point five kilos", FIELDS);
ok(wt.ok && wt.values.weight === 62.5, "unit words are consumed");
ok(!parse("weight sixty two pounds", FIELDS).ok, "pounds into a kg field is refused, not converted");
ok(!parse("one forty", FIELDS).ok, "an unnamed number with six fields on screen is ambiguous");
ok(parse("one forty", one("systolic")).ok, "with one field on screen it needs no name");
ok(!parse("systolic one forty systolic one fifty", FIELDS).ok, "two values for one field");
ok(!parse("temperature ninety nine", FIELDS).ok, "99 C is outside range: keypad, with a reason");
ok(!parse("weight ninety over sixty", FIELDS).ok, "'over' does not apply to weight");
ok(!parse("pulse quite fast", FIELDS).ok, "prose is not a value");
const sats = parse("sats ninety eight and pulse seventy two", FIELDS);
ok(sats.ok && sats.values.spo2 === 98 && sats.values.pulse === 72, "two named fields in one breath");

// -- the fail closed rule --------------------------------------------------
const good = toDraft("systolic one forty", 0.9, one("systolic"), META);
ok(Object.keys(good.values).length === 1, "a clean capture yields one value");
ok(good.confidence.systolic < 0.9, "and it is still highlighted for re-reading");
ok(Object.keys(toDraft("systolic one forty", 0.2, one("systolic"), META).values).length === 0,
   "a low recogniser confidence falls back to the keypad");
ok(toDraft("systolic sixty two five", 0.99, one("systolic"), META).reason !== undefined,
   "an unparseable phrase falls back to the keypad with a reason");
ok(Object.keys(toDraft("", 0.99, FIELDS, META).values).length === 0, "silence yields no value");
ok(FAIL_CLOSED_BELOW > 0, "there is a floor");

// The browser plumbing cannot be exercised here, but its fail closed branch
// can: node has no SpeechRecognition, and that must read as "keypad", not as
// a hang or a throw.
import { available, captureValue } from "./v2dd.ts";
ok(available() === false, "no recogniser outside a browser");
const none = await captureValue({ fields: one("systolic"), ...META });
ok(Object.keys(none.values).length === 0 && none.reason !== undefined,
   "with no recogniser the caller is told to show the keypad");

// The property no test can restore once it is lost: nothing in this module
// commits. Assert the shape of what it hands back, not just its contents.
ok(!("commit" in good) && !("committed" in good), "a Draft carries no commit");

console.log(`ok   voice grammar: ${checks} checks`);
