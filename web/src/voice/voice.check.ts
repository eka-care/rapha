/** Two runnable checks the v2dd wiring cannot be allowed to lose.
 *
 *  Run: node --experimental-strip-types src/voice/voice.check.ts   (from web/)
 *
 *  1. The capture controls come from the instrument declarations, not from
 *     this codebase's opinion about which fields are speakable. The check
 *     edits a declaration in memory and asserts the mount changes with it,
 *     which a hard-coded list would fail.
 *  2. Nothing on the voice path can commit. That is asserted twice: no module
 *     under web/src/voice contains a write of any kind, and
 *     in OperationPanel the two calls that do write sit inside the one
 *     function bound to the Commit button's onClick.
 *
 *  There is no number grammar any more. It read "one forty" in the browser,
 *  and the medical scribe service answers the form's own questions instead,
 *  which is checked in web/src/scribe/scribe.check.ts. Its absence is checked
 *  below, because an engine nothing calls is one somebody can call again.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { mountsFor } from "./instruments.ts";
import type { Operation, Questionnaire } from "../types";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");
const cat = JSON.parse(read("catalogue/catalogue.json"));
const schema = (id: string): Questionnaire => JSON.parse(read(`questionnaires/${id}.json`));

let checks = 0;
const ok = (cond: unknown, what: string) => {
  checks++;
  assert.ok(cond, `FAIL ${what}`);
};

const op = (id: string): Operation => cat.operations[id] as Operation;
const vitals = op("phc.op.vitals-record");
const consult = op("phc.op.consult-document");
const instruments = cat.instruments as Record<string, any>;
const mount = (kind: string, ms: ReturnType<typeof mountsFor>) => ms.find((m) => m.kind === kind);

// -- driven by the declaration, not by this code ---------------------------
const vm = mountsFor(instruments, vitals, schema(vitals.input));
const voice = mount("constrained-voice", vm);
ok(voice, "the vitals operation offers the declared voice instrument");
const declared = instruments["phc.inst.vitals-voice"].fields as string[];
assert.deepEqual(
  (voice as any).fields.map((f: any) => f.linkId).sort(),
  [...declared].sort(),
);
checks++;

// The load bearing one: change the declaration, the buttons change. A field
// list written into the renderer would sail through the assertion above and
// fail this.
const narrowed = JSON.parse(JSON.stringify(instruments));
narrowed["phc.inst.vitals-voice"].fields = ["pulse"];
assert.deepEqual(
  (mount("constrained-voice", mountsFor(narrowed, vitals, schema(vitals.input))) as any).fields.map(
    (f: any) => f.linkId,
  ),
  ["pulse"],
);
checks++;

const detached = JSON.parse(JSON.stringify(instruments));
detached["phc.inst.vitals-voice"].operations = [];
ok(
  !mount("constrained-voice", mountsFor(detached, vitals, schema(vitals.input))),
  "an instrument that does not name the operation is not offered on it",
);

// -- the renderer refuses a declaration that would skip the readback -------
for (const [key, bad] of [["commit", "auto"], ["readback", "optional"], ["grammar", "freeform"]]) {
  const broken = JSON.parse(JSON.stringify(instruments));
  broken["phc.inst.vitals-voice"][key] = bad;
  ok(
    !mount("constrained-voice", mountsFor(broken, vitals, schema(vitals.input))),
    `a declaration with ${key}: ${bad} puts no microphone on screen`,
  );
}

// -- the scribe is narrative, and only narrative --------------------------
const cm = mountsFor(instruments, consult, schema(consult.input));
const scribe = mount("scribe", cm) as any;
ok(scribe, "the consultation offers the declared scribe");
ok(scribe.targets.length > 0, "the scribe has somewhere to put prose");
ok(
  scribe.targets.every((q: any) => q.type === "text" || q.type === "structured"),
  "the scribe targets prose and lists only, never a number",
);
ok(!mount("scribe", vm), "the scribe is not offered on vitals");
ok(!mount("constrained-voice", cm), "the number grammar is not offered on the consultation");

// A scribe declaration that named a discrete field must still not reach one.
const greedy = JSON.parse(JSON.stringify(instruments));
greedy["phc.inst.consult-scribe"].operations = [vitals.id];
greedy["phc.inst.consult-scribe"].fields = ["systolic"];
ok(
  !mount("scribe", mountsFor(greedy, vitals, schema(vitals.input))),
  "a scribe pointed at a number field mounts nothing",
);

// -- the device is declared and honestly unbuilt --------------------------
const device = mount("device", vm) as any;
ok(device, "the declared device instrument is shown, not silently dropped");
assert.deepEqual([...device.fields].sort(), [...instruments["phc.inst.vitals-device"].fields].sort());
checks++;

// -- no code path commits without a tap -----------------------------------
// The voice modules have no writer in them at all. This is the property that
// is kept by absent code, so the check is for absence.
//
// Since the owner's decision that every aspect of scribing goes through the
// medical scribe service, a reading IS uploaded: the browser's own speech
// recognition is gone and the words come from the kernel. So the rule is no
// longer "these files touch no network", which would now be true only by
// hiding the upload one import away. It is this, which is the rule that was
// always meant: nothing on the voice path commits, and the ONE thing it may
// call that reaches a network is the reading, named here by name.
const WRITES = /\b(fetch|XMLHttpRequest|sendBeacon|navigator\.send|client\.(commit|confirm)|api\.(commit|confirm))\b/;
const sources = readdirSync(root + "web/src/voice")
  .map((f) => `web/src/voice/${f}`)
  .filter((f) => /\.tsx?$/.test(f) && !f.endsWith("voice.check.ts"));
// Two, since SpokenPrompt.tsx went with the instrument kind it drew. The
// count is asserted rather than left open because a glob that silently
// matches nothing passes every assertion under it.
ok(sources.length === 2, `the check is reading ${sources.length} voice modules, not 2`);
for (const f of sources) {
  const hit = read(f).split("\n").find((l) => WRITES.test(l) && !l.trim().startsWith("*"));
  ok(!hit, `${f} contains no write: ${hit ?? ""}`);
}

// What the voice path is allowed to reach for outside itself. A new import
// from anywhere that can write fails here rather than being discovered.
const OUTSIDE = /^import\s[^;]*?\sfrom\s"(\.\.\/[^"]+)"/;
for (const f of sources) {
  for (const line of read(f).split("\n")) {
    const hit = line.match(OUTSIDE);
    if (!hit) continue;
    ok(
      // ../scribe/session is the pure half: shapes and the two decisions
      // about what a reading says and what an instrument may take from it.
      // It is already held to the no-write rule by the loop above this one.
      ["../scribe/reading", "../scribe/session", "../types", "../validate.ts"]
        .includes(hit[1]) || hit[1].startsWith("../../"),
      `${f} imports ${hit[1]}, which is not on the short list the voice path may reach for`,
    );
  }
}

// And the reading itself: it uploads, so it is held to the same no-commit
// rule as the files above, plus the two properties that make an upload from
// the vitals station acceptable at all. Consent is the kernel's check, not a
// second one written in a browser, and the audio does not outlive the words.
const reading = read("web/src/scribe/reading.ts");
ok(!/client\.(commit|confirm)|api\.(commit|confirm)/.test(reading), "the reading commits nothing");
ok(/startSession\(/.test(reading) && /pollSession\(/.test(reading),
   "the reading uploads through the scribe route, which is where the consent check lives");
const readingCode = reading.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
ok(!/capture\.consented/.test(readingCode),
   "the reading does not re-implement the consent check the kernel already makes");
ok(/dropSession\(/.test(reading), "the recording is dropped once the words are read");

// THE NUMBER GRAMMAR IS GONE, not merely uncalled. It lived under
// packages/voice and read "one forty" in the browser. It refused a whole
// reading over four words that named no field, while the service had already
// answered the form correctly, and once the service's answer was taken
// directly it was 250 lines nothing called. An engine nothing calls is one
// somebody calls again, so this is checked rather than remembered.
//
// `spoken.json` stays in that folder: the two planners read it, and the
// grammar was only its third reader.
const left = readdirSync(root + "packages/voice/src");
assert.deepEqual(left, ["spoken.json"], "packages/voice holds no module any more");
checks++;
for (const f of sources)
  ok(!/^import[^;]*packages\/voice/m.test(read(f)),
     `${f} imports nothing from the deleted package`);

// The browser's own recogniser is gone from the whole voice path, not merely
// unused. It is the thing that answered `network` on a health centre's line.
for (const f of [...sources, "web/src/scribe/reading.ts"].filter((f) => !f.endsWith(".check.ts")))
  ok(!/SpeechRecognition|webkitSpeech/.test(read(f)), `${f} reaches for no browser recogniser`);

// And in the panel, the writes live in the one function the button calls.
const panel = read("web/src/form/Panel.tsx");
const from = panel.indexOf("const send = async () => {");
ok(from > 0, "Panel still has a send()");
const to = panel.indexOf("\n  };", from);
const send = panel.slice(from, to);
for (const call of ["client.commit(", "client.confirm("]) {
  ok(panel.split(call).length === 2, `${call} appears exactly once in the panel`);
  ok(send.includes(call), `${call} is inside send(), which only a tap calls`);
}
ok(panel.includes("onClick={send}"), "send() is bound to a click, still");
// Enter also commits (Principle 9: the keyboard is the whole interface for a
// clerk with a queue at the counter), so a bare tap is no longer the only
// line that calls send(). What must still hold is that nothing else does:
// no timer, no effect, no instrument callback reaches it directly.
const named = panel.split("\n").filter((l) => /\bsend\b/.test(l) && !l.trim().startsWith("*"));
assert.deepEqual(
  named.map((l) => l.trim()),
  ["const send = async () => {", 'if (e.key === "Enter" && !inText && !busy) { e.preventDefault(); void send(); }', "onClick={send}"],
  "FAIL send() is defined once and called only from the click and the Enter key",
);
checks++;
ok(!/useEffect|setTimeout|setInterval/.test(panel), "the panel has no timer and no effect that could fire a write");

// -- the consent line reaches the screen, not just the atom ----------------
// Every check above this one, and every check in bundles/phc/check.py, stops
// at the compiled instrument: it asserts `inst.says` is the right sentence,
// never that a person sees it. That is exactly how the sentence was deleted
// from the form and declared moved to an atom nothing read. These checks
// follow the declaration one hop further, into the renderer that draws it,
// the same way the writes above were traced into send() rather than trusted
// to be there.
//
// What this cannot cover: it cannot run the React tree, so it cannot prove a
// real DOM node paints the words, that CSS does not hide them, or that
// speechSynthesis is actually invoked in a browser. It is a source-text
// assertion, chosen because a .check.ts run under plain node cannot import a
// .tsx (JSX is not stripped by node --experimental-strip-types) the way
// voice.check.ts already reads OperationPanel.tsx as text above. A browser
// check (§ of the report) is what closes that last gap.
// THE SPOKEN PROMPT IS GONE, with the consent it read out.
//
// Forty lines here held it: registration mounted the declared instrument,
// the mount carried the atom's own sentence rather than a paraphrase, a
// facility turning the voice off still got the sentence on screen, and
// neither the panel's selector nor the component gated the on-screen text
// behind the off switch. Every one of those was a real bug once.
//
// The kind had exactly one declaration in this product -- the line a clerk
// read to a patient before recording them -- and the owner removed consent
// in full on 4 November 2026. An instrument kind nothing declares and no
// pill draws is what scripts/check_instruments.py exists to refuse, so the
// kind went, and the renderer's implementation went with it.
//
// What is asserted instead is that it really is all gone. A half-removed
// instrument kind is the `palette` failure again: a word the lint still
// accepts for something no screen implements.
for (const [what, src] of [["the panel", panel],
                           ["the mount builder", read("web/src/voice/instruments.ts")]] as const) {
  ok(!/spoken-prompt|SpokenPrompt/.test(src),
     `${what} still refers to the spoken-prompt instrument, which no bundle `
     + "can declare any more");
}
ok(!/"spoken-prompt"/.test(read("catalogue/vocab.py")),
   "spoken-prompt is still an instrument kind, so a bundle can declare one "
   + "and get a mount no screen renders");

console.log(`ok   voice mount: ${checks} checks`);
