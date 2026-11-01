/** The rail: brand, a New button, the declared views as nav, THE LINE, and
 *  who you are at the foot.
 *
 *  Every label is `v.title` off a declaration; this file types no view's name.
 *
 *  THE LINE, NOT RECENTS. The artifact this app is built from gives this
 *  column to the people waiting, because that is a health centre's whole day
 *  and a clinician does not navigate to it. What was here was a list of
 *  threads this browser had opened, which on a shared device at a station is
 *  whoever the last person looked at -- and which showed the same patient
 *  twice when they had two visits, under one name, with nothing to tell them
 *  apart. The rows below are the declared queue's own, so they are the same
 *  rows, in the same order, as the view behind them.
 */
import { useState } from "react";
import { Icon } from "../icons";
import type { Facility, QueueRow, ViewDecl } from "../types";
import { fields } from "../view/View";
import { human } from "../words";

/** The values a row wears as a label, which is the view's own `labels:`.
 *  The screen is told which columns those are and nothing about what they
 *  mean: a bundle that labels something else gets its own chips. */
function labelValues(decl: ViewDecl, row: QueueRow): string[] {
  return ((decl as { labels?: string[] }).labels ?? [])
    .map((c) => String(row.subject?.[c] ?? "").trim())
    .filter(Boolean);
}

/** One chip per declared label value in today's line, commonest first, plus
 *  the one that clears them. A line where every row wears the same label has
 *  nothing to narrow, and `pills.length > 1` is what drops the row entirely. */
function chips(line: { decl: ViewDecl; row: QueueRow }[]):
    { value: string; label: string; count: number }[] {
  const seen = new Map<string, number>();
  for (const { decl, row } of line)
    for (const v of labelValues(decl, row)) seen.set(v, (seen.get(v) ?? 0) + 1);
  const out = [...seen.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({ value, label: human(value), count }));
  return out.length ? [{ value: "", label: "All", count: line.length }, ...out] : [];
}

/** How many of the line fit before the rail is a scroll rather than a
 *  glance. The rest is one tap away in the view the rows came from. */
const LINE = 9;

export function Sidebar({
  facility, route, line, open, onGo, onCall, onCloseDrawer,
}: {
  facility?: Facility;
  route: string;
  /** Today's line, already loaded for the counts above: the same rows the
   *  queue view draws, with the declaration they came from so the name and
   *  the number are read the same way here as there. */
  line: { decl: ViewDecl; row: QueueRow }[];
  open: boolean;
  onGo: (hash: string) => void;
  /** A number called at the counter. The desk already searches by it, so
   *  this is that search with the box already filled. */
  onCall: (token: string) => void;
  onCloseDrawer: () => void;
}) {
  const goTo = (hash: string) => { onGo(hash); onCloseDrawer(); };
  // The queue this centre calls its line, in its own words. A facility with
  // no queue view declared gets no section, not an empty one.
  const lineTitle = line[0]?.decl.title ?? "";
  const [call, setCall] = useState("");
  const [filter, setFilter] = useState("");
  /** What this bundle calls the number on a row, off the declared columns,
   *  so the box is labelled in the centre's own word and this file types none
   *  of them. A bundle whose queue declares no such column has no number to
   *  call, and the box is absent rather than asking for one by a name the
   *  renderer made up. */
  const tokenWord = (line[0]?.decl.columns ?? []).find((c) => /token/i.test(c)) ?? "";
  const pills = chips(line);
  const shown = filter
    ? line.filter(({ decl, row }) => labelValues(decl, row).includes(filter))
    : line;
  return (
    <nav className="sb" data-open={open} aria-label="Main">
      <div className="sb-top">
        <span className="brand-mark"><Icon name="mark" /></span>
        <div style={{ minWidth: 0 }}>
          <div className="brand-n">{facility?.bundle.title ?? "Workspace"}</div>
          <div className="brand-s">{facility?.bundle.version ?? ""} · Workspace</div>
        </div>
      </div>

      {/* THE LINE AND NOTHING ELSE. A Register button, a search row, six
          view links and an account footer used to sit above the people
          waiting -- eleven things to read before the one this column is for.
          All of them are in the top bar now, which is where the artifact
          keeps them, and this column is the line: call a number, narrow by
          programme, and the people. */}
      {tokenWord && (
      <form className="sb-call" onSubmit={(e) => { e.preventDefault(); onCall(call.trim()); }}>
        <input
          className="sb-call-in"
          value={call}
          onChange={(e) => setCall(e.target.value)}
          placeholder={`Call a ${human(tokenWord).toLowerCase()}`}
          aria-label={`Call a ${human(tokenWord).toLowerCase()}`}
        />
        <button className="sb-call-go" type="submit">Call</button>
      </form>
      )}

      {/* Narrowed by whatever the view declared as a label. The screen is
          told the column and draws its values; it is told nothing about what
          a programme IS, which is why a bundle that labels something else
          gets its own chips with no edit here. */}
      {pills.length > 1 && (
        <div className="sb-pills">
          {pills.map((p) => (
            <button
              key={p.value}
              className={`sb-pill${filter === p.value ? " on" : ""}`}
              onClick={() => setFilter(filter === p.value ? "" : p.value)}
            >
              {p.label} {p.count}
            </button>
          ))}
        </div>
      )}

      <div className="sb-sec">{lineTitle} · today</div>
      <div className="sb-list">
        {shown.length === 0 ? (
          <div className="sb-empty">Nobody is waiting.</div>
        ) : shown.slice(0, LINE).map(({ decl, row }) => {
          const f = fields(decl, row);
          return (
            <button
              key={row.thread}
              className={`th-row${route === `threads/${row.thread}` ? " on" : ""}`}
              onClick={() => goTo(`#/threads/${row.thread}`)}
            >
              {f.token && <span className="th-tok">{f.token}</span>}
              <span className="th-b">
                <span className={`th-n${f.named ? "" : " u-mute"}`}>{f.name}</span>
                {row.station && <span className="th-s">{human(row.station)}</span>}
              </span>
              {row.flags?.some((x) => row.badges?.[x] === "crit") && (
                <span className="th-flag" aria-label="needs attention" />
              )}
            </button>
          );
        })}
        {shown.length > LINE && (
          <button className="sb-more" onClick={() => goTo(`#/views/${line[0].decl.id}`)}>
            {shown.length - LINE} more
          </button>
        )}
      </div>

    </nav>
  );
}
