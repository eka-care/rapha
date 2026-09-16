/** The agent's own output, checked without a browser.
 *
 *  Run: node --experimental-strip-types src/agent.check.ts   (from web/)
 *
 *  The brief is prose composed from rows, which is the kind of thing that
 *  reads fine on the fixture somebody wrote it against and falls apart on 1
 *  and on 0. Both ends are checked here, because "1 person in the facility.
 *  1 of them carries a flag" shipped in the first version of it.
 *
 *  It is also the one place a renderer is most tempted to type a station or a
 *  flag, so the portability assertion is repeated on the output rather than
 *  only on the source: give it a bundle whose words nobody has seen and the
 *  sentences have to come out in those words.
 */
import assert from "node:assert/strict";
import { brief, busiest, facilityAsks, needingAttention, threadAsks, type Loaded } from "./agent.ts";

let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };
const say = (l: Loaded[]) => brief(l).map((s) => s.text).join("");

const queue = (rows: unknown[], badges: Record<string, string> = {}): Loaded => ({
  decl: { id: "v.q", kind: "queue", title: "Lines", badges } as Loaded["decl"],
  result: { view: "v.q", kind: "queue", rows, generated_at: "" } as Loaded["result"],
});
const tasks = (rows: unknown[]): Loaded => ({
  decl: { id: "v.t", kind: "tasklist", title: "Needs you" } as Loaded["decl"],
  result: { view: "v.t", kind: "tasklist", rows, generated_at: "" } as Loaded["result"],
});
const person = (thread: string, station: string, flags: string[] = []) =>
  ({ thread, subject: { name: thread }, station, flags, badges: {}, opened_at: "" });

// -- the ends, where template prose breaks --------------------------------

assert.equal(say([]), "Nobody is in the facility yet. The first registration starts the day.");
assert.ok(!say([]).includes("0"), "an empty facility is a sentence, not a zero");
ok("empty: the brief says something rather than counting nothing");

const one = say([queue([person("a", "nurse", ["f"])], { f: "crit" }), tasks([])]);
assert.ok(one.includes("1 person"), one);
assert.ok(!/1 of them/.test(one), `"1 of them" for a facility of one: ${one}`);
assert.ok(!/\bpeoples?\b.*\b1\b/.test(one), one);
ok("one person: no plural and no 'N of them' when N is everybody");

const five = say([
  queue([person("a", "x", ["f"]), person("b", "x", ["f"]), person("c", "y"),
         person("d", "y"), person("e", "y")], { f: "crit" }),
  tasks([{ title: "Waiting on a lab result", count: 4, threads: [] }]),
]);
assert.ok(five.includes("5 people"), five);
assert.ok(five.includes("2 of them carry"), five);
assert.ok(five.includes("4 things still need"), five);
ok("five people: agreement holds on every clause");

// Subject/verb agreement is the thing a template gets wrong silently, so it
// is asserted across the range rather than at one convenient number.
for (const n of [1, 2, 7]) {
  const s = say([queue([person("a", "x")]), tasks([{ title: "T", count: n, threads: [] }])]);
  assert.ok(n === 1 ? /1 thing still needs/.test(s) : new RegExp(`${n} things still need `).test(s),
    `${n}: ${s}`);
}
ok("outstanding counts agree with their verb at 1, 2 and 7");

// -- a flag only counts when the declaration calls it out -------------------

const undeclared = [queue([person("a", "x", ["whatever"])], {})];
assert.equal(needingAttention(undeclared), 0,
  "a flag the queue declares no badge for is state, not attention");
assert.equal(needingAttention([queue([person("a", "x", ["f"])], { f: "warn" })]), 1);
ok("attention is what the declaration calls out, not every flag");

assert.equal(busiest([]), null, "no rows, no busiest station");
assert.deepEqual(busiest([queue([person("a", "x"), person("b", "x"), person("c", "y")])]),
  { station: "x", count: 2 });
ok("the busiest station is counted, not guessed");

// -- portability: the words are the bundle's ------------------------------

const alien = say([
  queue([person("a", "cryostore", ["seal.broken"]), person("b", "cryostore", ["seal.broken"]),
         person("c", "anteroom")], { "seal.broken": "crit" }),
  tasks([{ title: "Awaiting cryostore slot", count: 2, threads: [] }]),
]);
assert.ok(alien.includes("cryostore"), `the brief speaks the bundle's words: ${alien}`);
assert.ok(alien.includes("awaiting cryostore slot"), alien);
assert.ok(!/nurse|doctor|patient|vitals/i.test(alien),
  `a health centre word leaked into a bundle that has none: ${alien}`);
ok("portability: the brief is written in whatever words the bundle declared");

const asks = facilityAsks([
  tasks([{ title: "Awaiting cryostore slot", count: 2, threads: [] },
         { title: "Nothing outstanding", count: 0, threads: [] }]),
  queue([person("a", "anteroom")]),
]);
assert.deepEqual(asks, ["Awaiting cryostore slot", "Lines"],
  "the chips are the declared worklists that actually have something in them");
ok("suggested questions come from declarations, and skip an empty worklist");

// -- the thread's questions are kernel concepts ---------------------------

const t1 = threadAsks({ hasHistory: false, flags: [] });
const t2 = threadAsks({ hasHistory: true, flags: ["seal.broken"] });
assert.ok(!t1.includes("What changed since last time?"),
  "nothing to compare against, so nothing is offered");
assert.ok(t2.includes("What changed since last time?"), "a subject with history gets the question");
assert.ok(t2.includes("Why is this flagged?") && !t1.includes("Why is this flagged?"));
for (const q of [...t1, ...t2]) {
  assert.ok(!/patient|nurse|doctor|vitals|abha/i.test(q),
    `a thread question names a bundle's word: ${q}`);
}
ok("thread questions are offered only when they have an answer, in no bundle's words");

console.log(`\n${checks} checks passed`);
