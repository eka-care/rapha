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
import {
  answers, arrivals, describing, deskTitle, destination, directoryNote, firstStation,
  fresh, lead, rows, type Desk, type Resolution,
} from "./desk.ts";
import { identified, mobileHint, runsJourney } from "./abha/sdk.ts";

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

/** What a bundle calls one of its own stored codes. Two entries, so the
 *  difference between the code and the word is visible in an assertion. */
const DISPLAY = (link: string, value: string) =>
  (link === "category" && value === "ncd" ? "NCD" : value);

/** Everything the desk is handed. Nothing in it is typed by desk.ts. */
const RULES: Desk = {
  decl: DECL, questions: QUESTIONS, hint: mobileHint,
  freshLabel: "Register", display: DISPLAY, identified,
};

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
  const { name, meta } = lead(DECL, KAMALA, DISPLAY);
  assert.equal(name, "Kamala Devi", "a row leads with the first column the view declared");
  // EVERY other declared column the record carries, not the first three, and
  // each under the word the bundle gives that stored value. The mockup's row
  // is four facts wide for a reason: this is the line a clerk reads before
  // committing somebody else's record to the day. `ncd` would be the stored
  // code, and the queue beside this screen has never shown it.
  assert.equal(meta, "34 · female · Sonpur · NCD",
    "the line under the name is every declared column, in the declared order, "
    + "under the declared word");
  assert.ok(!/ncd/.test(meta),
    "a row drew the stored code where the queue beside it draws the bundle's word");

  // Reorder the declaration and the row changes with it, which is the whole
  // claim. If this passes while lead() has a field name written inside it,
  // the test is wrong, not the code: so swap two and check it MOVED.
  const swapped = lead({ ...(DECL as object), columns: ["village", "name", "age"] } as never, KAMALA, DISPLAY);
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
  const got = rows(RESOLVED, "kamala", RULES);
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
  assert.deepEqual(rows(null, "", RULES), [],
    "an empty box offers nothing at all, least of all a new patient");
  ok("desk: ours, then the directory's, then the one that creates, and never create alone");
}

// ------------------------------------------------- 4. the row that creates

{
  // A name is kept as the name, under whatever the view calls its first
  // column. Nothing here types that column.
  const byName = fresh("kamala", RULES);
  assert.equal(byName.values[(DECL as unknown as { columns: string[] }).columns[0]], "kamala",
    "what was typed is kept, under the view's own first column");
  assert.equal(byName.mobile, undefined, "a name is not handed to the journey as a mobile number");

  // A mobile number goes to the identity journey instead, which is what its
  // own `mobile` argument is for. Keeping it as the name would put a phone
  // number in the name field of a national health record.
  const byPhone = fresh("98 0000 0031", RULES);
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
  const got = rows(down, "kamala", RULES);
  assert.deepEqual(got.map((r) => r.kind), ["known", "fresh"],
    "the local half still answers, and the desk still offers to register");

  const said = directoryNote(down);
  // The fact a clerk needs, LEADING, because this is the half of the sentence
  // their next decision turns on: which register actually answered. A clerk
  // who cannot tell "nobody matched" from "I could not look" registers a
  // duplicate, and nothing merges two.
  assert.match(said, /^Only this centre's own register was searched/,
    "the quiet line leads with which register answered");
  assert.match(said, /no patient directory is configured or reachable\./,
    "and carries the kernel's own reason, rather than a sentence this renderer made up");
  // ONE SENTENCE. It used to be two, and the first of them was about a
  // directory the clerk never asked for.
  assert.equal(said.split(". ").length, 1,
    "the directory note is one sentence, not a paragraph about a directory " +
    "nobody was relying on: " + said);
  assert.ok(!/\.\./.test(directoryNote({ ...down, reason: "the socket timed out." })),
    "a reason that already ends in a full stop does not get a second one");
  assert.ok(!/reachableOnly|searched:no/.test(said), "two clauses ran together: " + said);
  assert.equal(directoryNote({ ...RESOLVED }), "",
    "a directory that answered says nothing at all");
  assert.equal(directoryNote(null), "", "and nothing is said before anything is searched");

  // AND IT IS NOT AN ALARM. Colour in this system means clinical risk, and a
  // directory that was never configured is not one -- but this note is drawn
  // on every search a deployment without one ever runs, so an amber block
  // here is an alarm a clerk meets hundreds of times a day for a condition
  // that will never change. It was one. The mutation this catches is a later
  // edit reaching for the warning token because the sentence sounds like a
  // warning.
  const css = read("style", "desk.css");
  const note = /\.desk-note\s*\{([^}]*)\}/.exec(css);
  assert.ok(note, "desk.css draws no .desk-note at all");
  assert.ok(!/--color-warning|--color-danger|--color-crit/.test(note![1]),
    "the directory note is drawn in an alarm colour: " + note![1].trim());
  assert.ok(!/background/.test(note![1]),
    "the directory note is a block, not a line: " + note![1].trim());

  // And it sits UNDER the people it is not about. Read off the screen's own
  // order, because the whole complaint was where it was, not what it said.
  const desk = read("screens", "Desk.tsx");
  const list = desk.indexOf('<div className="desk-hits"');
  const said2 = desk.indexOf("{note &&");
  assert.ok(list > 0, "the desk draws no results list at all");
  assert.ok(said2 > 0, "the desk no longer says anything about the directory");
  assert.ok(list < said2,
    "the directory note is drawn above the search results again");
  ok("desk: a directory that cannot be asked is one quiet line under the results, never an alarm over them");
}

