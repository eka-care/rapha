/** The day, as the centre owes it: a large date numeral, a bar in the state's
 *  tone, one sentence, and the ROLE that owns the contact. Rows are grouped
 *  late, owed, done. A row names a role and never a worker, because there is
 *  no staff register to name one from.
 *
 *  The tones and marks are the contact arc's own, so a missed contact is red
 *  here for the same reason it is red on the visit. Filtering by role happens
 *  here, on what the kernel already sent; nothing is stored.
 */
import { useEffect, useRef, useState } from "react";
import { api, useAsync } from "../api";
import { say } from "../announce";
import { Icon } from "../icons";
import { Loading } from "../parts";
import { MARK, TONE } from "../thread/Arc";
import type { CalendarRow, ViewResult } from "../types";
import { dateOf, dateWords, dayHeading, dayOn, dayOf, emptyLine, EVERYONE, forRole, inPiles, roleChips, scaleOf, withView, atOf } from "./day";
import { Grid } from "./Grid";
import { span, spanTitle, step, type Scale } from "./cells";

const SCALES: { scale: Scale; label: string }[] = [
  { scale: "week", label: "Week" }, { scale: "month", label: "Month" }, { scale: "year", label: "Year" },
];
/** Move the address; the hashchange listener below does the rest. */
const goTo = (change: Parameters<typeof withView>[1]) => { location.hash = withView(location.hash, change).replace(/^#/, ""); };

export function Calendar({ result, nameOf, role, onOpenPatient }: {
  result: ViewResult;
  /** What a patient's record is called, decided by the view's own columns.
   *  Handed in rather than imported, so this file and View.tsx do not import
   *  each other. */
  nameOf: (subjectRow: Record<string, unknown>) => string;
  /** The caller's own role. Its chip is the one selected on open. */
  role: string;
  onOpenPatient?: (subject: string) => void;
}) {
  // A role's name is the bundle's to give. Until the catalogue arrives the
  // raw id shows, which is plain, where a cased id would be a word we made up.
  const cat = useAsync(() => api.catalogue(), []);
  const roleName = (r: string) => cat.data?.vocabulary?.role_titles?.[r] ?? r;
  // A link from the home page names a day (`?on=`). It lives in the address,
  // so the back button and a reload both land on the same day. Nothing is kept.
  const [hash, setHash] = useState(() => location.hash);
  useEffect(() => {
    const on = () => setHash(location.hash);
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  const today = dateOf(result.generated_at);
  const asked = dayOn(hash);
  const other = asked && asked !== today ? asked : "";
  // The grid: the scale and the date are in the address, and the range asked
  // for follows the scale. The answer is tagged with the range it was asked
  // for, so a month is never drawn from a week's rows while the next read is
  // in flight.
  const scale = scaleOf(hash);
  const anchor = atOf(hash) || asked || today;
  const { from, to } = span(scale, anchor);
  const grid = useAsync(
    () => (from ? api.view(result.view, undefined, undefined, { from, to }).then((r) => ({ key: `${from}|${to}`, r })) : Promise.resolve(null)),
    [from, to, result.view]);
  const gridHave = grid.data && grid.data.key === `${from}|${to}` ? grid.data.r : null;
  const gridFailed = !gridHave && !!grid.error && !grid.loading;
  const gridRows = (gridHave?.rows ?? []) as CalendarRow[];
  // The answer carries the day it was asked for. useAsync sets `loading` in an
  // effect, after the render in which the day changed, and keeps the last
  // answer while the next is in flight; so "is this answer for THIS day" is
  // decided here, by the tag, never by `loading`.
  const fetched = useAsync(
    () => (other ? api.view(result.view, undefined, other).then((r) => ({ on: other, r })) : Promise.resolve(null)),
    [other, result.view]);
  const have = fetched.data && fetched.data.on === other ? fetched.data.r : null;
  const failed = !!other && !have && !!fetched.error && !fetched.loading;
  const waiting = !!other && !have && !failed;
  const answer = other ? have : result;
  const rows = (answer?.rows ?? []) as CalendarRow[];
  // A chip for every role that owns something on the day or in the grid.
  const { roles, initial } = roleChips([...rows, ...gridRows], role, roleName);
  const [picked, setPicked] = useState<string | null>(null);
  // The narrowing menu. One control for every role, rather than a chip each:
  // five chips wrapped to two lines above the day and still said nothing
  // about how much each one holds.
  const [menu, setMenu] = useState(false);
  const filter = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const away = (e: MouseEvent) => { if (!filter.current?.contains(e.target as Node)) setMenu(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    addEventListener("mousedown", away); addEventListener("keydown", esc);
    return () => { removeEventListener("mousedown", away); removeEventListener("keydown", esc); };
  }, [menu]);
  // A picked role that owns nothing on THIS day is not honoured: the screen
  // falls back to everyone, so the chip shown pressed is always one that
  // draws rows and "nothing here" is never said while other roles have work.
  const selected = picked !== null && (picked === EVERYONE || roles.includes(picked)) ? picked : initial;
  const shown = forRole(rows, selected);
  const piles = inPiles(shown, !other);
  const gridShown = forRole(gridRows, selected);
  // Emptiness is what the piles actually hold, not a count taken before them.
  const empty = emptyLine(rows.length, piles.reduce((n, p) => n + p.rows.length, 0));

  // The day the left column is about: the one asked for, or today.
  const onDay = other || today;
  const pick = (r: string) => {
    setPicked(r); setMenu(false);
    const n = forRole(rows, r).length;
    say(n === 1 ? "1 visit shown." : `${n} visits shown.`);
  };

  return (
    <div className="cal cal-page">
     {/* ONE BAND OF CONTROLS, NOT TWO. The scales sat on the right, the
         roles on the left as a wrapping strip of chips, and nothing on the
         page said which of them was the heading of the page itself. */}
     <header className="cal-top">
      <div className="cal-nav" data-scale={scale}>
        <button type="button" className="gr-arrow" aria-label={`Previous ${scale}`} onClick={() => goTo({ at: step(scale, anchor, -1) })}>
          <Icon name="chev" className="i" />
        </button>
        <button type="button" className="gr-arrow gr-next" aria-label={`Next ${scale}`} onClick={() => goTo({ at: step(scale, anchor, 1) })}>
          <Icon name="chev" className="i" />
        </button>
        <button type="button" className="cal-ghost" onClick={() => goTo({ on: "", at: "" })}>Today</button>
      </div>
      <h2 className="cal-title">{spanTitle(scale, anchor)}</h2>
      <div className="cal-tools">
        <div className="cal-filter" ref={filter}>
          <button
            type="button" className={`sb-filter-go${selected === EVERYONE ? "" : " on"}`}
            aria-expanded={menu} aria-haspopup="true" onClick={() => setMenu((v) => !v)}
          >
            <Icon name="sliders" className="i sm" />
            <span className="sb-filter-t">{selected === EVERYONE ? "Everyone" : roleName(selected)}</span>
            <span className="sb-filter-n">{shown.length}</span>
          </button>
          {menu && (
            <div className="sb-filter-menu">
              <button type="button" className={`sb-filter-item${selected === EVERYONE ? " on" : ""}`} onClick={() => pick(EVERYONE)}>
                <span>Everyone</span><span className="sb-filter-c">{rows.length}</span>
              </button>
              {roles.map((r) => (
                <button key={r} type="button" className={`sb-filter-item${selected === r ? " on" : ""}`} onClick={() => pick(r)}>
                  <span>{roleName(r)}</span><span className="sb-filter-c">{forRole(rows, r).length}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="cal-seg" role="group" aria-label="Scale">
          {SCALES.map((s) => (
            <button key={s.scale} type="button" className="cal-seg-b" aria-pressed={scale === s.scale} onClick={() => goTo({ scale: s.scale })}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
     </header>
     <aside className="cal-side" aria-label="The day">
      {/* The column always says which day it is showing. It said nothing at
          all on today, so a person who had wandered off and come back had
          no way to tell what they were looking at. */}
      <div className="cal-dayhead">
        <h2 className="cal-dayt">{dayHeading(onDay, today)}</h2>
        {other && (
          <button type="button" className="cal-ghost" onClick={() => goTo({ on: "", at: "" })}>Back to today</button>
        )}
      </div>
      {waiting && <Loading what="this day" shape="rows" rows={3} />}
      {failed && <div className="state-empty">This day could not be opened.</div>}

      {empty && !waiting && !failed && (
        <div className="state-empty">
          {empty}
          {rows.length > 0 && (
            <button type="button" className="cal-ghost" onClick={() => pick(EVERYONE)}>Show everyone</button>
          )}
        </div>
      )}

      {piles.map((g) => (
        <section key={g.pile} className="cal-pile" aria-label={g.label}>
          <h2 className="cal-h">{g.label} <span className="cal-n">{g.rows.length}</span></h2>
          <ul className="cal-list">
            {g.rows.map((r) => {
              const { day, month } = dayOf(r.due);
              return (
                <li key={`${r.schedule}|${r.episode}|${r.contact}|${r.subject}`}>
                  <button type="button" className="cal-row" onClick={() => onOpenPatient?.(r.subject)}>
                    <span className="cal-date">
                      <span className="cal-day">{day}</span>
                      <span className="cal-mon">{month}</span>
                    </span>
                    <span className="cal-bar" data-tone={TONE[r.state] ?? "b-mute"} aria-hidden="true" />
                    {/* THE TITLE KEEPS ITS OWN LINE. In one sentence with
                        her name it wrapped inside the word: "Second check-"
                        over "up". */}
                    <span className="cal-what">
                      <span className="cal-sentence" title={r.programme_title || undefined}>
                        <Icon name={(MARK[r.state] ?? "clock") as never} className="i sm" />
                        <span className="cal-t">{r.title}</span>
                      </span>
                      <span className="cal-who">for {nameOf(r.subject_row)}</span>
                      {/* The big numeral beside this is the DUE day, so the
                          line under it says so in words and says when the
                          window shuts. It said only "Closes 2026-11-27",
                          which is an ISO date in front of a health worker
                          and left the numeral unexplained. */}
                      <span className="cal-when">
                        {r.state === "done" && r.done_at
                          ? <>Recorded {dateWords(r.done_at)}</>
                          : r.state === "missed"
                            ? <>Due {dateWords(r.due)} · window shut {dateWords(r.closes)}</>
                            : <>Due {dateWords(r.due)} · open until {dateWords(r.closes)}</>}
                      </span>
                    </span>
                    <span className="cal-role">{roleName(r.owner)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
     </aside>
     <section className="cal-main" aria-label="Dates">
      {gridFailed && <div className="state-empty">This {scale} could not be opened.</div>}
      {!gridHave && !gridFailed && <Loading what={`this ${scale}`} shape="rows" rows={4} />}
      {gridHave && (
        <Grid
          scale={scale} anchor={anchor} today={today} rows={gridShown} nameOf={nameOf}
          onOpenPatient={onOpenPatient} onPickDay={(d) => goTo({ on: d, at: d })} onAnchor={(d) => goTo({ at: d })}
        />
      )}
     </section>
    </div>
  );
}
