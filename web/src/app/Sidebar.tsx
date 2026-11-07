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
import { say } from "../announce";
import { displayFor } from "../declarations";
import { filterRows, narrowings, sameFilter, type Filter } from "../loops";
import { initialsOf } from "../agent";
import { waited } from "../messages";
import type { Facility, QueueRow, ViewDecl } from "../types";
import { fields } from "../view/View";
import { human, title } from "../words";

/** How many of the line fit before the rail is a scroll rather than a
 *  glance. The rest is one tap away in the view the rows came from. */


/** WHICH SECOND PANEL THIS ROUTE WANTS, or none at all.
 *
 *  Home is deliberately `null`, and so is any view that is not a queue. A panel that is always open is not a panel,
 *  it is a margin, and the home screen is the one place whose whole job is
 *  to be looked at rather than navigated. The line belongs beside the line
 *  and beside a visit, because both are places you move between people
 *  from; the settings sections belong beside the settings.
 */
export type Panel = "line" | "settings" | null;

export function panelFor(route: string, _views: ViewDecl[]): Panel {
  // THE LINE BESIDE THE LINE, not beside every view. A calendar or a
  // dashboard is somewhere a person reads, not somewhere they move between
  // people from, and the queue down its side was a second screen's worth of
  // names next to a screen about something else. Only a view whose declared
  // kind is a queue gets it -- the same property the shell reads to decide
  // which rows the line is made of.
  // The Lines table is the whole list: search, tabs, filters and every patient
  // are on the page, so it draws no second panel of the same names. The panel
  // stays on a patient's visit, where it is the way to the next person.
  if (route.startsWith("views/")) return null;
  if (route.startsWith("threads/")) return "line";
  if (route.startsWith("settings")) return "settings";
  return null;
}

