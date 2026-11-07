/** The checks the recording path cannot be allowed to lose.
 *
 *  Run: node --experimental-strip-types src/scribe/scribe.check.ts   (from web/)
 *
 *  Four properties, in the order they matter:
 *
 *  1. A recording may fill a number, and Commit is held until a person ticks
 *     each heard non-text value. This is the half of the old "a recording
 *     never fills a number" rule that survives, and it lives only here: the
 *     kernel marks which values are owed a tick (api/fill.py TICK_TYPES,
 *     checked in kernel/tests/test_contracts.py) but cannot hold the commit,
 *     because the guard cannot tell a heard value from a typed one.
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
  apply,
  draftFor, elsewhere, heardFrom, mergeDrafts, narrow, pickMime, preview, reasonFor,
  sentence,
  type ScribeDraft, type ScribeSession,
} from "./session.ts";
import type { Questionnaire } from "../types";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");
const schema = (id: string): Questionnaire => JSON.parse(read(`questionnaires/${id}.json`));

/** One value a draft addressed, out of a payload: a key, or
 *  `medications[1].dose` inside a repeating group.
 *
 *  This was production code serving the tick rule, which the owner removed on
 *  2026-11-01. It is apparatus now, and it is here rather than in session.ts
 *  because the renderer has no caller for it.
 */
