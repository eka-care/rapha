/** The front desk, checked without a browser.
 *
 *  Run: node --experimental-strip-types src/desk.check.ts   (from web/)
 *
 *  Five properties. Each one is a decision in
 *  docs/superpowers/specs/2026-11-01-front-desk-and-design-system-design.md
 *  or in one of the three mockups, and each one is the kind that a later edit
 *  undoes quietly rather than loudly:
 *
 *  1. ONE FORM. A person found here and a person created here end on the same
 *     registration questionnaire. The spec's non-goal is explicit that two
 *     forms drift apart.
 *  2. FIND BEFORE CREATE. The row that creates somebody is last and is never
 *     the only thing offered when somebody was found. The anti-goal is a
 *     second national account for one person, which nothing merges and which
 *     the patient then carries permanently.
 *  3. NO SECOND ONE TIME PASSWORD. Somebody already found arrives with their
 *     values, and the panel's journey is suppressed by exactly that. NHA's own
 *     test is that a registration with an ABHA costs fewer keystrokes than one
 *     without, and asking for an OTP to learn what is on screen fails it.
 *  4. THE DIRECTORY MAY BE ABSENT. The local half always answers, and a
 *     directory that could not be asked is a sentence beside the results, not
 *     an error instead of them.
 *  5. THE SCREEN NAMES NOTHING. Not a station, a flag, a capability, a bundle
 *     or a column: what a row says comes from the view's own `columns:`, and
 *     which operation it commits through comes off the wire.
 *
 *  WHAT THIS CANNOT DO. It reads TypeScript as text and runs the pure half
 *  under plain node: no DOM, no React, no keyboard. It cannot prove that Tab
 *  moves the selection or that the panel opened. Those need the browser.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { answers, describing, directoryNote, fresh, lead, rows, type Resolution } from "./desk.ts";
import { mobileHint, runsJourney } from "./abha/sdk.ts";

const SRC = dirname(fileURLToPath(import.meta.url));
let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };
const read = (...p: string[]) => readFileSync(join(SRC, ...p), "utf8");

/** A view declaration shaped like the compiled one, with the columns in the
 *  order a bundle declared them. Nothing below reads a column by name. */
const DECL = { id: "v", kind: "queue", columns: ["name", "age", "sex", "village", "token", "category"] } as never;

/** The registration questionnaire's questions, reduced to what this file
 *  needs: an id, and a closed option list where there is one. */
const QUESTIONS = [
  { link_id: "name" },
  { link_id: "age" },
  { link_id: "sex", answer_option: [{ value: "female" }, { value: "male" }, { value: "other" }] },
  { link_id: "phone" },
  { link_id: "village" },
  { link_id: "category", answer_option: [{ value: "general" }, { value: "anc" }, { value: "ncd" }, { value: "tb" }] },
];

const KAMALA = {
  id: "seed-0001", name: "Kamala Devi", age: "34", sex: "female",
  phone: "9800000002", village: "Sonpur", category: "ncd",
  abha_number: null, directory_id: null, created_date: "2026-10-31T18:25:04+00:00",
};

const RESOLVED: Resolution = {
  query: "kamala",
  local: [KAMALA],
  suggestions: [{
    directory_id: "dir-77",
    values: { name: "Kamalamma R.", sex: "female", age: "58", phone: "9800000099", directory_id: "dir-77" },
    evidence: { name: "the patient directory, matched on name" },
    confidence: { name: 0.5, sex: 0.5, age: 0.5, phone: 0.5 },
  }],
  reachable: true,
  reason: "",
  commits_through: "phc.op.patient-register",
};

// ------------------------------------------------- 1. what a row says, and whose words

