/** Run: node --experimental-strip-types src/thread/earlier.check.ts   (from web/)
 *
 *  The three things the artifact puts around a visit, checked where they are
 *  decided. None of them needs a browser, a kernel or a microphone, which is
 *  the whole reason the deciding is in past.ts and not in the component.
 */
import assert from "node:assert/strict";
import {
  carriedForward, covers, heights, series, STRIP, team, trendable,
  type Catchment, type Visit,
} from "./earlier.ts";

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const kv = (link_id: string, label: string, value: string, crit = false) =>
  ({ link_id, label, value, crit });

const sep = (thread: string, when: string, values: ReturnType<typeof kv>[]): Visit =>
  ({ thread, when, values });

const today = sep("t3", "01 Nov", [
  kv("systolic", "Systolic BP", "138 mm[Hg]"),
  kv("weight", "Weight", "61 kg"),
  kv("spo2", "SpO2", "97 %"),
]);
const before = sep("t2", "18 Jun", [
  kv("systolic", "Systolic BP", "132 mm[Hg]"),
  kv("weight", "Weight", "59 kg"),
  kv("history", "History", "headache"),
]);

// -- the strip ------------------------------------------------------------
const strip = carriedForward(today, before);
assert.deepEqual(strip.map((c) => c.link_id), ["systolic", "weight"]);
checks++;
ok(strip[0].then === "132" && strip[0].now === "138 mm[Hg]",
   "the strip is the same question twice, with the unit said once");
ok(carriedForward(sep("a", "n", [kv("dose", "Dose", "5 mL")]),
                  sep("b", "b", [kv("dose", "Dose", "500 mg")]))[0].then === "500 mg",
   "a unit that changed between visits is kept, because that IS the change");
ok(!strip.some((c) => c.link_id === "spo2"),
   "a value only today carries nothing: the thread already draws it");
ok(!strip.some((c) => c.link_id === "history"),
   "a value only last time is not what this visit is about");
ok(carriedForward(today, null).length === 0 && carriedForward(null, before).length === 0,
   "a first visit has nothing to carry, and says so by drawing nothing");

// Nine questions, all of them DIFFERENT between the two visits, because
// `carriedForward` only carries what changed and the same visit twice now
// carries nothing. That is the rule below this one.
const wide = sep("t4", "x", Array.from({ length: 9 }, (_, i) => kv(`q${i}`, `Q${i}`, String(i + 1))));
const wider = sep("t5", "y", Array.from({ length: 9 }, (_, i) => kv(`q${i}`, `Q${i}`, String(i + 20))));
ok(carriedForward(wider, wide).length === STRIP, "the strip stops at four, so it stays a glance");

// AN ARROW FROM A VALUE TO ITSELF SAYS NOTHING. A returning patient's
// header read "sam -> sam, 28 -> 28, male -> male" above the record: four
// rows of furniture over the one row that moved.
ok(carriedForward(wide, wide).length === 0,
   "a value that did not change is not a change, and does not earn an arrow");
ok(!carriedForward(sep("a", "n", [kv("name", "Name", "Sam"), kv("bp", "BP", "138")]),
                   sep("b", "b", [kv("name", "Name", "Sam"), kv("bp", "BP", "132")]))
     .some((c) => c.link_id === "name"),
   "a name is the same on every visit, so it never belongs in a change strip");

// The one clinical judgement on screen is the kernel's, not this file's.
const flagged = carriedForward(
  sep("t3", "n", [kv("systolic", "Systolic BP", "186 mm[Hg]", true)]),
  sep("t2", "b", [kv("systolic", "Systolic BP", "132 mm[Hg]")]));
ok(flagged[0].crit, "out of range is carried from the kernel's own flag");
ok(!carriedForward(sep("a", "n", [kv("systolic", "S", "99")]),
                   sep("b", "b", [kv("systolic", "S", "80")]))[0].crit,
   "a value nobody flagged is not coloured by a rise alone");

// -- the trend ------------------------------------------------------------
const run = [before, today];
ok(trendable(run) === "systolic", "the first number two visits both recorded, in declared order");
ok(trendable([today]) === null, "one visit is not a trend");
ok(trendable([sep("a", "x", [kv("history", "History", "fever")]),
              sep("b", "y", [kv("history", "History", "cough")])]) === null,
   "prose is not a trend, however many visits said it");

const points = series(run, "systolic");
assert.deepEqual(points.map((p) => p.value), [132, 138]);
checks++;
ok(series([...run, sep("t4", "later", [kv("weight", "Weight", "62 kg")])], "systolic").length === 2,
   "a visit that did not take the reading is absent, not nought");

const bars = heights(points);
ok(bars[0] >= 0.3 && bars[1] === 1,
   "the lowest reading is a bar somebody can see, and the highest is full");
ok(heights([{ when: "x", value: 7, crit: false }])[0] === 1,
   "one reading is a full bar: there is no range to draw");

// -- who has been near it -------------------------------------------------
const rows = [
  { actor: "user:meena", outcome: "committed", operation: "phc.op.vitals-record" },
  { actor: "user:meena", outcome: "committed", operation: "phc.op.handover" },
  { actor: "user:mo", outcome: "committed", operation: "phc.op.consult-document" },
  { actor: "user:mo", outcome: "denied: no", operation: "phc.op.rx-prescribe" },
  { actor: null, outcome: "committed", operation: "phc.op.vitals-record" },
];
const who = team(rows, (op) => op.split(".").pop() ?? op, (a) => a.split(":")[1] ?? "");
assert.deepEqual(who.map((m) => m.actor), ["meena", "mo"]);
checks++;
ok(who[0].did === "vitals-record", "a person is named by the first thing they did, not the last");
ok(!team([rows[3]], () => "", () => "").length, "a refusal puts nobody on the team");
ok(!team([rows[4]], () => "", () => "").length, "and neither does an actor nobody recorded");


// -- who covers this patient ----------------------------------------------

const CATCH: Catchment = {
  column: "village",
  areas: [
    { area: "SC Yadiki", anm: "B. Jyothi", villages: { Yadiki: "G. Saroja", Sonpur: "M. Anjali" } },
    { area: "SC Tadpatri East", anm: "K. Suneetha", villages: { Tadpatri: "" } },
  ],
};

const mine = covers(CATCH, { village: "Sonpur" });
ok(mine?.anm === "B. Jyothi" && mine?.asha === "M. Anjali",
   "a village says which sub-centre, which ANM and which ASHA");
ok(covers(CATCH, { village: "Nowhere" }) === null,
   "a village nobody declared is not guessed at");
ok(covers(null, { village: "Sonpur" }) === null,
   "a centre that declares no catchment has none, rather than an empty frame");
ok(covers(CATCH, {}) === null, "a patient with no village is not placed");
const gap = covers(CATCH, { village: "Tadpatri" });
ok(gap !== null && gap.asha === "",
   "a habitation with nobody assigned is an ANSWER, not a dropped row: it is "
   + "the one worth seeing");

console.log(`ok   past visits: ${checks} checks`);
