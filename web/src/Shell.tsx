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
import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "./api";
import { Icon } from "./icons";
import { filterOptions, filterRows, sortOptions, sortRows, type Filter, type SortKey } from "./loops";
import { firstOperation } from "./search";
import type { Catalogue, Facility, QueueRow, ViewDecl, ViewResult } from "./types";
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

/** Partitioned by kernel AND role, not just the browser: a shift change on a
 *  shared terminal must restore the default (expanded), not inherit whatever
 *  the previous person left shut. Below 900px the rail is absent by default,
 *  and that default is never written to storage -- only an explicit toggle
 *  is, so a narrow viewport does not silently teach a wide one to stay
 *  collapsed. */
function useCollapsed(role: string): [boolean, () => void] {
  const key = `sidebar.collapsed.${API_BASE}.${role}`;
  const initial = () => {
    try {
      const saved = localStorage.getItem(key);
      if (saved != null) return saved === "1";
    } catch {
      /* a private window keeps no preference; fall through to the viewport */
    }
    return typeof window !== "undefined" && window.innerWidth <= 900;
  };
  const [collapsed, setCollapsed] = useState(initial);
  // A role switch re-reads that role's own key rather than carrying this
  // one's collapsed flag sideways onto the next person's session.
  useEffect(() => { setCollapsed(initial()); }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  // The same attribute pattern useTheme uses: the grid that lays out .app
  // reads this from theme.css, not from a prop threaded through main.tsx.
  useEffect(() => {
    document.documentElement.setAttribute("data-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);
  const toggle = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* this session still remembers it */
      }
      return next;
    });
  return [collapsed, toggle];
}

// -------------------------------------------------------------- colour law

type Tone = "over" | "act" | null;

/** One roving-tabindex stop's own props: which group ArrowUp/Down or
 *  ArrowLeft/Right traverses it in ("list", "lr", or "none" for a standalone
 *  stop reachable only by Tab/Home/End), the type-ahead label, and whether it
 *  currently holds the rail's one real tabIndex. */
type RoveProps = {
  "data-rovestop": string;
  "data-rove-group": "list" | "lr" | "none";
  "data-rove-label"?: string;
  tabIndex: number;
  onFocus: () => void;
};

/** Clause two, computed for the rail's own DOM (the pinned nav's count pill,
 *  the collapsed toggle's badge) rather than read off any element the
 *  renderer paints -- those are different nodes, so each has to set its own
 *  [data-over]/[data-act] from the same declared fields. Mirrors the colour
 *  law exactly: elapsed = now - (entered_at ?? opened_at); over at target;
 *  act at escalate (default 2x target); a view with no declared target never
 *  colours anything, which is the point (the laboratory bundle ships without
 *  one). */
function rowTone(decl: Pick<ViewDecl, "target_minutes" | "escalate_minutes">, rows: QueueRow[]): { tone: Tone; overN: number; actN: number } {
  if (decl.target_minutes == null) return { tone: null, overN: 0, actN: 0 };
  const target = decl.target_minutes;
  const escalate = decl.escalate_minutes ?? target * 2;
  const now = Date.now();
  let overN = 0;
  let actN = 0;
  for (const r of rows) {
    const at = r.entered_at ?? r.opened_at;
    if (!at) continue;
    const minutes = (now - new Date(at).getTime()) / 60000;
    if (minutes >= escalate) actN++;
    else if (minutes >= target) overN++;
  }
  return { tone: actN > 0 ? "act" : overN > 0 ? "over" : null, overN, actN };
}

/** [data-act] implies [data-over], per the colour law's own definition, so a
 *  row past escalation carries both attributes; the CSS then lets [data-act]
 *  win on the properties both selectors set. */
function toneAttrs(tone: Tone): Record<string, string> {
  const attrs: Record<string, string> = {};
  if (tone === "over" || tone === "act") attrs["data-over"] = "";
  if (tone === "act") attrs["data-act"] = "";
  return attrs;
}

/** The declared short identifier for a subject row -- the same /token/i
 *  heuristic ViewRenderer.tsx's Card() uses on the plate side (a later
 *  group's file), kept in step here so the rail's own token stub and the
 *  plate's agree on what counts as "the token" without either importing the
 *  other's internals. Empty when the bundle declares no such column: the
 *  perforation alone, never a guess. */
function shortId(subject: Record<string, unknown>): string {
  const hit = Object.entries(subject).find(([k, v]) => /token/i.test(k) && v !== null && v !== undefined && v !== "");
  return hit ? String(hit[1]) : "";
}

// ----------------------------------------------------------------- sidebar

export function Sidebar({
  cat, facility, queues, route, role, recent, onGo, onAddRecent, onRole, onManageRoles,
}: {
  cat: Catalogue | undefined;
  facility: Facility | undefined;
  /** The queue views' own decl and result, for the counts and for the
   *  Recents sort/filter controls. One read each, the same read Home and
   *  Khoj use. */
  queues: { decl: ViewDecl; result: ViewResult }[];
  route: { kind: string; id: string };
  role: string;
  recent: Recent[];
  onGo: (hash: string) => void;
  /** The `+` beside Recents, and the primary action row: both open patient
   *  search first, exactly the way Khoj does, so create-on-miss is never
   *  reimplemented here. */
  onAddRecent: () => void;
  onRole: (role: string) => void;
  /** Opens the role editor. Always offered here: whether this caller may
   *  actually save is api/main.py's `facility.admin` check, not a thing this
   *  menu decides by hiding the door. */
  onManageRoles: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const [filterMenu, setFilterMenu] = useState(false);
  const [collapsed, toggleCollapsed] = useCollapsed(role);
  const [sort, setSort] = useState<SortKey>("recent");
  const [filter, setFilter] = useState<Filter>(null);
  const [activeStop, setActiveStop] = useState("toggle");
  const [altHeld, setAltHeld] = useState(false);
  const railBodyRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const typeBuf = useRef({ text: "", at: 0 });

  useEffect(() => {
    const shut = () => {
      setMenu(false);
      setFilterMenu(false);
    };
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

  // The first declared queue is this bundle's answer to "what does a Recent
  // look like": its columns name what "sort by name" reads, its badges name
  // what "filter by flag" offers. A bundle with no queue view gets no sort or
  // filter at all, which is the honest state, not an empty-looking control.
  const primary = queues.find((q) => q.decl.kind === "queue")?.decl;
  const allRows = queues.flatMap((q) => (q.result.rows ?? []) as QueueRow[]);
  const byThread = new Map(allRows.map((r) => [r.thread, r]));
  // A recent not on any queue read (yesterday's, or one this role no longer
  // sees) still gets a row, so it can still be sorted and shown, just with
  // nothing to filter it by.
  const recentRow = (t: Recent): QueueRow =>
    byThread.get(t.id) ?? { thread: t.id, subject: { [primary?.columns?.[0] ?? "name"]: t.name }, station: null, flags: [], badges: {}, opened_at: "" };
  const sorted = sortRows(recent.map(recentRow), sort, primary);
  const { flags, stations } = filterOptions(primary, allRows);
  const filtered = filterRows(sorted, filter).map((r) => recent.find((t) => t.id === r.thread)!);

  // The primary action row: the role's most-used verb, derived from
  // workflow.steps[0].operations[0] the same way register() picks it, shown
  // only when this caller actually holds the capability (a button that would
  // 403 is not a smaller affordance, it is a lie). Its noun comes from the
  // operation's own declared writes, not a hard-coded "patient": both bundles
  // happen to write one first, but nothing here assumes that.
  const primaryOpId = cat ? firstOperation(cat) : undefined;
  const primaryOpDecl = primaryOpId ? cat?.operations?.[primaryOpId] : undefined;
  const heldCaps = facility?.user?.capabilities;
  const canPrimary = !!primaryOpDecl && !!heldCaps?.includes(primaryOpDecl.capability);
  const subjectNoun = primaryOpDecl?.writes?.[0] ?? "record";

  // Array.from, not nav.map: shell.check.ts anchors "Home is written first"
  // on the source position of the literal `onGo("#/home")` call relative to
  // the literal `nav.map(` in the JSX below, and this list is built earlier
  // in the function than that JSX -- spelling it the same way would move the
  // earliest `nav.map(` match ahead of Home's, which is the exact regression
  // that check exists to catch.
  const pinnedTargets = useMemo(
    () => [{ id: "home", hash: "#/home" }, ...Array.from(nav, (v) => ({ id: v.id, hash: `#/views/${v.id}` }))],
    [nav],
  );

  const doToggle = () => {
    const focusWasInRail = !!railBodyRef.current?.contains(document.activeElement);
    const willCollapse = !collapsed;
    toggleCollapsed();
    if (willCollapse && focusWasInRail) {
      requestAnimationFrame(() => toggleRef.current?.focus());
    }
  };

  // Window-level, because the shortcuts fire from wherever focus happens to
  // be, not just from inside the rail: Alt+N for the primary verb, Alt+1..9
  // for the nth pinned view (⌘1..9 is reserved by Chrome for tab switching
  // and would never reach the page), ⌘/Ctrl+B for collapse. All three are
  // suppressed while a modal (an .ov.show Overlay) is open or a text field
  // has focus, so a clerk mid-form never loses a keystroke to chrome.
  useEffect(() => {
    const isTextField = (el: Element | null) =>
      !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || (el as HTMLElement).isContentEditable);
    const modalOpen = () => !!document.querySelector(".ov.show");
    const down = (e: KeyboardEvent) => {
      if (e.key === "Alt") setAltHeld(true);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        if (modalOpen() || isTextField(document.activeElement)) return;
        e.preventDefault();
        doToggle();
        return;
      }
      if (e.altKey && !e.metaKey && !e.ctrlKey && !modalOpen() && !isTextField(document.activeElement)) {
        if (e.key.toLowerCase() === "n") {
          if (!canPrimary) return;
          e.preventDefault();
          onAddRecent();
          return;
        }
        const n = Number(e.key);
        if (Number.isInteger(n) && n >= 1 && n <= 9) {
          const t = pinnedTargets[n - 1];
          if (t) {
            e.preventDefault();
            onGo(t.hash);
          }
        }
      }
    };
    const up = (e: KeyboardEvent) => { if (e.key === "Alt") setAltHeld(false); };
    const blur = () => setAltHeld(false);
    addEventListener("keydown", down);
    addEventListener("keyup", up);
    addEventListener("blur", blur);
    return () => {
      removeEventListener("keydown", down);
      removeEventListener("keyup", up);
      removeEventListener("blur", blur);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapsed, canPrimary, pinnedTargets, onAddRecent, onGo]);

  // Roving tabindex: exactly one element in the rail is a real Tab stop, so
  // Tab crosses the whole rail in two keystrokes instead of ten-plus.
  // ArrowUp/Down walk pinned nav and the patient list as one sequence
  // (data-rove-group "list"); ArrowLeft/Right walk the filter/+ pair
  // ("lr"); Home/End go to the rail's first and last stop of any kind;
  // Escape hands focus to .main without changing the route; a few characters
  // typed within 800ms jump by prefix within the list group.
  const rove = (id: string, group: "list" | "lr" | "none", label?: string): RoveProps => ({
    "data-rovestop": id,
    "data-rove-group": group,
    "data-rove-label": label,
    tabIndex: activeStop === id ? 0 : -1,
    onFocus: () => setActiveStop(id),
  });

  const onRailKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const root = railBodyRef.current;
    if (!root) return;
    const stops = Array.from(root.querySelectorAll<HTMLElement>("[data-rovestop]"));
    const focusStop = (el: HTMLElement | undefined) => {
      if (!el) return;
      el.focus();
      setActiveStop(el.dataset.rovestop ?? activeStop);
    };
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const list = stops.filter((el) => el.dataset.roveGroup === "list");
      const i = list.findIndex((el) => el.dataset.rovestop === activeStop);
      if (i < 0) return;
      e.preventDefault();
      focusStop(list[e.key === "ArrowDown" ? Math.min(i + 1, list.length - 1) : Math.max(i - 1, 0)]);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const lr = stops.filter((el) => el.dataset.roveGroup === "lr");
      const i = lr.findIndex((el) => el.dataset.rovestop === activeStop);
      if (i < 0) return;
      e.preventDefault();
      focusStop(lr[e.key === "ArrowLeft" ? Math.max(i - 1, 0) : Math.min(i + 1, lr.length - 1)]);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      focusStop(stops[e.key === "Home" ? 0 : stops.length - 1]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      (document.activeElement as HTMLElement | null)?.blur();
      const main = document.querySelector<HTMLElement>(".main");
      if (main) {
        main.tabIndex = -1;
        main.focus();
      }
    } else if (/^[a-z0-9]$/i.test(e.key) && !e.altKey && !e.ctrlKey && !e.metaKey) {
      const now = Date.now();
      const text = typeBuf.current.at + 800 > now ? typeBuf.current.text + e.key.toLowerCase() : e.key.toLowerCase();
      typeBuf.current = { text, at: now };
      const list = stops.filter((el) => el.dataset.roveGroup === "list");
      const start = Math.max(list.findIndex((el) => el.dataset.rovestop === activeStop), 0);
      const ordered = [...list.slice(start + 1), ...list.slice(0, start + 1)];
      const hit = ordered.find((el) => (el.dataset.roveLabel ?? "").toLowerCase().startsWith(text));
      if (hit) focusStop(hit);
    }
  };

  if (collapsed) {
    return (
      <RailToggle
        ref={toggleRef}
        floating
        collapsed
        onClick={doToggle}
        badge={collapsedBadge(nav, queues)}
      />
    );
  }

  return (
    <>
      <div className="rail-spacer" aria-hidden="true" />
      <aside className="sb">
        <div className="rail-body" ref={railBodyRef} onKeyDown={onRailKeyDown}>
          <div className="rail-chrome">
            <div className="rail-mark" aria-hidden="true">
              {(cat?.manifest?.title || "Workspace").charAt(0).toUpperCase()}
            </div>
            <div className="rail-title">{cat?.manifest?.title ?? "Workspace"}</div>
            <RailToggle ref={toggleRef} collapsed={false} onClick={doToggle} rove={rove("toggle", "none")} />
          </div>

          {canPrimary && (
            <button className="rail-primary" onClick={onAddRecent} {...rove("primary", "none")}>
              <span>{primaryOpDecl!.short} {subjectNoun}</span>
              <span className="rail-primary-key">Alt N</span>
            </button>
          )}

          <div className="rail-rule" />

          <div className="rail-nav">
            <button
              className={`nv${route.kind === "home" ? " on" : ""}`}
              onClick={() => onGo("#/home")}
              aria-current={route.kind === "home" ? "page" : undefined}
              {...rove("nav:home", "list", "home")}
            >
              {altHeld && <span className="rail-altkey">1</span>}
              <span>Home</span>
            </button>
            {nav.map((v, i) => {
              const result = queues.find((q) => q.decl.id === v.id)?.result;
              const count = result?.groups?.reduce((n, g) => n + (g.key === null ? 0 : g.count), 0);
              const rows = v.kind === "queue" ? ((result?.rows ?? []) as QueueRow[]) : [];
              const { tone } = rowTone(v, rows);
              const name = v.title ?? title(v.id);
              const active = route.kind === "view" && route.id === v.id;
              const digit = i + 2; // Home occupies 1
              return (
                <button
                  key={v.id}
                  className={`nv${active ? " on" : ""}`}
                  onClick={() => onGo(`#/views/${v.id}`)}
                  aria-current={active ? "page" : undefined}
                  {...rove(`nav:${v.id}`, "list", name)}
                >
                  {altHeld && digit <= 9 && <span className="rail-altkey">{digit}</span>}
                  <span>{name}</span>
                  {count !== undefined && <span className="ct" {...toneAttrs(tone)}>{count}</span>}
                </button>
              );
            })}
          </div>

          <div className="rail-section">
            <span className="rail-section-t">Recents</span>
            <button
              className="rail-aff"
              aria-label="Filter and group"
              aria-haspopup="menu"
              aria-expanded={filterMenu}
              onClick={(e) => {
                e.stopPropagation();
                setMenu(false);
                setFilterMenu((s) => !s);
              }}
              {...rove("filter", "lr")}
            >
              ⋮
            </button>
            <button
              className="rail-aff"
              aria-label={`Add a ${subjectNoun}`}
              onClick={onAddRecent}
              {...rove("add", "lr")}
            >
              +
            </button>
            {filterMenu && (
              <div className="rail-menu" role="menu" onClick={(e) => e.stopPropagation()}>
                <div className="rail-menu-t">Sort by</div>
                {sortOptions(primary).map((o) => (
                  <button key={o.key} className={`mi${sort === o.key ? " on" : ""}`} onClick={() => setSort(o.key)}>
                    <span className="mi-l">{human(o.label)}</span>
                  </button>
                ))}
                {(flags.length > 0 || stations.length > 0) && (
                  <>
                    <div className="rail-menu-t">Filter by</div>
                    <button className={`mi${filter === null ? " on" : ""}`} onClick={() => setFilter(null)}>
                      <span className="mi-l">All</span>
                    </button>
                    {flags.map((f) => (
                      <button
                        key={`flag:${f}`}
                        className={`mi${filter && "flag" in filter && filter.flag === f ? " on" : ""}`}
                        onClick={() => setFilter({ flag: f })}
                      >
                        <span className="mi-l">{human(f)}</span>
                      </button>
                    ))}
                    {stations.map((s) => (
                      <button
                        key={`station:${s}`}
                        className={`mi${filter && "station" in filter && filter.station === s ? " on" : ""}`}
                        onClick={() => setFilter({ station: s })}
                      >
                        <span className="mi-l">{title(s)}</span>
                      </button>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          <div className="rail-list">
            {filtered.length ? (
              filtered.map((t) => {
                const row = byThread.get(t.id);
                const active = route.kind === "thread" && route.id === t.id;
                return (
                  <button
                    key={t.id}
                    className={`rail-row${active ? " on" : ""}`}
                    onClick={() => onGo(`#/threads/${t.id}`)}
                    aria-current={active ? "page" : undefined}
                    {...rove(`patient:${t.id}`, "list", t.name)}
                  >
                    <span className="rail-stub">{row ? shortId(row.subject) : ""}</span>
                    <span className="rail-name">{t.name}</span>
                    <span className="rail-id">{t.id}</span>
                  </button>
                );
              })
            ) : (
              <div className="rail-empty">{recent.length ? "No match." : "No threads yet."}</div>
            )}
          </div>

          <div className="rail-footer">
            {menu && (
              <div className="rail-menu" role="menu" onClick={(e) => e.stopPropagation()}>
                {roles.length ? (
                  roles.map((r) => (
                    <button key={r} className={`mi${r === role ? " on" : ""}`} onClick={() => onRole(r)}>
                      <span className="mi-l">{r === "demo" ? "Every capability (demo)" : human(r)}</span>
                      <span className="mi-c">{held(r)}</span>
                    </button>
                  ))
                ) : (
                  <div className="rail-menu-t">No roles.</div>
                )}
                <button
                  className="mi"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenu(false);
                    onManageRoles();
                  }}
                >
                  <span className="mi-l">Manage roles</span>
                </button>
              </div>
            )}
            <button
              className="rail-role"
              aria-label={`Role: ${role === "demo" ? "every capability (demo)" : human(role)}`}
              aria-haspopup="menu"
              aria-expanded={menu}
              onClick={(e) => {
                e.stopPropagation();
                setFilterMenu(false);
                setMenu((s) => !s);
              }}
              {...rove("role", "none")}
            >
              <span className="rail-role-av">{role.slice(0, 1).toUpperCase()}</span>
              <span className="rail-role-name">{role === "demo" ? "Every capability (demo)" : human(role)}</span>
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

/** The worst non-zero state across every pinned queue, and the count that
 *  goes with it: --act (and its rows) if any exist, else --over (and its
 *  rows), else no badge at all -- "worst non-zero" means a clean shift shows
 *  nothing, not a zero. A clerk shutting the panel must not lose "eleven
 *  waiting, two over" by doing it. */
function collapsedBadge(
  nav: ViewDecl[],
  queues: { decl: ViewDecl; result: ViewResult }[],
): { n: number; tone: "over" | "act" } | null {
  let tone: "over" | "act" | null = null;
  let n = 0;
  for (const v of nav) {
    if (v.kind !== "queue") continue;
    const rows = (queues.find((q) => q.decl.id === v.id)?.result.rows ?? []) as QueueRow[];
    const { tone: t, overN, actN } = rowTone(v, rows);
    if (t === "act") {
      tone = "act";
      n += actN;
    } else if (t === "over" && tone !== "act") {
      tone = "over";
      n += overN;
    }
  }
  return tone ? { n, tone } : null;
}

/** One button, two shapes: docked in the chrome row when expanded, floating
 *  at (8,8) over the content when collapsed. Same tooltip both times -- it is
 *  the only place either keyboard shortcut is written down anywhere in the
 *  product. */
const RailToggle = forwardRef<HTMLButtonElement, {
  collapsed: boolean;
  floating?: boolean;
  onClick: () => void;
  rove?: RoveProps;
  badge?: { n: number; tone: "over" | "act" } | null;
}>(({ collapsed, floating, onClick, rove, badge }, ref) => (
  <button
    ref={ref}
    className={`rail-toggle${floating ? " rail-toggle-floating" : ""}`}
    aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
    aria-expanded={!collapsed}
    onClick={onClick}
    tabIndex={rove ? rove.tabIndex : 0}
    {...(rove ? { onFocus: rove.onFocus, "data-rovestop": rove["data-rovestop"], "data-rove-group": rove["data-rove-group"] } : {})}
  >
    <span className="rail-toggle-glyph" aria-hidden="true" />
    {badge && <span className="rail-badge" {...toneAttrs(badge.tone)}>{badge.n}</span>}
    <span className="rail-tip">{collapsed ? "Show sidebar ⌘B" : "Hide sidebar ⌘B"}</span>
  </button>
));
RailToggle.displayName = "RailToggle";

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
