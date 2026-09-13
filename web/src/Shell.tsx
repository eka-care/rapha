/** The workspace frame: the sidebar, the topbar, the overlay furniture.
 *
 *  Every word in the sidebar comes from a declaration or from this browser.
 *  The brand is the manifest. The nav is the views the bundle declares that
 *  are not summaries, in manifest order, with counts from the queue results.
 *  The role menu is /facility.roles against /catalogue.bundles. Recents are
 *  this viewer's own localStorage and nobody else's.
 *
 *  Nothing here is written for a bundle: point it at the laboratory kernel and
 *  the same code draws the laboratory's words.
 */
import { useEffect, useState } from "react";
import { API_BASE } from "./api";
import { Icon, iconForView } from "./icons";
import type { Catalogue, Facility, ViewDecl, ViewResult } from "./types";
import { human, title } from "./ui";

// ------------------------------------------------------------------ recents

export type Recent = { id: string; name: string };
// Keyed by the kernel, because a thread id means nothing on a different one.
// Two kernels on two ports are two facilities; without this the laboratory's
// sidebar opened on the health centre's patients, left there by an earlier
// session, and clicking one was a 404. Same browser, same origin, different
// facility, and only this key knows the difference.
const RECENTS = "phc.recents." + API_BASE;

/** Per viewer, not shared, and a convenience rather than a record: the kernel
 *  has no notion of a browsing history and should not grow one for this. */
export function recents(): Recent[] {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENTS) || "[]");
    return Array.isArray(raw) ? raw.slice(0, 10) : [];
  } catch {
    return [];
  }
}

export function remember(r: Recent) {
  try {
    const next = [r, ...recents().filter((x) => x.id !== r.id)].slice(0, 10);
    localStorage.setItem(RECENTS, JSON.stringify(next));
  } catch {
    /* a private window keeps no recents, which is not a failure */
  }
}

// -------------------------------------------------------------------- toast

let say: (m: string) => void = () => {};
export const toast = (m: string) => say(m);

export function Toast() {
  const [msg, setMsg] = useState("");
  useEffect(() => {
    say = (m) => {
      setMsg(m);
      setTimeout(() => setMsg(""), 2600);
    };
    return () => {
      say = () => {};
    };
  }, []);
  return (
    <div className={`toast${msg ? " show" : ""}`}>
      <span className="dot" />
      <span>{msg}</span>
    </div>
  );
}

// ------------------------------------------------------------------- theme

const THEME = "phc.theme";

export function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem(THEME) || "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME, theme);
    } catch {
      /* the attribute is still set for this session */
    }
  }, [theme]);
  return [theme, () => setTheme(theme === "light" ? "dark" : "light")];
}

// ---------------------------------------------------------------- collapse

const COLLAPSED = "phc.sidebar.collapsed";

/** Per viewer, per browser, same treatment as the theme: remembered in
 *  localStorage, and nothing else needs to know about it. */
function useCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSED) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED, collapsed ? "1" : "0");
    } catch {
      /* this session still remembers it */
    }
  }, [collapsed]);
  return [collapsed, () => setCollapsed((c) => !c)];
}

// ----------------------------------------------------------------- sidebar

