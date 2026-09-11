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
import { cue, weigh } from "./loops.ts";
import type { Operation, QueueRow } from "./types";

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

console.log(`ok   ${checks} loop checks`);
