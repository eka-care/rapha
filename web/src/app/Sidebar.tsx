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
import { Icon, type IconName } from "../icons";
import type { Facility, QueueRow, ViewDecl } from "../types";
import { fields } from "../view/View";
import { human } from "../words";

/** How many of the line fit before the rail is a scroll rather than a
 *  glance. The rest is one tap away in the view the rows came from. */
const LINE = 9;

const ICON: Record<string, IconName> = {
  queue: "users", tasklist: "list", dashboard: "vitals", summary: "doc",
};

export function Sidebar({
  facility, views, route, line, counts, open, onGo, onNew, onDesk, deskLabel,
  onSettings, onCloseDrawer,
}: {
  facility?: Facility;
  views: ViewDecl[];
  route: string;
  /** Today's line, already loaded for the counts above: the same rows the
   *  queue view draws, with the declaration they came from so the name and
   *  the number are read the same way here as there. */
  line: { decl: ViewDecl; row: QueueRow }[];
  counts: Record<string, number>;
  open: boolean;
  onGo: (hash: string) => void;
  onNew: () => void;
  /** The front desk: one box over this centre's register and the patient
   *  directory. The button that used to open the palette twice now opens the
   *  desk once, because "new" at a front desk means a person and not a
   *  conversation. */
  onDesk: () => void;
  /** What that button says. The declared verb of the operation the desk
   *  commits through, so a health centre reads "Register" and a laboratory
   *  reads "Accession" with nothing here knowing either word. */
  deskLabel: string;
  onSettings: () => void;
  onCloseDrawer: () => void;
}) {
  const goTo = (hash: string) => { onGo(hash); onCloseDrawer(); };
  // The queue this centre calls its line, in its own words. A facility with
  // no queue view declared gets no section, not an empty one.
  const lineTitle = line[0]?.decl.title ?? "";
  return (
    <nav className="sb" data-open={open} aria-label="Main">
      <div className="sb-top">
        <span className="brand-mark"><Icon name="mark" /></span>
        <div style={{ minWidth: 0 }}>
          <div className="brand-n">{facility?.bundle.title ?? "Workspace"}</div>
          <div className="brand-s">{facility?.bundle.version ?? ""} · Workspace</div>
        </div>
      </div>

      <div className="sb-pad">
        <button className="sb-btn" onClick={onDesk}>
          <Icon name="plus" className="i sm" />
          {deskLabel}
        </button>
      </div>
      <div className="sb-pad" style={{ paddingTop: 0 }}>
        <button className="sb-btn ghost" onClick={onNew}>
          <Icon name="search" className="i sm" />
          Search
          <span className="kbd ml-auto">⌘K</span>
        </button>
      </div>

      <div className="sb-nav">
        <button className={`nv${route === "" || route === "today" ? " on" : ""}`}
          onClick={() => goTo("#/")}>
          <Icon name="home" className="i sm" />
          Home
        </button>
        {views.map((v) => (
          <button
            key={v.id}
            className={`nv${route === `views/${v.id}` ? " on" : ""}`}
            onClick={() => goTo(`#/views/${v.id}`)}
          >
            <Icon name={ICON[v.kind] ?? "list"} className="i sm" />
            {v.title}
            {counts[v.id] > 0 && <span className="ct">{counts[v.id]}</span>}
          </button>
        ))}
        <button className={`nv${route === "settings" ? " on" : ""}`} onClick={() => goTo("#/settings")}>
          <Icon name="cog" className="i sm" />
          Control panel
        </button>
      </div>

      <div className="sb-sec">{lineTitle}</div>
      <div className="sb-list">
        {line.length === 0 ? (
          <div className="sb-empty">Nobody is waiting.</div>
        ) : line.slice(0, LINE).map(({ decl, row }) => {
          const f = fields(decl, row);
          return (
            <button
              key={row.thread}
              className={`th-row${route === `threads/${row.thread}` ? " on" : ""}`}
              onClick={() => goTo(`#/threads/${row.thread}`)}
            >
              {f.token && <span className="th-tok">{f.token}</span>}
              <span className="th-b">
                <span className="th-n">{f.name}</span>
                {row.station && <span className="th-s">{human(row.station)}</span>}
              </span>
              {row.flags?.some((x) => row.badges?.[x] === "crit") && (
                <span className="th-flag" aria-label="needs attention" />
              )}
            </button>
          );
        })}
        {line.length > LINE && (
          <button className="sb-more" onClick={() => goTo(`#/views/${line[0].decl.id}`)}>
            {line.length - LINE} more
          </button>
        )}
      </div>

      <div className="sb-foot">
        <button className="rolebtn" onClick={onSettings}>
          <span className="rb-av"><Icon name="user" className="i sm" /></span>
          <div style={{ minWidth: 0, flex: 1, textAlign: "left" }}>
            <div className="rb-n">{human(facility?.user.role ?? "account")}</div>
            <div className="rb-s">
              {facility?.user.capabilities.length ?? 0} capabilities
            </div>
          </div>
          <Icon name="chev" className="i sm" />
        </button>
      </div>
    </nav>
  );
}
