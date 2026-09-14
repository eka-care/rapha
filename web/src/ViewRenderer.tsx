/** The view renderer. Given a ViewResult it draws it. There are three kinds
 *  and one entry point, because contracts.View is one dataclass with a kind.
 *
 *  It contains no screen. A queue of patients by station and a queue of
 *  samples by bench are the same code; the difference is the declaration.
 *
 *  Memoised (Vernier step 10): Home's pointer-driven reorder changes its own
 *  `order` state on every plate boundary crossed, which re-renders Home and
 *  every <Card>/<ViewRenderer> underneath it. Without memo, that re-runs
 *  QueueView/Dashboard/TaskList's own row-building work every time a card
 *  merely changes position, for a re-render whose props (`result`, `titles`,
 *  `onOpenThread`) never actually changed. `React.memo` makes a pointer
 *  crossing cost nothing here; the crossing is still visible via the
 *  imperative FLIP transform Home applies directly to the DOM.
 */
import { memo, useState } from "react";
import type { AuditRecord, MetricValue, Operation, Proposal, QueueRow, SectionResult, StepStatus, TaskRow, ViewDecl, ViewResult } from "./types";
import { Badge, Empty, human, title } from "./ui";

function ViewRendererImpl({
  result, titles, onOpenThread, onAction, onReview, decl, maxRows,
}: {
  result: ViewResult;
  /** Declaration id to human title, for anything the result names by id but
   *  does not label: metrics, today. The declarations carry the words. */
  titles?: Record<string, string>;
  onOpenThread?: (thread: string) => void;
  onAction?: (op: Operation) => void;
  onReview?: (p: Proposal) => void;
  /** The colour law's declared thresholds live on the view's own decl, not
   *  on the result. Optional: a caller with only a result (no decl at hand)
   *  still renders, just without a wait rule -- the same fallback the law
   *  itself specifies for a bundle that declares no target. */
  decl?: Pick<ViewDecl, "target_minutes" | "escalate_minutes">;
  /** Home's plate body caps at six rows, then a 32px "+N more" row that
   *  expands in place; a dedicated full-page view (reached from the rail,
   *  not embedded in a plate) shows everything. Only Dashboard and TaskList
   *  read this: a plate never embeds a queue. */
  maxRows?: number;
}) {
  if (result.kind === "queue") return <QueueView result={result} decl={decl} onOpenThread={onOpenThread} />;
  if (result.kind === "dashboard") return <Dashboard rows={result.rows as MetricValue[]} titles={titles} maxRows={maxRows} />;
  if (result.kind === "summary") {
    return <Sections sections={result.rows as SectionResult[]} onAction={onAction} onReview={onReview} />;
  }
  if (result.kind === "tasklist") {
    return <TaskList rows={result.rows as TaskRow[]} onOpenThread={onOpenThread} maxRows={maxRows} />;
  }
  return <Empty>No renderer for a <b>{result.kind}</b> view.</Empty>;
}

export const ViewRenderer = memo(ViewRendererImpl);

// ---------------------------------------------------------- the colour law --
//
// The one place in the renderer that turns a declared threshold plus a row's
// own timestamp into the wait rule's fill and [data-over]/[data-act]. Mirrors
// Shell.tsx's rowTone exactly (elapsed = now - (entered_at ?? opened_at); over
// at target; act at escalate, default 2x target) -- that file carries its own
// copy for the rail's nav counts and collapsed badge (sites 4 and 5 of the
// colour law), which are different DOM nodes than any row this file draws and
// cannot share a React tree with them; Home.tsx imports these instead of
// reimplementing them a third time, so there is exactly one implementation of
// "what tone is this row" for every row a subject actually appears in.
export type Tone = "over" | "act" | null;

function elapsedMinutes(row: { entered_at?: string | null; opened_at?: string }): number | null {
  const at = row.entered_at ?? row.opened_at;
  if (!at) return null;
  const ms = Date.now() - new Date(at).getTime();
  return Number.isFinite(ms) ? ms / 60000 : null;
}

export function toneOf(
  decl: Pick<ViewDecl, "target_minutes" | "escalate_minutes"> | undefined,
  row: { entered_at?: string | null; opened_at?: string },
): Tone {
  if (decl?.target_minutes == null) return null;
  const minutes = elapsedMinutes(row);
  if (minutes == null) return null;
  const escalate = decl.escalate_minutes ?? decl.target_minutes * 2;
  if (minutes >= escalate) return "act";
  if (minutes >= decl.target_minutes) return "over";
  return null;
}

