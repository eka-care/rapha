/** Demo data. Not a fallback and not a fixture the app silently uses: it is
 *  behind a button, the header says loudly when it is on, and nothing it
 *  returns is ever written anywhere.
 *
 *  It exists so this renderer can be looked at, and reviewed, before the
 *  kernel API exists. The operations are the real compiled ones from
 *  catalogue/catalogue.json; the threads, the queue and the numbers are made
 *  up. The visibility rule below is catalogue/guard.py visible(), copied,
 *  because a demo that shows actions a person could not take would be a lie
 *  about the product.
 */
import compiled from "../../catalogue/catalogue.json";
import { ApiError } from "./api";
import type { Catalogue, Facility, Operation, Proposal, ThreadView, ViewResult } from "./types";

const OPS = (compiled as unknown as Catalogue).operations;
const CAPS = (compiled as { capabilities: string[] }).capabilities;

const VIEWS = {
  "phc.view.station-queue": { id: "phc.view.station-queue", kind: "queue" as const, title: "Today's patients by station" },
  "phc.view.patient-summary": { id: "phc.view.patient-summary", kind: "summary" as const, title: "Visit summary" },
  "phc.view.facility-dashboard": { id: "phc.view.facility-dashboard", kind: "dashboard" as const, title: "Facility today" },
};

const STEPS: [string, string, string?][] = [
  ["reception", "registered"],
  ["nurse", "vitals.recorded"],
  ["doctor", "consult.documented"],
  ["lab", "lab.resulted", "lab.ordered"],
  ["pharmacy", "dispensed.complete", "rx.confirmed"],
];

const HELD = CAPS; // the demo person holds everything, so every station is visible

type Row = {
  id: string; subject: Record<string, unknown>; flags: string[]; opened_at: string;
  proposals: Proposal[]; audit: [string, string, string][];
};

const ROWS: Row[] = [
  {
    id: "enc-1",
    subject: { name: "Lakshmi Devi", age: 41, sex: "female", village: "Kadapa", token: 12, abha_number: "linked" },
    flags: ["registered", "abha.linked", "vitals.recorded", "vitals.flagged"],
    opened_at: "2026-09-10T09:12:00Z",
    proposals: [],
    audit: [["2026-09-10T09:12:00Z", "phc.op.patient-register", "frontdesk.meena"],
            ["2026-09-10T09:31:00Z", "phc.op.vitals-record", "nurse.suma"]],
  },
  {
    id: "enc-2",
    subject: { name: "Ramesh Kumar", age: 58, sex: "male", village: "Pulivendula", token: 13 },
    flags: ["registered", "abha.pending"],
    opened_at: "2026-09-10T09:40:00Z",
    proposals: [
      {
        id: "prop-1", thread: "enc-2", operation: "phc.op.vitals-record",
        payload: { systolic: 114, diastolic: 90, pulse: 88 },
        proposed_by: "nurse.suma", surface: "rendered", status: "pending",
        created_at: "2026-09-10T09:44:00Z",
        confidence: { systolic: 0.62, diastolic: 0.95, pulse: 0.97 },
        transcript: "one forty over ninety, pulse eighty eight",
      },
    ],
    audit: [["2026-09-10T09:40:00Z", "phc.op.patient-register", "frontdesk.meena"]],
  },
  {
    id: "enc-3",
    subject: { name: "Anjali S", age: 27, sex: "female", village: "Kadapa", token: 14, abha_number: "linked" },
    flags: ["registered", "abha.linked", "vitals.recorded", "consult.documented", "rx.confirmed"],
    opened_at: "2026-09-10T10:02:00Z",
    proposals: [
      {
        id: "prop-2", thread: "enc-3", operation: "phc.op.pharmacy-dispense",
        payload: { dispenses: ["Amoxicillin 500mg, 15 tablets"], batch: "AMX-2291", partial: false },
        proposed_by: "agent", surface: "mcp", status: "pending", created_at: "2026-09-10T10:31:00Z",
      },
    ],
    audit: [["2026-09-10T10:02:00Z", "phc.op.patient-register", "frontdesk.meena"],
            ["2026-09-10T10:14:00Z", "phc.op.vitals-record", "nurse.suma"],
            ["2026-09-10T10:29:00Z", "phc.op.consult-document", "mo.rao"],
            ["2026-09-10T10:30:00Z", "phc.op.rx-prescribe", "mo.rao"]],
  },
];

const stationOf = (flags: string[]) => {
  for (const [station, done, applies] of STEPS) {
    if (flags.includes(done)) continue;
    if (applies && !flags.includes(applies)) continue;
    return station;
  }
  return null;
};

const lineOf = (flags: string[]) => {
  const now = stationOf(flags);
  return STEPS.map(([station, done, applies]) => ({
    station,
    label: done,
    status: flags.includes(done) ? "done" : applies && !flags.includes(applies) ? "skipped" : station === now ? "now" : "pending",
  })) as ThreadView["line"];
};

/** catalogue/guard.py visible(), copied. Capability, then every precondition. */
const visible = (op: Operation, caps: string[], flags: string[]) =>
  caps.includes(op.capability) &&
  (op.preconditions ?? []).every((p) =>
    p.startsWith("not ") ? !flags.includes(p.slice(4)) : flags.includes(p));

