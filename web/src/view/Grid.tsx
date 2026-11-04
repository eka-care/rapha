/** A week, a month or a year, in the shape of a calendar.
 *
 *  A contact is drawn in the one cell the kernel names for it, and nowhere else (see cells.ts). Contacts
 *  have no time of day, so in the week they sit in the all-day band; the hour
 *  rows below are empty on purpose until appointments can be booked, and they
 *  open at clinic hours so the empty night does not take the screen.
 *
 *  Tone and mark come from the contact arc's own tables, so a missed contact
 *  is the same red here as on the visit. This file draws what it is given:
 *  fetching, the scale switcher and the date in the address belong to the page.
 *  Below 600px the week is one day at a time and the year is one column.
 */
import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { MARK, TONE } from "../thread/Arc";
import type { CalendarRow } from "../types";
import { dayLabel, dayOf } from "./day";
import { cells, dayTone, step, tipOf, wasDue, type Scale } from "./cells";

/** How many contacts a month cell lists before it says "+N more". */
const MAX = 3;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
/** The hour grid opens here, not at midnight. */
const FIRST_HOUR = 7;
const HOUR_PX = 48;
/** The week's band has no room limit: it grows to fit, so it never says "+N more". */
const NO_LIMIT = Infinity;

type Cell = ReturnType<typeof cells>[number];