{
  // The order is the view's, and so is the selection. A row leads with the
  // first column the view declared and says the next three underneath; it
  // does not pick a field it likes the look of. This is the bug the patient
  // screen had: it showed age, sex and village at a bundle whose subject
  // might be a specimen.
  const { name, meta } = lead(DECL, KAMALA);
  assert.equal(name, "Kamala Devi", "a row leads with the first column the view declared");
  assert.equal(meta, "34 · female · Sonpur", "and says the next three underneath, in the declared order");

  // Reorder the declaration and the row changes with it, which is the whole
  // claim. If this passes while lead() has a field name written inside it,
  // the test is wrong, not the code: so swap two and check it MOVED.
  const swapped = lead({ ...(DECL as object), columns: ["village", "name", "age"] } as never, KAMALA);
  assert.equal(swapped.name, "Sonpur", "reordering the declaration reorders the row");
  assert.equal(swapped.meta, "Kamala Devi · 34", "and the line underneath follows it");

  // A column the record has nothing for is skipped rather than drawn as a
  // gap, and the plumbing never appears when a view declares no columns.
  const sparse = describing(undefined, { id: "x", name: "A", created_date: "y", village: "" });
  assert.deepEqual(sparse, ["name"], "with no declaration: no plumbing, no empty columns");
  ok("desk: what a row says comes from the view's own columns, in its order");
}

// ------------------------------------------------- 2. the form, and only this form's questions

{
  // Everything the record carries that THIS form asks for, and nothing else.
  // A payload key the questionnaire does not have is a commit the kernel
  // refuses; a choice value not on the question's own list is worse, because
  // the select renders empty over a payload that still carries it, and that
  // is a commit nobody read.
  const filled = answers(KAMALA, QUESTIONS);
  assert.deepEqual(filled, {
    name: "Kamala Devi", age: "34", sex: "female",
    phone: "9800000002", village: "Sonpur", category: "ncd",
  }, "the form opens with what the record carried, for the questions it asks");
  assert.ok(!("abha_number" in filled) && !("id" in filled) && !("directory_id" in filled),
    "and with nothing the form did not ask for");

  const offList = answers({ ...KAMALA, sex: "F" }, QUESTIONS);
  assert.ok(!("sex" in offList),
    "a choice value that is not on the question's own list is dropped, not " +
    "carried invisibly under an empty select");

  // The same record against a questionnaire that asks for one more thing gets
  // that one more thing, with no edit here. That is what "asked of the
  // questions, not of a field list" buys.
  const wider = answers({ ...KAMALA, district: "Anantapur" }, [...QUESTIONS, { link_id: "district" }]);
  assert.equal(wider.district, "Anantapur", "a bundle that asks for more is told more");
  ok("desk: the form is filled from the record, question by question, and never beyond them");
}

// ------------------------------------------------- 3. find before create

{
  const got = rows(RESOLVED, "kamala", DECL, QUESTIONS, mobileHint, "Register");
  assert.deepEqual(got.map((r) => r.kind), ["known", "suggested", "fresh"],
    "ours first, then the directory's, then the row that creates: find before create");
  assert.equal(got[0].name, "Kamala Devi");
  assert.equal(got[1].name, "Kamalamma R.");

  // A found person's values ride on their row, which is what stops the panel
  // running the identity journey. If this ever came back empty the journey
  // would mount and the patient would be asked for a one time password to
  // tell the screen what is already on it.
  assert.ok(Object.keys(got[0].values).length > 0,
    "somebody already found arrives with their values, so no OTP is spent on them");
  assert.ok(Object.keys(got[1].values).length > 0,
    "and so does somebody the directory suggested");

  // The directory's own confidence is carried through untouched. The kernel
  // caps it under the form's SURE threshold on purpose, so the fields draw
  // unconfirmed and get read.
  assert.deepEqual(got[1].confidence, RESOLVED.suggestions[0].confidence,
    "a suggestion's confidence reaches the form rather than being rounded up on the way");
  assert.deepEqual(got[1].evidence, RESOLVED.suggestions[0].evidence,
    "and so does the field the match was made on");

  // Nothing typed, nothing offered: a blank desk does not offer to create.
  assert.deepEqual(rows(null, "", DECL, QUESTIONS, mobileHint, "Register"), [],
    "an empty box offers nothing at all, least of all a new patient");
  ok("desk: ours, then the directory's, then the one that creates, and never create alone");
}

// ------------------------------------------------- 4. the row that creates

