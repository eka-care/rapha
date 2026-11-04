/** Run: node --experimental-strip-types src/thread/arc-scale.check.ts   (from web/) */
import assert from "node:assert/strict";
import { months } from "./arc-scale.ts";
import type { Episode } from "../types.ts";

let checks = 0;
const ok = (c: unknown, what: string) => { checks++; assert.ok(c, `FAIL ${what}`); };

const contact = (n: string, opens: string, due: string, closes: string, state: string) =>
  ({ contact: n, title: `Visit ${n}`, schedule: "s", episode: "e", opens, due, closes, state,
     owner: "anm", operation: "op", authority: "", reports_as: "", done_at: "" }) as never;
const ep = (id: string, contacts: unknown[]): Episode =>
  ({ id, type: "pregnancy", status: "open", opened_at: "", ended_at: "", outcome: "",
     anchor_date: "", anchor_basis: "", encounters: [], contacts, nothing_due: "" }) as Episode;

// An arc that crosses a new year is one arc, first month to last, no pinned count.
const a = ep("a", [
  contact("1", "2026-09-01", "2026-09-10", "2026-09-30", "done"),
  contact("2", "2026-11-01", "2026-11-15", "2026-11-30", "missed"),
  contact("3", "2027-02-01", "2027-02-20", "2027-03-10", "upcoming"),
]);
const m = months(a);
ok(m[0].month === "2026-09", "first month is the month the first contact opens");
ok(m[m.length - 1].month === "2027-03", "last month is the month the last contact closes");
ok(m.map((x) => x.month).join() === "2026-09,2026-10,2026-11,2026-12,2027-01,2027-02,2027-03",
   "every month between is present, including the empty ones");

// Each contact lands on its own due date and no other.
const marked = m.flatMap((x) => x.days).filter((d) => d.state);
ok(marked.length === 3, "three contacts mark three days");
ok(marked.map((d) => d.day).join() === "2026-09-10,2026-11-15,2027-02-20", "on the due dates");
ok(marked[1].state === "missed" && marked[1].event === "Visit 2", "state and title carried");
ok(m[1].days.every((d) => !d.state), "the empty month has no marks");
ok(m[1].days.length === 31 && m[3].days.length === 31 && m[5].days.length === 28, "month lengths");

// Two episodes are two arcs.
ok(months(ep("b", [contact("1", "2026-01-01", "2026-01-05", "2026-01-31", "done")])).length === 1,
   "one month alone");
// No contacts: no months.
ok(months(ep("c", [])).length === 0, "no contacts, no months");
// Same day: the worse state wins.
const same = months(ep("d", [
  contact("1", "2026-05-01", "2026-05-09", "2026-05-30", "done"),
  contact("2", "2026-05-01", "2026-05-09", "2026-05-30", "missed"),
]));
ok(same[0].days[8].state === "missed", "missed shows over done on one day");
console.log(`ok   arc-scale: ${checks} checks`);