const threadOf = (r: Row): ThreadView => ({
  id: r.id,
  workflow: "phc.wf.outpatient",
  subject: r.subject,
  flags: [...r.flags].sort(),
  station: stationOf(r.flags),
  line: lineOf(r.flags),
  actions: Object.values(OPS).filter((op) => visible(op, HELD, r.flags)),
  proposals: r.proposals,
  audit: r.audit.map(([at, operation, actor], i) => ({
    id: `${r.id}-a${i}`, thread: r.id, operation, actor, surface: "rendered",
    payload: {}, outcome: "allowed", at,
  })),
  capabilities: CAPS,
  held: HELD,
  nudge: r.flags.includes("vitals.flagged")
    ? "Blood pressure is flagged. The doctor sees this before the patient sits down."
    : "",
});

const queue = (): ViewResult => ({
  view: "phc.view.station-queue",
  title: VIEWS["phc.view.station-queue"].title,
  kind: "queue",
  generated_at: new Date().toISOString(),
  groups: STEPS.map(([station]) => ({
    key: station,
    count: ROWS.filter((r) => stationOf(r.flags) === station).length,
  })),
  rows: ROWS.map((r) => ({
    thread: r.id,
    subject: r.subject,
    station: stationOf(r.flags),
    flags: r.flags,
    badges: Object.fromEntries(
      r.flags.filter((f) => ["abha.pending", "vitals.flagged", "lab.critical", "dispensed.partial"].includes(f))
        .map((f) => [f, f === "abha.pending" ? "warn" : f === "dispensed.partial" ? "mute" : "crit"]),
    ),
    opened_at: r.opened_at,
  })),
});

const summary = (threadId: string): ViewResult => {
  const r = ROWS.find((x) => x.id === threadId);
  if (!r) throw new Error(`no demo thread ${threadId}`);
  const t = threadOf(r);
  return {
    view: "phc.view.patient-summary",
    title: VIEWS["phc.view.patient-summary"].title,
    kind: "summary",
    generated_at: new Date().toISOString(),
    rows: [
      { title: "Visit", show: "line", rows: t.line },
      { title: "Flags", show: "flags", rows: t.flags },
      {
        title: "Vitals", resource: "observation",
        rows: r.flags.includes("vitals.recorded")
          ? [{ code: "systolic", value: 168, unit: "mm[Hg]", created_date: "2026-09-10" },
             { code: "diastolic", value: 104, unit: "mm[Hg]", created_date: "2026-09-10" }]
          : [],
      },
      { title: "Awaiting confirmation", show: "proposals", rows: t.proposals },
      { title: "What you can do", show: "actions", rows: t.actions },
      { title: "Audit trail", show: "audit", rows: t.audit },
    ],
  };
};

const dashboard = (): ViewResult => ({
  view: "phc.view.facility-dashboard",
  title: VIEWS["phc.view.facility-dashboard"].title,
  kind: "dashboard",
  generated_at: new Date().toISOString(),
  rows: [
    { metric: "phc.metric.visits", title: "Visits", value: 3, numerator: 3, denominator: null, unit: "count", window: "week", window_start: "2026-09-07" },
    { metric: "phc.metric.abha-coverage", title: "ABHA coverage", value: 66.7, numerator: 2, denominator: 3, unit: "percent", window: "week", window_start: "2026-09-07" },
    { metric: "phc.metric.vitals-flagged-rate", title: "Vitals flagged", value: 50.0, numerator: 1, denominator: 2, unit: "percent", window: "week", window_start: "2026-09-07" },
  ],
});

const wait = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 120));

export const mockApi = {
  catalogue: () =>
    wait({
      ...(compiled as unknown as Catalogue),
      views: VIEWS,
      manifest: { id: "phc", title: "Primary health centre", version: "demo", views: Object.keys(VIEWS) },
    } as Catalogue),
  facility: () =>
    wait({
      bundle: { id: "phc", title: "Primary health centre", version: "demo", workflow: "phc.wf.outpatient" },
      capabilities: CAPS,
      views: Object.values(VIEWS),
      // The real kernel's role list is vocab.BUNDLES, one list for every
      // bundle. Demo mode has no store to switch against, so the switcher
      // offers only the union role it is actually drawing.
      roles: ["demo"],
      user: { id: "user:demo", role: "demo", capabilities: CAPS },
    } as Facility),
  view: (id: string, thread?: string) =>
    wait(id.endsWith("dashboard") ? dashboard() : thread ? summary(thread) : queue()),
  thread: (id: string) => {
    const r = ROWS.find((x) => x.id === id);
    if (!r) return Promise.reject(new Error(`no demo thread ${id}`));
    return wait(threadOf(r));
  },
  commit: async () => {
    throw new DemoWrite();
  },
  confirm: async () => {
    throw new DemoWrite();
  },
  reject: async () => {
    throw new DemoWrite();
  },
  openThread: async () => {
    throw new DemoWrite();
  },
};

/** Writing is the one thing demo mode will not fake. A demo that says
 *  "recorded" when nothing was recorded teaches the wrong reflex. */
class DemoWrite extends ApiError {
  constructor() {
    super(
      "This is demo data, so nothing was written.",
      "Turn demo off to write.",
    );
  }
}