/** The wait rule's own style+attributes for one row, given the tone it has
 *  already been assigned (which may have been demoted by an act budget --
 *  see QueueView below -- so this never recomputes tone itself). --t is the
 *  elapsed/target fraction, clamped to 1: once a row is over, its bar is
 *  already full width and only its colour still moves. */
function waitAttrs(
  decl: Pick<ViewDecl, "target_minutes" | "escalate_minutes"> | undefined,
  row: { entered_at?: string | null; opened_at?: string },
  tone: Tone,
): React.HTMLAttributes<HTMLElement> & { "data-over"?: string; "data-act"?: string } {
  if (decl?.target_minutes == null) return {};
  const minutes = elapsedMinutes(row);
  if (minutes == null) return {};
  const t = Math.min(1, minutes / decl.target_minutes);
  const attrs: React.HTMLAttributes<HTMLElement> & { "data-over"?: string; "data-act"?: string } =
    { style: { "--t": t } as React.CSSProperties };
  if (tone === "over" || tone === "act") attrs["data-over"] = "";
  if (tone === "act") attrs["data-act"] = "";
  return attrs;
}

/** The age cell's own word, so colour is never the only channel: "18m over"
 *  for amber, "41m · act now" for red, a plain "6m" otherwise. Null when
 *  the row carries no timestamp at all (nothing to read back). */
function ageLabel(row: { entered_at?: string | null; opened_at?: string }, tone: Tone): string | null {
  const minutes = elapsedMinutes(row);
  if (minutes == null) return null;
  const m = Math.max(0, Math.round(minutes));
  if (tone === "act") return `${m}m · act now`;
  if (tone === "over") return `${m}m over`;
  return `${m}m`;
}

/** The declared short identifier for a subject row. There is no separate
 *  "short id column" field on ViewDecl (an additive contract change nobody
 *  has needed yet), so this is the same /token/i heuristic Shell.tsx's own
 *  shortId carries for the rail -- kept in step here rather than imported so
 *  neither file reaches into the other's internals, the same call that
 *  file's own comment documents. Home.tsx imports THIS copy for its own
 *  subject rows (the Recent plate), so within the renderer itself there is
 *  exactly one implementation, not a third fork of it. */
export function shortId(subject: Record<string, unknown>): string {
  const hit = Object.entries(subject).find(([k, v]) => /token/i.test(k) && v !== null && v !== undefined && v !== "");
  return hit ? String(hit[1]) : "";
}

// ------------------------------------------------------- plate row cap ----

/** Home layout, band 3: "six rows maximum, then a 32px '+14 more' row that
 *  expands in place." One hook for both row-producing kinds so the cap and
 *  its expand button exist in exactly one place. `maxRows` unset (a
 *  full-page view, not a plate) shows everything. */
function useRowCap(total: number, maxRows?: number) {
  const [expanded, setExpanded] = useState(false);
  const capped = maxRows != null && !expanded && total > maxRows;
  const limit = capped ? maxRows : total;
  const hidden = capped ? total - maxRows! : 0;
  return { limit, hidden, expand: () => setExpanded(true) };
}

function MoreRow({ hidden, onExpand }: { hidden: number; onExpand: () => void }) {
  if (hidden <= 0) return null;
  return (
    <button type="button" className="plate-more" onClick={onExpand}>+{hidden} more</button>
  );
}

// -------------------------------------------------------------- tasklist ----

/** A row is a title and a count, per the declaration's own copy rule: nothing
 *  here invents prose. `operation` present makes the row actionable, which
 *  here means opening the first matching thread, where that operation is
 *  drawn like any other; absent, it is a worklist with nowhere to tap.
 *
 *  No token stub here: a TaskRow is a count across many threads, not one
 *  subject, and no entered_at either, so it carries no wait rule -- both
 *  would be invented information the kernel never sent. */
function TaskList({ rows, onOpenThread, maxRows }: { rows: TaskRow[]; onOpenThread?: (t: string) => void; maxRows?: number }) {
  if (!rows.length) return <Empty>Nothing declared for this list.</Empty>;
  const { limit, hidden, expand } = useRowCap(rows.length, maxRows);
  return (
    <div className="tasklist">
      {rows.slice(0, limit).map((r) => (
        <div className="plate-row task-row" key={r.title}>
          <div className="task-t">{r.title}</div>
          <div className="task-n">{r.count}</div>
          {r.operation && r.count > 0 && (
            <button className="cq" onClick={() => onOpenThread?.(r.threads[0])}>Open</button>
          )}
        </div>
      ))}
      <MoreRow hidden={hidden} onExpand={expand} />
    </div>
  );
}