/** True below the width where seven columns stop being readable. */
function useNarrow(): boolean {
  const q = "(max-width: 600px)";
  const [narrow, setNarrow] = useState(() => typeof matchMedia === "function" && matchMedia(q).matches);
  useEffect(() => {
    const m = matchMedia(q);
    const on = () => setNarrow(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return narrow;
}

export type GridProps = {
  scale: Scale;
  /** Any date inside what is shown: the week, month or year is found from it. */
  anchor: string;
  /** The kernel's own date for today, not the browser's clock. */
  today: string;
  rows: CalendarRow[];
  nameOf: (subjectRow: Record<string, unknown>) => string;
  onOpenPatient?: (subject: string) => void;
  /** A day was chosen: its date numeral, a "+N more", or a day in the year. */
  onPickDay?: (day: string) => void;
  /** The phone's one-day week moved to another day. */
  onAnchor?: (day: string) => void;
  /** The grid is one person's own: a chip leaves her name out, since the page
   *  is already hers. */
  own?: boolean;
};

export function Grid(p: GridProps) {
  const narrow = useNarrow();
  if (p.scale === "year") return <Year {...p} />;
  if (p.scale === "month") return <Month {...p} />;
  return narrow ? <OneDay {...p} /> : <Week {...p} />;
}

function Chip({ row, cell, nameOf, onOpenPatient, own }: Pick<GridProps, "nameOf" | "onOpenPatient" | "own"> & { row: CalendarRow; cell: string }) {
  const who = nameOf(row.subject_row);
  // A late contact is drawn on today; the chip says when she was really due.
  const was = wasDue(row, cell);
  const said = `${row.title}${own ? "" : ` for ${who}`}${was ? `, due ${was}` : ""}`;
  return (
    <button
      type="button" className="gr-chip" data-tone={TONE[row.state] ?? "b-mute"}
      title={tipOf(row, said)} aria-label={said} onClick={() => onOpenPatient?.(row.subject)}
    >
      <Icon name={(MARK[row.state] ?? "clock") as never} className="i sm" />
      {!own && <span className="gr-chip-who">{who}</span>}
      {was && <span className="gr-chip-was">due {was}</span>}
      <span className="gr-chip-t">{row.title}</span>
    </button>
  );
}

function DayNumber({ c, onPickDay, label }: { c: Cell; onPickDay?: (d: string) => void; label?: string }) {
  return (
    <button
      type="button" className="gr-num" aria-current={c.isToday ? "date" : undefined}
      aria-label={dayLabel(c.key, c.isToday ? c.key : "")} onClick={() => onPickDay?.(c.key)}
    >
      {label ?? dayOf(c.key).day}
    </button>
  );
}

function Month(p: GridProps) {
  const all = cells("month", p.anchor, p.rows, MAX, p.today);
  return (
    <div className="gr gr-month" role="group" aria-label="Month">
      {WEEKDAYS.map((w) => <div key={w} className="gr-wd">{w}</div>)}
      {all.map((c) => (
        <div key={c.key} className="gr-cell" data-out={!c.inMonth || undefined} data-today={c.isToday || undefined}>
          <DayNumber c={c} onPickDay={p.onPickDay} />
          {c.rows.map((r) => (
            <Chip key={`${r.schedule}|${r.episode}|${r.contact}|${r.subject}`} row={r} cell={c.key} nameOf={p.nameOf} onOpenPatient={p.onOpenPatient} own={p.own} />
          ))}
          {c.more > 0 && (
            <button type="button" className="gr-more" onClick={() => p.onPickDay?.(c.key)}>+{c.more} more</button>
          )}
        </div>
      ))}
    </div>
  );
}

/** The all-day band and the hour grid, for the seven days or for one. */
function Days({ all, p, single }: { all: Cell[]; p: GridProps; single: boolean }) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => { if (scroller.current) scroller.current.scrollTop = FIRST_HOUR * HOUR_PX - 12; }, []);
  const cols = { gridTemplateColumns: `56px repeat(${all.length}, minmax(0, 1fr))` };
  return (
    <div className="gr gr-week" role="group" aria-label={single ? "Day" : "Week"}>
      <div className="gr-head" style={cols}>
        <div />
        {all.map((c) => (
          <div key={c.key} className="gr-dayhead" data-today={c.isToday || undefined}>
            <span className="gr-wd">{dayLabel(c.key, "").split(" ")[0]}</span>
            <DayNumber c={c} onPickDay={p.onPickDay} />
          </div>
        ))}
      </div>
      <div className="gr-allday" style={cols}>
        <div className="gr-gutter">all-day</div>
        {all.map((c) => (
          <div key={c.key} className="gr-band" data-today={c.isToday || undefined}>
            {c.rows.map((r) => (
              <Chip key={`${r.schedule}|${r.episode}|${r.contact}|${r.subject}`} row={r} cell={c.key} nameOf={p.nameOf} onOpenPatient={p.onOpenPatient} own={p.own} />
            ))}
            {c.more > 0 && <button type="button" className="gr-more" onClick={() => p.onPickDay?.(c.key)}>+{c.more} more</button>}
          </div>
        ))}
      </div>
      <div className="gr-hours" ref={scroller} tabIndex={0} aria-label="Hours">
        <div className="gr-hours-in" style={{ ...cols, height: 24 * HOUR_PX }}>
          <div className="gr-hourcol">
            {Array.from({ length: 24 }, (_, h) => (
              <div key={h} className="gr-gutter gr-hr" style={{ top: h * HOUR_PX }}>
                {h === 0 ? "" : `${h % 12 || 12} ${h < 12 ? "am" : "pm"}`}
              </div>
            ))}
          </div>
          {all.map((c) => <div key={c.key} className="gr-hourcol gr-lines" data-today={c.isToday || undefined} />)}
        </div>
      </div>
    </div>
  );
}

const Week = (p: GridProps) => <Days all={cells("week", p.anchor, p.rows, NO_LIMIT, p.today)} p={p} single={false} />;

function OneDay(p: GridProps) {
  // The week's cells include the shown day; it is the one the phone draws.
  const day = cells("week", p.anchor, p.rows, NO_LIMIT, p.today).find((c) => c.key === p.anchor);
  return (
    <div className="gr-one">
      <div className="gr-nav">
        <button type="button" className="gr-arrow" aria-label="Previous day" onClick={() => p.onAnchor?.(step("day", p.anchor, -1))}>
          <Icon name="chev" className="i" />
        </button>
        <span className="gr-nav-t">{dayLabel(p.anchor, p.today)}</span>
        <button type="button" className="gr-arrow gr-next" aria-label="Next day" onClick={() => p.onAnchor?.(step("day", p.anchor, 1))}>
          <Icon name="chev" className="i" />
        </button>
      </div>
      {day && <Days all={[day]} p={p} single />}
    </div>
  );
}

function Year(p: GridProps) {
  const y = p.anchor.slice(0, 4);
  // The whole year in one pass, rows listed (the year ignores `max`); each
  // month below borrows only its shape from the month scale.
  const day = new Map(cells("year", p.anchor, p.rows, 0, p.today).map((c) => [c.key, c]));
  return (
    <div className="gr gr-year" role="group" aria-label="Year">
      {MONTH_NAMES.map((name, i) => {
        const first = `${y}-${String(i + 1).padStart(2, "0")}-01`;
        return (
          <section key={first} className="gr-mini" aria-label={name}>
            <h3 className="gr-mini-h">{name}</h3>
            <div className="gr-mini-g">
              {WEEKDAYS.map((w) => <span key={w} className="gr-mini-wd">{w[0]}</span>)}
              {cells("month", first, [], 0).map((shape) => {
                if (!shape.inMonth) return <span key={shape.key} />;
                const c = day.get(shape.key)!;
                const tone = dayTone(c.rows.map((r) => TONE[r.state] ?? "b-mute"));
                return (
                  <button
                    key={c.key} type="button" className="gr-dot" data-tone={tone}
                    data-today={c.isToday || undefined} aria-current={c.isToday ? "date" : undefined}
                    aria-label={`${dayLabel(c.key, p.today)}${c.rows.length ? `, ${c.rows.length} due` : ""}`}
                    onClick={() => p.onPickDay?.(c.key)}
                  >
                    {dayOf(c.key).day}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