export function Sidebar({
  facility, route, line, narrow, open, panel, sections,
  onGo, onNarrow, onCall, onCloseDrawer, onFold,
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
  /** How the line is narrowed right now. Held by the shell, because the list
   *  screen draws the same people and must obey the same narrowing. */
  narrow: Filter;
  onNarrow: (f: Filter) => void;
  open: boolean;
  onGo: (hash: string) => void;
  /** A number called at the counter. The desk already searches by it, so
   *  this is that search with the box already filled. */
  onCall: (token: string) => void;
  onCloseDrawer: () => void;
  /** Tuck the line away. Absent where the panel is not the line. */
  onFold?: () => void;
}) {
  const goTo = (hash: string) => { onGo(hash); onCloseDrawer(); };
  // The queue this centre calls its line, in its own words. A facility with
  // no queue view declared gets no section, not an empty one.
  const lineTitle = line[0]?.decl.title ?? "";
  const [call, setCall] = useState("");
  const [filters, setFilters] = useState(false);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const toggle = (k: string) => setClosed((was) => {
    const next = new Set(was);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  });
  /** A number typed is a person asked for. Loose on the comparison, because the
   *  board outside says 7 and the row may carry "007" or "A-7". */
  const loose = (v: string) => v.toLowerCase().replace(/[^a-z0-9]/g, "").replace(/^0+(?=\d)/, "");

  // THE ONE CONTROL OVER TODAY'S LINE. Where they are, what they are on and
  // what is flagged, every option off the declaration, grouped under the
  // three words a person reads to tell those apart. The chips that used to
  // sit above the list screen are these; there is no second place to set it.
  //
  // The whole line is grouped, not the narrowed part, so the counts do not
  // change as a person moves between narrowings -- a menu whose other
  // options read nought once you have picked one cannot be used to pick
  // again.
  const groups = narrowings(
    line[0]?.decl,
    line.map(({ row }) => row),
    displayFor,
    (word) => title(human(word)),
  );
  const chosen = groups.flatMap((g) => g.items).find((i) => sameFilter(i.filter, narrow));
  const shown = (() => {
    const rows = filterRows(line.map(({ row }) => row), narrow);
    const keepers = new Set(rows.map((r) => r.thread));
    return line.filter(({ row }) => keepers.has(row.thread));
  })();

  // The search: a name, a village, a programme or a token, any of them.
  const q = call.trim();
  const visible = shown.filter(({ decl, row }) => {
    if (!q) return true;
    const lq = q.toLowerCase();
    return Object.values(row.subject ?? {}).some((v) => String(v ?? "").toLowerCase().includes(lq))
      || loose(fields(decl, row).token) === loose(q);
  });
  // Grouped by where they are, longest wait first, and finished patients last.
  // The groups are places, not steps: a patient can be anywhere in any order.
  const DONE = "\u0000done";
  const places = new Map<string, typeof visible>();
  for (const item of visible) {
    const k = item.row.station ?? DONE;
    places.set(k, [...(places.get(k) ?? []), item]);
  }
  const oldest = (items: typeof visible) =>
    items.map((i) => i.row.opened_at).filter(Boolean).sort()[0] ?? "~";
  const grouped = [...places.entries()]
    .map(([k, items]) => ({ k, items, label: k === DONE ? "Done" : title(human(k)), oldest: oldest(items) }))
    .sort((a, b) => (a.k === DONE ? 1 : b.k === DONE ? -1 : a.oldest.localeCompare(b.oldest)));
  const openFirst = (list: typeof visible) => {
    if (list.length === 1) goTo(`#/threads/${list[0].row.thread}`);
    else if (list.length === 0 && q) onCall(q);
  };

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
          {`${line.length} today, ${line.filter(({ row }) => row.station).length} here`}
        </div>
        {onFold && (
          <button type="button" className="sb-fold" onClick={onFold}
                  aria-label="Hide the line" title="Hide the line" aria-expanded="true">
            <Icon name="sidebar" className="i sm" />
          </button>
        )}
      </div>

      {/* THE LINE AND NOTHING ELSE. A Register button, a search row, six
          view links and an account footer used to sit above the people
          waiting -- eleven things to read before the one this column is for.
          All of them are in the top bar now, which is where the artifact
          keeps them, and this column is the line: call a number, narrow by
          programme, and the people. */}
      <div className="sb-find">
        <Icon name="search" className="i sm" />
        <input
          value={call}
          onChange={(e) => setCall(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") openFirst(visible); }}
          placeholder="Find a patient or token…"
          aria-label="Find a patient or token"
        />
      </div>

      {/* ONE CONTROL OVER THE DAY, AND ONLY ONE.
          There were two. A strip of chips above the list screen -- a chip
          per station, per programme and for how somebody arrived, with the
          flags behind a button -- and this menu, over the programmes and
          the flags again. Two controls over one question, offering
          different narrowings, neither of them moving the other, and the
          strip taller than the list it filtered.
          It is here, because this is where the people are, and what it
          sets narrows the list screen too. Every option is a declaration's:
          a station today's rows are at, a value in a column the view calls
          a label, the mark the view calls provenance, a badge the view
          declares. The three headings are this renderer's own, and they are
          the only words in it. */}
      {groups.length > 0 && (
        <div className="sb-filter">
          <button type="button" className={`sb-filter-go${narrow ? " on" : ""}`}
                  aria-expanded={filters} aria-haspopup="true"
                  onClick={() => setFilters((v) => !v)}>
            <Icon name="sliders" className="i sm" />
            <span className="sb-filter-t">
              {chosen ? chosen.label : "Filters"}
            </span>
            <span className="sb-filter-n">{visible.length}</span>
          </button>
          {narrow && (
            <button type="button" className="sb-filter-x" aria-label="Show everybody"
                    onClick={() => onNarrow(null)}>
              <Icon name="plus" className="i sm" />
            </button>
          )}
          {filters && (
            <div className="sb-filter-menu">
              {/* The way back to everybody is first and is not under a
                  heading, because it is not one of the three questions --
                  it is the answer to all of them. */}
              <button type="button"
                      className={`sb-filter-item${narrow === null ? " on" : ""}`}
                      onClick={() => {
                        onNarrow(null);
                        setFilters(false);
                        say(line.length === 1 ? "1 shown." : `${line.length} shown.`);
                      }}>
                <span>Everybody</span>
                <span className="sb-filter-c">{line.length}</span>
              </button>
              {groups.map((g) => (
                <div className="sb-filter-grp" key={g.title}>
                  <div className="sb-filter-h">{g.title}</div>
                  {g.items.map((i) => (
                    <button type="button" key={i.key}
                            className={`sb-filter-item${sameFilter(i.filter, narrow) ? " on" : ""}${i.risk ? " risk" : ""}`}
                            onClick={() => {
                        onNarrow(i.filter);
                        setFilters(false);
                        say(i.n === 1 ? "1 shown." : `${i.n} shown.`);
                      }}>
                      <span>{i.label}</span>
                      <span className="sb-filter-c">{i.n}</span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="sb-list">
        {visible.length === 0 ? (
          <div className="sb-empty">{q ? "Nobody matches." : "Nobody is waiting."}</div>
        ) : grouped.map((g) => (
          <div className="sb-g" key={g.k}>
            <button type="button" className="sb-gh" aria-expanded={!closed.has(g.k)} onClick={() => toggle(g.k)}>
              <Icon name="chev" className={`i sm sb-gc${closed.has(g.k) ? " shut" : ""}`} />
              <span className="sb-gl">{g.label}</span>
              <span className="sb-gn">{g.items.length}</span>
            </button>
            {!closed.has(g.k) && g.items.map(({ decl, row }) => {
              const f = fields(decl, row);
              return (
                <button
                  key={row.thread}
                  className={`th-row${route === `threads/${row.thread}` ? " on" : ""}`}
                  onClick={() => goTo(`#/threads/${row.thread}`)}
                >
                  <span className={`th-av${f.named ? "" : " none"}`} aria-hidden="true">{f.named ? initialsOf(f.name) : "?"}</span>
                  <span className="th-b">
                    <span className="th-l1">
                      <span className={`th-n${f.named ? "" : " u-mute"}`}>{f.name}</span>
                      {f.token && <span className="ticket th-tok" title="Token" aria-label={`Token ${f.token}`}><Icon name="ticket" className="i tk-i" />{f.token}</span>}
                    </span>
                    {row.station && waited(row.opened_at) && <span className="th-s">Waiting {waited(row.opened_at)}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>

    </nav>
  );
}
