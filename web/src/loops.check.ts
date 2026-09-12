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
import { cue, keep, mine, opensOnArrival, records, weigh } from "./loops.ts";
import type { Operation, QueueRow, SectionResult } from "./types";

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

console.log(`ok   ${checks} loop checks`);
