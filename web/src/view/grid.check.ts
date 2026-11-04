/** The calendar grid's rules, over plain data.
 *
 *  Run: node --experimental-strip-types src/view/grid.check.ts   (from web/)
 *
 *  THE PLACEMENT RULE these pin: a contact sits on its DUE day and on no
 *  other. The day list answers "what is owed today" by window; the grid
 *  answers "when is each one due". Both are right, and this file is where the
 *  grid's half is held, so nobody unifies them.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cells, span, step } from "./grid.ts";
import type { CalendarRow } from "../types.ts";

let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };

const row = (contact: string, due: string, state = "due"): CalendarRow => ({
  contact, title: contact, schedule: "s", episode: "e", opens: due, due, closes: due, state,
  owner: "r", operation: "", authority: "", reports_as: "", done_at: "",
  subject: "p-" + contact, subject_row: {},
} as unknown as CalendarRow);

const days = (from: string, to: string) =>
  (Date.UTC(+to.slice(0, 4), +to.slice(5, 7) - 1, +to.slice(8)) -
   Date.UTC(+from.slice(0, 4), +from.slice(5, 7) - 1, +from.slice(8))) / 86_400_000 + 1;

// 4 Nov 2026 is a Wednesday; 1 Nov 2026 is a Sunday.
const ANCHOR = "2026-11-04";

// ---------------------------------------------------------------- spans
{
  const w = span("week", ANCHOR);
  assert.equal(days(w.from, w.to), 7);
  assert.ok(w.from <= ANCHOR && ANCHOR <= w.to, "the week holds its anchor");
  ok("a week's span is seven days and holds the anchor");

  const m = span("month", ANCHOR);
  assert.ok(m.from < "2026-11-01", "the span starts before the 1st");
  assert.ok(m.to > "2026-11-30", "and ends after the last");
  assert.equal(days(m.from, m.to), 42, "six whole rows");
  ok("a month's span covers the visible grid, spill days and all");

  const y = span("year", ANCHOR);
  assert.deepEqual(y, { from: "2026-01-01", to: "2026-12-31" });
  assert.deepEqual(span("year", "2028-02-29"), { from: "2028-01-01", to: "2028-12-31" });
  ok("a year's span is its twelve months");

  assert.deepEqual(span("week", "2026-12-30"), span("week", "2027-01-01"), "a week across New Year");
  assert.equal(span("month", "2026-12-15").to >= "2027-01-01", true);
  ok("a span rolls across a year boundary");
}

{
  assert.equal(step("day", "2026-12-31", 1), "2027-01-01");
  assert.equal(step("week", ANCHOR, -1), "2026-10-28");
  assert.equal(step("month", "2026-01-31", 1), "2026-02-01");
  assert.equal(step("month", "2026-01-15", -1), "2025-12-01");
  assert.equal(step("year", "2028-02-29", 1), "2029-02-01");
  assert.equal(step("day", "nonsense", 1), "nonsense");
  ok("stepping lands on a real date: a month never overshoots, a bad anchor is left alone");
}

// ---------------------------------------------------------------- placement
{
  const rows = [row("a", "2026-11-10"), row("b", "2026-11-10", "missed"), row("c", "2026-11-12", "done")];
  const grid = cells("month", ANCHOR, rows, 5);
  const holding = (c: string) => grid.filter((g) => g.rows.some((r) => r.contact === c));
  assert.equal(holding("a").length, 1);
  assert.equal(holding("a")[0].key, "2026-11-10");
  assert.equal(holding("c")[0].key, "2026-11-12");
  assert.equal(grid.reduce((n, g) => n + g.rows.length, 0), 3, "each drawn once, none twice");
  ok("a contact draws in the cell of its due day and in no other");

  // Its WINDOW is wide and it must not matter: a missed contact whose window
  // closed three weeks on is still only on its due day.
  const wide = { ...row("w", "2026-11-03", "missed"), opens: "2026-10-20", closes: "2026-11-24" } as CalendarRow;
  const g2 = cells("month", ANCHOR, [wide], 5).filter((g) => g.rows.length);
  assert.deepEqual(g2.map((g) => g.key), ["2026-11-03"]);
  ok("a wide window does not spread a contact over the days inside it");

  const spill = cells("month", ANCHOR, [row("before", "2026-10-28"), row("after", "2026-12-02")], 5)
    .filter((g) => g.rows.length);
  assert.deepEqual(spill.map((g) => [g.key, g.inMonth]), [["2026-10-28", false], ["2026-12-02", false]]);
  ok("a contact due on a spill day draws there, marked as not in the month");

  assert.equal(cells("month", ANCHOR, [row("far", "2027-03-01"), row("bad", "")], 5)
    .reduce((n, g) => n + g.rows.length, 0), 0);
  ok("a row outside the grid, or with no date, is not drawn anywhere");

  assert.deepEqual(cells("month", ANCHOR, [], 5).map((g) => g.key),
    [...cells("month", ANCHOR, [], 5).map((g) => g.key)].sort());
  assert.equal(cells("month", ANCHOR, [], 5).length, 42);
  assert.equal(cells("month", ANCHOR, [], 5).filter((g) => g.inMonth).length, 30);
  assert.equal(cells("week", ANCHOR, [], 5).length, 7);
  ok("a month is 42 cells in order, 30 of them in November; a week is 7");
}

// ---------------------------------------------------------------- overflow
{
  const many = ["a", "b", "c", "d", "e"].map((c) => row(c, "2026-11-10"));
  const cell = cells("week", "2026-11-10", many, 3).find((g) => g.key === "2026-11-10")!;
  assert.equal(cell.rows.length, 3);
  assert.equal(cell.more, 2);
  assert.deepEqual(cell.rows.map((r) => r.contact), ["a", "b", "c"], "the first max, in the kernel's order");
  const roomy = cells("week", "2026-11-10", many, 5).find((g) => g.key === "2026-11-10")!;
  assert.deepEqual([roomy.rows.length, roomy.more], [5, 0]);
  ok("a cell over max reports the remainder, and rows + remainder is everything");

  // The year lists nothing, so nothing overflows: max is ignored there.
  const yc = cells("year", ANCHOR, many, 1).find((g) => g.key === "2026-11-10")!;
  assert.equal(yc.rows.length, 5);
  assert.equal(yc.more, 0);
  assert.equal(cells("year", ANCHOR, [], 1).length, 365);
  assert.equal(cells("year", "2028-06-01", [], 1).length, 366);
  ok("the year ignores max: it tints a day, it lists nothing");
}

// ---------------------------------------------------------------- today
{
  for (const scale of ["week", "month", "year"] as const) {
    const marked = cells(scale, ANCHOR, [], 3, "2026-11-05").filter((g) => g.isToday);
    assert.deepEqual(marked.map((g) => g.key), ["2026-11-05"], scale);
  }
  assert.equal(cells("week", ANCHOR, [], 3, "2027-01-01").filter((g) => g.isToday).length, 0);
  assert.equal(cells("week", ANCHOR, [], 3).filter((g) => g.isToday).length, 0);
  ok("today's cell is marked, only one is, and none when today is elsewhere or unknown");
}

// ---------------------------------------------------------------- the renderer's vocabulary
{
  const here = dirname(fileURLToPath(import.meta.url));
  const cat = JSON.parse(readFileSync(join(here, "..", "..", "..", "catalogue", "catalogue.json"), "utf8"));
  const words = new Set<string>();
  const add = (ws: unknown) => { for (const w of (ws as string[]) ?? []) if (typeof w === "string" && w.length > 3) words.add(w); };
  add(cat.capabilities); add(cat.states); add(Object.keys(cat.bundles ?? {}));
  for (const wf of Object.values(cat.workflows ?? {}) as { steps?: { station: string }[] }[])
    add((wf.steps ?? []).map((s) => s.station));
  add(Object.keys(cat.operations ?? {}));
  for (const v of Object.values(cat.views ?? {}) as { columns?: string[] }[]) add(v.columns);
  // The kernel's four contact states are a word list the renderer is held
  // to as well: tone and mark come from the arc's own tables by lookup.
  for (const s of ["upcoming", "done", "missed"]) words.add(s);
  const prose = (s: string) => s.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
  for (const f of ["grid.ts", "Grid.tsx"]) {
    const body = prose(readFileSync(join(here, f), "utf8"));
    const hit = [...words].filter((w) => new RegExp(`["'\`]${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["'\`]`).test(body));
    assert.deepEqual(hit, [], `${f} names: ${hit.join(", ")}`);
  }
  ok("neither grid file spells a station, flag, capability, operation, state or column");
}

console.log(`\n${checks} checks passed`);
