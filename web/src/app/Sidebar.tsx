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

import { Icon, type IconName } from "../icons";
import type { Facility, QueueRow, ViewDecl } from "../types";
import { fields } from "../view/View";
import { human, title } from "../words";

/** The values a row wears as a label, which is the view's own `labels:`.
 *  The screen is told which columns those are and nothing about what they
 *  mean: a bundle that labels something else gets its own chips. */
function labelValues(decl: ViewDecl, row: QueueRow): string[] {
  return ((decl as { labels?: string[] }).labels ?? [])
    .map((c) => String(row.subject?.[c] ?? "").trim())
    .filter(Boolean);
}

/** EVERYTHING A ROW WEARS is something the line can be narrowed by: the
 *  declared label values AND the flags the rows are carrying today. It was
 *  the labels alone, so the rail could narrow to a programme but not to the
 *  three people whose vitals are flagged -- which is the narrowing somebody
 *  standing at the station actually wants.
 *
 *  Both come off the declaration. A label is a column the view names, a
 *  flag is the workflow's own state, and this file invents neither: a
 *  bundle with different states gets different chips with no change here. */
const flagsOf = (row: QueueRow) => row.flags ?? [];

function tags(line: { decl: ViewDecl; row: QueueRow }[], row: QueueRow, decl: ViewDecl) {
  void line;
  return [...labelValues(decl, row), ...flagsOf(row)];
}

/** One chip per thing the rows wear, commonest first, plus the one that
 *  clears them. A line where every row wears the same label has nothing to
 *  narrow, and `pills.length > 1` is what drops the row entirely. */
function chips(line: { decl: ViewDecl; row: QueueRow }[]):
    { value: string; label: string; count: number }[] {
  const seen = new Map<string, number>();
  for (const { decl, row } of line)
    for (const v of tags(line, row, decl)) seen.set(v, (seen.get(v) ?? 0) + 1);
  const out = [...seen.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, label: title(human(value)), count }));
  return out.length ? [{ value: "", label: "All", count: line.length }, ...out] : [];
}

/** How many of the line fit before the rail is a scroll rather than a
 *  glance. The rest is one tap away in the view the rows came from. */
const LINE = 9;

/** WHICH SECOND PANEL THIS ROUTE WANTS, or none at all.
 *
 *  Home is deliberately `null`. A panel that is always open is not a panel,
 *  it is a margin, and the home screen is the one place whose whole job is
 *  to be looked at rather than navigated. The line belongs beside the line
 *  and beside a visit, because both are places you move between people
 *  from; the settings sections belong beside the settings.
 */
export type Panel = "line" | "settings" | null;

export function panelFor(route: string): Panel {
  if (route.startsWith("views/") || route.startsWith("threads/")) return "line";
  if (route.startsWith("settings")) return "settings";
  return null;
}

