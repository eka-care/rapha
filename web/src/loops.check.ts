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
import { weigh } from "./loops.ts";
import type { Operation } from "./types";

const root = fileURLToPath(new URL("../../", import.meta.url));
const cat = JSON.parse(readFileSync(root + "catalogue/catalogue.json", "utf8"));

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const op = (id: string): Operation => cat.operations[id] as Operation;
const doctor = [op("phc.op.consult-document"), op("phc.op.rx-prescribe"),
                op("phc.op.lab-order"), op("phc.op.capture-withdraw")];

// -- the closer is the one filled button -----------------------------------
const w = weigh(doctor, "phc.op.consult-document");
ok(w.primary?.id === "phc.op.consult-document", "the closer is primary");
ok(w.overflow.length === 3, "everything else is overflow");
ok(!w.overflow.some((o) => o.id === w.primary?.id), "primary never repeats in overflow");

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

console.log(`ok   ${checks} loop checks`);