// ---------------------------------------------------------------- queue ----

/** Grafts item 3's fix, rendered: over-threshold rows sort to the top of an
 *  unambiguous vertical list (the 2x2/auto-fill grid this replaced is exactly
 *  what would have made that position ambiguous). Stable beyond tone: two
 *  rows of the same tone keep their original order. */
function sortByTone(rows: QueueRow[], decl?: Pick<ViewDecl, "target_minutes" | "escalate_minutes">): { row: QueueRow; tone: Tone }[] {
  const rank = (t: Tone) => (t === "act" ? 0 : t === "over" ? 1 : 2);
  return rows
    .map((row, i) => ({ row, i, tone: toneOf(decl, row), minutes: elapsedMinutes(row) ?? -1 }))
    // Within the same tone, the longest-waiting row sorts first -- the one
    // act slot the budget below allows is the most overdue row, not merely
    // whichever the API happened to list first; two rows of equal wait keep
    // their original order (stable).
    .sort((a, b) => rank(a.tone) - rank(b.tone) || b.minutes - a.minutes || a.i - b.i)
    .map(({ row, tone }) => ({ row, tone }));
}

/** The act budget: one act element per plate, full stop. The rest are still
 *  exactly as over-threshold (still sorted up, still carry [data-over] and
 *  their own true "Nm over" reading), they are simply not the second red
 *  element on the same screen -- the header's own "+N act now" is where they
 *  are counted, never a hidden row. Returns the demoted tone per row and the
 *  true act total for that header line. */
function budgetAct(decorated: { row: QueueRow; tone: Tone }[]): { row: QueueRow; tone: Tone; shown: Tone }[] {
  let used = 0;
  return decorated.map(({ row, tone }) => {
    if (tone !== "act") return { row, tone, shown: tone };
    used += 1;
    return { row, tone, shown: used === 1 ? "act" : "over" };
  });
}

function QueueView({
  result, decl, onOpenThread,
}: {
  result: ViewResult;
  decl?: Pick<ViewDecl, "target_minutes" | "escalate_minutes">;
  onOpenThread?: (t: string) => void;
}) {
  const rows = result.rows as QueueRow[];
  const groups = result.groups ?? [];
  const [tab, setTab] = useState("all");

  // A row belongs to a group by station or by flag, whichever the view grouped
  // on. A thread that has finished its line has no station, and the server
  // groups those under a null key. If some server instead names that group,
  // the orphan fallback below finds it: the one group with a count that no row
  // claimed is where the finished threads went.
  const DONE = "\u0000done";                       // a tab id null cannot be
  const idOf = (key: string | null) => key ?? DONE;
  const inGroup = (r: QueueRow, key: string) =>
    key === DONE ? r.station === null : r.station === key || r.flags.includes(key);

  const groupIds = groups.map((g) => idOf(g.key as string | null));
  const loose = rows.filter((r) => !groupIds.some((k) => inGroup(r, k)));
  const orphan = loose.length
    ? groups.find((g) => g.count > 0 && !rows.some((r) => inGroup(r, idOf(g.key as string | null))))
    : undefined;
  const holds = (r: QueueRow, key: string) =>
    inGroup(r, key) || (orphan !== undefined && key === idOf(orphan.key as string | null) && loose.includes(r));

  const tabs: [string, string, number][] = [
    ["all", "All", rows.length],
    ...groups.map((g) => {
      const id = idOf(g.key as string | null);
      return [id, id === DONE ? "Complete" : title(id), g.count] as [string, string, number];
    }),
    ...(loose.length && !orphan ? ([["_loose", "Complete", loose.length]] as [string, string, number][]) : []),
  ];
  const list = tab === "all" ? rows : tab === "_loose" ? loose : rows.filter((r) => holds(r, tab));

  const budgeted = budgetAct(sortByTone(list, decl));
  const actTotal = budgeted.filter((b) => b.tone === "act").length;

  return (
    <>
      {tabs.length > 1 && (
        <div className="qtabs">
          {tabs.map(([k, label, n]) => (
            <button key={k} className={`qtab${tab === k ? " on" : ""}`} onClick={() => setTab(k)}>
              {label}
              <span className="n">{n}</span>
            </button>
          ))}
        </div>
      )}
      {actTotal > 1 && (
        <div className="qact" data-act>+{actTotal - 1} act now</div>
      )}
      {budgeted.length ? (
        <div className="plate standalone qlist">
          {budgeted.map(({ row, shown }) => <Card key={row.thread} row={row} decl={decl} tone={shown} onOpen={onOpenThread} />)}
        </div>
      ) : (
        <Empty>Nobody here.</Empty>
      )}
    </>
  );
}