{
  // A name is kept as the name, under whatever the view calls its first
  // column. Nothing here types that column.
  const byName = fresh("kamala", DECL, mobileHint, "Register");
  assert.equal(byName.values[(DECL as unknown as { columns: string[] }).columns[0]], "kamala",
    "what was typed is kept, under the view's own first column");
  assert.equal(byName.mobile, undefined, "a name is not handed to the journey as a mobile number");

  // A mobile number goes to the identity journey instead, which is what its
  // own `mobile` argument is for. Keeping it as the name would put a phone
  // number in the name field of a national health record.
  const byPhone = fresh("98 0000 0031", DECL, mobileHint, "Register");
  assert.equal(byPhone.mobile, "9800000031", "a mobile number is handed to the journey, spaces and all");
  assert.deepEqual(byPhone.values, {}, "and is NOT written into the name");

  // The label is the caller's, which is the declared verb of the operation.
  assert.equal(byName.name, "Register", "the create row says what the declaration calls it");
  ok("desk: a typed name is kept as the name, a typed number goes to the journey, neither is guessed");
}

// ------------------------------------------------- 5. a directory that is not there

{
  const down: Resolution = {
    ...RESOLVED, suggestions: [], reachable: false,
    reason: "no patient directory is configured or reachable",
  };
  const got = rows(down, "kamala", DECL, QUESTIONS, mobileHint, "Register");
  assert.deepEqual(got.map((r) => r.kind), ["known", "fresh"],
    "the local half still answers, and the desk still offers to register");

  const said = directoryNote(down);
  assert.match(said, /could not be asked/,
    "a directory that could not be ASKED says so: a clerk who cannot tell that " +
    "from 'nobody matched' registers a duplicate");
  assert.match(said, /no patient directory is configured or reachable\./,
    "and says what it said, rather than a sentence this renderer made up");
  // The kernel's clause does not end in a full stop and nothing promises it
  // ever will, so the renderer finishes the sentence rather than running the
  // next one onto the end of it.
  assert.ok(!/reachable Only/.test(said),
    "two sentences ran together: " + said);
  assert.ok(!/\.\./.test(directoryNote({ ...down, reason: "the socket timed out." })),
    "and a reason that already ends in a full stop does not get a second one");
  assert.equal(directoryNote({ ...RESOLVED }), "",
    "a directory that answered says nothing at all");
  assert.equal(directoryNote(null), "", "and nothing is said before anything is searched");
  ok("desk: a directory that cannot be asked is a sentence, never an error instead of the results");
}

// ------------------------------------------------- 6. the screen names nothing

{
  const desk = read("screens", "Desk.tsx");
  const pure = read("desk.ts");
  const body = (s: string) => s.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");

  // The operation is the wire's answer or the workflow's, never a literal.
  // ui.check.ts's portability rule already forbids this bundle's words; this
  // is the positive half, which that rule cannot express: it is not enough
  // that the id is absent, the screen has to be READING one.
  assert.match(body(desk), /found\?\.commits_through \?\? firstOperation\(cat, workflow\)/,
    "which operation the desk commits through is the server's answer, then the workflow's");
  assert.ok(!/phc\.|lab\./.test(body(desk) + body(pure)),
    "no bundle's operation, view or schema id is written into the desk");

  // What the row says is read off the declaration, not off a field list.
  assert.match(body(pure), /decl\?\.columns \?\? \[\]/,
    "the desk reads the view's declared columns");

  // The create row's label is the declaration's verb.
  assert.match(body(desk), /createLabel\(cat, workflow\)/,
    "the create row and the heading are named by the declaration, not by this file");

  // The two sentences the desk DOES write are about where a person was found,
  // which is this renderer's own kernel contract and not a bundle's word:
  // a patient is either in this centre's register or in the directory.
  // Neither may ever grow into a station or a programme.
  const written = [...body(desk).matchAll(/^const ([A-Z_]+) = "([^"]+)";$/gm)].map((m) => m[2]);
  assert.ok(written.every((w) => !/station|queue|ward|programme/i.test(w)),
    "a constant on this screen names a station or a programme: " + written.join(", "));
  ok("desk: the operation, the heading and the labels all come from declarations");
}

// ------------------------------------------------- 7. the keyboard is on the screen

