/** Where each contact sits on a calendar, kept apart from how it is drawn so
 *  it can be checked under plain node.
 *
 *  THE PLACEMENT RULE: a contact sits in ONE cell, the one the kernel names
 *  in the row's `cell`: its due day, or today when it is missed and its due
 *  day is before the range. The counts the kernel sends come from the same
 *  field, so grid and counts agree. A row with no `cell` (the single-day
 *  answer's shape) is placed nowhere.
 *
 *  Never across its window, however wide. Drawn across its window, one woman
 *  would fill twenty squares and a missed contact would fill every day after it for ever, and a
 *  month would become a wall of colour nobody reads. The day list answers a
 *  different question, "what is owed today", by window, and is right too.
 *  Do not unify the two.
 *
 *  Nothing here knows a role, a station or a state: rows are placed by one
 *  date and counted. Nothing is stored; every call works from what it is given.
 */
import type { CalendarRow, Episode } from "../types";
import { human, title } from "../words.ts";
import { dayOf } from "./day.ts";

export type Scale = "week" | "month" | "year";

const DAY = 86_400_000;
const pad = (n: number) => String(n).padStart(2, "0");

/** Dates are read by position and moved in UTC, so no time zone and no
 *  daylight-saving change can shift one by a day. Returns null for anything
 *  that is not exactly YYYY-MM-DD. */
const ms = (iso: string): number | null => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null;
};
const iso = (t: number) => {
  const d = new Date(t);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
};

/** The Sunday on or before `t`. Weeks start on Sunday, as Google's do. */
const weekStart = (t: number) => t - new Date(t).getUTCDay() * DAY;

/** The days a scale shows, first to last, for an anchor. A month always shows
 *  six whole weeks, so the grid does not change height as months change, and
 *  so its first and last rows are the neighbouring months' spill days. */
function days(scale: Scale, anchor: string): string[] {
  const a = ms(anchor);
  if (a === null) return [];
  const d = new Date(a);
  if (scale === "week") {
    const s = weekStart(a);
    return Array.from({ length: 7 }, (_, i) => iso(s + i * DAY));
  }
  if (scale === "month") {
    const s = weekStart(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
    return Array.from({ length: 42 }, (_, i) => iso(s + i * DAY));
  }
  const first = Date.UTC(d.getUTCFullYear(), 0, 1);
  const n = (Date.UTC(d.getUTCFullYear() + 1, 0, 1) - first) / DAY;
  return Array.from({ length: n }, (_, i) => iso(first + i * DAY));
}

/** The range to ask the kernel for. A month's includes its spill days, because
 *  those days are drawn and must draw their contacts. */
export function span(scale: Scale, anchor: string): { from: string; to: string } {
  const all = days(scale, anchor);
  return { from: all[0] ?? "", to: all[all.length - 1] ?? "" };
}

/** One cell per day of the scale, in order, each holding the rows whose
 *  `cell` is that day.
 *  A cell over `max` keeps the first `max` in the order given and reports the
 *  rest in `more`, so nothing is dropped without being counted.
 *
 *  `max` is ignored for the year: a year tints a day by whether it has work
 *  and lists nothing, so there is nothing to overflow. One signature serves
 *  all three scales rather than a second function for one of them.
 *
 *  `today` is the kernel's own date (the answer's `generated_at`), never the
 *  browser's clock. Left out, no cell is marked. */
export function cells(scale: Scale, anchor: string, rows: CalendarRow[], max: number, today = ""):
  { key: string; inMonth: boolean; isToday: boolean; rows: CalendarRow[]; more: number }[] {
  const on = new Map<string, CalendarRow[]>();
  for (const r of rows) {
    if (!r.cell) continue;
    const list = on.get(r.cell);
    if (list) list.push(r); else on.set(r.cell, [r]);
  }
  const month = anchor.slice(0, 7);
  return days(scale, anchor).map((key) => {
    const here = on.get(key) ?? [];
    const cap = scale === "year" ? here.length : Math.max(0, max);
    return {
      key,
      inMonth: scale === "month" ? key.startsWith(month) : true,
      isToday: key === today,
      rows: here.slice(0, cap),
      more: here.length - Math.min(here.length, cap),
    };
  });
}

/** The anchor one step on (or back, with a negative `by`): a day, a week, a
 *  month or a year at a time. A month step lands on the 1st, so 31 January
 *  plus one month is February and never 3 March. */
export function step(unit: Scale | "day", anchor: string, by: number): string {
  const a = ms(anchor);
  if (a === null) return anchor;
  const d = new Date(a);
  if (unit === "day") return iso(a + by * DAY);
  if (unit === "week") return iso(a + by * 7 * DAY);
  if (unit === "month") return iso(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + by, 1));
  return iso(Date.UTC(d.getUTCFullYear() + by, d.getUTCMonth(), 1));
}