// ------------------------------------------------- 5b. what this screen is called

{
  // A screen's name is a declaration's word like every other word here. It
  // was the declared TITLE OF THE OPERATION the panel commits through, so the
  // screen was called "Register a new patient" while a clerk was searching
  // for somebody who is already registered.
  //
  // The declaration that already says what this place is, is the workflow's:
  // its first step is the station a patient reaches first, and this screen is
  // that station.
  const CAT = {
    workflows: {
      "x.wf.line": {
        id: "x.wf.line", title: "A line",
        steps: [
          { station: "reception", done_when: "registered", applies_when: null, operations: ["x.op.register"] },
          { station: "nurse", done_when: "seen", applies_when: null, operations: [] },
          { station: "lab", done_when: "resulted", applies_when: "ordered", operations: [] },
          { station: "pharmacy", done_when: "given", applies_when: null, operations: [] },
        ],
      },
    },
    operations: {},
  } as never;

  assert.equal(deskTitle(CAT, "x.wf.line"), "Reception",
    "the screen is named after the station a patient reaches first");
  assert.equal(firstStation(CAT, "x.wf.line"), "reception",
    "and the station itself is the workflow's answer, read not typed");

  // Change the declaration and the name changes with it. If this passes while
  // deskTitle has a word written inside it, the test is wrong, not the code.
  const other = { workflows: { w: { id: "w", title: "t", steps: [{ station: "accession", done_when: "a", applies_when: null, operations: [] }] } }, operations: {} } as never;
  assert.equal(deskTitle(other, "w"), "Accession",
    "a bundle whose line starts somewhere else names this screen after that");
  assert.equal(deskTitle({ workflows: {}, operations: {} } as never, undefined), "",
    "a workflow with no steps names nothing, and the caller falls back rather than inventing a word");

  // ------------------------------------------- where a row leads
  //
  // The mockup draws the selected row as `↵ send to nurse`, and `↵` alone
  // told a clerk nothing about what was about to happen to the person in
  // front of them.
  const REG = { id: "x.op.register", station: "reception" } as never;
  assert.equal(destination(CAT, REG, "x.wf.line"), "nurse",
    "the row says where taking it sends this person: the next step of the line");

  // A CONDITIONAL step is skipped. The laboratory step applies only to a
  // patient somebody ordered a test for, so naming it on the row would
  // promise a destination most patients never walk.
  const SEEN = { id: "x.op.vitals", station: "nurse" } as never;
  assert.equal(destination(CAT, SEEN, "x.wf.line"), "pharmacy",
    "a step the workflow declares conditional is not promised as a destination");

  const LAST = { id: "x.op.give", station: "pharmacy" } as never;
  assert.equal(destination(CAT, LAST, "x.wf.line"), "",
    "an operation that ends the line promises nothing, rather than guessing");
  assert.equal(destination(CAT, undefined, "x.wf.line"), "",
    "and so does an operation the workflow has never heard of");
  ok("desk: the screen is named by the first station, and a row says which station it leads to");
}

// ------------------------------------------------- 5c. the shift, before a key is pressed