/** One subject row: the token stub, the name, the rest of the declared
 *  columns, the age cell (colour law's word channel) and the wait rule
 *  (colour law's length channel), in that order. The columns are whatever
 *  the view declared, so the row cannot hard-code them: the first stringy
 *  column is the headline, the rest sit beside it. */
function Card({
  row, decl, tone, onOpen,
}: {
  row: QueueRow;
  decl?: Pick<ViewDecl, "target_minutes" | "escalate_minutes">;
  tone: Tone;
  onOpen?: (t: string) => void;
}) {
  const cols = Object.entries(row.subject).filter(([, v]) => v !== null && v !== undefined && v !== "");
  const headIdx = Math.max(0, cols.findIndex(([k, v]) => k === "name" || typeof v === "string"));
  const head = cols[headIdx] ? String(cols[headIdx][1]) : row.thread;
  const tok = shortId(row.subject);
  const rest = cols
    .filter(([k], i) => i !== headIdx && !/token/i.test(k))
    .map(([, v]) => String(v));
  const age = ageLabel(row, tone);

  return (
    <button className="plate-row qrow" onClick={() => onOpen?.(row.thread)} {...waitAttrs(decl, row, tone)}>
      <span className="stub">{tok}</span>
      <span className="qrow-name">
        {head}
        {rest.length > 0 && <span className="qrow-rest"> · {rest.join(" · ")}</span>}
      </span>
      {age && <span className="qrow-age">{age}</span>}
      <span className="qrow-chips">
        <Badge style="blue">{row.station ? human(row.station) : "Complete"}</Badge>
        {Object.entries(row.badges ?? {}).map(([flag, style]) => (
          <Badge key={flag} style={style}>{human(flag)}</Badge>
        ))}
      </span>
    </button>
  );
}

// -------------------------------------------------------------- summary ----

