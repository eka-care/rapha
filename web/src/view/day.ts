/** What the day screen decides, kept apart from how it is drawn so it can be
 *  checked under plain node. Nothing here knows a role, a station or a
 *  patient: it sorts what the kernel sent into the three piles a person acts
 *  on, and says so when a pile is empty.
 */
import type { CalendarRow } from "../types";
import type { Scale } from "./cells.ts";

/** Late first, because it is the only pile where somebody must act now. */
export const PILES: { pile: string; label: string; state: string }[] = [
  { pile: "late", label: "Late", state: "missed" },
  { pile: "owed", label: "Owed today", state: "due" },
  { pile: "done", label: "Done", state: "done" },
];

/** THE PILES PARTITION THE ROWS: every row the kernel sent is in exactly one
 *  pile, always. A state this file does not know is not dropped, because a
 *  contact the kernel says is owed vanishing from the day with no sign is the
 *  worst thing this screen could do. It gets a pile of its own, last, named by
 *  the state value itself, which is the kernel's word and not ours.
 *  "Owed today" is only true of today; on any other day the pile is "Owed",
 *  because the day's own heading already says which day. */
export function inPiles(rows: CalendarRow[], isToday = true): { pile: string; label: string; rows: CalendarRow[] }[] {
  const known = new Set(PILES.map((p) => p.state));
  const piles = PILES.map((p) => ({ pile: p.pile, label: p.pile === "owed" && !isToday ? "Owed" : p.label, rows: rows.filter((r) => r.state === p.state) }));
  const strange = [...new Set(rows.map((r) => r.state).filter((s) => !known.has(s)))].sort();
  for (const s of strange) piles.push({ pile: s, label: s, rows: rows.filter((r) => r.state === s) });
  return piles.filter((p) => p.rows.length > 0);
}

/** "Everyone" is the empty string, so a role can never collide with it. */
export const EVERYONE = "";

/** One chip per role that owns something in this answer, in the order the
 *  person reads them (by displayed name). Because the piles partition the rows,
 *  every chip here draws at least one row. The caller's own is selected on
 *  open, or everyone when the caller owns nothing here. */
export function roleChips(
  rows: CalendarRow[], caller: string, label: (role: string) => string = (r) => r,
): { roles: string[]; initial: string } {
  const roles = [...new Set(rows.map((r) => r.owner).filter(Boolean))]
    .sort((a, b) => label(a).localeCompare(label(b)));
  return { roles, initial: roles.includes(caller) ? caller : EVERYONE };
}

export const forRole = (rows: CalendarRow[], role: string): CalendarRow[] =>
  role === EVERYONE ? rows : rows.filter((r) => r.owner === role);

/** The sentence for a day with nothing on the screen. Two different reasons,
 *  and a person who filtered needs to be told it was the filter. */
export function emptyLine(total: number, shown: number): string | null {
  if (shown > 0) return null;
  return total === 0
    ? "Nobody is owed a contact on this day."
    : "Nothing here for this role. Choose everyone to see the rest.";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A date is exactly YYYY-MM-DD. Read by position, never through Date, so no
 *  time zone can move it a day. */
export function dayOf(iso: string): { day: string; month: string } {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
  return m ? { day: String(Number(m[3])), month: MONTHS[Number(m[2]) - 1] ?? "" } : { day: "", month: "" };
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The date part of a kernel timestamp, or "" when it is not one. */
export function dateOf(stamp: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})(?:T|$)/.exec(stamp ?? "");
  return m ? m[1] : "";
}

/** The date a link to the day screen carries (`?on=YYYY-MM-DD`), or "" when
 *  it carries none or not a whole date. Never trusted further than that. */
export function dayOn(hash: string): string {
  const m = /[?&]on=(\d{4}-\d{2}-\d{2})(?:&|$)/.exec(hash ?? "");
  return m ? m[1] : "";
}

