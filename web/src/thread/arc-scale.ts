/** The same contacts, laid out as months.
 *
 *  PRESENTATION ONLY. Every date and state here was sent by the kernel; this
 *  file only groups them into the months they fall in. The window is the arc
 *  itself, from the month the first contact opens to the month the last one
 *  closes, never a calendar year, which would cut most pregnancies in half.
 *  An episode with no contacts has no months, so an ended one draws nothing.
 *
 *  A day is `owed` when it lies inside some contact's open-to-close window,
 *  so a month is only called empty when nobody is expected in any of it.
 */
import type { Episode } from "../types";

export type Scale = "day" | "month" | "year";
export type Day = { day: string; state?: string; event?: string; owed?: boolean };
export type Month = { month: string; days: Day[] };

/** Worst first: a day that holds a missed contact must not look done. */
const WORSE = ["missed", "due", "upcoming", "done"];
/** No arc is this long; a span past it is a bad date, not a long arc. */
export const MAX_MONTHS = 240;

/** A real calendar date, or false. Round-tripped so "2026-02-30" fails. */
function real(iso: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
}
const ym = (iso: string) => iso.slice(0, 7);

export function months(episode: Episode): Month[] {
  const cs = episode.contacts.filter((c) => real(c.opens) && real(c.closes));
  if (!cs.length) return [];
  const first = cs.map((c) => ym(c.opens)).sort()[0];
  const last = cs.map((c) => ym(c.closes)).sort().reverse()[0];
  const out: Month[] = [];
  let y = Number(first.slice(0, 4)), mo = Number(first.slice(5, 7));
  for (;;) {
    const key = `${y}-${String(mo).padStart(2, "0")}`;
    if (key > last) break;
    if (out.length >= MAX_MONTHS) return [];
    const n = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    const days = Array.from({ length: n }, (_, i): Day => {
      const day = `${key}-${String(i + 1).padStart(2, "0")}`;
      const here = cs.filter((c) => c.due === day)
        .sort((a, b) => WORSE.indexOf(a.state) - WORSE.indexOf(b.state));
      const owed = cs.some((c) => c.opens <= day && day <= c.closes);
      return here.length ? { day, owed, state: here[0].state, event: here[0].title } : { day, owed };
    });
    out.push({ month: key, days });
    mo === 12 ? (y++, (mo = 1)) : mo++;
  }
  return out;
}

export type Band =
  | { kind: "month"; m: Month }
  | { kind: "gap"; from: string; to: string; count: number };

/** Months nobody is owed anything in, run together into one band. */
export function bands(ms: Month[]): Band[] {
  const out: Band[] = [];
  for (const m of ms) {
    if (m.days.some((d) => d.owed || d.state)) { out.push({ kind: "month", m }); continue; }
    const last = out[out.length - 1];
    if (last?.kind === "gap") { last.to = m.month; last.count++; }
    else out.push({ kind: "gap", from: m.month, to: m.month, count: 1 });
  }
  return out;
}