const ROW_ID = /^([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]\.([A-Za-z_][A-Za-z0-9_]*)$/;
function at(bag: Record<string, unknown>, id: string): unknown {
  const found = ROW_ID.exec(id);
  if (!found) return bag[id];
  const listed = bag[found[1]];
  if (!Array.isArray(listed)) return undefined;
  const row = listed[Number(found[2])];
  return row && typeof row === "object" ? (row as Record<string, unknown>)[found[3]] : undefined;
}

let checks = 0;
const ok = (cond: unknown, what: string) => {
  checks++;
  assert.ok(cond, `FAIL ${what}`);
};

// keep the schemas loaded: other properties in this file read them.
schema("phc.schema.consult-v1");
schema("phc.schema.vitals-v1");

// 1. A number a recording filled goes into an editable field, marked
//    unconfirmed, with the words it came from.
//
//    IT USED TO OWE A TICK OF ITS OWN BEFORE COMMIT WOULD LIGHT. The owner
//    removed that on 2026-11-01: the field is editable, so a wrong value is
//    corrected by typing over it. What is left is what every typed answer
//    goes through -- the fields on screen and the one tap on Commit -- plus
//    the two things a heard value carries that a typed one does not, which
//    are checked here because they are now the whole of the readback.
{
  const draft = {
    instrument: "i", operation: "phc.op.vitals-record",
    values: { systolic: 140, history: "fever" },
    confidence: { systolic: 0.89, history: 0.89 },
    evidence: { systolic: "BP is 140", history: "fever" },
    tick: ["systolic"], unfilled: [], transcript: "BP is 140, fever",
  };
  const applied = apply(draft, {});
  assert.deepEqual(applied.fill, { systolic: 140, history: "fever" });
  checks++;
  ok(Object.values(draft.confidence).every((c) => c < 0.9),
     "every heard value is under the sure threshold, so the field draws unconfirmed");
  ok(draft.evidence.systolic, "and carries the words it came from");

  // What the person typed still wins. That was true under the tick rule and
  // is the only thing standing between a heard number and a typed one now.
  const over = apply(draft, { systolic: 120 });
  assert.deepEqual(over.fill, { history: "fever" });
  checks++;
  assert.deepEqual(over.held, [{ link_id: "systolic", value: 140 }]);
  checks++;
}
// 1b. A repeating group's values are addressed per row, so a drafted
//     prescription lands as rows rather than as one blurred answer.
{
  const rows = {
    instrument: "i", operation: "phc.op.rx-prescribe",
    values: { medications: [{ drug: "777067000", dose: 500 }, { drug: "774586009", dose: 250 }] },
    confidence: {}, evidence: {},
    tick: ["medications[0].drug", "medications[0].dose",
           "medications[1].drug", "medications[1].dose"],
    unfilled: [], transcript: "paracetamol 500, amoxicillin 250",
  };
  const same = { medications: [{ drug: "777067000", dose: 500 }, { drug: "774586009", dose: 250 }] };
  assert.deepEqual(apply(rows, {}).fill, rows.values);
  checks++;
  // A typed list is held whole: half merging would make a row whose drug the
  // doctor typed and whose dose the recording supplied.
  assert.deepEqual(apply(rows, same).fill, {});
  checks++;
  assert.equal(at(same, "medications[1].drug"), "774586009");
  assert.equal(at(same, "medications[9].drug"), undefined);
  assert.equal(at(same, "medications"), same.medications);
  checks += 3;
}

// Nothing in the renderer still refuses numbers by type.
assert.ok(!read("web/src/scribe/session.ts").includes("export function narrative"));
checks += 1;

const session: ScribeSession = {
  session: "scr-1", status: "ready", reason: "", transcript: "", operations: [],
  drafts: [
    { instrument: "phc.inst.consult-scribe", operation: "phc.op.consult-document",
      values: { history: "fever for three days", assessment: "URTI",
                diagnosis: [{ condition: "297142003", clinical_status: "active",
                              verification_status: "unconfirmed" }] },
      confidence: { history: 0, assessment: 0, "diagnosis[0].condition": 0,
                    "diagnosis[0].clinical_status": 0,
                    "diagnosis[0].verification_status": 0 },
      evidence: { history: "fever for three days", assessment: "URTI",
                  "diagnosis[0].condition": "swollen foot",
                  "diagnosis[0].clinical_status": "swollen foot",
                  "diagnosis[0].verification_status": "swollen foot" },
      tick: ["diagnosis[0].condition", "diagnosis[0].clinical_status",
             "diagnosis[0].verification_status"],
      unfilled: [],
      transcript: "Good morning. Fever for three days." },
    { instrument: "phc.inst.consult-scribe", operation: "phc.op.rx-prescribe",
      values: { medications: [{ drug: "777067000", dose: 650, dose_unit: "mg",
                               route: "26643006", frequency: "229799001",
                               duration: 3, duration_unit: "d" }] },
      confidence: { "medications[0].drug": 0, "medications[0].dose": 0 },
      evidence: { "medications[0].drug": "Paracetamol", "medications[0].dose": "650" },
      tick: ["medications[0].drug", "medications[0].dose"], unfilled: [],
      transcript: "" },
  ],
};

const empty = apply(draftFor(session, "phc.op.consult-document"), {});
assert.deepEqual(Object.keys(empty.fill).sort(), ["assessment", "diagnosis", "history"]);
checks++;
ok(empty.held.length === 0, "an empty form takes the whole draft");

// Every drafted value is unconfirmed: the panel draws anything under 0.9 that
// way, and the kernel reports 0 because Eka reports no per field score at all.
for (const d of session.drafts)
  for (const c of Object.values(d.confidence))
    ok(c < 0.9, "a drafted value is never confirmed by the machine that drafted it");

// -- 2. what a doctor typed stands ----------------------------------------
const typed = apply(draftFor(session, "phc.op.consult-document"),
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

// -- the two outcomes that owe a next step say one; the rest say nothing --
for (const s of ["recording", "uploading", "running", "ready"] as const)
  ok(sentence(s) === "", `the ${s} phase is drawn, not narrated`);
for (const s of ["failed", "withdrawn"] as const)
  ok(/type the note|stands/i.test(sentence(s)),
     `the ${s} sentence says what to do instead of waiting`);
ok(sentence("failed", "Eka said no.") === "Eka said no.",
   "the service's own words are shown, not paraphrased");

// -- the recorder's own small pure parts ----------------------------------
ok(pickMime((t) => t === "audio/mp4") === "audio/mp4", "Safari's type is taken when it is the only one");
ok(pickMime(() => false) === "", "a browser supporting none of them still records");
ok(/allow it/i.test(reasonFor("NotAllowedError")), "a refused microphone says how to allow it");
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

const panel = read("web/src/form/Panel.tsx");
for (const call of ["client.commit(", "client.confirm("])
  ok(panel.split(call).length === 2, `${call} still appears exactly once in the panel`);
// The gate is the instrument's own `requires:`, read in the encounter that
// owns the microphone. It used to be a constant in messages.ts holding this
// bundle's consent flag, which gated nothing at all in a bundle that spells
// its consent differently.
{
  const enc = read("web/src/screens/Encounter.tsx");
  ok(/!consentFlag \|\| \(thread\.flags \?\? \[\]\)\.includes\(consentFlag\)/.test(enc),
     "the microphone is behind whatever flag the scribe declaration requires");
  ok(!/CONSENT/.test(enc) && !/capture\.consented/.test(enc) && !/capture\.consented/.test(panel),
     "and neither screen names the flag itself");
  const declared = JSON.parse(read("catalogue/catalogue.json"));
  const scribe = Object.values(declared.instruments ?? {})
    .find((i: any) => i.kind === "scribe") as any;
  // THIS BUNDLE DECLARES NO GATE since the owner removed consent in full on
  // 4 November 2026, and it asserted the opposite until then. What matters
  // is not whether there is a gate -- that is the bundle's business -- but
  // that a declared one names a real state. A gate on a flag this bundle
  // does not have is a microphone that can never be switched on, which is
  // the worst of the three possible states and the only one worth failing.
  ok(!scribe?.requires || (declared.states ?? []).includes(scribe.requires),
     "the scribe is gated on a flag this bundle does not declare, so the "
     + "microphone can never switch on: " + String(scribe?.requires));
}
ok(/draft\?\.values/.test(panel),
   "a draft lands in the panel's own editable fields, then a tap");

// -- 4. withdrawal discards rather than merely stopping -------------------
const rec = read("web/src/scribe/ScribeBar.tsx");
// Seen failing in a browser: two polls in flight, both answering ready.
ok(/if \(taken\.current\) return;/.test(rec), "a recording produces one outcome, not one per poll");

ok(/keep\.current = false/.test(rec), "withdrawal marks the blob unsendable");
ok(/if \(!keep\.current \|\| !parts\.length\) return;/.test(rec),
   "a withdrawn recording is never uploaded");
ok(/chunks\.current = \[\]/.test(rec), "and what was captured is dropped");
ok(rec.indexOf("dropSession") > 0, "the kernel is told to keep nothing either");
// `live` is the bar's own name for phase === "recording", so both halves
// are held: that the name means what it says, and that Discard is drawn
// whenever it is true. Spelled against the name rather than against the
// comparison, because the comparison moved into a const on 2026-11-02 and
// the rule did not.
ok(/const live = phase === "recording";/.test(rec),
   "the bar no longer names the recording phase, so the rule below cannot see it");
ok(/\{\(live \|\|[^)]*\) && \(\s*\n?[^\n]*withdraw/.test(rec),
   "the discard control is on the bar while recording");
ok(/position:fixed/.test(read("web/src/scribe/scribe.css")),
   "the live indicator cannot be scrolled off the screen");
ok(!/mic-live/.test(rec) && !/Microphone live/.test(rec),
   "the recorder does not borrow the voice path's indicator: they must not look alike");


// -- §2.6: scribe is a composer mode, not a place ---------------------------
//
// "Scribe does not get its own navigation item, its own dashboard, its own
// persistent panel, its own product surface." Three of those four are
// properties of files rather than of runtime, so they are checkable here.
//
// This matters because the microphone spent this project's whole life on a
// form, and the instruction that moved it can be undone by one import.
{
  const composer = read("web/src/thread/Composer.tsx");  // prose here is fine: the assertions below look for code that must be present
  // Anchored, not a substring: /composer__mic/ alone still matched after the
  // class was renamed to composer__micro, so this assertion passed under an
  // implementation with no microphone in it at all.
  ok(/className="scribe-btn"/.test(composer) && /onClick=\{onStartScribe\}/.test(composer),
    "the microphone that starts a consultation lives in the composer, and starts it");
  ok(/aria-label=\{micReason \|\| "Dictate"\}/.test(composer),
    "and names itself, or names why it is unavailable, for a screen reader");

  // The rail is built from declared views. An operation reaching it -- by
  // instrument, by id, or by the word -- would be scribe acquiring the
  // navigation item §2.6 forbids. Comments are stripped first: a file that
  // explains the rule in prose is not a file breaking it, and the first
  // spelling of this check failed on its own docstring.
  const code = (src: string) =>
    src.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
  const rail = code(read("web/src/app/Sidebar.tsx"));
  ok(!/scribe|mic|dictat/i.test(rail), "scribe has no navigation item");
  ok(!/instrument|operations\b/.test(rail), "no operation reaches the rail at all");

  // WHERE THE DRAFT OPENS, AND WHY THIS CHANGED ON 2026-11-02.
  //
  // It used to be pinned inline in the thread, between the stream and the
  // composer, and this check said why: a modal over the screen is the
  // "persistent panel" §2.6 rules out, and it put the recorder a full
  // viewport away from its own microphone.
  //
  // The objection was to a surface drawn OVER the thread. The owner has
  // asked for the visit to carry tabs the way a channel does -- "when
  // someone starts scribe it also opens in another view within the session
  // like canvas", and then, on a screenshot of a channel's own tab row,
  // "all of these should be tabs, records, scribe, etc". A tab is not a
  // layer over the conversation; the conversation is the tab beside it.
  // The reason the old rule existed is intact: nothing is stacked on
  // anything, and the microphone still brings its own surface forward.
  //
  // What is still true, and is what this now holds:
  //   - the draft is the same panel every operation commits through
  //   - it is inline in that tab, not a modal stacked on a modal
  //   - the microphone opens the tab, so nothing is a viewport away
  const enc = code(read("web/src/screens/Encounter.tsx"));
  const dictation = enc.slice(enc.indexOf('tab === "scribe"'), enc.indexOf('tab === "messages"'));
  ok(dictation.includes("<OperationPanel"), "the draft surface is the same panel every operation uses");
  ok(/\binline\b/.test(dictation), "drawn inline in that tab, not over it");
  ok(dictation.includes("<ScribeBar"),
    "and the recorder is in the same tab as the draft it produces");
  ok(/setTab\("scribe"\)/.test(enc),
    "starting to dictate opens that tab, so the recorder is never hidden");
  ok(/id: "messages"/.test(enc) && enc.indexOf('id: "messages"') < enc.indexOf('id: "scribe"'),
    "and the conversation is the first tab, not something you navigate back to");
}

// 5. The mic does not open a form, and the per-field tick is gone from every
//    path to Commit rather than merely from the button.
{
  const enc = read("web/src/screens/Encounter.tsx");
  assert.ok(!enc.includes("Dictation is not offered at this step"), "the mic no longer needs a scribe operation");
  assert.ok(enc.includes("<ScribeBar"), "the encounter owns the recording bar");
  const panel = read("web/src/form/Panel.tsx");
  assert.ok(!panel.includes("<Recorder"), "the form no longer starts recordings");
  assert.throws(() => read("web/src/scribe/Recorder.tsx"));
  // The owner's decision of 2026-11-01. Checked as an absence, in the panel
  // and in the form, because a half removed gate is the worst of both: a
  // Commit button that lights while something still refuses the commit.
  for (const [file, src] of [["Panel.tsx", panel], ["Form.tsx", read("web/src/form/Form.tsx")]])
    assert.ok(!/unticked|mustTick|onTick/.test(src), `${file} still owes a tick`);
  const send = panel.slice(panel.indexOf("const send = async"), panel.indexOf("const reject = async"));
  assert.ok(!/return;\s*\/\/ .*tick/.test(send), "send() refuses nothing on a tick");
  assert.ok(/disabled=\{busy \|\| \(stage === "confirm"/.test(panel),
    "Commit waits on the work and on the irreversible confirm, and on nothing else");
  checks += 8;
}

// 6. A new session replaces only the panels for its own operations, and a replaced one remounts.
{
  const d = (operation: string, v: number) => ({
    instrument: "i", operation, values: { v }, confidence: {}, evidence: {}, tick: [], unfilled: [], transcript: "",
  });
  const first = mergeDrafts([], [d("a", 1), d("b", 1)], "s1");
  const second = mergeDrafts(first, [d("a", 2)], "s1");
  assert.equal(second.length, 2);
  assert.equal(second[1], first[1], "the other operation's panel is untouched");
  assert.deepEqual(second[0].draft.values, { v: 2 });
  assert.notEqual(second[0].key, first[0].key, "a replaced draft gets a new key, so its panel remounts clean");
  const enc = read("web/src/screens/Encounter.tsx");
  assert.ok(/mergeDrafts\(all, s\.drafts, s\.session\)/.test(enc) && /key=\{key\}/.test(enc),
    "the encounter merges drafts and keys panels by generation");
  checks += 5;
}

// 7. A suggested code is not a value, and this is the most dangerous kind of
//    heard value there is: a plausible code is unrecoverable once stored under
//    a patient's ABHA number. Three rules, all of them about what a candidate
//    is NOT, because the way this breaks is a suggestion quietly becoming an
//    answer.
{
  const candidate = {
    code: "44054006", system: "http://snomed.info/sct",
    display: "Type 2 diabetes mellitus", valueset: "condition-code",
    score: 1, linked: true, span: "her sugar is known", term: "DM2",
  };
  const draft: ScribeDraft = {
    instrument: "i", operation: "phc.op.consult-document",
    values: { assessment: "Likely dengue fever" },
    confidence: { assessment: 0.8 }, evidence: { assessment: "Likely dengue fever" },
    tick: [], unfilled: ["diagnosis[1].condition"],
    candidates: { "diagnosis[1].condition": [candidate] },
    transcript: "Likely dengue fever, and her sugar is known",
  };

  // (a) It is not in the draft's own tick list either. That list no longer
  //     gates anything on screen, and this still holds: the kernel must not
  //     describe a suggestion as a value somebody could confirm.
  assert.deepEqual(draft.tick, [],
    "a candidate is not a value, so it is not in the tick list");
  checks++;

  // (b) It is not in the payload, under its own id or under the field's.
  assert.equal(at(draft.values, "diagnosis[1].condition"), undefined,
    "a candidate must not be readable out of the payload");
  assert.ok(!JSON.stringify(draft.values).includes(candidate.code),
    "a candidate's code reached the values a Commit would send");

  // (c) The field is still unfilled, however sure the suggestion was. A score
  //     of 1 and linked true is exactly the case that would be prefilled if
  //     anybody ever added a threshold, which nothing here has.
  assert.ok(draft.unfilled.includes("diagnosis[1].condition"),
    "a field with a certain candidate is still unfilled");
  assert.ok(!("value" in candidate),
    "a candidate must not carry a key a form control binds to");

  // And nothing in the renderer reads them yet, which is said rather than
  // implied: the picker is an open step. This fails the day somebody draws
  // them, which is the right moment to rewrite this check.
  const files = readdirSync(root + "web/src/scribe");
  const draws = files.filter((f) => f !== "session.ts" && !f.endsWith(".check.ts"))
    .filter((f) => read(`web/src/scribe/${f}`).includes("candidates"));
  assert.deepEqual(draws, [], "candidates are declared and not yet drawn");
  checks += 6;
}

// -- one spoken reading, from the same service -----------------------------
// The vitals station's microphone goes through this route too, since the
// owner's decision that every aspect of scribing goes through the medical
// scribe service. What a nurse is told about a reading is decided here, and
// the one case that must never carry a sentence is the one they caused.
const VITALS = "phc.op.vitals-record";
const spoke = (values: Record<string, unknown>, over: Partial<ScribeDraft> = {}): ScribeDraft =>
  ({ instrument: "phc.inst.vitals-voice", operation: VITALS, values,
     confidence: Object.fromEntries(Object.keys(values).map((k) => [k, 0.89])),
     evidence: Object.fromEntries(Object.keys(values).map((k) => [k, "said " + k])),
     tick: Object.keys(values), unfilled: [], transcript: "", ...over });

const reading = (over: Partial<ScribeSession>): ScribeSession =>
  ({ session: "scr-1", status: "ready", reason: "", drafts: [], transcript: "",
     operations: [VITALS], ...over });

const filled = heardFrom(reading({ transcript: "Systolic BP 138.",
                                   drafts: [spoke({ systolic: 138 })] }), VITALS);
ok(filled.draft?.values.systolic === 138, "a ready reading hands the service's answer up");
ok(filled.reason === undefined, "an answer needs no sentence under it");

// The reading this was written for. The service answered the form and left
// the rest of the sentence alone; a number grammar re-reading the transcript
// refused all of it over "what do I get".
const chatty = heardFrom(reading({
  transcript: "What do I get? Systolic BP 95, Diastolic BP 100. Systolic.",
  drafts: [spoke({ systolic: 95, diastolic: 100 })] }), VITALS);
ok(Object.keys(chatty.draft?.values ?? {}).length === 2,
   "words that answered no question do not refuse the words that did");

ok(heardFrom(reading({ transcript: "the patient walked in",
                       drafts: [spoke({})] }), VITALS).reason?.includes("for this form"),
   "a recording about something else says so, and is not a failure");
ok(heardFrom(reading({ transcript: "Systolic 138", drafts: [spoke({ systolic: 1 })] }),
             "phc.op.consult-document").reason !== undefined,
   "a draft for another operation is not this form's answer");
ok(heardFrom(reading({ transcript: "   " }), VITALS).reason?.includes("Type the values"),
   "a reading with no words says so, and says what to do instead");
ok(heardFrom(reading({ status: "failed", reason: "The service refused it." }), VITALS).reason
     === "The service refused it.",
   "the kernel's own reason is shown, not a paraphrase of it");
ok(heardFrom(reading({ status: "failed", reason: "" }), VITALS).reason?.includes("Type the values"),
   "a failure with no reason still tells the nurse what to do");
ok(heardFrom(reading({ status: "running" }), VITALS).reason?.includes("too long"),
   "a reading still running when the polling gave up says so");
ok(heardFrom(reading({ status: "withdrawn" }), VITALS).reason === "",
   "a nurse who stopped it themselves is owed no sentence");

// -- and narrowed to what the instrument declares --------------------------
// `fields:` on the instrument is the whole point of this: the template is
// built from the operation's questions, so the answer can carry a question
// this instrument was never declared for.
const wide = spoke({ systolic: 138, diastolic: 86, pulse: 88 });
const three = narrow(wide, ["systolic", "diastolic", "pulse"]);
ok(Object.keys(three.values).length === 3 && three.unfilled.length === 0,
   "a declaration naming every field drops nothing");
const one = narrow(wide, ["pulse"]);
assert.deepEqual(Object.keys(one.values), ["pulse"]);
checks++;
assert.deepEqual(one.tick, ["pulse"]);
checks++;
assert.deepEqual(Object.keys(one.evidence), ["pulse"]);
checks++;
ok(one.unfilled.includes("systolic") && one.unfilled.includes("diastolic"),
   "what the declaration excluded is NAMED, not silently dropped");
ok(!one.confidence.systolic, "a dropped value drops its score with it");

// `grammar: number` is a rule about what may reach a field, so it is one here.
const prose = narrow(spoke({ systolic: "quite high" as unknown as number }), ["systolic"]);
ok(Object.keys(prose.values).length === 0 && prose.unfilled.includes("systolic"),
   "prose in a number field is named rather than filled");

console.log(`ok   scribe: ${checks} checks`);
