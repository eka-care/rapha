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

/** The scale a link to the calendar carries (`scale=week|month|year`). A month
 *  when it carries none or one this screen does not draw. */
export function scaleOf(hash: string): Scale {
  const m = /[?&]scale=(week|month|year)(?:&|$)/.exec(hash ?? "");
  return (m ? m[1] : "month") as Scale;
}

/** The same address with the date and/or scale changed. A part left out is
 *  kept; an empty date is removed. Anything else in the query is kept too. */
export function withView(hash: string, change: { on?: string; at?: string; scale?: Scale }): string {
  const [path, query = ""] = (hash ?? "").split("?");
  const parts = new Map(query.split("&").filter(Boolean).map((kv) => [kv.split("=")[0], kv] as const));
  if (change.on !== undefined) { if (change.on) parts.set("on", `on=${change.on}`); else parts.delete("on"); }
  if (change.at !== undefined) { if (change.at) parts.set("at", `at=${change.at}`); else parts.delete("at"); }
  if (change.scale) parts.set("scale", `scale=${change.scale}`);
  const order = ["on", "at", "scale", ...[...parts.keys()].filter((k) => !["on", "at", "scale"].includes(k))];
  const q = order.filter((k) => parts.has(k)).map((k) => parts.get(k)).join("&");
  return q ? `${path}?${q}` : path;
}

/** The date the grid is paged to (`at=YYYY-MM-DD`), or "" when the address
 *  carries none. The day list has its own date (`on=`); the two are separate. */
export function atOf(hash: string): string {
  const m = /[?&]at=(\d{4}-\d{2}-\d{2})(?:&|$)/.exec(hash ?? "");
  return m ? m[1] : "";
}

/** The cards on the home page, in the order they stack. One per contact, so a
 *  woman owed two visits has two cards: each is a separate piece of work.
 *  Late leads (longest-late first), then the soonest owed; the day screen's
 *  rule. Work already done is not coming up. The stack is the viewer's own
 *  role's, or everyone's when they own nothing. A new array; `rows` is not
 *  touched, and nothing is kept. */
export function stack(rows: CalendarRow[], now: string, role: string): CalendarRow[] {
  const open = rows.filter((r) => r.state !== "done");
  const mine = forRole(open, role);
  const late = (r: CalendarRow) => r.state === "missed" || (!!r.due && r.due < now);
  return (mine.length ? mine : open).slice().sort((a, b) => {
    const la = late(a), lb = late(b);
    if (la !== lb) return la ? -1 : 1;
    return a.due === b.due ? 0 : a.due < b.due ? -1 : 1;
  });
}

/** The card to show after paging `by` from `at`, never outside the stack. */
export function pageBy(at: number, by: number, count: number): number {
  return Math.max(0, Math.min(count - 1, at + by));
}

/** The address of her own page, anchored on the date the contact is owed.
 *  `at` is the shape the calendar already reads. */
export function cardHash(row: CalendarRow): string {
  return `/patients/${encodeURIComponent(row.subject)}?at=${row.due}`;
}

/** When a contact is owed, in words. A late one says since when. */
export function owedLine(row: CalendarRow, now: string): string {
  if (row.state === "missed" || (row.due && row.due < now)) return `Late since ${dayLabel(row.due, now)}`;
  const d = dayLabel(row.due, now);
  return d === "Today" || d === "Tomorrow" ? `Due ${d.toLowerCase()}` : `Due ${d}`;
}
