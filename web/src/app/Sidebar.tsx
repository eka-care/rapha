/** §4.1. Brand, New, the declared views, recents, and who you are.
 *
 *  Every nav label below is `v.title` off a declaration. This file types no
 *  view's name, which is what a check can prove: a renderer that never writes
 *  the word cannot be the one that put it on screen.
 *
 *  §4.1's "do not put these in primary navigation" list -- scribe, handover,
 *  vitals, lab, pharmacy, ABHA, AI -- is honoured by construction rather than
 *  by a filter: operations are not nav, so none of them can appear here.
 */
import { Icon, type IconName } from "../icons";
import type { Facility, ViewDecl } from "../types";

import type { Recent } from "../loops";
export type { Recent };

const ICON: Record<string, IconName> = {
  queue: "users", tasklist: "list", dashboard: "vitals", summary: "doc",
};

export function Sidebar({
  facility, views, route, recents, counts, open, onGo, onNew, onSettings, onCloseDrawer,
}: {
  facility?: Facility;
  views: ViewDecl[];
  route: string;
  recents: Recent[];
  counts: Record<string, number>;
  open: boolean;
  onGo: (hash: string) => void;
  onNew: () => void;
  onSettings: () => void;
  onCloseDrawer: () => void;
}) {
  return (
    <nav className="sidebar" data-open={open} aria-label="Main">
      <div className="sidebar-head">
        <Icon name="mark" />
        <span className="sidebar-brand">{facility?.bundle.title ?? "Workspace"}</span>
      </div>

      <div style={{ padding: "0 var(--space-2) var(--space-2)" }}>
        <button className="nav-item" onClick={onNew} style={{ fontWeight: 600 }}>
          <span className="nav-item__icon"><Icon name="plus" /></span>
          <span>New</span>
        </button>
      </div>

      <div className="sidebar-scroll">
        <div className="sidebar-nav">
          <button
            className="nav-item"
            data-active={route === "" || route === "today"}
            onClick={() => { onGo("#/"); onCloseDrawer(); }}
          >
            <span className="nav-item__icon"><Icon name="home" /></span>
            <span>Today</span>
          </button>

          {views.map((v) => (
            <button
              key={v.id}
              className="nav-item"
              data-active={route === `views/${v.id}`}
              onClick={() => { onGo(`#/views/${v.id}`); onCloseDrawer(); }}
            >
              <span className="nav-item__icon"><Icon name={ICON[v.kind] ?? "list"} /></span>
              <span>{v.title}</span>
              {counts[v.id] > 0 && <span className="nav-item__count">{counts[v.id]}</span>}
            </button>
          ))}
        </div>

        {recents.length > 0 && (
          <>
            <div className="sidebar-group">Recents</div>
            <div className="sidebar-nav" style={{ paddingTop: 0 }}>
              {recents.map((r) => (
                <button
                  key={r.id}
                  className="nav-item"
                  data-active={route === `threads/${r.id}`}
                  onClick={() => { onGo(`#/threads/${r.id}`); onCloseDrawer(); }}
                >
                  <span className="nav-item__icon"><Icon name="chat" /></span>
                  <span>{r.name}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="sidebar-foot">
        <button className="nav-item" onClick={onSettings} data-active={route === "settings"}>
          <span className="nav-item__icon"><Icon name="user" /></span>
          <span>
            {facility?.user.role ? labelFor(facility.user.role) : "Account"}
          </span>
          <span className="nav-item__icon" style={{ marginLeft: "auto" }}><Icon name="cog" /></span>
        </button>
      </div>
    </nav>
  );
}

const labelFor = (role: string) =>
  role.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