export function Sidebar({
  facility, route, line, open, panel, sections, onGo, onCall, onCloseDrawer,
}: {
  facility?: Facility;
  route: string;
  /** What this panel is showing, decided by `panelFor` in the shell so that
   *  the shell can also decide whether to give it any width. */
  panel: Exclude<Panel, null>;
  /** The settings sections, when that is what this panel is for. Their
   *  words come from Control.tsx, which owns them. */
  sections: { id: string; title: string; icon: IconName }[];
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
  const [filters, setFilters] = useState(false);
  /** What this bundle calls the number on a row, off the declared columns,
   *  so the box is labelled in the centre's own word and this file types none
   *  of them. A bundle whose queue declares no such column has no number to
   *  call, and the box is absent rather than asking for one by a name the
   *  renderer made up. */
  const tokenWord = (line[0]?.decl.columns ?? []).find((c) => /token/i.test(c)) ?? "";
  /** CALLING A NUMBER IS CALLING A PERSON, not searching for digits.
   *
   *  This column already holds the line and every row's number, so the
   *  number resolves here: the thread whose token matches opens, which is
   *  the patient walking up to the counter. It went to the front desk with
   *  the digits in the search box instead, which is a different act -- that
   *  is what you do when you do not know who someone is, and a token is the
   *  one thing that says exactly who they are.
   *
   *  Loose on the comparison, because the board outside says 7 and the row
   *  may carry "007" or "A-7", and a clerk retyping a number to make it
   *  match is a clerk doing the computer's job.
   */
  const loose = (v: string) => v.toLowerCase().replace(/[^a-z0-9]/g, "").replace(/^0+(?=\d)/, "");
  const callOut = () => {
    const want = loose(call.trim());
    if (!want) return;
    const hit = line.find(({ decl, row }) => loose(fields(decl, row).token) === want);
    setCall("");
    // NOT IN THE LINE IS NOT AN ERROR. A number nobody here holds is most
    // often somebody who has not been registered yet, so it falls through
    // to the desk with what was typed, which is where that is put right.
    if (hit) goTo(`#/threads/${hit.row.thread}`);
    else onCall(call.trim());
  };

  const pills = chips(line);
  const shown = filter
    ? line.filter(({ decl, row }) => tags(line, row, decl).includes(filter))
    : line;

  if (panel === "settings") {
    // `#/settings` with no section shows the first one, so that is the row
    // that has to look selected. Without this the page showed Appearance
    // while the column showed nothing chosen.
    const part = route.split("/")[1] || sections[0]?.id;
    return (
      <nav className="sb" data-open={open} aria-label="Settings sections">
        <div className="sb-head">
          <div className="sb-head-t">Settings</div>
          <div className="sb-head-s">{facility?.bundle.title ?? "This centre"}</div>
        </div>
        <div className="sb-nav">
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`sb-sec-i${s.id === part ? " on" : ""}`}
              aria-current={s.id === part ? "page" : undefined}
              onClick={() => goTo(`#/settings/${s.id}`)}
            >
              <Icon name={s.icon} className="i sm" />
              {s.title}
            </button>
          ))}
        </div>
      </nav>
    );
  }

  return (
    <nav className="sb" data-open={open} aria-label="The line">
      {/* The brand moved to the icon rail, where it is the one mark at the
          top of the one column that is always there. It was repeated here
          over a list of patients, which is the second place a person looks
          and the last place that needs telling them which product this is. */}
      <div className="sb-head">
        <div className="sb-head-t">{lineTitle || "Today"}</div>
        <div className="sb-head-s">
          {shown.length === 1 ? "1 patient" : `${shown.length} patients`}
        </div>
      </div>

      {/* THE LINE AND NOTHING ELSE. A Register button, a search row, six
          view links and an account footer used to sit above the people
          waiting -- eleven things to read before the one this column is for.
          All of them are in the top bar now, which is where the artifact
          keeps them, and this column is the line: call a number, narrow by
          programme, and the people. */}
      {tokenWord && (
      <form className="sb-call" onSubmit={(e) => { e.preventDefault(); callOut(); }}>
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

      {/* ONE CONTROL, NOT TEN CHIPS. Every programme and every flag in the
          line used to be a chip, so a day with four programmes and three
          flags put eight buttons above the people -- a filter bar taller
          than what it filtered. It is one icon now, and what it opens is
          the same declared list: the view's own label column and the
          workflow's own flags, counted. This file is told the column and
          draws its values; it is told nothing about what a programme IS. */}
      {pills.length > 1 && (
        <div className="sb-filter">
          <button type="button" className={`sb-filter-go${filter ? " on" : ""}`}
                  aria-expanded={filters} aria-haspopup="true"
                  onClick={() => setFilters((v) => !v)}>
            <Icon name="sliders" className="i sm" />
            <span className="sb-filter-t">
              {filter ? (pills.find((p) => p.value === filter)?.label ?? "Filtered") : "Narrow the line"}
            </span>
            <span className="sb-filter-n">{shown.length}</span>
          </button>
          {filter && (
            <button type="button" className="sb-filter-x" aria-label="Show everybody"
                    onClick={() => setFilter("")}>
              <Icon name="plus" className="i sm" />
            </button>
          )}
          {filters && (
            <ul className="sb-filter-menu">
              {pills.map((p) => (
                <li key={p.value}>
                  <button type="button"
                          className={`sb-filter-item${filter === p.value ? " on" : ""}`}
                          onClick={() => { setFilter(p.value); setFilters(false); }}>
                    <span>{p.label}</span>
                    <span className="sb-filter-c">{p.count}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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
                {row.station && <span className="th-s">{title(row.station)}</span>}
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
