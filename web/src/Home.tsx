/** Home: the shift, at a glance, from one read of each declared view.
 *
 *  Three bands, height-locked top to bottom: a 48px resume/facility band
 *  (never a greeting -- see ResumeBand below), a 60px live scale drawn as a
 *  ruler, then a single-column rack of full-width plates. Nothing here names
 *  a station, a flag or a bundle: point it at the laboratory kernel and it
 *  draws the laboratory's words.
 *
 *  A plate body is always one column, by construction (.stack/.plate in
 *  theme.css): two siblings can never sit side by side, so unequal height
 *  between them can never leave the dead column the two-up grid did.
 *
 *  Reorder is pointer events plus FLIP on transform, not HTML5 drag-and-drop
 *  (deleted outright -- it never fires on touch, never sets a real drag
 *  image, and the old dropOnto always spliced the source BEFORE the
 *  destination, which made every forward drag a silent no-op). One move()
 *  is shared by the pointer path and the keyboard path, so the swap-vs-splice
 *  divergence that bug lived in cannot exist here. Drag state lives in a
 *  ref, not useState, and ViewRenderer is memoised, so a pointer crossing
 *  moves pixels without re-rendering a single metric or task row.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { API_BASE, currentRole } from "./api";
import { Icon } from "./icons";
import type { Catalogue, QueueRow, ViewDecl, ViewResult } from "./types";
import { human, title } from "./ui";
import { shortId, toneOf, ViewRenderer } from "./ViewRenderer";
import type { Recent } from "./Shell";

type Loaded = { decl: ViewDecl; result: ViewResult };

// Per viewer, per facility: two kernels on two ports are two facilities, the
// same reason Shell.tsx keys Recents this way.
const ORDER_KEY = "phc.home.order." + API_BASE;
const RESUME_KEY = "resume." + API_BASE;
const EASE = "cubic-bezier(.2,0,0,1)";
const DUR_FLIP = 180;

function loadOrder(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/** Reconciles a saved order against the cards that actually exist this load:
 *  a saved id no card claims any more is dropped, and a card with no saved
 *  position is appended in the declared, default order. Because the id a
 *  card is keyed by is the declaration's own id (or "recent"), never
 *  anything drawn from the data inside it, a reseed that keeps the same
 *  declarations still resolves to the same order. */
