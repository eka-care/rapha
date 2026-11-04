/** The same contacts, laid out as months.
 *
 *  PRESENTATION ONLY. Every date and state here was sent by the kernel; this
 *  file only groups them into the months they fall in. The window is the arc
 *  itself, from the month the first contact opens to the month the last one
 *  closes, never a calendar year, which would cut most pregnancies in half.
 *  An episode with no contacts has no months, so an ended one draws nothing.
 */
import type { Episode } from "../types";

export type Scale = "day" | "month" | "year";
export type Month = { month: string; days: { day: string; state?: string; event?: string }[] };

/** Worst first: a day that holds a missed contact must not look done. */
const WORSE = ["missed", "due", "upcoming", "done"];

const ym = (iso: string) => iso.slice(0, 7);

export function months(episode: Episode): Month[] {
  const cs = episode.contacts.filter((c) => /^\d{4}-\d{2}-\d{2}/.test(c.opens) && /^\d{4}-\d{2}-\d{2}/.test(c.closes));
  if (!cs.length) return [];
  const first = cs.map((c) => ym(c.opens)).sort()[0];
  const last = cs.map((c) => ym(c.closes)).sort().reverse()[0];
  const out: Month[] = [];
  let y = Number(first.slice(0, 4)), mo = Number(first.slice(5, 7));
  for (;;) {
    const key = `${y}-${String(mo).padStart(2, "0")}`;
    if (key > last) break;
    const n = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    const days = Array.from({ length: n }, (_, i) => {
      const day = `${key}-${String(i + 1).padStart(2, "0")}`;
      const here = cs.filter((c) => c.due === day)
        .sort((a, b) => WORSE.indexOf(a.state) - WORSE.indexOf(b.state));
      return here.length ? { day, state: here[0].state, event: here[0].title } : { day };
    });
    out.push({ month: key, days });
    mo === 12 ? (y++, (mo = 1)) : mo++;
  }
  return out;
}