/** The tone a day is tinted in, from the tones of the rows it holds: the most
 *  urgent wins, so a day with a done contact and a missed one tints as missed.
 *  No rows is no tint. A tone this list does not know still tints, in the
 *  quietest known one: a day with work must never look empty. Tones are the
 *  arc's own names; no state is spelled here. */
const URGENCY = ["b-crit", "b-ink", "b-mute", "b-ok"];
export function dayTone(tones: string[]): string | undefined {
  if (!tones.length) return undefined;
  return URGENCY.find((t) => tones.includes(t)) ?? "b-mute";
}

/** When a row was really due, as "9 Sep", but only when it is drawn in a cell
 *  that is not its due day (a late contact sits on today). "" otherwise, so a
 *  chip says nothing extra when the square already tells the truth. */
export function wasDue(row: CalendarRow, cell: string): string {
  if (!row.due || row.due === cell) return "";
  const { day, month } = dayOf(row.due);
  return day ? `${day} ${month}` : "";
}

/** The hover text for a contact: its plain name, with the programme's own
 *  phrasing beside it in brackets. Unchanged when the programme has none. */
export function tipOf(row: CalendarRow): string {
  return row.programme_title ? `${row.title} (${row.programme_title})` : row.title;
}

/** The day her page treats as today: the kernel's, when what arrived is a real-looking date or the kernel's timestamp, and the browser's otherwise, so an answer without it still draws. */
export function todayOf(stamp: unknown, browser: string): string {
  return typeof stamp === "string" && /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(T|$)/.test(stamp) ? stamp.slice(0, 10) : browser;
}

/** One woman's own episodes as grid rows, for her record.
 *
 *  A DELIBERATE DIFFERENCE FROM THE FACILITY PAGE. The centre's range answer
 *  moves a contact missed before the span onto today, so it is not lost off
 *  the edge. Her record keeps it on the day it was due, because her page is a
 *  history and the reason to open it is to see when things slipped. Both are
 *  right for their question; do not "fix" one to match the other. A contact
 *  with an unreadable due date lands in no cell, and is still in the plain
 *  list on her page.
 *
 *  Her page reads her episodes, not the centre's range answer, so her contacts
 *  have no `cell`; this gives each the one the kernel gives: its due day. A
 *  late contact keeps its due day here, because her record is the place to see
 *  when each was due. With more than one episode on the page, each title says
 *  which episode it belongs to, so two on one day are two and can be told
 *  apart. A new array each call; the episodes are not touched and nothing is
 *  kept. */
export function ownRows(episodes: Episode[], subject: string, subjectRow: Record<string, unknown>): CalendarRow[] {
  const tag = episodes.length > 1;
  return episodes.flatMap((e) => e.contacts.map((c) => ({
    ...c,
    episode: c.episode || e.id,
    title: tag ? `${c.title} \u00b7 ${title(human(e.type))}` : c.title,
    subject, subject_row: subjectRow, cell: c.due,
  })));
}

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

/** What the toolbar calls the span on screen. */
export function spanTitle(scale: Scale, anchor: string): string {
  const [y, m] = anchor.split("-");
  if (scale === "year") return y;
  if (scale === "month") return `${MONTH_NAMES[Number(m) - 1] ?? ""} ${y}`;
  const { from, to } = span("week", anchor);
  const a = dayOf(from), b = dayOf(to);
  return a.month === b.month ? `${a.day} to ${b.day} ${b.month} ${y}` : `${a.day} ${a.month} to ${b.day} ${b.month} ${y}`;
}
