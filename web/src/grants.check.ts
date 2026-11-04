/** inert() and its reason, as pure functions over declarations.
 *
 *  Run: node --experimental-strip-types src/grants.check.ts   (from web/)
 *
 *  Two ways this rule degenerates and still "passes" a lazy check: calling
 *  every capability reachable (the disabled state never appears), or calling
 *  every capability inert (nothing is ever grantable). Both are asserted
 *  against here, not just "some switch is disabled".
 *
 *  And the second reason a grant is dead: the plugins this centre does not
 *  run. That is the kernel's decision, served at GET /facility, and the
 *  withheld maps below are read from the bundle's own declaration through
 *  kernel/plugins.py rather than typed here, so a facility shape that changes
 *  changes this check.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { inert, inertReason, type Withheld } from "./grants.ts";
import type { Catalogue } from "./types";

const root = fileURLToPath(new URL("../../", import.meta.url));
const cat: Catalogue = JSON.parse(readFileSync(root + "catalogue/catalogue.json", "utf8"));

/** What GET /facility serves for one shape of this bundle, asked of the
 *  kernel rather than written down. Without this the two sentences below
 *  would be this check agreeing with itself. */
const shape = (facility: string): Withheld =>
  JSON.parse(execFileSync("python3", ["-c",
    "import json,sys;sys.path.insert(0,'.');from kernel import declarations as d;" +
    `b=d.load('phc', facility=${JSON.stringify(facility)});` +
    "print(json.dumps({'withheld': b.withheld, 'without': b.without}))",
  ], { cwd: root, encoding: "utf8" }));

const WHOLE = shape("all-plugins");
const NO_LAB = shape("no-laboratory");
assert.deepEqual(WHOLE, { withheld: {}, without: {} }, "every plugin on withholds nothing");
assert.ok(Object.keys(NO_LAB.withheld).length > 0, "the no-laboratory shape withholds something");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

// -- a capability the sole workflow draws is not inert -----------------------
ok(inert("vitals.record", cat, WHOLE) === false, "vitals.record is drawn by the outpatient line");
ok(inert("patient.register", cat, WHOLE) === false, "patient.register is drawn at reception");
ok(inert("rx.prescribe", cat, WHOLE) === false, "rx.prescribe is drawn at the doctor's step");

// -- visit.household used to stand at a station the line never visited ------
// It no longer does: the line gained a community step when the postnatal
// schedule needed somewhere to draw the home visit from. The general
// household visit is STILL undrawn, which is a real gap recorded in
// catalogue/ops/phc.op.postnatal-visit.md, but the capability is live
// because another operation that needs it is offered.
ok(inert("visit.household", cat, WHOLE) === false,
   "visit.household is drawn by the postnatal visit at the community step");

// The sentence for a station the line does not have is still asserted, over
// a line with that step taken out. Real declarations, one step removed, so
// this exercises the function rather than agreeing with itself.
const noHouse = {
  ...cat,
  workflows: Object.fromEntries(Object.entries(cat.workflows ?? {}).map(([id, wf]) => [
    id, { ...wf, steps: (wf.steps ?? []).filter((s) => s.station !== "community") },
  ])),
} as typeof cat;
ok(inert("visit.household", noHouse, WHOLE) === true,
   "take the community step away and the capability is dead again");

// -- both are proven true, so neither "always reachable" nor "always inert" -
// makes every assertion above pass: one needs a false, the other needs a
// true, and this file has both.
const some = ["patient.register", "abha.link", "vitals.record", "encounter.document",
              "rx.prescribe", "lab.order", "lab.result.enter", "pharmacy.dispense"]
  .map((c) => inert(c, cat, WHOLE));
ok(some.some((v) => v === false), "at least one capability with a drawn operation is grantable");
ok(inert("visit.household", noHouse, WHOLE) !== inert("vitals.record", cat, WHOLE),
   "the two differ");

// -- the reason names the operation's own station and the workflow's own
//    title, not a sentence written once for this one case -------------------
const reason = inertReason("visit.household", noHouse, WHOLE);
ok(reason.includes("community"), "names the station the operation actually declares");
// And with the step present, the sentence says the line does not offer it
// THERE rather than claiming the line has no such station, which would be a
// false explanation of a true refusal.
const offered = inertReason("visit.household", cat, WHOLE);
ok(offered.includes("does not offer") && offered.includes("community"),
   `a station the line has gets its own sentence: ${offered}`);
ok(reason.toLowerCase().includes(cat.workflows!["phc.wf.outpatient"].title.toLowerCase()),
   "names the workflow's own title, not a hard coded line name");

// -- a plugin this centre does not run ---------------------------------------
// The capability is still DECLARED by the bundle, and the operation that
// names it is still drawn by the line, so the workflow alone calls it
// grantable. Only the facility knows better, which was the whole of
// contradiction 25.
for (const cap of Object.keys(NO_LAB.withheld)) {
  ok(inert(cap, cat, NO_LAB) === true,
     `${cap} is dead at a centre that withholds the plugin declaring it`);
  const why = inertReason(cap, cat, NO_LAB);
  ok(why === `This centre does not run ${NO_LAB.without[NO_LAB.withheld[cap]]}.`,
     `${cap}'s reason names the plugin's own declared title: ${why}`);
}

// And the map is what made the difference, not the workflow: at least one of
// those capabilities IS grantable at a centre that runs every plugin, so the
// loop above is not just restating what `drawn_by` already refused. Not every
// one of them is -- the laboratory's own validate step stands outside this
// line -- which is why this is "some" and says so.
const flipped = Object.keys(NO_LAB.withheld)
  .filter((cap) => inert(cap, cat, WHOLE) === false);
ok(flipped.length > 0,
   `the withheld map alone makes ${flipped.length} capability dead: ${flipped.join(", ")}`);

// And the facility's reason is reported instead of the workflow's, not as
// well: a capability that is both withheld AND undrawn says the thing an
// administrator can act on.
ok(inertReason("vitals.record", cat, { withheld: { "vitals.record": "p" }, without: {} })
     === "This centre does not run p.",
   "a withheld capability's sentence wins over the workflow's");

// Nothing a centre runs is made inert by the withheld map being present.
ok(inert("vitals.record", cat, NO_LAB) === false,
   "a capability no plugin withholds is untouched by another plugin being off");

console.log(`ok   ${checks} role checks`);
