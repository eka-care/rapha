/** The loop rules, as pure functions over declarations.
 *
 *  Run: node --experimental-strip-types src/loops.check.ts   (from web/)
 *
 *  Nothing here names a station or a bundle. Every input is built from
 *  catalogue.json, so a rule that only works for the health centre fails.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  carriedInto, cue, derivedStates, filterOptions, filterRows, keep, marked, mine, offered,
  provenanceOf,
  opensOnArrival, records, RISK_TONE, sortOptions, sortRows, weigh,
} from "./loops.ts";
import type { Operation, QueueRow, SectionResult, ViewDecl } from "./types";

const root = fileURLToPath(new URL("../../", import.meta.url));
const cat = JSON.parse(readFileSync(root + "catalogue/catalogue.json", "utf8"));

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const op = (id: string): Operation => cat.operations[id] as Operation;
// Four of the doctor's own operations, so `overflow.length === 3` below is a
// real three. The fourth was the capture withdrawal until 4 November 2026,
// when the owner removed consent; the referral is the doctor's action that
// took its place in this list.
const doctor = [op("phc.op.consult-document"), op("phc.op.rx-prescribe"),
                op("phc.op.lab-order"), op("phc.op.referral-raise")];

// -- the closer is the one filled button -----------------------------------
const w = weigh(doctor, "phc.op.consult-document");
ok(w.primary?.id === "phc.op.consult-document", "the closer is primary");
ok(w.overflow.length === 3, "everything else is overflow");
ok(!w.overflow.some((o) => o.id === w.primary?.id), "primary never repeats in overflow");

// -- the closer need not be first: position is not the rule, closes is -----
const mid = weigh(doctor, "phc.op.lab-order");
ok(mid.primary?.id === "phc.op.lab-order", "the closer is primary even when it is not actions[0]");
ok(mid.overflow.some((o) => o.id === "phc.op.consult-document"), "actions[0] moves to overflow when it is not the closer");

// -- no closes, or a closer not offered: fall back to the first action ------
const none = weigh(doctor, null);
ok(none.primary?.id === "phc.op.consult-document", "falls back to the first action");
const gone = weigh(doctor.slice(1), "phc.op.consult-document");
ok(gone.primary?.id === "phc.op.rx-prescribe", "a closer whose precondition is unmet is not primary");

// -- nothing to do is not a crash ------------------------------------------
const empty = weigh([], "phc.op.consult-document");
ok(empty.primary === undefined && empty.overflow.length === 0, "an empty action list is empty");

// -- say a thing once ------------------------------------------------------
const all = [w.primary!.id, ...w.overflow.map((o) => o.id)];
ok(new Set(all).size === all.length, "no operation is offered twice");

// -- the cue after a loop closes -------------------------------------------
const row = (thread: string, name: string, station: string): QueueRow => ({
  thread, subject: { name }, station, flags: [], badges: {}, opened_at: "",
});
const register = op("phc.op.patient-register");

// -- a surface may only open what the kernel is still offering -------------
// The bug this closes: a surface opened `phc.op.patient-register` by id, on
// a thread whose own `actions` had already, correctly, stopped offering it —
// six denials in 28 seconds on an already-registered patient. `offered()` is
// the one gate every call site that opens an operation on an existing thread
// must pass through: it hands back the kernel's own object from `actions`,
// or nothing, so there is no way to construct an operation the current list
// does not contain. Would this still pass if the function ignored `actions`
// and just returned the operation by id regardless? No: the second and
// fourth checks below fail immediately if it does.
ok(offered(register.id, [register]) === register, "an operation present in actions is handed back");
ok(offered(register.id, [op("phc.op.vitals-record")]) === undefined,
   "an operation absent from actions is refused, not returned by id");
ok(offered(op("phc.op.vitals-record").id, doctor) === undefined,
   "absence holds for an id from a different bundle's operation too");
ok(offered("phc.op.patient-register", []) === undefined, "an empty actions list offers nothing");

// A role that can start a new subject loops on new subjects.
const opened = cue({ station: "reception", opener: register, queue: [], closed: "enc-1" });
ok(opened.kind === "open", "a role holding the opener is cued to start another");

// A role that cannot loops on its own queue, and never on the thread it closed.
const next = cue({
  station: "nurse", opener: null, closed: "enc-1",
  queue: [row("enc-1", "Kamala Devi", "nurse"), row("enc-2", "Iqbal Ahmed", "nurse")],
});
ok(next.kind === "next" && next.thread === "enc-2", "cues the next one, not the one just closed");

// Only this station's queue.
const elsewhere = cue({
  station: "nurse", opener: null, closed: "enc-1",
  queue: [row("enc-3", "Sunita Rao", "pharmacy")],
});
ok(elsewhere.kind === "empty", "another station's queue is not this role's work");

// An empty queue says so and invents nothing.
const quiet = cue({ station: "nurse", opener: null, queue: [], closed: "enc-1" });
ok(quiet.kind === "empty", "an empty queue is an empty cue");
ok(!/\d/.test(quiet.label), "the empty cue states no count it does not have");
ok(quiet.label.includes("nurse"), "the empty cue names the station it is empty at, from data, not a bare literal");

// A cue with no station (the whole visit is the subject, no current station)
// still says something, rather than naming a station that is not there.
const noStation = cue({ station: null, opener: null, queue: [], closed: "enc-1" });
ok(noStation.kind === "empty" && noStation.label === "Nobody waiting", "no station, no station name invented");

// -- how much AI a role touches is declared, never coded --------------------
ok(opensOnArrival(register), "registration opens on arrival");
ok(register.instrument === "form", "and it is a form, which is why front desk sees no AI");
ok(op("phc.op.vitals-record").instrument === "device", "vitals declares a device");
ok(op("phc.op.consult-document").instrument === "scribe", "the consultation declares the scribe");
ok(!opensOnArrival(undefined), "nothing to open is not an open");

// Irreversible work is never opened for someone who did not ask for it.
ok(!opensOnArrival(op("phc.op.abha-link")), "an irreversible operation waits to be asked for");

// -- a role sees its own work, not the handover log -------------------------
ok(mine(op("phc.op.vitals-record"), "nurse"), "the nurse's own work stays open");
ok(!mine(register, "nurse"), "reception's finished form collapses for the nurse");
ok(mine(register, "reception"), "and stays open for the clerk who filled it");
ok(mine(register, null), "a complete line collapses nothing");

// -- the rail is the declared summary, rendered as a list -------------------
const secs: SectionResult[] = [
  { title: "Visit", show: "line", rows: [] },
  { title: "Vitals", resource: "observation", rows: [{}, {}] },
  { title: "Notes", resource: "notes", rows: [{}] },
  { title: "Prescription", resource: "medication_request", rows: [] },
  { title: "Audit trail", show: "audit", rows: [{}] },
];
const r = records(secs);
ok(r.length === 2, "only sections that read a resource and have rows are records");
ok(r.every((x) => x.title !== "Audit trail"), "audit is events, not documents");
ok(r.every((x) => x.title !== "Visit"), "the line is not a document");
ok(r[0].title === "Vitals" && r[0].count === 2, "a record carries its count");

// -- recents point at threads that still exist ------------------------------
const rs = [{ id: "enc-1", name: "Kamala Devi" }, { id: "962", name: "962" }];
ok(keep(rs, ["enc-1"]).length === 1, "a recent the kernel no longer serves is dropped");
ok(keep(rs, ["enc-1"])[0].id === "enc-1", "and the live one is kept");
ok(keep(rs, []).length === 0, "nothing live means no recents");
// A reseed changes every id, which is how eight dead tokens came to be nav.
ok(keep(rs, ["enc-9"]).length === 0, "a reseed clears them rather than leaving 404s");

// -- Recents: sort and filter, and the controls that offer them ------------
//
// Built for the health centre's own queue view here, but nothing below is
// keyed to a PHC word: swap the decl passed in and the controls swap with it,
// which is the property the last two checks in this section prove.
const qrow = (thread: string, name: string, station: string, flags: string[], at: string): QueueRow => ({
  thread, subject: { name }, station, flags, badges: {}, opened_at: at,
});
const three: QueueRow[] = [
  qrow("t1", "Charlie", "B", [], "2020-01-01T00:00:00Z"),
  qrow("t2", "Alice", "A", ["crit"], "2020-01-03T00:00:00Z"),
  qrow("t3", "Bob", "C", [], "2020-01-02T00:00:00Z"),
];
const decl: Pick<ViewDecl, "columns" | "badges"> = { columns: ["name"], badges: { crit: "crit" } };
const ids = (rows: QueueRow[]) => rows.map((r) => r.thread);

// A sort that ignores its key returns the same order for two different keys.
// These two keys are chosen so the correct answer differs between them:
// alphabetical by name (Alice, Bob, Charlie) is not alphabetical by station
// (A, B, C maps to Alice, Charlie, Bob).
ok(
  JSON.stringify(ids(sortRows(three, "name", decl))) !== JSON.stringify(ids(sortRows(three, "station", decl))),
  "sorting by name and by station give different orders on data where they must",
);
assert.deepEqual(ids(sortRows(three, "name", decl)), ["t2", "t3", "t1"], "FAIL sort by name is alphabetical on the declared column");
checks++;
assert.deepEqual(ids(sortRows(three, "station", decl)), ["t2", "t1", "t3"], "FAIL sort by station is alphabetical on station");
checks++;
assert.deepEqual(ids(sortRows(three, "recent", decl)), ["t2", "t3", "t1"], "FAIL sort by recent is newest opened_at first");
checks++;
// A sort that just hands back its input, unchanged, passes none of the three
// above by luck alone: the input order (t1, t2, t3) matches none of them.
ok(ids(three)[0] === "t1" && ids(three)[1] === "t2", "the fixture's own order is not already any of the three sorts");
ok(!Object.is(sortRows(three, "name", decl), three), "sortRows hands back a copy, not the input array");
assert.deepEqual(ids(three), ["t1", "t2", "t3"], "FAIL sortRows must not mutate its input");
checks++;

// A filter that ignores its predicate returns every row regardless.
assert.deepEqual(ids(filterRows(three, { flag: "crit" })), ["t2"], "FAIL filtering by flag keeps only the row carrying it");
checks++;
assert.deepEqual(ids(filterRows(three, { station: "B" })), ["t1"], "FAIL filtering by station keeps only that station's row");
checks++;
// A filter that returns nothing regardless of input would also pass a check
// that only asserts "the result is smaller"; asserting the exact surviving
// set, on both a matching and a no-op filter, catches that shortcut too.
assert.deepEqual(ids(filterRows(three, null)), ["t1", "t2", "t3"], "FAIL no filter keeps every row, not none");
checks++;
ok(filterRows(three, { flag: "crit" }).length > 0, "a real filter keeps at least the matching row, not an empty result");

// -- the control set changes when the declaration does ----------------------
// Same technique as web/src/voice/voice.check.ts: mutate the declaration in
// memory and assert the offered controls move with it. A hard-coded "name,
// station" or "crit, warn" would pass everything above and fail only here.
const withColumn = sortOptions(decl);
ok(withColumn.some((o) => o.key === "name"), "a declared first column earns a name sort");
const noColumn = sortOptions({ columns: [], badges: {} });
ok(!noColumn.some((o) => o.key === "name"), "no declared column, no name sort offered");

const oneBadge = filterOptions(decl, three);
assert.deepEqual(oneBadge.flags, ["crit"], "FAIL the flag filter lists exactly the declared badges");
checks++;
const twoBadges = filterOptions({ columns: ["name"], badges: { crit: "crit", warn: "warn" } }, three);
assert.deepEqual(twoBadges.flags, ["crit", "warn"], "FAIL a bundle declaring a second badge gets a second flag filter, with no change here");
checks++;
ok(
  JSON.stringify(oneBadge.flags) !== JSON.stringify(twoBadges.flags),
  "the filter control set actually moved when the declaration did, not just its size",
);

// -- how a row got here: declared, marked, filterable ----------------------
//
// Three facts come off the declaration and none of them is written down here:
// which column carries the provenance, which of its values earns the mark,
// and what the chip is called. Every assertion below is phrased against a
// made-up column and a made-up value, so nothing in this block would still
// pass if the renderer started knowing a health centre's actual words.
const PROV_DECL = {
  columns: ["name", "howtheygothere"],
  badges: {},
  provenance: { column: "howtheygothere", mark: "by-themselves", label: "On their own" },
};
const arrived = (thread: string, how: string | undefined): QueueRow => ({
  thread, subject: { name: thread, ...(how ? { howtheygothere: how } : {}) },
  station: "A", flags: [], badges: {}, opened_at: "2026-11-01T09:00:00Z",
});
const mixed: QueueRow[] = [
  arrived("t1", "by-themselves"),
  arrived("t2", undefined),
  arrived("t3", "by-themselves"),
];

assert.deepEqual(provenanceOf(PROV_DECL), PROV_DECL.provenance,
  "FAIL the declaration's own three parts come back unchanged");
checks++;
ok(provenanceOf({ columns: ["name"], badges: {} }) === null,
  "a view that declares no provenance offers none, so no mark and no chip are drawn");
// Declared, but naming a column the view does not carry: no mark, rather than
// a mark drawn off a field no row has.
ok(provenanceOf({ columns: ["name"], badges: {},
                  provenance: { column: "howtheygothere", mark: "x", label: "y" } }) === null,
  "provenance naming a column this view does not carry draws nothing");
// But a view that declares NO columns at all is not a view that excluded the
// column; it is one that listed none, and a screen reading it falls back to
// whatever the subject carries. The declaration about that subject still
// holds, so the provenance still does. Guarding on the intersection alone
// switched the rule OFF on exactly the screen that had no column list, which
// is where the stored value went back to being drawn as a word.
assert.deepEqual(
  provenanceOf({ columns: [], badges: {}, provenance: PROV_DECL.provenance }),
  PROV_DECL.provenance,
  "FAIL a view that lists no columns keeps the provenance it declares");
checks++;

const prov = provenanceOf(PROV_DECL)!;
ok(marked(mixed[0], prov) && marked(mixed[2], prov),
  "a row whose column carries the declared value wears the mark");
ok(!marked(mixed[1], prov),
  "and a row whose column carries nothing does not, which is how the ordinary way in reads");
ok(!marked(arrived("t4", "by-themselves-ish"), prov),
  "a value that merely starts the same does not wear it: the match is the whole value");
ok(!marked(mixed[0], null),
  "and with no declaration nothing is marked at all, not everything");

// The chip. One, under the declaration's own word, and only while somebody in
// the room wears the mark.
const chip = filterOptions(PROV_DECL, mixed, []).provenance;
assert.deepEqual(chip, { column: "howtheygothere", value: "by-themselves", label: "On their own" },
  "FAIL the chip carries the declared column, value and word");
checks++;
ok(filterOptions(PROV_DECL, [arrived("t9", undefined)], []).provenance === null,
  "and a day when nobody registered themselves offers no chip, rather than one that can only say nought");
ok(filterOptions({ columns: ["name"], badges: {} }, mixed, []).provenance === null,
  "a view declaring no provenance offers no chip either");

// Filterable, which is the reason it is a column. Both ends pinned: selecting
// everybody and selecting nobody would each satisfy a membership test.
const only = filterRows(mixed, { column: chip!.column, value: chip!.value });
assert.deepEqual(ids(only), ["t1", "t3"], "FAIL filtering by the declared column keeps exactly those rows");
checks++;
ok(only.length > 0 && only.length < mixed.length,
  "and the filter narrows the list rather than keeping all of it or none");

// -- a guess never looks like a decision -----------------------------------
//
// The queue draws a label dashed when the kernel worked the state out of the
// records, and solid when a person asserted it. The difference is the
// workflow's own declaration: `{stored: true}` is somebody's tick, and
// `exists`, `all_of` and `gte` are the kernel reading what it already holds.
// Checked against the compiled workflows rather than a hand-made pair, so a
// bundle that redeclares one of its states moves this and nothing else.
for (const wf of Object.values(cat.workflows ?? {}) as { states?: Record<string, unknown> }[]) {
  const derived = derivedStates(wf);
  const asserted = Object.entries(wf.states ?? {})
    .filter(([, how]) => !!how && typeof how === "object" && "stored" in (how as object))
    .map(([state]) => state);
  const worked = Object.keys(wf.states ?? {}).filter((state) => !asserted.includes(state));
  ok(asserted.every((state) => !derived.has(state)),
     "a state somebody stored is never called derived");
  ok(worked.every((state) => derived.has(state)),
     "a state the kernel works out of the records always is");
  ok(derived.size === worked.length, "and the two sets are the whole of the declaration");
}
{
  // The two shapes written out, so the rule survives a bundle that happens to
  // declare only one kind.
  const both = derivedStates({ states: { kept: { stored: true }, read: { exists: {} } } });
  ok(!both.has("kept"), "stored means a person decided it");
  ok(both.has("read"), "anything else means the kernel worked it out");
  ok(derivedStates(undefined).size === 0,
     "with no workflow nothing is called a guess, which draws every label solid");
}

// -- colour means clinical risk, and one tone carries it --------------------
//
// The tone itself is each view's decision, flag by flag. Which tone is red is
// this renderer's, written once. If no declared view ever uses it, the red
// pill is unreachable and the rule is decoration.
{
  const used = Object.values(cat.views ?? {})
    .flatMap((v) => Object.values(((v as ViewDecl).badges ?? {})));
  ok(used.includes(RISK_TONE), "some declared view gives a flag the tone that means risk");
  ok(used.some((t) => t !== RISK_TONE),
     "and some flag has a quieter tone, so the queue is not all red");
}

// -- what one commit hands the next panel, and what it must never hand it ---
//
// A registration runs the ABHA journey and the journey hands back a national
// identifier that registration itself does not write. Until this existed the
// screen dropped it, and the clerk who opened the link panel next was shown
// the journey again: a second one time password, to a handset the patient may
// not be carrying, for a number the screen had been holding for minutes.
//
// Every case below is a property about somebody's permanent record, so none
// of them is a text assertion. The function is run.
{
  const identifier = { abha_number: "12-3456-7890-1234" };
  const asksForIt = [{ link_id: "abha_number" }, { link_id: "method" }];
  const doesNot = [{ link_id: "systolic" }, { link_id: "diastolic" }];
  const held = { thread: "enc-1", payload: identifier };

  ok(JSON.stringify(carriedInto(held, "enc-1", asksForIt)) === JSON.stringify(identifier),
     "the operation that asks for the identifier is given it, so nobody spends a second OTP");

  // THE ONE THAT IS ABOUT A PERSON AND NOT ABOUT TIDINESS. Nothing merges two
  // ABHA numbers; a patient carries that mistake permanently.
  ok(carriedInto(held, "enc-2", asksForIt) === undefined,
     "a value learned on one visit is NEVER offered on another patient's form");

  ok(carriedInto(held, "enc-1", doesNot) === undefined,
     "an operation that does not ask for it is not told; a payload key a form " +
     "has no question for is a commit the kernel refuses");
  ok(carriedInto(null, "enc-1", asksForIt) === undefined,
     "nothing learned yet seeds nothing");

  // An empty object is not the same answer as nothing. A seed, even an empty
  // one, tells the panel this person has already been identified and
  // suppresses the journey that is the only way to identify them.
  ok(carriedInto({ thread: "enc-1", payload: {} }, "enc-1", asksForIt) === undefined,
     "an empty seed is undefined, not {}, or the journey is suppressed with " +
     "nothing to have suppressed it");

  // Only the keys the form asks for travel, even when more was learned.
  const extra = { thread: "enc-1", payload: { ...identifier, consent_given: true } };
  ok(Object.keys(carriedInto(extra, "enc-1", [{ link_id: "abha_number" }]) ?? {}).join() === "abha_number",
     "only what this form asks for travels; a consent is a person saying yes " +
     "and is never carried from one screen to another");
}

console.log(`ok   ${checks} loop checks`);
