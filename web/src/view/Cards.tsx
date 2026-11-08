import { useState } from "react";
import { Icon } from "../icons";
import type { CalendarRow } from "../types";
import { owedLine, pageBy } from "./day";

/** How many cards sit side by side before the arrows are needed. */
const SHOWN = 4;

/** The home page's visits owed, as a row of cards. Each is the size its words
 *  need and no wider, so a short list does not stretch across the screen; the
 *  most urgent is first. A card carries the woman, not a count. Which cards, and
 *  in what order, is day.ts's; this draws them.
 *
 *  It was a stack, the nearest card large and the rest tucked behind it. Behind
 *  a card is where a late visit hid, and a card stretched to the full width of
 *  the page was mostly empty. */
export function Cards({ rows, now, nameOf, metaOf, roleName, onOpen }: {
  rows: CalendarRow[];
  now: string;
  nameOf: (subjectRow: Record<string, unknown>) => string;
  metaOf: (subjectRow: Record<string, unknown>) => string;
  roleName: (role: string) => string;
  onOpen: (row: CalendarRow) => void;
}) {
  const [at, setAt] = useState(0);
  const here = pageBy(at, 0, rows.length);
  const shown = rows.slice(here, here + SHOWN);
  const last = rows.length - 1;
  return (
    <div className="stk">
      <div className="stk-grid">
        {shown.map((r) => {
          const meta = metaOf(r.subject_row);
          const key = `${r.schedule}|${r.episode}|${r.contact}|${r.subject}`;
          return (
            <button key={key} type="button" className="stk-card" onClick={() => onOpen(r)}>
              <span className="stk-when" data-late={r.state === "missed" ? "" : undefined}>{owedLine(r, now)}</span>
              <span className="stk-who">{nameOf(r.subject_row)}</span>
              {meta && <span className="stk-meta">{meta}</span>}
              <span className="stk-what" title={r.programme_title || undefined}>{r.title}</span>
              {r.owner && <span className="stk-role">{roleName(r.owner)}</span>}
              <span className="stk-go">Open</span>
            </button>
          );
        })}
      </div>
      {rows.length > SHOWN && (
        <div className="stk-nav">
          <button type="button" className="stk-arrow" aria-label="Earlier visit" disabled={here === 0}
                  onClick={() => setAt(pageBy(here, -SHOWN, rows.length))}>
            <Icon name="chev" className="i sm stk-flip" />
          </button>
          <span className="stk-count" aria-live="polite">
            {here + 1}–{Math.min(here + SHOWN, rows.length)} of {rows.length}
          </span>
          <button type="button" className="stk-arrow" aria-label="Later visit" disabled={here + SHOWN > last}
                  onClick={() => setAt(pageBy(here, SHOWN, rows.length))}>
            <Icon name="chev" className="i sm" />
          </button>
        </div>
      )}
    </div>
  );
}
