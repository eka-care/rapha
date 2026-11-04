/** Run: node --experimental-strip-types src/thread/arc-scale.check.ts   (from web/) */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bands, months, unplaced } from "./arc-scale.ts";
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

// Two overlapping episodes of one type stay two arcs, each with its own months.
const e1 = ep("e1", [contact("1", "2026-03-01", "2026-03-10", "2026-03-31", "done")]);
const e2 = ep("e2", [contact("1", "2026-04-01", "2026-04-10", "2026-05-31", "due")]);
ok(months(e1).map((x) => x.month).join() === "2026-03" &&
   months(e2).map((x) => x.month).join() === "2026-04,2026-05", "two episodes, two arcs");
// No contacts: no months.
ok(months(ep("c", [])).length === 0, "no contacts, no months");
// Same day: the worse state wins.
const same = months(ep("d", [
  contact("1", "2026-05-01", "2026-05-09", "2026-05-30", "done"),
  contact("2", "2026-05-01", "2026-05-09", "2026-05-30", "missed"),
]));
ok(same[0].days[8].state === "missed", "missed shows over done on one day");
// Bad dates cannot hang or draw: out of range month, far future, junk.
ok(months(ep("x", [contact("1", "2026-13-01", "2026-13-05", "2026-13-30", "due")])).length === 0, "month 13 draws nothing");
ok(months(ep("y", [contact("1", "2026-01-01", "2026-01-05", "9999-12-31", "due")])).length === 0, "absurd span draws nothing");
ok(months(ep("z", [contact("1", "soon", "x", "later", "due")])).length === 0, "junk draws nothing");
ok(months(ep("w", [contact("1", "2026-02-30", "2026-02-30", "2026-03-05", "due")])).length === 0, "30 February is not a date");
// A leap February has 29 days.
ok(months(ep("l", [contact("1", "2028-02-01", "2028-02-10", "2028-02-28", "due")]))[0].days.length === 29, "leap february");
// A window is owed across months: March is not empty when a window runs through it.
const w = months(ep("v", [contact("1", "2026-02-01", "2026-02-10", "2026-03-10", "missed")]));
ok(w[1].days[0].owed && w[1].days[9].owed && !w[1].days[10].owed, "window covers 1 to 10 March");
// Consecutive empty months become one band.
const b = bands(months(ep("g", [
  contact("1", "2026-01-01", "2026-01-05", "2026-01-31", "done"),
  contact("2", "2026-06-01", "2026-06-05", "2026-06-30", "due"),
])));
ok(b.length === 3 && b[1].kind === "gap" && (b[1] as { count: number }).count === 4, "four empty months, one band");
// One good contact and one unreadable: months are drawn AND the loss is counted.
const half = ep("h", [
  contact("1", "2026-03-01", "2026-03-10", "2026-03-31", "done"),
  contact("2", "soon", "later", "never", "due"),
]);
ok(months(half).length === 1 && unplaced(half) === 1, "months drawn and one contact reported unplaced");
ok(unplaced(a) === 0, "nothing unplaced when every date reads");
// The component must actually render the warning. JSX cannot be loaded here,
// so read the source: if Arc.tsx stops calling unplaced(), an arc that dropped
// a contact goes back to presenting an incomplete picture as a complete one.
const arcSource = readFileSync(new URL("./Arc.tsx", import.meta.url), "utf8");
ok(/unplaced\(episode\)\s*>\s*0/.test(arcSource),
   "Arc.tsx renders the unplaced-contact warning; without it a dropped contact leaves a month falsely reading as empty");
console.log(`ok   arc-scale: ${checks} checks`);