{
  const desk = read("screens", "Desk.tsx");
  const css = read("style", "desk.css");

  // The clerk is talking to a patient. Every one of these is a reach for the
  // mouse if it is missing.
  for (const [key, why] of [
    ["ArrowDown", "move down the list"],
    ["ArrowUp", "move back up it"],
    ["Enter", "take the selected row"],
    ["Tab", "jump to the row that creates somebody new"],
    ["Escape", "clear the box"],
  ] as const) {
    assert.ok(new RegExp(`e\\.key === "${key}"`).test(desk), `the desk has no way to ${why}`);
  }
  assert.match(desk, /box\.current\?\.focus\(\)/,
    "the box has focus on arrival; a desk you have to click into first is a desk with a mouse in it");

  // Tab must not trap. The guard is what lets a second Tab leave the field,
  // and losing it would strand a keyboard user on this screen.
  assert.match(desk, /e\.key === "Tab" && !e\.shiftKey && freshAt >= 0 && pick !== freshAt/,
    "Tab moves the selection ONCE and then lets go; without the guard the field is a trap");

  // And the selection has to be visible without a mouse anywhere near it.
  assert.match(css, /\.desk-hit\[data-active="true"\]\s*\{[^}]*border-color:\s*var\(--color-accent\)/,
    "the keyboard selection is drawn, not merely tracked");
  const hoverOnly = [...css.matchAll(/([^{}]+):hover[^{]*\{([^}]*)\}/g)]
    .filter((m) => /(^|;)\s*(display|visibility|content)\s*:/.test(m[2]))
    .map((m) => m[1].trim());
  assert.deepEqual(hoverOnly, [],
    "the desk reveals something on hover, which a keyboard never produces: " + hoverOnly.join(", "));
  ok("desk: arrows, Enter, Tab and Escape all work, Tab does not trap, and the selection is visible");
}

// ------------------------------------------------- 8. the one time password nobody has to spend

{
  // THE PROPERTY THIS WHOLE SCREEN EXISTS FOR, and the one the first pass
  // could not test. It was an expression inside form/Panel.tsx, which no
  // check can import because the journey it mounts reaches a stylesheet. The
  // mutation that inverted it ran green: every word a reader would grep for
  // stayed exactly where it was, the types were still sound, and the only
  // visible effect was a patient being asked to read a one time password off
  // a handset to tell the screen a name that was already on it.
  //
  // The rule now lives in abha/sdk.ts and is run here against the four cases
  // that matter, by behaviour and not by text.
  const REGISTERS = ["registered", "abha.pending"];
  const nobody = { reviewing: false, found: false };

  assert.equal(runsJourney("any.op.register", REGISTERS, nobody), true,
    "registering somebody nobody has found runs the journey, which is where " +
    "a new patient's name and address come from instead of the keyboard");
  assert.equal(runsJourney("any.op.register", REGISTERS, { reviewing: false, found: true }), false,
    "A PATIENT THE DESK ALREADY FOUND IS NEVER SENT THROUGH THE JOURNEY. " +
    "Spending a one time password to learn what is on the screen is the test " +
    "NHA uses to say the ABHA step is in the wrong place, and it is the main " +
    "thing standing between this and a paper register");
  assert.equal(runsJourney("any.op.register", REGISTERS, { reviewing: true, found: false }), false,
    "reviewing somebody else's proposal keeps the plain form; re-running a " +
    "national identity journey is not how you read a payload");
  assert.equal(runsJourney("any.op.accession", ["order.accessioned"], nobody), false,
    "an operation that does not say an ABHA belongs here never opens the journey, " +
    "which is how a laboratory's accession and a centre's registration share one panel");

  // And the panel has to be ASKING. A correct function nothing calls is the
  // same bug one indirection further away.
  const panel = read("form", "Panel.tsx")
    .split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
  assert.match(panel, /runsJourney\(op\.id, op\.emits, \{ reviewing: !!proposal, found: !!seed \}\)/,
    "the panel decides this for itself again instead of asking the rule; " +
    "an inlined copy is a copy that can be inverted alone");
  ok("desk: a patient already found is never asked for a one time password");
}

console.log(`\n${checks} checks passed`);