function useCardOrder(ids: string[]): [string[], (next: string[]) => void] {
  const [order, setOrder] = useState<string[]>(() => reconcile(loadOrder(), ids));
  const key = ids.join(" ");
  useEffect(() => {
    // Reconciled against what is on disk, not against `prev`: `ids` often
    // arrives late (the queues and tasklists load asynchronously), so the
    // first render's `cardIds` can be empty. Reconciling an empty `prev`
    // against a saved order would treat the saved order as claiming nothing
    // and silently fall back to the declared default.
    setOrder(reconcile(loadOrder(), ids));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const persist = (next: string[]) => {
    setOrder(next);
    try {
      localStorage.setItem(ORDER_KEY, JSON.stringify(next));
    } catch {
      /* this session still holds the order in memory */
    }
  };
  return [order, persist];
}

function reconcile(saved: string[], ids: string[]): string[] {
  const known = new Set(ids);
  const kept = saved.filter((id) => known.has(id));
  const missing = ids.filter((id) => !kept.includes(id));
  return [...kept, ...missing];
}

/** The one reorder primitive, shared by the pointer path and the keyboard
 *  path so the swap-vs-splice divergence the old build had (moveBy swapped
 *  neighbours, dropOnto spliced) cannot come back. */
function move<T>(arr: T[], from: number, to: number): T[] {
  const next = arr.slice();
  next.splice(to, 0, next.splice(from, 1)[0]);
  return next;
}

type ResumeState = { label: string; hash: string };

function loadResume(): ResumeState | null {
  try {
    const raw = JSON.parse(localStorage.getItem(RESUME_KEY) || "null");
    if (raw && typeof raw.label === "string" && typeof raw.hash === "string") return raw;
  } catch {
    /* nothing to resume */
  }
  return null;
}

export function Home({
  cat, queues, dashboards, tasklists, recent, onOpenThread, onGo, titles,
}: {
  cat: Catalogue;
  queues: Loaded[];
  dashboards: Loaded[];
  tasklists: Loaded[];
  recent: Recent[];
  onOpenThread: (id: string) => void;
  onGo: (hash: string) => void;
  titles?: Record<string, string>;
}) {
  const first = queues[0];
  const rows = (first?.result.rows ?? []) as QueueRow[];
  const groups = (first?.result.groups ?? []).filter((g) => g.key !== null);
  const totalCount = groups.reduce((n, g) => n + g.count, 0);

  // The reorderable pool: every actual plate on the page, in the order the
  // bands declare by default. The live scale above is not in it: it is not a
  // plate, it is the ground the rest sit on.
  const cardIds = [
    ...dashboards.map((d) => d.decl.id),
    ...tasklists.map((t) => t.decl.id),
    ...(recent.length > 0 ? ["recent"] : []),
  ];
  const [order, persist] = useCardOrder(cardIds);

  const byId = (id: string) =>
    dashboards.find((d) => d.decl.id === id)
    ?? tasklists.find((t) => t.decl.id === id)
    ?? (id === "recent" ? "recent" : undefined);

  // Every thread Recents knows by id, so the Recent plate's own rows can draw
  // the same token stub a patient row anywhere else in the product does: the
  // rail's Recents list builds the identical lookup off the identical props
  // for the identical reason (Shell.tsx's shortId comment explains why that
  // is a second, deliberate copy rather than an import from here).
  const byThread = new Map<string, QueueRow>();
  for (const q of queues) for (const r of q.result.rows as QueueRow[]) byThread.set(r.thread, r);

  // The plate's own declared title, for the reorder announcement -- "Needs
  // you, position 2 of 4", not the declaration id turned into words.
  const plateTitles = new Map<string, string>();
  for (const d of dashboards) plateTitles.set(d.decl.id, d.decl.title ?? title(d.decl.id));
  for (const t of tasklists) plateTitles.set(t.decl.id, t.decl.title ?? title(t.decl.id));
  if (recent.length > 0) plateTitles.set("recent", "Recent");

  const reorder = useReorder(order, persist, plateTitles);

  return (
    <div className="home">
      <ResumeBand cat={cat} onGo={onGo} />
      <LiveScale first={first} rows={rows} groups={groups} totalCount={totalCount} />

      <div className="stack" ref={reorder.stackRef}>
        {order.map((id, index) => {
          const entry = byId(id);
          if (!entry) return null;
          const setPlateRef = reorder.plateRef(id);
          const setHandleRef = reorder.handleRef(id);
          const handleProps = reorder.handleProps(id, index);
          if (entry === "recent") {
            return (
              <Plate key="recent" plateTitle="Recent" rowCount={recent.length} setPlateRef={setPlateRef} setHandleRef={setHandleRef} handleProps={handleProps}>
                {recent.length ? (
                  <div className="plate-body">
                    {recent.map((t) => {
                      const row = byThread.get(t.id);
                      return (
                        <button key={t.id} type="button" className="plate-row qrow" onClick={() => onOpenThread(t.id)}>
                          <span className="stub">{row ? shortId(row.subject) : ""}</span>
                          <span className="qrow-name">{t.name}</span>
                          <span className="qrow-id">{t.id}</span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="plate-empty">No threads yet.</div>
                )}
              </Plate>
            );
          }
          const rowCount = (entry.result.rows as unknown[]).length;
          return (
            <Plate key={id} plateTitle={entry.decl.title ?? title(entry.decl.id)} rowCount={rowCount} setPlateRef={setPlateRef} setHandleRef={setHandleRef} handleProps={handleProps}>
              <ViewRenderer result={entry.result} titles={titles} onOpenThread={onOpenThread} maxRows={6} />
            </Plate>
          );
        })}
        <div className="drop-seam" ref={reorder.seamRef} />
      </div>

      <div aria-live="polite" className="sr-only" ref={reorder.announceRef} />
    </div>
  );
}

// --------------------------------------------------------------- band 1 ----

/** Height-locked at 48px forever, whether it carries a resume prompt or the
 *  facility/date/role line that fills the same 48px when there is nothing to
 *  resume: the point is that nothing below it ever moves either way. Nothing
 *  in this renderer writes RESUME_KEY yet (that needs a hook into the form
 *  surface, outside these three files); this reads it so the band is ready
 *  the day something does, and falls back honestly until then. */
function ResumeBand({ cat, onGo }: { cat: Catalogue; onGo: (hash: string) => void }) {
  const [resume, setResume] = useState<ResumeState | null>(loadResume);
  if (resume) {
    return (
      <div className="resume">
        <span className="resume-t">Resume · {resume.label}</span>
        <button type="button" className="resume-take" onClick={() => onGo(resume.hash)}>Take it</button>
        <button
          type="button"
          className="resume-x"
          aria-label="Dismiss resume"
          onClick={() => {
            try { localStorage.removeItem(RESUME_KEY); } catch { /* still clears the band this session */ }
            setResume(null);
          }}
        >
          ×
        </button>
      </div>
    );
  }
  const role = currentRole();
  const roleLabel = role === "demo" ? "Every capability (demo)" : human(role);
  return (
    <div className="resume">
      <span className="resume-t">{cat.manifest?.title ?? "Workspace"} · {dateLabel()} · {roleLabel}</span>
    </div>
  );
}

function dateLabel(): string {
  return new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" }).format(new Date());
}

// --------------------------------------------------------------- band 2 ----

/** A bar chart drawn as a ruler: each declared station a segment sized
 *  proportionally to its count, minimum 80px so a thin sliver never loses
 *  its own label, a zero-count station a 2px tick instead of nothing.
 *  Nothing here ticks: "as of Ns" reads the result's own generated_at once
 *  per render (a real refetch elsewhere moves it), not a setInterval -- the
 *  spec kills the one clock that would repaint every second on a screen that
 *  snaps everything else. */
function LiveScale({
  first, rows, groups, totalCount,
}: {
  first: Loaded | undefined;
  rows: QueueRow[];
  groups: { key: string | null; count: number }[];
  totalCount: number;
}) {
  if (!first) return <div className="scale" />;
  return (
    <div className="scale">
      <div className="scale-segs">
        {groups.map((g) => {
          const key = String(g.key);
          const here = rows.filter((r) => r.station === g.key || (r.flags ?? []).includes(key));
          const tone = worstTone(first.decl, here);
          const label = title(key) + (tone === "act" ? " · act now" : tone === "over" ? " over" : "");
          if (g.count === 0) {
            return (
              <div className="scale-seg scale-seg-zero" key={key}>
                <i className="scale-tick" />
                <div className="scale-seg-n">{title(key)}</div>
              </div>
            );
          }
          return (
            <div
              className="scale-seg"
              key={key}
              style={{ "--n": g.count } as React.CSSProperties}
              {...(tone ? { "data-over": "" } : {})}
              {...(tone === "act" ? { "data-act": "" } : {})}
            >
              <div className="scale-count">{g.count}</div>
              <div className="scale-seg-n">{label}</div>
            </div>
          );
        })}
        {totalCount === 0 && <div className="scale-empty">Nobody in the line.</div>}
      </div>
      <div className="scale-stale">as of {staleness(first.result.generated_at)}</div>
    </div>
  );
}

/** The worst tone among a station's own rows: any row past escalation makes
 *  the segment act; failing that, any row past target makes it over. Same
 *  colour law, same declared fields, applied to a group instead of a row --
 *  toneOf (ViewRenderer.tsx) is the one implementation both read. */
function worstTone(decl: Pick<ViewDecl, "target_minutes" | "escalate_minutes">, rows: QueueRow[]): "over" | "act" | null {
  let worst: "over" | "act" | null = null;
  for (const r of rows) {
    const t = toneOf(decl, r);
    if (t === "act") return "act";
    if (t === "over") worst = "over";
  }
  return worst;
}

function staleness(generatedAt: string | undefined): string {
  if (!generatedAt) return "just now";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(generatedAt).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  return `${minutes}m`;
}

// --------------------------------------------------------------- band 3 ----

/** One rack-mounted plate: a 44px header (handle, title, row count, at most
 *  one inline primary action) over whatever body its caller draws. The
 *  handle is a real <button>, absolutely positioned so it costs the header
 *  zero layout height, last in DOM order and visually first. No plate here
 *  gets a header-level primary action: a dashboard has nothing to commit to,
 *  a tasklist's own rows already carry theirs, and Recent opens by tapping
 *  the row -- the "View all" pattern the spec calls the abandonment
 *  archetype (a card reporting a state it cannot change) is deleted, not
 *  relocated. */
function Plate({
  plateTitle, rowCount, action, setPlateRef, setHandleRef, handleProps, children,
}: {
  plateTitle: string;
  rowCount: number;
  action?: React.ReactNode;
  setPlateRef: (el: HTMLDivElement | null) => void;
  setHandleRef: (el: HTMLButtonElement | null) => void;
  handleProps: React.ButtonHTMLAttributes<HTMLButtonElement>;
  children: React.ReactNode;
}) {
  return (
    <div className="plate" ref={setPlateRef}>
      <div className="plate-h">
        <span className="plate-t">{plateTitle}</span>
        <span className="plate-n">{rowCount}</span>
        {action}
        <button ref={setHandleRef} type="button" className="plate-handle" aria-label={`Reorder ${plateTitle}`} {...handleProps}>
          <Icon name="handle" size="sm" />
        </button>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------- the reorder ----
//
// Pointer events plus setPointerCapture, insert index from sibling
// midpoints (not from whatever the destination happens to be, which is the
// root cause of the old dropOnto's forward-drag no-op), FLIP on transform for
// the settle, and the identical move() for a keyboard press. Everything that
// changes on every pointer flicker -- which plate is lifted, where the
// insert point currently sits -- lives in a ref and in direct style writes on
// the DOM nodes themselves, never in useState: the only React state this
// touches is `order`, and only once an index actually changes, not once per
// pixel.
function useReorder(order: string[], persist: (next: string[]) => void, plateTitles: Map<string, string>) {
  const stackRef = useRef<HTMLDivElement | null>(null);
  const seamRef = useRef<HTMLDivElement | null>(null);
  const announceRef = useRef<HTMLDivElement | null>(null);
  const plateRefs = useRef(new Map<string, HTMLDivElement>());
  const handleRefs = useRef(new Map<string, HTMLButtonElement>());
  const focusOrigin = useRef(new Map<string, number>());
  const flipFirst = useRef<Record<string, DOMRect> | null>(null);
  const focusAfterFlip = useRef<string | null>(null);
  const drag = useRef<{
    id: string;
    pointerId: number;
    startIndex: number;
    startClientY: number;
    baseOrder: string[];
    heights: Record<string, number>;
    origTops: Record<string, number>;
    moved: boolean;
    currentIndex: number;
  } | null>(null);
  // A ref callback that changes identity every render makes React detach and
  // reattach it on every commit (a real cost during a drag, which re-renders
  // Home on every index crossing) -- these two caches hand out the SAME
  // function for a given id across renders, so React only ever attaches it
  // once and leaves it alone.
  const plateRefFns = useRef(new Map<string, (el: HTMLDivElement | null) => void>());
  const handleRefFns = useRef(new Map<string, (el: HTMLButtonElement | null) => void>());
  const plateRef = (id: string) => {
    let fn = plateRefFns.current.get(id);
    if (!fn) {
      fn = (el) => { if (el) plateRefs.current.set(id, el); else plateRefs.current.delete(id); };
      plateRefFns.current.set(id, fn);
    }
    return fn;
  };
  const handleRef = (id: string) => {
    let fn = handleRefFns.current.get(id);
    if (!fn) {
      fn = (el) => { if (el) handleRefs.current.set(id, el); else handleRefs.current.delete(id); };
      handleRefFns.current.set(id, fn);
    }
    return fn;
  };

  const announce = (id: string, index: number) => {
    const el = announceRef.current;
    if (el) el.textContent = `${plateTitles.get(id) ?? title(id)}, position ${index + 1} of ${order.length}`;
  };

  function reorder(from: number, to: number) {
    if (from === to || from < 0 || to < 0 || to >= order.length) return;
    const rects: Record<string, DOMRect> = {};
    for (const [id, el] of plateRefs.current) rects[id] = el.getBoundingClientRect();
    flipFirst.current = rects;
    focusAfterFlip.current = order[from];
    announce(order[from], to);
    persist(move(order, from, to));
  }

  useLayoutEffect(() => {
    const first = flipFirst.current;
    flipFirst.current = null;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (first) {
      for (const [id, el] of plateRefs.current) {
        const before = first[id];
        if (!before) continue;
        // "Last" has to be read AFTER the drag/preview transform is cleared,
        // not before: the FLIP rects were captured in reorder() while the
        // dragged plate's translate and every crossed sibling's preview
        // translate were still applied, so a "Last" read with those same
        // transforms still in effect is stale in the same way "First" is --
        // the two stale offsets cancel and dy collapses to a pure layout
        // delta with the actual visual offset thrown away, which is why the
        // release used to teleport into the new slot on frame 0 and animate
        // back from there instead of the other way around.
        el.style.transition = "none";
        el.style.transform = "";
        el.style.position = "";
        el.style.zIndex = "";
        el.style.boxShadow = "";
        el.style.willChange = "";
        const after = el.getBoundingClientRect();
        const dy = before.top - after.top;
        el.style.transform = dy ? `translate3d(0px, ${dy}px, 0)` : "";
      }
      if (reduced) {
        for (const [, el] of plateRefs.current) { el.style.transform = ""; el.style.transition = ""; }
      } else {
        requestAnimationFrame(() => {
          for (const [, el] of plateRefs.current) {
            el.style.transition = `transform ${DUR_FLIP}ms ${EASE}`;
            el.style.transform = "";
          }
        });
      }
    }
    if (focusAfterFlip.current) {
      handleRefs.current.get(focusAfterFlip.current)?.focus();
      focusAfterFlip.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order]);

  function computeTops(ids: string[], heights: Record<string, number>): Record<string, number> {
    let acc = 0;
    const tops: Record<string, number> = {};
    for (const id of ids) { tops[id] = acc; acc += heights[id] ?? 0; }
    return tops;
  }

  function onPointerDown(e: React.PointerEvent<HTMLButtonElement>, id: string) {
    if (e.button !== 0) return;
    const startIndex = order.indexOf(id);
    if (startIndex < 0) return;
    const heights: Record<string, number> = {};
    for (const [oid, el] of plateRefs.current) heights[oid] = el.getBoundingClientRect().height;
    drag.current = {
      id, pointerId: e.pointerId, startIndex, startClientY: e.clientY,
      baseOrder: order.slice(), heights, origTops: computeTops(order, heights),
      moved: false, currentIndex: startIndex,
    };
    try {
      (e.currentTarget as HTMLButtonElement).setPointerCapture(e.pointerId);
    } catch {
      /* a pointer the browser already released (or a synthetic id in a
         test) still leaves drag.current set above, and every other handler
         here reads that ref, not capture state -- so the gesture still
         works, it just stops receiving events if the pointer truly leaves
         the handle instead of following it through capture. */
    }
  }

  function onPointerMove(e: React.PointerEvent<HTMLButtonElement>, id: string) {
    const st = drag.current;
    if (!st || st.id !== id || st.pointerId !== e.pointerId) return;
    const dy = e.clientY - st.startClientY;
    if (!st.moved) {
      if (Math.abs(dy) < 4) return;
      st.moved = true;
      const el = plateRefs.current.get(id);
      if (el) {
        el.style.position = "relative";
        el.style.zIndex = "2";
        el.style.willChange = "transform";
        el.style.boxShadow = "0 2px 0 rgba(27,31,28,.10)";
      }
      stackRef.current?.setAttribute("data-dragging", id);
    }
    const draggedEl = plateRefs.current.get(id);
    if (draggedEl) draggedEl.style.transform = `translate3d(0px, ${dy}px, 0)`;

    const draggedHeight = st.heights[id] ?? 0;
    const draggedMid = st.origTops[id] + draggedHeight / 2 + dy;
    // Insert index from sibling MIDPOINTS: count how many others' original
    // midpoints the dragged plate's own (moving) midpoint has passed. Never
    // computed from the destination's own index -- that is the exact root
    // cause of the old dropOnto's forward-drag no-op.
    const others = st.baseOrder.filter((oid) => oid !== id);
    let idx = 0;
    for (const oid of others) {
      const mid = st.origTops[oid] + (st.heights[oid] ?? 0) / 2;
      if (draggedMid > mid) idx++;
    }
    if (idx !== st.currentIndex) {
      st.currentIndex = idx;
      const hypothetical = move(st.baseOrder, st.startIndex, idx);
      const newTops = computeTops(hypothetical, st.heights);
      for (const oid of st.baseOrder) {
        if (oid === id) continue;
        const el = plateRefs.current.get(oid);
        if (!el) continue;
        const shift = newTops[oid] - st.origTops[oid];
        el.style.transition = `transform ${DUR_FLIP}ms ${EASE}`;
        el.style.transform = shift ? `translate3d(0px, ${shift}px, 0)` : "";
      }
      positionSeam(hypothetical, st);
      announce(id, idx);
    }
  }

  function positionSeam(hypothetical: string[], st: NonNullable<typeof drag.current>) {
    const seam = seamRef.current;
    if (!seam) return;
    // Wherever the dragged plate would land in the hypothetical order is
    // exactly the top edge of the gap its siblings have already opened.
    const y = computeTops(hypothetical, st.heights)[st.id];
    seam.style.transform = `translate3d(0px, ${y}px, 0)`;
    seam.style.opacity = "1";
  }

  function endDrag(id: string) {
    const st = drag.current;
    if (!st || st.id !== id) return;
    drag.current = null;
    stackRef.current?.removeAttribute("data-dragging");
    if (seamRef.current) seamRef.current.style.opacity = "0";
    if (st.moved && st.currentIndex !== st.startIndex) {
      reorder(st.startIndex, st.currentIndex);
    } else {
      // A click, or a drag that returned to where it started: nothing to
      // persist, but the lift styling and any sibling preview still need to
      // clear, since no order change means no FLIP effect will run to do it.
      const el = plateRefs.current.get(id);
      if (el) { el.style.position = ""; el.style.zIndex = ""; el.style.willChange = ""; el.style.boxShadow = ""; el.style.transform = ""; }
      for (const oid of st.baseOrder) {
        if (oid === id) continue;
        const sib = plateRefs.current.get(oid);
        if (sib) sib.style.transform = "";
      }
    }
  }

  function onPointerUp(e: React.PointerEvent<HTMLButtonElement>, id: string) {
    if (drag.current?.pointerId !== e.pointerId) return;
    endDrag(id);
  }

  function onPointerCancel(e: React.PointerEvent<HTMLButtonElement>, id: string) {
    if (drag.current?.pointerId !== e.pointerId) return;
    const st = drag.current;
    drag.current = null;
    stackRef.current?.removeAttribute("data-dragging");
    if (seamRef.current) seamRef.current.style.opacity = "0";
    const el = plateRefs.current.get(id);
    if (el) { el.style.position = ""; el.style.zIndex = ""; el.style.willChange = ""; el.style.boxShadow = ""; el.style.transform = ""; }
    for (const oid of st.baseOrder) {
      const sib = plateRefs.current.get(oid);
      if (sib && oid !== id) sib.style.transform = "";
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLButtonElement>, id: string) {
    const i = order.indexOf(id);
    if (i < 0) return;
    if (e.key === "ArrowUp") { e.preventDefault(); reorder(i, Math.max(0, i - 1)); }
    else if (e.key === "ArrowDown") { e.preventDefault(); reorder(i, Math.min(order.length - 1, i + 1)); }
    else if (e.key === "Home") { e.preventDefault(); reorder(i, 0); }
    else if (e.key === "End") { e.preventDefault(); reorder(i, order.length - 1); }
    else if (e.key === "Escape") {
      const origin = focusOrigin.current.get(id);
      if (origin != null) { e.preventDefault(); reorder(i, origin); }
    }
  }

  return {
    stackRef, seamRef, announceRef, plateRef, handleRef,
    handleProps: (id: string, index: number): React.ButtonHTMLAttributes<HTMLButtonElement> => ({
      onPointerDown: (e) => onPointerDown(e, id),
      onPointerMove: (e) => onPointerMove(e, id),
      onPointerUp: (e) => onPointerUp(e, id),
      onPointerCancel: (e) => onPointerCancel(e, id),
      onKeyDown: (e) => onKeyDown(e, id),
      // Recorded once per focus "session", not on every re-render: a run of
      // ArrowUp presses refocuses the same handle after each move (so Escape
      // can find it later), and if that programmatic refocus overwrote the
      // origin every time, Escape would only ever undo the LAST keystroke
      // instead of the whole run back to where Tab first landed.
      onFocus: () => { if (!focusOrigin.current.has(id)) focusOrigin.current.set(id, index); },
      onBlur: () => focusOrigin.current.delete(id),
    }),
  };
}
