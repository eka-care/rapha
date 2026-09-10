/** Two runnable checks the v2dd wiring cannot be allowed to lose.
 *
 *  Run: node --experimental-strip-types src/voice/voice.check.ts   (from web/)
 *
 *  1. The capture controls come from the instrument declarations, not from
 *     this codebase's opinion about which fields are speakable. The check
 *     edits a declaration in memory and asserts the mount changes with it,
 *     which a hard-coded list would fail.
 *  2. Nothing on the voice path can commit. That is asserted twice: no module
 *     under packages/voice or web/src/voice contains a write of any kind, and
 *     in OperationPanel the two calls that do write sit inside the one
 *     function bound to the Commit button's onClick.
 *
 *  The number grammar itself is checked in packages/voice/src/grammar.check.ts:
 *  numbers, decimals, units, and every ambiguous phrase refused.
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
  scribe.targets.every((q: any) => q.type === "text"),
  "the scribe targets text questions only, never a number",
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
const WRITES = /\b(fetch|XMLHttpRequest|sendBeacon|navigator\.send|client\.(commit|confirm)|api\.(commit|confirm))\b/;
const sources = [
  ...readdirSync(root + "packages/voice/src").map((f) => `packages/voice/src/${f}`),
  ...readdirSync(root + "web/src/voice").map((f) => `web/src/voice/${f}`),
].filter((f) => /\.tsx?$/.test(f) && !f.endsWith("voice.check.ts"));
ok(sources.length >= 6, "the check is actually reading the voice modules");
for (const f of sources) {
  const hit = read(f).split("\n").find((l) => WRITES.test(l) && !l.trim().startsWith("*"));
  ok(!hit, `${f} contains no write: ${hit ?? ""}`);
}

// And in the panel, the writes live in the one function the button calls.
const panel = read("web/src/OperationPanel.tsx");
const from = panel.indexOf("const send = async () => {");
ok(from > 0, "OperationPanel still has a send()");
const to = panel.indexOf("\n  };", from);
const send = panel.slice(from, to);
for (const call of ["client.commit(", "client.confirm("]) {
  ok(panel.split(call).length === 2, `${call} appears exactly once in the panel`);
  ok(send.includes(call), `${call} is inside send(), which only a tap calls`);
}
ok(panel.includes("onClick={send}"), "send() is bound to a click and to nothing else");
const named = panel.split("\n").filter((l) => /\bsend\b/.test(l) && !l.trim().startsWith("*"));
assert.deepEqual(
  named.map((l) => l.trim()),
  ["const send = async () => {", "onClick={send}"],
  "FAIL send() is defined once and called from one onClick, and from nothing else",
);
checks++;
ok(!/useEffect|setTimeout|setInterval/.test(panel), "the panel has no timer and no effect that could fire a write");

console.log(`ok   voice mount: ${checks} checks`);
