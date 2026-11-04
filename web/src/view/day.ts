/** What the day screen decides, kept apart from how it is drawn so it can be
 *  checked under plain node. Nothing here knows a role, a station or a
 *  patient: it sorts what the kernel sent into the three piles a person acts
 *  on, and says so when a pile is empty.
 */
import type { CalendarRow } from "../types";

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
 *  the state value itself, which is the kernel's word and not ours. */
export function inPiles(rows: CalendarRow[]): { pile: string; label: string; rows: CalendarRow[] }[] {
  const known = new Set(PILES.map((p) => p.state));
  const piles = PILES.map((p) => ({ pile: p.pile, label: p.label, rows: rows.filter((r) => r.state === p.state) }));
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