/** "Today", "Tomorrow", or "Fri 6 Nov". The weekday is worked out in UTC from
 *  the parts, so no time zone can move it a day. */
export function dayLabel(iso: string, today: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
  if (!m) return iso;
  if (iso === today) return "Today";
  const t = /^(\d{4})-(\d{2})-(\d{2})$/.exec(today ?? "");
  if (t && Date.UTC(+m[1], +m[2] - 1, +m[3]) - Date.UTC(+t[1], +t[2] - 1, +t[3]) === 86_400_000) return "Tomorrow";
  const wd = WEEKDAYS[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()];
  const { day, month } = dayOf(iso);
  return `${wd} ${day} ${month}`;
}

/** The days the home page's card lists: from today on, only days with
 *  something owed, the first `limit`. The kernel's groups are the whole
 *  month, so earlier days and empty ones are cut here. */
export function comingUp(
  groups: { key: string | null; count: number }[] | undefined,
  today: string,
  limit = 5,
): { key: string; count: number }[] {
  return (groups ?? [])
    .filter((g): g is { key: string; count: number } => !!g.key && g.key >= today && g.count > 0)
    .sort((a, b) => (a.key < b.key ? -1 : 1))
    .slice(0, limit);
}

/** The first day of the month after `iso`, or "" when `iso` is not a date.
 *  Read by position, so the year rolls over without a time zone in sight. */
export function monthAfter(iso: string): string {
  const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(iso ?? "");
  if (!m) return "";
  const y = Number(m[1]), mo = Number(m[2]);
  return mo === 12 ? `${y + 1}-01-01` : `${y}-${String(mo + 1).padStart(2, "0")}-01`;
}

/** The day to ask the kernel about for the rest of the span, or "" when this
 *  month's groups already fill it. The kernel scopes groups to one month on
 *  purpose; the card carries on into the next itself. */
export function wantsNextMonth(
  groups: { key: string | null; count: number }[] | undefined,
  today: string,
  limit = 5,
): string {
  return comingUp(groups, today, limit).length >= limit ? "" : monthAfter(today);
}

/** What the home card lists, and whether it knows that is all there is.
 *  `later` is the next month's groups once read, "failed" when that read
 *  failed, and null when none was asked for. The days already read are always
 *  kept; a failure is said, never swallowed, so a short card is not mistaken
 *  for a quiet fortnight. */
export function cardDays(
  groups: { key: string | null; count: number }[] | undefined,
  later: { key: string | null; count: number }[] | "failed" | null,
  today: string,
  limit = 5,
): { days: { key: string; count: number }[]; unread: boolean } {
  const more = Array.isArray(later) ? later : [];
  return { days: comingUp([...(groups ?? []), ...more], today, limit), unread: later === "failed" };
}

/** The scale a link to the calendar carries (`scale=week|month|year`). A month
 *  when it carries none or one this screen does not draw. */
export function scaleOf(hash: string): Scale {
  const m = /[?&]scale=(week|month|year)(?:&|$)/.exec(hash ?? "");
  return (m ? m[1] : "month") as Scale;
}

/** The same address with the date and/or scale changed. A part left out is
 *  kept; an empty date is removed. Anything else in the query is kept too. */
export function withView(hash: string, change: { on?: string; scale?: Scale }): string {
  const [path, query = ""] = (hash ?? "").split("?");
  const parts = new Map(query.split("&").filter(Boolean).map((kv) => [kv.split("=")[0], kv] as const));
  if (change.on !== undefined) { if (change.on) parts.set("on", `on=${change.on}`); else parts.delete("on"); }
  if (change.scale) parts.set("scale", `scale=${change.scale}`);
  const order = ["on", "scale", ...[...parts.keys()].filter((k) => k !== "on" && k !== "scale")];
  const q = order.filter((k) => parts.has(k)).map((k) => parts.get(k)).join("&");
  return q ? `${path}?${q}` : path;
}
