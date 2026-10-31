/** The rail, as the prototype draws it: brand, a New button, the declared
 *  views as nav, recents, and who you are at the foot.
 *
 *  Every label is `v.title` off a declaration; this file types no view's name.
 */
import { Icon, type IconName } from "../icons";
import type { Recent } from "../loops";
import type { Facility, ViewDecl } from "../types";
import { human } from "../words";

export type { Recent };

const ICON: Record<string, IconName> = {
  queue: "users", tasklist: "list", dashboard: "vitals", summary: "doc",
};

export function Sidebar({
  facility, views, route, recents, counts, open, onGo, onNew, onDesk, deskLabel, onSettings, onCloseDrawer,
}: {
  facility?: Facility;
  views: ViewDecl[];
  route: string;
  recents: Recent[];
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

      <div className="sb-sec">Recents</div>
      <div className="sb-list">
        {recents.length === 0 ? (
          <div className="sb-empty">No threads yet. Open a patient or start a workspace chat.</div>
        ) : recents.map((r) => (
          <button
            key={r.id}
            className={`th-row${route === `threads/${r.id}` ? " on" : ""}`}
            onClick={() => goTo(`#/threads/${r.id}`)}
          >
            <Icon name="chat" className="i sm" />
            <span className="th-n">{r.name}</span>
          </button>
        ))}
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
