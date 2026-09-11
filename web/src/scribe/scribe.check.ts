/** The checks the recording path cannot be allowed to lose.
 *
 *  Run: node --experimental-strip-types src/scribe/scribe.check.ts   (from web/)
 *
 *  Four properties, in the order they matter:
 *
 *  1. A recording never fills a number. The kernel does not send one and this
 *     side drops one if it ever does, so the property survives a change on
 *     either side of the wire.
 *  2. Nothing a doctor typed is overwritten by a draft that arrives later.
 *  3. Nothing on this path can write: no module under web/src/scribe contains
 *     commit or confirm, and the panel's two writes are still inside the one
 *     function a tap calls.
 *  4. The withdrawal control exists, is reachable while recording, and the
 *     blob is dropped unsent rather than uploaded and then forgotten.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  apply, draftFor, elsewhere, narrative, pickMime, preview, reasonFor, sentence,
  type ScribeSession,
} from "./session.ts";
import type { Questionnaire } from "../types";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");
const schema = (id: string): Questionnaire => JSON.parse(read(`questionnaires/${id}.json`));

let checks = 0;
const ok = (cond: unknown, what: string) => {
  checks++;
  assert.ok(cond, `FAIL ${what}`);
};

const consult = schema("phc.schema.consult-v1");
const vitals = schema("phc.schema.vitals-v1");

// -- 1. narrative and lists, never a number -------------------------------
const allowed = narrative(consult);
ok(allowed.has("history") && allowed.has("assessment"), "prose fields may be drafted");
ok(allowed.has("diagnosis"), "a structured list may be drafted");
ok(!allowed.has("capture_stop"), "the consent question is not the scribe's to answer");
assert.deepEqual([...narrative(vitals)], [], "FAIL no field on the vitals form may be drafted");
checks++;

const session: ScribeSession = {
  session: "scr-1", status: "ready", reason: "",
  drafts: [
    { instrument: "phc.inst.consult-scribe", operation: "phc.op.consult-document",
      values: { history: "fever for three days", assessment: "URTI",
                diagnosis: [{ code: "Acute upper respiratory tract infection" }],
                systolic: 138 },
      confidence: { history: 0, assessment: 0, diagnosis: 0, systolic: 0 },
      transcript: "Good morning. Fever for three days." },
    { instrument: "phc.inst.consult-scribe", operation: "phc.op.rx-prescribe",
      values: { medications: [{ medication: "Paracetamol 650 mg", dosage_instruction: "SOS" }] },
      confidence: { medications: 0 }, transcript: "" },
  ],
};

const empty = apply(draftFor(session, "phc.op.consult-document"), allowed, {});
assert.deepEqual(Object.keys(empty.fill).sort(), ["assessment", "diagnosis", "history"]);
checks++;
assert.deepEqual(empty.refused, ["systolic"], "FAIL a number in a draft is dropped, not filled");
checks++;
ok(empty.held.length === 0, "an empty form takes the whole draft");

// Every drafted value is unconfirmed: the panel draws anything under 0.9 that
// way, and the kernel reports 0 because Eka reports no per field score at all.
for (const d of session.drafts)
  for (const c of Object.values(d.confidence))
    ok(c < 0.9, "a drafted value is never confirmed by the machine that drafted it");

// -- 2. what a doctor typed stands ----------------------------------------
const typed = apply(draftFor(session, "phc.op.consult-document"), allowed,
                    { history: "pt says fever x3d", diagnosis: [] });
ok(!("history" in typed.fill), "a field the doctor typed into is not overwritten");
assert.deepEqual(typed.held.map((h) => h.link_id), ["history"]);
checks++;
ok("diagnosis" in typed.fill, "an empty list is not 'already typed'");
ok(preview(typed.held[0].value) === "fever for three days", "the held draft is shown in full");
ok(preview([{ medication: "Paracetamol 650 mg", dosage_instruction: "SOS" }])
   === "Paracetamol 650 mg SOS", "a structured draft reads back as words");

// The other form the same recording filled is named rather than dropped.
assert.deepEqual(elsewhere(session, "phc.op.consult-document"), ["phc.op.rx-prescribe"]);
checks++;
ok(!draftFor(session, "phc.op.vitals-record"), "no draft is offered for an operation with none");

// -- every sentence ends in the keyboard ----------------------------------
for (const s of ["running", "failed", "withdrawn"] as const)
  ok(/type the note|stands/i.test(sentence(s)),
     `the ${s} sentence says what to do instead of waiting`);
ok(sentence("failed", "Eka said no.") === "Eka said no.",
   "the service's own words are shown, not paraphrased");

// -- the recorder's own small pure parts ----------------------------------
ok(pickMime((t) => t === "audio/mp4") === "audio/mp4", "Safari's type is taken when it is the only one");
ok(pickMime(() => false) === "", "a browser supporting none of them still records");
ok(/allow it/.test(reasonFor("NotAllowedError")), "a refused microphone says how to allow it");
ok(/type the note/i.test(reasonFor("NotFoundError")), "and says the keyboard is the same record");

// -- 3. nothing on this path writes ---------------------------------------
const WRITES = /\b(client\.(commit|confirm)|api\.(commit|confirm)|\/commit|\/confirm)\b/;
const sources = readdirSync(root + "web/src/scribe")
  .filter((f) => /\.tsx?$/.test(f) && f !== "scribe.check.ts")
  .map((f) => `web/src/scribe/${f}`);
ok(sources.length >= 3, "the check is actually reading the scribe modules");
for (const f of sources) {
  const hit = read(f).split("\n").find((l) => WRITES.test(l) && !l.trim().startsWith("*"));
  ok(!hit, `${f} contains no commit: ${hit ?? ""}`);
}

const panel = read("web/src/OperationPanel.tsx");
for (const call of ["client.commit(", "client.confirm("])
  ok(panel.split(call).length === 2, `${call} still appears exactly once in the panel`);
ok(panel.includes("<Recorder"), "the panel draws the recorder");
ok(/flags \?\? \[\]\)\.includes\(CONSENT\)/.test(panel),
   "the recorder is behind the consent flag, and the reason is drawn when it is missing");
ok(/onValues=\{fromInstrument\}/.test(panel.slice(panel.indexOf("<Recorder"))),
   "a draft lands through the same path a spoken value does: editable fields, then a tap");

// -- 4. withdrawal discards rather than merely stopping -------------------
const rec = read("web/src/scribe/Recorder.tsx");
// Seen failing in a browser before it was a check: the poll that applies the
// draft is started several renders before it answers, so reading the payload
// prop through that closure reads the form as it was when the recording
// stopped, and a doctor who typed while waiting loses it.
ok(/apply\(draft, narrative\(schema\), latest\.current\)/.test(rec),
   "the draft is weighed against the form as it is now, not as it was");
ok(/latest\.current = payload/.test(rec), "and that ref is refreshed every render");
// Also seen failing in a browser: two polls in flight, both answering ready,
// the second one finding the fields the first had just filled and calling the
// whole draft text the doctor had written.
ok(/if \(taken\.current\) return;/.test(rec), "a recording produces one outcome, not one per poll");

ok(/keep\.current = false/.test(rec), "withdrawal marks the blob unsendable");
ok(/if \(!keep\.current \|\| !parts\.length\) return;/.test(rec),
   "a withdrawn recording is never uploaded");
ok(/chunks\.current = \[\]/.test(rec), "and what was captured is dropped");
ok(rec.indexOf("dropSession") > 0, "the kernel is told to keep nothing either");
ok(/Patient asked to stop/.test(rec) && rec.indexOf("Patient asked to stop") < rec.indexOf("sc-row"),
   "the withdrawal control is inside the live indicator, reachable from any scroll position");
ok(/position:fixed/.test(read("web/src/scribe/scribe.css")),
   "the live indicator cannot be scrolled off the screen");
ok(!/mic-live/.test(rec) && !/Microphone live/.test(rec),
   "the recorder does not borrow the voice path's indicator: they must not look alike");

console.log(`ok   scribe: ${checks} checks`);
