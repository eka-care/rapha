/** One runnable check for the thread's logic and the palette's.
 *
 *  Run: node --experimental-strip-types src/messages.check.ts   (from web/)
 *
 *  It reads the real compiled catalogue and the real questionnaires, so it
 *  fails when a declaration changes shape, which is the point. The fixture
 *  thread is hand-built, because the interesting cases (a refusal older than
 *  the last post, a proposal for an operation the visit has moved past) do not
 *  reliably exist in a seeded database.
 *
 *  Four of these assertions are safety properties, not conveniences:
 *
 *   - the composer never returns a disabled pill;
 *   - no module the thread screen composes from can commit or confirm;
 *   - a superseded proposal offers no Review;
 *   - a refused audit row never renders as a posted record.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  actorOf, agentLine, clock, composer, fmt, header, messages, queueViewFor, summariesFor,
  type Ctx,
} from "./messages.ts";
import { firstOperation, isAsk, rows } from "./search.ts";
import { blankRow, itemFields, toRow } from "./structured.ts";
import type { Catalogue, Operation, Questionnaire, ThreadView, ViewDecl, ViewResult } from "./types";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");
const cat = JSON.parse(read("catalogue/catalogue.json")) as Catalogue;

const schema = (id: string | undefined): Questionnaire | null => {
  if (!id) return null;
  try {
    return JSON.parse(read(`questionnaires/${id}.json`)) as Questionnaire;
  } catch {
    return null;
  }
};

const VITALS = "phc.op.vitals-record";
const CONSULT = "phc.op.consult-document";
const WF = "phc.wf.outpatient";
assert.ok(cat.operations[VITALS], "the compiled catalogue should carry the vitals operation");

const queue = queueViewFor(cat, WF)!;
assert.equal(queue.kind, "queue");

const ctx: Ctx = { operations: cat.operations, schema, badges: queue.badges ?? {} };

const thread: ThreadView = {
  id: "enc-t",
  workflow: WF,
  subject: { encounter: "enc-t", name: "A Patient", age: "34", sex: "female", village: "Sonpur",
             token: "A02", abha_number: null, status: "in_progress", created_by: "seed" },
  flags: ["registered", "vitals.recorded", "abha.pending"],
  station: "doctor",
  line: [
    { station: "reception", label: "registered", status: "done" },
    { station: "nurse", label: "vitals.recorded", status: "done" },
    { station: "doctor", label: "consult.documented", status: "now" },
  ],
  actions: [cat.operations[CONSULT]],
  proposals: [
    {
      id: "prop-1", thread: "enc-t", operation: VITALS,
      payload: { systolic: 140, diastolic: 90, pulse: 72 },
      proposed_by: "agent", surface: "mcp", status: "pending",
      created_at: "2026-09-10T18:53:11Z", flags_raised: [],
    },
  ],
  audit: [
    { id: "a1", thread: "enc-t", operation: "phc.op.lab-order", actor: "user:mo", surface: "mcp",
      payload: {}, outcome: "denied: precondition not met: consult.documented",
      at: "2026-09-10T18:40:00Z", proposal: null },
    { id: "a2", thread: "enc-t", operation: VITALS, actor: "user:nurse", surface: "rendered",
      payload: { systolic: 190, diastolic: 125, pulse: 72, override_reason: "cuff reads high, repeated" },
      outcome: "allowed", at: "2026-09-10T18:45:00Z", proposal: null },
    { id: "a3", thread: "enc-t", operation: VITALS, actor: "agent", surface: "mcp",
      payload: { systolic: 140 }, outcome: "proposed", at: "2026-09-10T18:53:11Z", proposal: "prop-1" },
    { id: "a4", thread: "enc-t", operation: "phc.op.abha-link", actor: "agent", surface: "mcp",
      payload: {}, outcome: "denied: payload invalid: method is required",
      at: "2026-09-10T18:55:00Z", proposal: null },
  ],
  capabilities: ["encounter.document", "vitals.record", "lab.order"],
  held: ["encounter.document"],
  nudge: "doctor: Document a consultation",
};

// ---------------------------------------------------------------- messages

const msgs = messages(thread, ctx);

// Order is the record's order, whatever the kinds are.
assert.deepEqual(
  msgs.map((m) => m.kind),
  ["denied", "posted", "proposal", "denied"],
  "messages are one time-sorted list of the record's events",
);

// A proposal's own `proposed` audit row is the same event as its card, and
// drawing both would show the same values twice.
assert.equal(msgs.filter((m) => m.kind === "posted").length, 1);

const posted = msgs.find((m) => m.kind === "posted")!;
assert.equal(posted.title, cat.operations[VITALS].title, "the card is titled by the declaration");
const labels = posted.values.map((v) => v.label);
assert.ok(labels.includes("Systolic BP"), "payload values are labelled by the questionnaire");
assert.ok(
  posted.values.find((v) => v.link_id === "systolic")!.value.endsWith("mm[Hg]"),
  "the unit comes from styling_metadata.phc",
);
assert.ok(
  posted.values.find((v) => v.link_id === "override_reason")!.crit,
  "the reason someone typed to get past a range block is never quiet",
);
assert.ok(
  posted.values.some((v) => v.crit && v.link_id !== "override_reason"),
  "190/125 is outside the critical band the declaration names",
);

// A refusal is a refusal: it is never drawn as a record of something done.
const denials = msgs.filter((m) => m.kind === "denied");
assert.equal(denials.length, 2);
assert.equal(denials[0].old, true, "a refusal before the last post folds away");
assert.equal(denials[1].old, false, "the newest refusal stays on screen");
for (const d of denials) assert.ok(!("values" in d), "a refusal has no values to show");

// The visit is past vitals, so a pending vitals proposal is superseded: the
// guard would refuse it, and the screen has to say so before the tap.
const prop = msgs.find((m) => m.kind === "proposal")!;
assert.equal(prop.stale, true);
assert.equal(prop.by, "agent");
assert.equal(prop.values.length, 3);

// ... and when the operation is live again, it is reviewable.
const live = messages({ ...thread, actions: [cat.operations[VITALS]] }, ctx);
assert.equal(live.find((m) => m.kind === "proposal")!.stale, false);

assert.equal(actorOf("user:lab_incharge"), "lab incharge");
assert.equal(actorOf("agent:demo"), "agent", "a machine is one word on a card, whichever account it used");
assert.equal(actorOf(null), "unattributed");
assert.equal(clock("2026-09-10T18:45:00Z"), "18:45");

// ---------------------------------------------------------------- the agent

const line = agentLine(thread, ctx);
assert.equal(line.sentences.length, 2, "what just happened, and where the baton is. Nothing else");
assert.ok(line.sentences[0].includes("was refused"), "the newest event is the first sentence");
assert.equal(line.sentences[1], "Doctor: Document a consultation.", "the kernel's nudge is the second, ended");
assert.ok(line.actions.length <= 5);

const quiet = agentLine(
  { ...thread, actions: [], audit: [], nudge: "Waiting at doctor. Nobody with your capabilities can act here." },
  ctx,
);
assert.deepEqual(quiet.actions, [], "no actions means no props, and no greyed ones either");
assert.equal(quiet.sentences.length, 2, "with nothing to offer, the agent does not offer");
assert.ok(
  quiet.sentences[1].includes("Nobody with your capabilities"),
  "the reason for an absence is said in words",
);

// ---------------------------------------------------------------- composer

// The scribe shortcut, the capped action list and the "More" pill used to be
// tested here. loops.ts (loops.check.ts) now owns that behaviour: the agent's
// bubble draws the one primary action and its overflow, so composer() has
// only the summary pills left to be responsible for.
const bar = composer(thread, cat);
assert.ok(bar.pills.length > 0);
for (const p of bar.pills) {
  assert.ok(!("disabled" in p), "a pill is never disabled: an unavailable action is absent");
}
assert.ok(
  bar.pills.every((p) => p.kind === "summary"),
  "the composer offers summary views only; an operation is offered once, by the agent's own bubble",
);
assert.ok(
  bar.pills.some((p) => p.kind === "summary"),
  "every summary view this workflow declares is a pill on the thread",
);

assert.ok(summariesFor(cat, WF).length >= 1);

// ------------------------------------------------------------------ header

const head = header(thread, queue);
assert.equal(head.name, "A Patient");
assert.equal(head.initials, "AP");
assert.ok(
  !head.meta.some((m) => m === "in_progress" || m === "seed"),
  "the queue view's columns decide the meta line, so plumbing never reaches it",
);
assert.deepEqual(head.meta, ["34", "female", "Sonpur"]);
assert.ok(head.badges.some((b) => b.text === "A02"), "the token is a badge, not part of the meta");
assert.ok(
  head.badges.some((b) => b.text === "abha pending" && b.style === "warn"),
  "a flag is styled by the queue view's badge map, not by a regex over its name",
);
assert.ok(
  !head.badges.some((b) => b.text === "registered"),
  "a flag the view did not name is not a badge",
);

// A thread whose subject carries no name falls back to the id rather than
// inventing one. bundles/LAB-LOG.md 12: a lab thread has no patient row.
const nameless = header({ ...thread, subject: { encounter: "spec-1", token: "L07", status: "in_progress" } }, queue);
assert.equal(nameless.name, "L07", "with no name column on the subject, the token is the headline");
assert.ok(!nameless.badges.some((b) => b.text === "L07"), "and it is not also a badge");

// With no queue view at all, nothing has declared what matters, so the first
// field that is not obvious plumbing is the least-worst headline. It is a
// worse screen than the declared one, which is the argument for declaring.
const unguided = header({ ...thread, subject: { encounter: "spec-1", status: "x" } }, undefined);
assert.equal(unguided.name, "spec-1");
assert.equal(header({ ...thread, subject: {} }, undefined).name, "enc-t", "and with nothing, the id");

// ------------------------------------------------------------------ palette

const decl = queue;
const result: ViewResult = {
  view: decl.id, kind: "queue", generated_at: "", groups: [],
  rows: [
    { thread: "enc-1", subject: { name: "Kamala Devi", age: "34", sex: "female", village: "Sonpur", token: "A02" },
      station: "doctor", flags: [], badges: { "abha.pending": "warn" }, opened_at: "" },
    { thread: "enc-2", subject: { name: "Rahul Yadav", age: "51", sex: "male", village: "Bela", token: "A03" },
      station: "nurse", flags: [], badges: {}, opened_at: "" },
  ],
};
const nav: ViewDecl[] = [decl];

const all = rows("", [{ decl, result }], nav);
assert.equal(all.filter((r) => r.kind === "thread").length, 2, "an empty box lists today's line");
assert.ok(all.some((r) => r.kind === "home"), "Home is always reachable");

const hit = rows("kamala", [{ decl, result }], nav);
assert.deepEqual(hit.filter((r) => r.kind === "thread").map((r) => r.id), ["enc-1"]);
assert.equal(hit.find((r) => r.kind === "thread")!.group, "Matches");

const village = rows("bela", [{ decl, result }], nav);
assert.deepEqual(village.filter((r) => r.kind === "thread").map((r) => r.id), ["enc-2"],
  "any column the view declared is searchable, not only the name");

const miss = rows("zzz", [{ decl, result }], nav);
assert.equal(miss.filter((r) => r.kind === "thread").length, 0, "a miss is a miss");

const question = rows("how many are waiting?", [{ decl, result }], nav);
assert.equal(question[0].kind, "ask", "a question offers the agent first");
assert.equal(isAsk("Kamala"), false);

// Create on miss opens the first operation of the workflow's first step,
// whichever the bundle says that is.
assert.equal(firstOperation(cat, WF), cat.workflows![WF].steps[0].operations[0]);

// ------------------------------------------ a structured answer has fields
//
// The sub fields of a structured question are not in the questionnaire. They
// are in the operation's own mapping, which is what makes a real control for
// one possible without a word of PHC in the renderer.

// catalogue/catalogue.json keeps `operations` catalogue-wide, from
// catalogue/build.py, and the mapping is attached per bundle by
// kernel/declarations.py. The API merges the two on /catalogue and so does
// this, from the same code, rather than from a copy of what it should say.
const mapped: Record<string, Operation> = JSON.parse(
  execFileSync("python3", ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(root.replace(/\/$/, ""))})
from kernel import declarations
print(json.dumps(declarations.load().operations))
`], { encoding: "utf8" }),
);
for (const [id, op] of Object.entries(mapped)) cat.operations[id] = op;

for (const [id, link_id, expected] of [
  ["phc.op.rx-prescribe", "medications", ["medication", "dosage_instruction"]],
  ["phc.op.lab-order", "investigations", ["code"]],
  // Two records, both per_item, and the second names the same keys: one field
  // each, not four.
  ["phc.op.pharmacy-dispense", "dispenses", ["medication", "quantity"]],
  ["phc.op.consult-document", "diagnosis", ["code"]],
] as [string, string, string[]][]) {
  const op = cat.operations[id];
  assert.ok(op, `${id} is not in the catalogue`);
  assert.deepEqual(itemFields(op, link_id).map((f) => f.key), expected, id);
  // Every field must name the resource its row becomes, or the form cannot
  // say what one row is.
  for (const f of itemFields(op, link_id)) assert.ok(f.resource, `${id} ${f.key} has no resource`);
}

// An operation with no mapping for that question gets nothing back, and the
// form falls to the free text row it always drew.
assert.deepEqual(itemFields(cat.operations["phc.op.vitals-record"], "medications"), []);
assert.deepEqual(itemFields(undefined, "medications"), []);

// A row the kernel sent as a bare string keeps its text where mapping.items()
// would have looked for it, so opening a proposal never loses a line.
const rxFields = itemFields(cat.operations["phc.op.rx-prescribe"], "medications");
assert.deepEqual(toRow("Amoxicillin 500mg", rxFields), { medication: "Amoxicillin 500mg" });
assert.deepEqual(toRow({ medication: "A", dosage_instruction: "B" }, rxFields),
  { medication: "A", dosage_instruction: "B" });
assert.deepEqual(toRow("CBC", []), { code: "CBC" });
assert.equal(blankRow({ medication: "", dosage_instruction: "  " }), true);
assert.equal(blankRow({ medication: "A" }), false);

// And a card reads one back with the names on it rather than as a run-on
// string. This is the whole difference between a record and a sentence.
assert.equal(fmt([{ medication: "Amoxicillin 500mg", dosage_instruction: "1 cap TDS" }]),
  "Medication: Amoxicillin 500mg, Dosage instruction: 1 cap TDS");
assert.equal(fmt([{ code: "CBC" }, { code: "RBS" }]), "CBC; RBS");
assert.equal(fmt("plain"), "plain");

// ------------------------------------------------------- no write from here

// The thread screen composes from these four modules. If a commit or a confirm
// ever appears in one of them, the conversation has become a machine surface.
for (const file of ["src/messages.ts", "src/search.ts", "src/ask.ts", "src/Thread.tsx",
                    "src/structured.ts"]) {
  const body = read(`web/${file}`)
    .split("\n")
    .filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l))          // prose about commits is fine
    .join("\n");
  assert.ok(!/\bclient\./.test(body), `${file} must hold no client`);
  assert.ok(!/\bfetch\(/.test(body) || file === "src/ask.ts", `${file} must not fetch`);
  assert.ok(!/\.commit\(|\.confirm\(/.test(body), `${file} must have no commit or confirm path`);
}

console.log("ok   thread messages, agent line, composer, header and palette rows");
console.log("ok   a structured answer's fields come from the operation's own mapping");