{
  // The screen used to say "Nobody searched for yet." to a clerk arriving at
  // their shift. Three facts are already in the rows the declared queue view
  // returns, and each one is a decision in the spec: who self registered at
  // the poster and is still waiting, how long the line is, and who has
  // already been through this desk today -- which is how a second
  // registration for one person is caught by eye before it exists.
  const at = (thread: string, station: string | null, opened: string) =>
    ({ thread, subject: {}, station, flags: [], badges: {}, opened_at: opened } as never);
  const QUEUE = [
    at("t1", "reception", "2026-11-01T09:00:00Z"),
    at("t2", "nurse", "2026-11-01T09:30:00Z"),
    at("t3", "reception", "2026-11-01T09:40:00Z"),
    at("t4", "pharmacy", "2026-11-01T08:00:00Z"),
    at("t5", null, "2026-11-01T07:00:00Z"),
  ];
  const day = arrivals(QUEUE, "reception");

  assert.deepEqual(day.waiting.map((r) => r.thread), ["t1", "t3"],
    "waiting here is everybody standing at the first step: arrived, not sent on");
  assert.deepEqual(day.moving.map((r) => r.thread), ["t2", "t4"],
    "and the line is everybody past it who is still walking it");
  assert.deepEqual(day.sent.map((r) => r.thread), ["t2", "t4", "t5"],
    "already sent on is everybody past the first step, NEWEST FIRST, so the " +
    "person registered a minute ago is the one a clerk sees");
  assert.equal(day.all, 5, "and the day's number is every row the view returned");

  // Capped. This screen's job is the box: a list that grows with the day is a
  // dashboard, and the spec is explicit that this is not one.
  const many = Array.from({ length: 20 }, (_, i) => at(`m${i}`, "reception", `2026-11-01T09:${i}:00Z`));
  assert.equal(arrivals(many, "reception").waiting.length, 4,
    "the waiting list is capped; the desk is not a queue screen");
  assert.equal(arrivals(many, "nurse").sent.length, 4, "and so is the list of who has been through");

  // A bundle whose workflow declares no steps has no first station, and then
  // nobody is "waiting here" rather than everybody being.
  assert.deepEqual(arrivals(QUEUE, undefined).waiting, [],
    "with no declared first station the desk claims nobody, rather than claiming everybody");
  ok("desk: the shift before the first keystroke is read off the declared queue, and is capped");
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

// ------------------------------------------------- 7b. the key that was mouse only

{
  const desk = read("screens", "Desk.tsx");
  const body = desk.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");

  // A ROW IS TAKEN BY A CLICK, NOT BY A MOUSEDOWN. This is the defect that
  // broke the whole "new: Tab, then 4 answers" path and it was invisible to
  // every check here: the row was a real button with a real handler, the
  // handler was correct, and it hung off `onMouseDown` -- which is an event
  // only a mouse produces. A clerk who tabbed onto the row and pressed Enter
  // fired a `click` that nothing was listening for. The row took the focus
  // and did nothing, twice, and the mouse worked perfectly, which is the
  // worst possible shape for a bug on a screen whose entire reason to exist
  // is that nobody touches the mouse.
  assert.match(body, /onClick=\{\(\) => \{ void choose\(r\); \}\}/,
    "a desk row is not taken by a click, so Enter on a focused row does nothing");
  // And mousedown does nothing but hold the keyboard still. If it ever takes
  // the row again, a mouse click takes it twice.
  assert.match(body, /onMouseDown=\{\(e\) => e\.preventDefault\(\)\}/,
    "mousedown on a desk row must only keep the focus in the box");
  assert.ok(!/onMouseDown=\{\([^)]*\) => \{[^}]*choose/.test(body),
    "a desk row takes itself on mousedown as well as on click: a mouse would take it twice");
  ok("desk: a row is taken by the keyboard, not only by a mouse");
}

// ------------------------------------------------- 7c. what the clerk typed survives

{
  // THE MOCKUP'S OWN PROMISE ON THAT ROW: "keeps what you typed as the name".
  // The row kept it and the screen would not hand it over, because the only
  // way into the panel's fields was `seed` -- and a seed means somebody was
  // FOUND, which is precisely what stops the national identity journey. So
  // the typed name was dropped rather than risk suppressing the journey, and
  // a clerk typed the same name twice, thirty seconds apart, with the patient
  // watching.
  //
  // `start` is the second door: into the fields, never into the found/not
  // found decision. Both halves are asserted, because passing it as a seed
  // would make this test pass and would silently cost every new patient a one
  // time password they did not need to spend.
  const desk = read("screens", "Desk.tsx")
    .split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
  assert.match(desk, /start=\{opening\.kind === "fresh" \? opening\.values : undefined\}/,
    "what the clerk typed is not carried into the form at all");
  assert.match(desk, /seed=\{opening\.kind === "fresh" \? undefined : opening\.values\}/,
    "the row that creates somebody new hands over a SEED, which would stop the journey");

  const panel = read("form", "Panel.tsx")
    .split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
  assert.match(panel, /proposal\?\.payload \?\? draft\?\.values \?\? seed \?\? start \?\? \{\}/,
    "the panel does not open with what the clerk typed");
  // And the journey still reads `seed` and only `seed`.
  assert.match(panel, /runsJourney\(op\.id, op\.emits, \{ reviewing: !!proposal, found: !!seed \}\)/,
    "the journey decision has been widened to count what the clerk typed as " +
    "having found somebody, which costs every new patient an OTP");

  // AND THE FORM DOES NOT TELL THE CLERK OFF BEFORE THEY HAVE TYPED. The list
  // of what is still empty is a report on what a MACHINE left out. On a form
  // nobody has touched it is five red words for not having started.
  assert.match(panel, /const prefilled = !!proposal \|\| !!draft \|\| !!seed \|\| Object\.keys\(fromAbha\)\.length > 0;/,
    "nothing decides whether a machine filled this form in");
  assert.match(panel, /\{showForm && prefilled && missing\.length > 0 && !tried &&/,
    "the form lists what is missing before anybody has typed a character");
  // AND A CLERK CAN TYPE MORE THAN ONE CHARACTER INTO A FIELD.
  //
  // The panel's focus ref was an inline arrow, which React treats as a NEW
  // ref on every render: it called the callback with null and then with the
  // node again after every keystroke, so the "closing" branch refocused
  // whoever opened the panel, the `landed` guard was reset, and `el.focus()`
  // moved the keyboard back onto the dialog. A clerk typed one character into
  // a field and the rest went nowhere -- on every field, of every operation,
  // on every screen that opens a panel. The guard in that callback was
  // written to prevent exactly this and could never fire.
  //
  // A stable identity is the whole fix, and it is invisible to every other
  // check here: the branches, the guard and the focus call are all unchanged.
  assert.match(panel, /const landing = useCallback\(\(el: HTMLElement \| null\) => \{/,
    "the panel's focus ref is not stable, so it re-runs on every keystroke");
  assert.match(panel, /\}, \[inline\]\);/,
    "the panel's focus ref has grown a dependency that changes as the form is filled in");
  assert.match(panel, /ref=\{landing\}/, "and the dialog still uses it");
  assert.ok(!/ref=\{\(el\) =>/.test(panel),
    "the panel attaches an inline ref callback, which React re-runs every render");
  ok("desk: the typed name reaches the form, the journey still runs, an untouched form does not scold, and the keyboard stays in the field");
}

// ------------------------------------------------- 7d. every field has a name

{
  // SC 1.3.1 / 4.1.2, on the form this product is actually used through. The
  // visible label was drawn above every field and attached to none of them:
  // three of the six widget kinds carried an id and three did not, and the
  // three that did not were the plain string, the closed choice and the
  // checkbox -- between them every field on the registration form. A person
  // using a screen reader was asked to fill in seven blanks.
  //
  // Checked here rather than in a browser because it is a property of the
  // source: a widget with no id cannot be labelled by anything.
  const form = read("form", "Form.tsx");
  const widget = form.slice(form.indexOf("function Widget("), form.indexOf("/** A structured answer"));
  const branches = [...widget.matchAll(/case "([a-z]+)":/g)].map((m) => m[1]);
  assert.ok(branches.length >= 5, "the widget check found no branches to check: " + branches.join(", "));
  // Every control the widget renders, with the id its label points at. The
  // structured branch renders a group whose sub widgets are each already
  // inside their own label, so it is the one that is allowed none.
  const controls = [...widget.matchAll(/<(input|select|textarea)\s([^>]*)/g)]
    .map((m) => ({ tag: m[1], attrs: m[2] }));
  const nameless = controls.filter((c) => !/\bid=\{id\}/.test(c.attrs)).map((c) => c.tag);
  assert.deepEqual(nameless, [],
    "a form control is drawn with no id, so nothing can label it: " + nameless.join(", "));
  assert.match(form, /<label className="f-lab" htmlFor=\{q\.type === "structured" \? undefined : `\$\{ids\}-\$\{q\.link_id\}`\}>/,
    "the question's own label is not attached to the field it names");
  ok(`a11y: all ${controls.length} controls in the form carry the id their label points at`);
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
