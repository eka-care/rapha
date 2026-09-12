/** inert() and its reason, as pure functions over declarations.
 *
 *  Run: node --experimental-strip-types src/roles.check.ts   (from web/)
 *
 *  Two ways this rule degenerates and still "passes" a lazy check: calling
 *  every capability reachable (the disabled state never appears), or calling
 *  every capability inert (nothing is ever grantable). Both are asserted
 *  against here, not just "some switch is disabled".
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { inert, inertReason } from "./grants.ts";
import type { Catalogue } from "./types";

const root = fileURLToPath(new URL("../../", import.meta.url));
const cat: Catalogue = JSON.parse(readFileSync(root + "catalogue/catalogue.json", "utf8"));

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

// -- a capability the sole workflow draws is not inert -----------------------
ok(inert("vitals.record", cat) === false, "vitals.record is drawn by the outpatient line");
ok(inert("patient.register", cat) === false, "patient.register is drawn at reception");
ok(inert("rx.prescribe", cat) === false, "rx.prescribe is drawn at the doctor's step");

// -- visit.household's operation stands at a station the line never visits --
ok(inert("visit.household", cat) === true, "household-visit stands at community, which this line has no step for");

// -- both are proven true, so neither "always reachable" nor "always inert" -
// makes every assertion above pass: one needs a false, the other needs a
// true, and this file has both.
const some = ["patient.register", "abha.link", "vitals.record", "encounter.document",
              "rx.prescribe", "lab.order", "lab.result.enter", "pharmacy.dispense"]
  .map((c) => inert(c, cat));
ok(some.some((v) => v === false), "at least one capability with a drawn operation is grantable");
ok(inert("visit.household", cat) !== inert("vitals.record", cat), "the two differ");

// -- the reason names the operation's own station and the workflow's own
//    title, not a sentence written once for this one case -------------------
const reason = inertReason("visit.household", cat);
ok(reason.includes("community"), "names the station the operation actually declares");
ok(reason.toLowerCase().includes(cat.workflows!["phc.wf.outpatient"].title.toLowerCase()),
   "names the workflow's own title, not a hard coded line name");

console.log(`ok   ${checks} role checks`);
