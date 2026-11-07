/** The home page's stack of visits owed: the nearest card largest, the ones
 *  behind it smaller, arrows to reach later ones. A card carries the woman,
 *  not a count. Which cards, and in what order, is day.ts's; this draws them.
 *
 *  A CARD IS A DATE AND A VISIT, in that order across the card: the day as a
 *  calendar block on the left, everything about the visit to the right of
 *  it. The date the block draws is the one `owedLine` speaks of, read through
 *  day.ts, so the block and the words beside it cannot disagree.
 */
import { useState } from "react";
import { Icon } from "../icons";
import type { CalendarRow } from "../types";
import { dayOf, owedDate, owedLine, pageBy, weekdayOf } from "./day";

/** How many cards show at once: the front one and two behind it. */
const DEPTH = 3;

export function Cards({ rows, now, nameOf, metaOf, roleName, scope, onOpen }: {
  /** Already ordered by `stack`. */
  rows: CalendarRow[];
  now: string;
  nameOf: (subjectRow: Record<string, unknown>) => string;
  /** What the register holds about her, already joined; "" when nothing. */
  metaOf: (subjectRow: Record<string, unknown>) => string;
  roleName: (role: string) => string;
  /** WHOSE VISITS THESE ARE, in words. "1 of 24" over a card, with "14 more
   *  for others" under it, is three numbers a reader cannot add up: the 24
   *  was already only the viewer's own. The count says which list it is
   *  counting. */
  scope: string;
  onOpen: (row: CalendarRow) => void;
}) {
  const [at, setAt] = useState(0);
  const here = pageBy(at, 0, rows.length);
  const shown = rows.slice(here, here + DEPTH);
  const last = rows.length - 1;
  return (
    <div className="stk">
      <div className="stk-deck" style={{ "--n": shown.length } as React.CSSProperties}>
        {shown.map((r, depth) => {
          const meta = metaOf(r.subject_row);
          const key = `${r.schedule}|${r.episode}|${r.contact}|${r.subject}`;
          // Late is the kernel's word, and it carries twice: the block
          // takes the critical tone and the line beside it says since when.
          const late = r.state === "missed" ? "" : undefined;
          const on = owedDate(r);
          const { day, month } = dayOf(on);
          const body = (
            <>
              <span className="stk-date" data-late={late} aria-hidden="true">
                <span className="stk-d">{day}</span>
                <span className="stk-m">{month}</span>
                <span className="stk-wd">{weekdayOf(on)}</span>
              </span>
              <span className="stk-body">
                <span className="stk-when" data-late={late}>{owedLine(r, now)}</span>
                <span className="stk-who">{nameOf(r.subject_row)}</span>
                {meta && <span className="stk-meta">{meta}</span>}
                <span className="stk-what" title={r.programme_title || undefined}>{r.title}</span>
                {r.owner && <span className="stk-role">{roleName(r.owner)}</span>}
              </span>
            </>
          );
          return depth === 0 ? (
            <button key={key} type="button" className="stk-card" style={{ "--depth": 0 } as React.CSSProperties}
                    onClick={() => onOpen(r)}>
              {body}
              <span className="stk-go">Open</span>
            </button>
          ) : (
            <div key={key} className="stk-card stk-behind" aria-hidden="true"
                 style={{ "--depth": depth } as React.CSSProperties}>{body}</div>
          );
        })}
      </div>
      <div className="stk-nav">
        <button type="button" className="stk-arrow" aria-label="Earlier visit" disabled={here === 0}
                onClick={() => setAt(pageBy(here, -1, rows.length))}>
          <Icon name="chev" className="i sm stk-flip" />
        </button>
        <span className="stk-count" aria-live="polite">{here + 1} of {rows.length} {scope}</span>
        <button type="button" className="stk-arrow" aria-label="Later visit" disabled={here >= last}
                onClick={() => setAt(pageBy(here, 1, rows.length))}>
          <Icon name="chev" className="i sm" />
        </button>
      </div>
    </div>
  );
}