export function Sections({
  sections, onAction, onReview,
}: {
  sections: SectionResult[];
  onAction?: (op: Operation) => void;
  onReview?: (p: Proposal) => void;
}) {
  return (
    <div className="secgrid">
      {sections.map((s) => (
        <div className="card" key={s.title}>
          <div className="card-h">
            <div className="card-t">{s.title}</div>
            <span className="badge b-mute">{s.rows?.length ?? 0}</span>
          </div>
          <div className="secbody">
            <SectionRows section={s} onAction={onAction} onReview={onReview} />
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionRows({
  section, onAction, onReview,
}: {
  section: SectionResult;
  onAction?: (op: Operation) => void;
  onReview?: (p: Proposal) => void;
}) {
  const rows = section.rows ?? [];
  if (!rows.length) return <div className="f-hint">Nothing yet.</div>;

  switch (section.show ?? sniff(rows[0])) {
    case "line":
      return <Line line={rows as StepStatus[]} />;
    case "flags":
      return (
        <div className="caps">
          {(rows as string[]).map((f) => <span className="cap on" key={f}>{f}</span>)}
        </div>
      );
    case "actions":
      return (
        <div className="cbar wrap">
          {(rows as Operation[]).map((op) => (
            <button key={op.id} className="cq" title={op.summary} onClick={() => onAction?.(op)}>
              {op.irreversibility === "irreversible" && "! "}{op.short}
            </button>
          ))}
        </div>
      );
    case "proposals":
      return <>{(rows as Proposal[]).map((p) => <ProposalRow key={p.id} p={p} onReview={onReview} />)}</>;
    case "audit":
      return <>{(rows as AuditRecord[]).map((a) => <AuditRow key={a.id} a={a} />)}</>;
    default:
      return <Table rows={rows as Record<string, unknown>[]} />;
  }
}

/** contracts.Section says which kernel structure a section shows, but the API
 *  is entitled to send only the rows. Recognising the structure from its shape
 *  keeps a section that arrives without `show` drawn properly instead of
 *  falling into a table of the wrong thing. */
function sniff(row: unknown): string | undefined {
  if (typeof row === "string") return "flags";
  if (!row || typeof row !== "object") return undefined;
  const k = row as Record<string, unknown>;
  if ("station" in k && "label" in k && "status" in k) return "line";
  if ("outcome" in k && "at" in k) return "audit";
  if ("payload" in k && "status" in k) return "proposals";
  if ("capability" in k && "irreversibility" in k) return "actions";
  return undefined;
}

export function Line({ line }: { line: StepStatus[] }) {
  return (
    <div className="states">
      {line.map((s, i) => (
        <div key={s.station} className={`st ${s.status === "done" ? "done" : s.status === "now" ? "now" : s.status === "skipped" ? "skip" : ""}`}>
          <span className="n">{s.status === "done" ? "✓" : i + 1}</span>
          {human(s.label || s.station)}
          {s.status === "skipped" && <span className="st-skip">not this visit</span>}
        </div>
      ))}
    </div>
  );
}

export function ProposalRow({ p, onReview }: { p: Proposal; onReview?: (p: Proposal) => void }) {
  const n = Object.keys(p.payload ?? {}).length;
  return (
    <div className="opcard prop">
      <div className="op-t">
        {human(p.operation)}
        <Badge style="warn">awaiting a person</Badge>
      </div>
      <div className="op-m">{p.proposed_by ?? "unattributed"} · {p.surface} · {n} value{n === 1 ? "" : "s"}</div>
      {onReview && <button className="cq" style={{ marginTop: 8 }} onClick={() => onReview(p)}>Review</button>}
    </div>
  );
}

export function AuditRow({ a }: { a: AuditRecord }) {
  const denied = a.outcome.startsWith("denied");
  return (
    <div className="au">
      <span>{a.at?.slice(11, 16) || a.at}</span>
      <b>{a.operation.replace(/^[a-z0-9]+\.op\./, "")}</b>
      <span className="au-actor">{a.actor ?? "unattributed"}</span>
      <Badge style={denied ? "crit" : a.outcome === "proposed" ? "warn" : "ok"}>{a.outcome}</Badge>
    </div>
  );
}

/** A resource section: the view declared which fields, the API sent them, so
 *  the columns are the keys of the first row. */
function Table({ rows }: { rows: Record<string, unknown>[] }) {
  // A row that is not an object has no columns. Rendering one as a table puts
  // every character in its own cell, which is how you find out.
  if (rows.some((r) => !r || typeof r !== "object")) {
    return (
      <div className="caps">
        {rows.map((r, i) => <span className="cap on" key={i}>{fmt(r)}</span>)}
      </div>
    );
  }
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r ?? {})))];
  return (
    <div className="tblwrap">
      <table className="tbl">
        <thead>
          <tr>{cols.map((c) => <th key={c}>{human(c)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{cols.map((c) => <td key={c}>{fmt(r?.[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const fmt = (v: unknown): string =>
  v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);

// ------------------------------------------------------------ dashboard ----

function Dashboard({ rows, titles, maxRows }: { rows: MetricValue[]; titles?: Record<string, string>; maxRows?: number }) {
  if (!rows.length) return <Empty>This dashboard declares no metrics.</Empty>;
  const { limit, hidden, expand } = useRowCap(rows.length, maxRows);
  return (
    <div className="mgrid">
      {rows.slice(0, limit).map((m) => (
        // The exact window start is an ISO timestamp. It is the row's title
        // attribute, not a second line under a line that already says "in the
        // week": nobody reads a machine timestamp off a dashboard.
        <div className="plate-row metric" key={m.metric} title={`since ${m.window_start}`}>
          <span className="m-lab">{m.title ?? titles?.[m.metric] ?? human(m.metric)}</span>
          <span className="m-val">{metricValue(m)}</span>
          <span className="m-sub">
            {m.denominator === null || m.denominator === undefined
              ? `${m.numerator} in the ${m.window}`
              : `${m.numerator} of ${m.denominator} in the ${m.window}`}
          </span>
        </div>
      ))}
      <MoreRow hidden={hidden} onExpand={expand} />
    </div>
  );
}

function metricValue(m: MetricValue): string {
  if (m.unit === "percent") return `${(m.value ?? 0).toFixed(1)}%`;
  if (m.unit === "ratio") return (m.value ?? 0).toFixed(2);
  return String(m.value ?? 0);
}