export function Sidebar({
  cat, facility, queues, route, role, recent, onGo, onRole, onManageRoles,
}: {
  cat: Catalogue | undefined;
  facility: Facility | undefined;
  /** The queue views' results, for the counts. One read each, the same read
   *  Home and the palette use. */
  queues: ViewResult[];
  route: { kind: string; id: string };
  role: string;
  recent: Recent[];
  onGo: (hash: string) => void;
  onRole: (role: string) => void;
  /** Opens the role editor. Always offered here: whether this caller may
   *  actually save is api/main.py's `facility.admin` check, not a thing this
   *  menu decides by hiding the door. */
  onManageRoles: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const [collapsed, toggleCollapsed] = useCollapsed();
  useEffect(() => {
    const shut = () => setMenu(false);
    addEventListener("click", shut);
    return () => removeEventListener("click", shut);
  }, []);

  const nav = navViews(cat, facility?.user?.capabilities);
  const roles = facility?.roles ?? [];
  // vocab.BUNDLES is the kernel's whole role table and the demo union role is
  // not in it, so the caller's own capability list from /facility is the only
  // answer for that one. A role the table does not carry says so rather than
  // claiming none.
  const held = (r: string): string | number =>
    cat?.bundles?.[r]?.length ?? (r === facility?.user?.role ? facility.user.capabilities.length : "?");

  const label = (name: string) => (collapsed ? undefined : name);

  return (
    <aside className={`sb${collapsed ? " collapsed" : ""}`}>
      <div className="sb-top">
        <div className="brand-mark"><Icon name="mark" size="lg" /></div>
        {!collapsed && (
          <div>
            <div className="brand-n">{cat?.manifest?.title ?? "Workspace"}</div>
            <div className="brand-s">
              {cat?.manifest ? `${cat.manifest.id} · ${cat.manifest.version}` : "no manifest"}
            </div>
          </div>
        )}
        <button
          className="icon-btn ml-auto"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          onClick={toggleCollapsed}
        >
          <Icon name="chev" size="sm" />
        </button>
      </div>

      <div className="sb-nav">
        <button className={`nv${route.kind === "home" ? " on" : ""}`} onClick={() => onGo("#/home")} aria-label="Home">
          <Icon name="home" size="sm" />{label("Home")}
        </button>
        {nav.map((v) => {
          const result = queues.find((q) => q.view === v.id);
          const count = result?.groups?.reduce((n, g) => n + (g.key === null ? 0 : g.count), 0);
          const name = v.title ?? title(v.id);
          return (
            <button
              key={v.id}
              className={`nv${route.kind === "view" && route.id === v.id ? " on" : ""}`}
              onClick={() => onGo(`#/views/${v.id}`)}
              aria-label={name}
            >
              <Icon name={iconForView(v)} size="sm" />
              {label(name)}
              {!collapsed && count !== undefined && <span className="ct">{count}</span>}
            </button>
          );
        })}
      </div>

      {!collapsed && <div className="sb-sec">Recents</div>}
      <div className="sb-list">
        {!collapsed && recent.length ? (
          recent.map((t) => (
            <button
              key={t.id}
              className={`th${route.kind === "thread" && route.id === t.id ? " on" : ""}`}
              onClick={() => onGo(`#/threads/${t.id}`)}
            >
              <Icon name="chat" size="sm" />
              <span className="th-n">{t.name}</span>
            </button>
          ))
        ) : (
          !collapsed && (
            <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--gray-400)" }}>
              No threads yet.
            </div>
          )
        )}
      </div>

      <div className="sb-foot">
        <div className={`menu${menu ? " show" : ""}`}>
          {roles.length ? (
            roles.map((r) => (
              <button
                key={r}
                className={`mi${r === role ? " on" : ""}`}
                onClick={() => onRole(r)}
              >
                <span className="mi-l">{r === "demo" ? "Every capability (demo)" : human(r)}</span>
                <span className="mi-c">{held(r)}</span>
              </button>
            ))
          ) : (
            <div style={{ padding: 9, fontSize: 11, color: "var(--ink-3)" }}>No roles.</div>
          )}
          <button
            className="mi"
            onClick={(e) => {
              e.stopPropagation();
              setMenu(false);
              onManageRoles();
            }}
          >
            <Icon name="cog" size="sm" />
            <span className="mi-l">Manage roles</span>
          </button>
        </div>
        <button
          className="rolebtn"
          aria-label={`Role: ${role === "demo" ? "every capability (demo)" : human(role)}`}
          onClick={(e) => {
            e.stopPropagation();
            setMenu(!menu);
          }}
        >
          <span className="rb-av">{role.slice(0, 1).toUpperCase()}</span>
          {!collapsed && (
            <span style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
              <span className="rb-n">{role === "demo" ? "Every capability (demo)" : human(role)}</span>
              <div className="rb-s">{held(role)} capabilities</div>
            </span>
          )}
          {!collapsed && <Icon name="chev" size="sm" />}
        </button>
      </div>
    </aside>
  );
}

/** Nav is every declared view that is not a summary AND whose capability the
 *  caller holds, in the order the manifest listed them. A summary belongs to a
 *  thread, not to the sidebar. Nothing is keyed to a view id: a bundle that
 *  declares a fourth view gets a fourth entry with no change here.
 *
 *  The capability filter is the same rule the thread obeys: a thing you cannot
 *  do is absent, not drawn and then refused. Without it the laboratory drew
 *  "Turnaround today" for a technologist, who holds no `reporting.view`, and
 *  tapping it produced a 403 panel. `held` undefined means the caller is not
 *  known yet, and an unfiltered nav is better than an empty sidebar while
 *  /facility is in flight. */
export function navViews(cat: Catalogue | undefined, held?: string[]): ViewDecl[] {
  const all = cat?.views ?? {};
  const order = cat?.manifest?.views ?? Object.keys(all);
  const mine = held ? new Set(held) : null;
  const seen = new Set<string>();
  const out: ViewDecl[] = [];
  for (const id of [...order, ...Object.keys(all)]) {
    const v = all[id];
    if (!v || v.kind === "summary" || seen.has(id)) continue;
    if (mine && v.capability && !mine.has(v.capability)) continue;
    seen.add(id);
    out.push(v);
  }
  return out;
}

// -------------------------------------------------------------------- modal

/** A form opens over the conversation, never inside it, so that committing
 *  does not push the thread down the page. Esc closes, and so does the
 *  backdrop: neither writes anything. */
export function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="ov show" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      {children}
    </div>
  );
}

/** The right-hand drawer a summary view opens in. Same reason as the modal:
 *  the conversation stays where it was. */
export function Sheet({
  title: heading, onClose, children,
}: {
  title: string; onClose: () => void; children: React.ReactNode;
}) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="sheet show">
      <div className="sh-h">
        <div className="sh-t">
          <Icon name="eye" />
          {heading}
          <button className="icon-btn ml-auto" onClick={onClose} title="Close">✕</button>
        </div>
      </div>
      <div className="sh-b">{children}</div>
    </div>
  );
}
