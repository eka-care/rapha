/** The calendar grid's rules, over plain data.
 *
 *  Run: node --experimental-strip-types src/view/grid.check.ts   (from web/)
 *
 *  THE PLACEMENT RULE these pin: a contact sits in the one cell the kernel
 *  names (its due day, or today when missed and due before the range), and in no
 *  other. That is the FACILITY page's rule. One woman's own page differs on
 *  purpose: ownRows keeps a missed contact on the day it was due, because her
 *  record is a history and the point is to see when things slipped. Two right
 *  answers to two questions; do not make either match the other. The day list answers "what is owed today" by window; the grid
 *  answers "when is each one due". Both are right, and this file is where the
 *  grid's half is held, so nobody unifies them.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cells, dayTone, ownRows, span, step, wasDue } from "./cells.ts";
import type { CalendarRow, Episode } from "../types.ts";

let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };

const row = (contact: string, due: string, state = "due", cell = due): CalendarRow => ({
  contact, cell, title: contact, schedule: "s", episode: "e", opens: due, due, closes: due, state,
  owner: "r", operation: "", authority: "", reports_as: "", done_at: "",
  subject: "p-" + contact, subject_row: {},
} as unknown as CalendarRow);

const days = (from: string, to: string) =>
  (Date.UTC(+to.slice(0, 4), +to.slice(5, 7) - 1, +to.slice(8)) -
   Date.UTC(+from.slice(0, 4), +from.slice(5, 7) - 1, +from.slice(8))) / 86_400_000 + 1;

// 4 Nov 2026 is a Wednesday; 1 Nov 2026 is a Sunday.
const ANCHOR = "2026-11-04";
// Weeks start on Sunday. 1 Dec 2026 is a Tuesday, so December's grid has spill
// days on both sides (29 Nov to 9 Jan); November's starts exactly on the 1st.
const DEC = "2026-12-09";

// ---------------------------------------------------------------- spans
{
  const w = span("week", ANCHOR);
  assert.equal(days(w.from, w.to), 7);
  assert.ok(w.from <= ANCHOR && ANCHOR <= w.to, "the week holds its anchor");
  ok("a week's span is seven days and holds the anchor");

  assert.equal(w.from, "2026-11-01", "a week starts on Sunday");
  assert.equal(w.to, "2026-11-07");
  const m = span("month", DEC);
  assert.deepEqual(m, { from: "2026-11-29", to: "2027-01-09" });
  assert.ok(m.from < "2026-12-01" && m.to > "2026-12-31", "starts before the 1st, ends after the last");
  assert.equal(days(m.from, m.to), 42, "six whole rows");
  assert.equal(cells("month", DEC, [], 5)[0].inMonth, false);
  assert.equal(cells("month", DEC, [], 5).filter((c) => c.inMonth).length, 31);
  assert.equal(new Date(m.from + "T00:00:00Z").getUTCDay(), 0, "the first column is Sunday");
  ok("a month's span covers the visible grid, spill days and all, from a Sunday");

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
  ok("a contact draws in one cell and in no other");

  // Its WINDOW is wide and it must not matter: a missed contact whose window
  // closed three weeks on is still only on its due day.
  const wide = { ...row("w", "2026-11-03", "missed"), opens: "2026-10-20", closes: "2026-11-24" } as CalendarRow;
  const g2 = cells("month", ANCHOR, [wide], 5).filter((g) => g.rows.length);
  assert.deepEqual(g2.map((g) => g.key), ["2026-11-03"]);
  ok("a wide window does not spread a contact over the days inside it");

  const spill = cells("month", DEC, [row("before", "2026-11-30"), row("after", "2027-01-05")], 5)
    .filter((g) => g.rows.length);
  assert.deepEqual(spill.map((g) => [g.key, g.inMonth]), [["2026-11-30", false], ["2027-01-05", false]]);
  ok("a contact in a spill day draws there, marked as not in the month");

  // THE CASE THAT WAS BROKEN: a missed contact due before the range is placed
  // by the kernel on today. It draws in today's square and not in its due
  // day's, which here is not even on the screen.
  const late = row("late", "2026-09-09", "missed", "2026-11-04");
  const lg = cells("month", ANCHOR, [late], 5, "2026-11-04");
  assert.deepEqual(lg.filter((g) => g.rows.length).map((g) => g.key), ["2026-11-04"]);
  assert.equal(lg.find((g) => g.key === "2026-11-04")!.isToday, true);
  // And the reverse: a cell that differs from a due day on screen wins.
  const moved = cells("week", ANCHOR, [row("m", "2026-11-02", "missed", "2026-11-04")], 5)
    .filter((g) => g.rows.length).map((g) => g.key);
  assert.deepEqual(moved, ["2026-11-04"]);
  // No cell (the single-day answer's shape): placed nowhere, however its due day falls.
  const bare = { ...row("bare", "2026-11-04"), cell: undefined } as CalendarRow;
  assert.equal(cells("month", ANCHOR, [bare], 5).reduce((n, g) => n + g.rows.length, 0), 0);
  ok("a row draws in the cell the kernel names, not its due day; a row with no cell draws nowhere");

  assert.equal(cells("month", ANCHOR, [row("far", "2027-03-01"), row("bad", "")], 5)
    .reduce((n, g) => n + g.rows.length, 0), 0);
  ok("a row outside the grid, or with no date, is not drawn anywhere");

  assert.deepEqual(cells("month", ANCHOR, [], 5).map((g) => g.key),
    [...cells("month", ANCHOR, [], 5).map((g) => g.key)].sort());
  assert.equal(cells("month", ANCHOR, [], 5).length, 42);
  assert.equal(cells("month", ANCHOR, [], 5).filter((g) => g.inMonth).length, 30);
  assert.equal(cells("month", ANCHOR, [], 5)[0].key, "2026-11-01");
  assert.equal(cells("week", ANCHOR, [], 5).length, 7);
  // A month whose 1st is a Saturday, and a leap February.
  const aug = cells("month", "2026-08-15", [], 5);
  assert.equal(aug[0].key, "2026-07-26");
  assert.equal(aug.findIndex((c) => c.inMonth), 6, "the 1st is the last column of the first row");
  assert.equal(aug.filter((c) => c.inMonth).length, 31);
  const feb = cells("month", "2028-02-10", [], 5);
  assert.equal(feb[0].key, "2028-01-30");
  assert.equal(feb.filter((c) => c.inMonth).length, 29);
  assert.ok(feb.some((c) => c.key === "2028-02-29" && c.inMonth));
  ok("a month is 42 cells in order, 30 of them in November, which starts on its first Sunday; a week is 7");
}

// ---------------------------------------------------------------- overflow
{
  const many = ["a", "b", "c", "d", "e"].map((c) => row(c, "2026-11-10"));
  const cell = cells("week", "2026-11-10", many, 3).find((g) => g.key === "2026-11-10")!;
  assert.equal(cell.rows.length, 3);
  assert.equal(cell.more, 2);
  assert.deepEqual(cell.rows.map((r) => r.contact), ["a", "b", "c"], "the first max, in the kernel's order");
  const exact = cells("week", "2026-11-10", many.slice(0, 4), 3).find((g) => g.key === "2026-11-10")!;
  assert.deepEqual([exact.rows.length, exact.more], [3, 1], "max + 1 reports one more");
  const full = cells("week", "2026-11-10", many.slice(0, 3), 3).find((g) => g.key === "2026-11-10")!;
  assert.deepEqual([full.rows.length, full.more], [3, 0], "exactly max reports none");
  const free = cells("week", "2026-11-10", many, Infinity).find((g) => g.key === "2026-11-10")!;
  assert.deepEqual([free.rows.length, free.more], [5, 0], "no limit lists everyone");
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

// ---------------------------------------------------------------- tone and lateness
{
  assert.equal(dayTone([]), undefined, "no work, no tint");
  assert.equal(dayTone(["b-ok", "b-crit"]), "b-crit", "done and missed tints as missed");
  assert.equal(dayTone(["b-ok", "b-mute", "b-ink"]), "b-ink");
  assert.equal(dayTone(["b-ok"]), "b-ok");
  assert.equal(dayTone(["something-new"]), "b-mute", "an unknown tone still tints");
  ok("a day tints by its most urgent tone, never by nothing when it has work");

  const late = row("late", "2026-09-09", "missed", "2026-11-04");
  assert.equal(wasDue(late, "2026-11-04"), "9 Sep");
  assert.notEqual(wasDue(late, "2026-11-04"), "4 Nov", "the chip's date is not the square's");
  assert.equal(wasDue(row("ontime", "2026-11-04"), "2026-11-04"), "");
  ok("a contact drawn away from its due day says when it was really due");
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
  // `due` is three letters, under the length filter above, so it is added
  // here, where no filter applies.
  for (const s of ["due", "upcoming", "done", "missed"]) words.add(s);
  const prose = (s: string) => s.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
  for (const f of ["cells.ts", "Grid.tsx"]) {
    const body = prose(readFileSync(join(here, f), "utf8"));
    const hit = [...words].filter((w) => new RegExp(`["'\`]${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["'\`]`).test(body));
    assert.deepEqual(hit, [], `${f} names: ${hit.join(", ")}`);
  }
  ok("neither grid file spells a station, flag, capability, operation, state or column");
}

// ------------------------------------------------- one woman's own episodes
{
  const contact = (n: string, due: string, state = "due") => ({
    contact: n, title: "Visit " + n, schedule: "s", episode: "", opens: due, due, closes: due, state,
    owner: "r", operation: "", authority: "", reports_as: "", done_at: "", basis: "",
  });
  const ep = (id: string, type: string, cs: ReturnType<typeof contact>[]) =>
    ({ id, type, status: "open", opened_at: "", ended_at: "", outcome: "", anchor_date: "", anchor_basis: "",
       encounters: [], contacts: cs, nothing_due: "" }) as unknown as Episode;
  const she = { name: "Lakshmi" };
  const one = ownRows([ep("e1", "pregnancy", [contact("a", "2026-09-09", "missed"), contact("b", "2026-11-20")])], "p1", she);
  // Her contacts sit on their due days, whatever their state, even a missed one
  // before the range: her page shows when each was due, not a pile on today.
  assert.deepEqual(one.map((r) => r.cell), ["2026-09-09", "2026-11-20"]);
  assert.ok(one.every((r) => r.subject === "p1" && r.subject_row === she));
  assert.ok(one.every((r) => r.episode === "e1"), "each row carries its episode");
  const g = cells("month", "2026-09-09", one, 3, "2026-11-04");
  assert.equal(g.find((c) => c.key === "2026-09-09")?.rows.length, 1);
  assert.equal(g.find((c) => c.key === "2026-11-20"), undefined, "November's visit is not in September's grid");
  // Nothing at all is nothing, not an error.
  assert.deepEqual(ownRows([], "p1", she), []);
  assert.deepEqual(ownRows([ep("e1", "pregnancy", [])], "p1", she), []);
  // Two episodes stay two: same day, two rows, told apart by the episode's name.
  const two = ownRows([ep("e1", "pregnancy", [contact("a", "2026-11-20")]), ep("e2", "child_care", [contact("a", "2026-11-20")])], "p1", she);
  assert.equal(two.length, 2);
  assert.notEqual(two[0].title, two[1].title, "two episodes on one day must be told apart");
  assert.ok(two[0].title.startsWith("Visit a") && /Pregnancy/.test(two[0].title) && /Child care/.test(two[1].title));
  // A single episode needs no tag.
  assert.equal(one[0].title, "Visit a");
  // The input is not touched, and nothing is kept between calls.
  const src = [ep("e1", "pregnancy", [contact("a", "2026-11-20")])];
  const before = JSON.stringify(src);
  ownRows(src, "p1", she);
  assert.equal(JSON.stringify(src), before);
  // A visit whose date cannot be read is placed nowhere, breaks nothing, and
  // is not lost: her plain list below the grid shows every contact unfiltered.
  const junk = ownRows([ep("e1", "pregnancy", [contact("a", "soon"), contact("b", "2026-11-20")])], "p1", she);
  assert.equal(junk.length, 2);
  const jg = cells("month", "2026-11-04", junk, 3, "2026-11-04");
  assert.equal(jg.reduce((n, c) => n + c.rows.length, 0), 1, "only the readable one is drawn in the grid");
  const arcSrc = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "thread", "Arc.tsx"), "utf8");
  assert.match(arcSrc, /episode\.contacts\.map\(/, "the list draws every contact, unfiltered");
  ok("her own episodes: placed on their due days, two stay two, none is a sentence's business");
}

console.log(`\n${checks} checks passed`);
