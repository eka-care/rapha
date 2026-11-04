/** The day, as the centre owes it: a large date numeral, a bar in the state's
 *  tone, one sentence, and the ROLE that owns the contact. Rows are grouped
 *  late, owed, done. A row names a role and never a worker, because there is
 *  no staff register to name one from.
 *
 *  The tones and marks are the contact arc's own, so a missed contact is red
 *  here for the same reason it is red on the visit. Filtering by role happens
 *  here, on what the kernel already sent; nothing is stored.
 */
import { useEffect, useState } from "react";
import { api, useAsync } from "../api";
import { Icon } from "../icons";
import { Loading } from "../parts";
import { MARK, TONE } from "../thread/Arc";
import type { CalendarRow, ViewResult } from "../types";
import { dateOf, dayLabel, dayOn, dayOf, emptyLine, EVERYONE, forRole, inPiles, roleChips } from "./day";

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
  const { roles, initial } = roleChips(rows, role, roleName);
  const [picked, setPicked] = useState<string | null>(null);
  // A picked role that owns nothing on THIS day is not honoured: the screen
  // falls back to everyone, so the chip shown pressed is always one that
  // draws rows and "nothing here" is never said while other roles have work.
  const selected = picked !== null && (picked === EVERYONE || roles.includes(picked)) ? picked : initial;
  const shown = forRole(rows, selected);
  const piles = inPiles(shown, !other);
  // Emptiness is what the piles actually hold, not a count taken before them.
  const empty = emptyLine(rows.length, piles.reduce((n, p) => n + p.rows.length, 0));

  return (
    <div className="cal">
      <div className="cal-chips" role="group" aria-label="Whose contacts">
        {[EVERYONE, ...roles].map((r) => (
          <button
            key={r || "everyone"} type="button" className="cal-chip"
            aria-pressed={selected === r} onClick={() => setPicked(r)}
          >
            {r === EVERYONE ? "Everyone" : roleName(r)}
          </button>
        ))}
      </div>

      {other && <h2 className="cal-h">{dayLabel(other, today)}</h2>}
      {waiting && <Loading what="this day" shape="rows" rows={3} />}
      {failed && <div className="state-empty">This day could not be opened.</div>}

      {empty && !waiting && !failed && <div className="state-empty">{empty}</div>}

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
                    <span className="cal-what">
                      <span className="cal-sentence">
                        <Icon name={(MARK[r.state] ?? "clock") as never} className="i sm" />
                        {r.title} for {nameOf(r.subject_row)}
                      </span>
                      <span className="cal-when">
                        {r.state === "done" && r.done_at ? <>Recorded {r.done_at}</> : <>Closes {r.closes}</>}
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
    </div>
  );
}
