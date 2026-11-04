/** The day, as the centre owes it: a large date numeral, a bar in the state's
 *  tone, one sentence, and the ROLE that owns the contact. Rows are grouped
 *  late, owed, done. A row names a role and never a worker, because there is
 *  no staff register to name one from.
 *
 *  The tones and marks are the contact arc's own, so a missed contact is red
 *  here for the same reason it is red on the visit. Filtering by role happens
 *  here, on what the kernel already sent; nothing is stored.
 */
import { useState } from "react";
import { Icon } from "../icons";
import { MARK, TONE } from "../thread/Arc";
import type { CalendarRow, QueueRow, ViewDecl, ViewResult } from "../types";
import { title } from "../words";
import { dayOf, emptyLine, EVERYONE, forRole, inPiles, roleChips } from "./day";
import { fields } from "./View";

export function Calendar({ result, decl, role, onOpenPatient }: {
  result: ViewResult;
  decl?: ViewDecl;
  /** The caller's own role. Its chip is the one selected on open. */
  role: string;
  onOpenPatient?: (subject: string) => void;
}) {
  const rows = (result.rows ?? []) as CalendarRow[];
  const { roles, initial } = roleChips(rows, role);
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? initial;
  const shown = forRole(rows, selected);
  const empty = emptyLine(rows.length, shown.length);

  return (
    <div className="cal">
      <div className="cal-chips" role="group" aria-label="Whose contacts">
        {[EVERYONE, ...roles].map((r) => (
          <button
            key={r || "everyone"} type="button" className="cal-chip"
            aria-pressed={selected === r} onClick={() => setPicked(r)}
          >
            {r === EVERYONE ? "Everyone" : title(r)}
          </button>
        ))}
      </div>

      {empty && <div className="state-empty">{empty}</div>}

      {inPiles(shown).map((g) => (
        <section key={g.pile} className="cal-pile" aria-label={g.label}>
          <h2 className="cal-h">{g.label} <span className="cal-n">{g.rows.length}</span></h2>
          <ul className="cal-list">
            {g.rows.map((r) => {
              const { day, month } = dayOf(r.due);
              const who = fields(decl, { subject: r.subject_row } as unknown as QueueRow);
              return (
                <li key={`${r.contact}-${r.subject}`}>
                  <button type="button" className="cal-row" onClick={() => onOpenPatient?.(r.subject)}>
                    <span className="cal-date">
                      <span className="cal-day">{day}</span>
                      <span className="cal-mon">{month}</span>
                    </span>
                    <span className="cal-bar" data-tone={TONE[r.state] ?? "b-mute"} aria-hidden="true" />
                    <span className="cal-what">
                      <span className="cal-sentence">
                        <Icon name={(MARK[r.state] ?? "clock") as never} className="i sm" />
                        {r.title} for {who.name}
                      </span>
                      <span className="cal-when">
                        {r.state === "done" && r.done_at ? <>Recorded {r.done_at}</> : <>Closes {r.closes}</>}
                      </span>
                    </span>
                    <span className="cal-role">{title(r.owner)}</span>
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
