/** What the day screen decides, kept apart from how it is drawn so it can be
 *  checked under plain node. Nothing here knows a role, a station or a
 *  patient: it sorts what the kernel sent into the three piles a person acts
 *  on, and says so when a pile is empty.
 */
import type { CalendarRow } from "../types";

export type Pile = "late" | "owed" | "done";

/** Late first, because it is the only pile where somebody must act now. */
export const PILES: { pile: Pile; label: string; state: string }[] = [
  { pile: "late", label: "Late", state: "missed" },
  { pile: "owed", label: "Owed today", state: "due" },
  { pile: "done", label: "Done", state: "done" },
];

export function inPiles(rows: CalendarRow[]): { pile: Pile; label: string; rows: CalendarRow[] }[] {
  return PILES
    .map((p) => ({ pile: p.pile, label: p.label, rows: rows.filter((r) => r.state === p.state) }))
    .filter((p) => p.rows.length > 0);
}

/** "Everyone" is the empty string, so a role can never collide with it. */
export const EVERYONE = "";

/** One chip per role that owns something in this answer, and which one is
 *  selected on open: the caller's own, or everyone when the caller owns
 *  nothing here (a chip that would show an empty day is a trap). */
export function roleChips(rows: CalendarRow[], caller: string): { roles: string[]; initial: string } {
  const roles = [...new Set(rows.map((r) => r.owner).filter(Boolean))].sort();
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
