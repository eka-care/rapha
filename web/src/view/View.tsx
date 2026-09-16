/** The four declared view kinds, drawn as §54's list.
 *
 *  Which columns a queue shows, which flags get which tone, and what the view
 *  is called are all the declaration's answers. This file contains no station,
 *  no flag and no view title, which is how the same component draws a health
 *  centre's line and a laboratory's bench.
 */
import { Icon } from "../icons";
import { human, title } from "../words";
import { Empty } from "../parts";
import type {
  MetricValue, QueueRow, SectionResult, StepStatus, TaskRow, ViewDecl, ViewResult,
} from "../types";

/** §62's tones, from the declaration's own badge style. A style the bundle
 *  invents that we have no tone for falls through to neutral rather than
 *  being guessed at. */
const TONE: Record<string, string> = { crit: "critical", warn: "warning", ok: "success", mute: "" };

export function View({ result, decl, onOpenThread }: {
  result: ViewResult;
  decl?: ViewDecl;
  onOpenThread?: (thread: string) => void;
}) {
  if (result.kind === "queue") {
    return <Queue rows={(result.rows ?? []) as QueueRow[]} decl={decl} onOpenThread={onOpenThread} />;
  }
  if (result.kind === "tasklist") {
    return <Tasks rows={(result.rows ?? []) as TaskRow[]} onOpenThread={onOpenThread} />;
  }
  if (result.kind === "dashboard") {
    return <Dashboard rows={(result.rows ?? []) as MetricValue[]} />;
  }
  return <Sections sections={(result.rows ?? []) as SectionResult[]} />;
}

// ------------------------------------------------------------------ queue

/** The columns this list shows. The declaration names them; if it names none,
 *  fall back to whatever the subject carries, minus the plumbing nobody reads
 *  in a list. */
export function columnsOf(decl: ViewDecl | undefined, rows: QueueRow[]): string[] {
  if (decl?.columns?.length) return decl.columns;
  const seen = new Set<string>();
  for (const r of rows) for (const k of Object.keys(r.subject ?? {})) {
    if (!/(^|_)id$|_date$|_by$/.test(k)) seen.add(k);
  }
  return [...seen].slice(0, 5);
}

const show = (v: unknown) =>
  v === null || v === undefined || v === "" ? "—" : String(v);

function Queue({ rows, decl, onOpenThread }: {
  rows: QueueRow[]; decl?: ViewDecl; onOpenThread?: (t: string) => void;
}) {
  if (!rows.length) {
    return <Empty title="Nobody is waiting.">This list fills as people are registered.</Empty>;
  }
  const columns = columnsOf(decl, rows);
  // One shared track for the header and every row, so they cannot drift.
  const track = `minmax(200px, 1.6fr) ${columns.slice(1).map(() => "minmax(120px, 1fr)").join(" ")} minmax(140px, 1fr)`;
  return (
    <div className="patient-list" role="table">
      <div className="patient-row patient-row--head" role="row" style={{ gridTemplateColumns: track }}>
        {columns.map((c) => <span className="patient-cell" role="columnheader" key={c}>{title(human(c))}</span>)}
        <span className="patient-cell" role="columnheader">Status</span>
      </div>
      {rows.map((r) => (
        <button
          type="button"
          role="row"
          className="patient-row"
          style={{ gridTemplateColumns: track }}
          key={r.thread}
          onClick={() => onOpenThread?.(r.thread)}
        >
          {columns.map((c, i) => (
            <span className="patient-cell" role="cell" key={c}>
              <span className={i === 0 ? "patient-name" : ""}>{show(r.subject?.[c])}</span>
              {i === 0 && r.station && <span className="patient-sub"> · {human(r.station)}</span>}
            </span>
          ))}
          <span className="patient-cell patient-cell--tags" role="cell">
            {(r.flags ?? []).length === 0 && <span className="u-faint">—</span>}
            {(r.flags ?? []).map((f) => (
              <span className="status" data-tone={TONE[r.badges?.[f] ?? ""] || undefined} key={f}>
                {human(f)}
              </span>
            ))}
          </span>
        </button>
      ))}
    </div>
  );
}

// --------------------------------------------------------------- tasklist

function Tasks({ rows, onOpenThread }: { rows: TaskRow[]; onOpenThread?: (t: string) => void }) {
  if (!rows.length) {
    return <Empty title="You're clear.">Nothing needs your attention.</Empty>;
  }
  return (
    <div className="patient-list">
      {rows.map((r) => (
        <div className="patient-row" style={{ gridTemplateColumns: "1fr auto auto", cursor: "default" }} key={r.title}>
          <span className="patient-cell patient-name">{r.title}</span>
          <span className="patient-cell t-num u-mute">{r.count}</span>
          {/* §10: a row is only actionable when the declaration gave it an
              operation. Without one it is a worklist to open, not a button. */}
          {r.operation && r.threads?.[0] ? (
            <button className="btn" onClick={() => onOpenThread?.(r.threads[0])}>Open</button>
          ) : <span />}
        </div>
      ))}
    </div>
  );
}

// -------------------------------------------------------------- dashboard

function Dashboard({ rows }: { rows: MetricValue[] }) {
  if (!rows.length) return <Empty title="No measurements yet." />;
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
      {rows.map((m) => (
        <div className="thread-object" key={m.metric} style={{ width: "auto" }}>
          <div className="thread-object__body">
            <div className="t-meta u-faint">{m.title ?? human(m.metric)}</div>
            <div className="t-display t-num" style={{ marginTop: "var(--space-2)" }}>
              {m.unit === "percent" ? `${Math.round(m.value)}%` : m.value}
            </div>
            {m.denominator !== null && m.denominator !== undefined && (
              <div className="t-meta u-faint t-num" style={{ marginTop: "var(--space-1)" }}>
                {m.numerator} of {m.denominator}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- summary

function Sections({ sections }: { sections: SectionResult[] }) {
  if (!sections.length) return <Empty title="Nothing recorded yet." />;
  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      {sections.map((s) => (
        <div className="thread-object" key={s.title}>
          <header className="thread-object__header">
            <span>{s.title}</span>
            <span className="thread-object__header-end t-num">{s.rows?.length ?? 0}</span>
          </header>
          <div className="thread-object__body">
            <SectionRows section={s} />
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionRows({ section }: { section: SectionResult }) {
  const rows = section.rows ?? [];
  if (!rows.length) return <div className="t-meta u-faint">None.</div>;
  if (section.show === "line") return <Line line={rows as StepStatus[]} />;
  if (section.show === "flags") {
    return (
      <div className="quick">
        {(rows as string[]).map((f) => <span className="status" key={f}>{human(f)}</span>)}
      </div>
    );
  }
  return (
    <div className="kv">
      {(rows as Record<string, unknown>[]).map((r, i) => (
        <div className="kv__row" key={i}>
          <span className="kv__label">{describe(r)}</span>
          <span className="kv__value">{when(r)}</span>
        </div>
      ))}
    </div>
  );
}

/** The most useful thing a row of an unknown resource can say about itself,
 *  without this file knowing what resource it is. */
function describe(r: Record<string, unknown>): string {
  for (const k of ["title", "text", "name", "code", "operation", "status"]) {
    if (r[k]) return String(r[k]);
  }
  const first = Object.entries(r).find(([k, v]) => !/(^|_)id$/.test(k) && v);
  return first ? `${title(human(first[0]))}: ${first[1]}` : "—";
}
const when = (r: Record<string, unknown>) => {
  const k = Object.keys(r).find((x) => /_date$|^at$|_at$/.test(x));
  return k && r[k] ? new Date(String(r[k])).toLocaleString(undefined, { day: "numeric", month: "short" }) : "";
};

/** A thread's declared steps. §81: where the patient is, kept separate from
 *  who owns the work and what has happened. */
export function Line({ line }: { line: StepStatus[] }) {
  return (
    <div className="line">
      {line.map((s) => (
        <span className="line__step" data-status={s.status} key={s.station}>
          <span className="line__dot" aria-hidden="true" />
          {human(s.label || s.station)}
          {s.status === "done" && <span className="u-sr">done</span>}
          {s.status === "now" && <span className="u-sr">current</span>}
          {s.status === "skipped" && <span className="u-sr">not this visit</span>}
        </span>
      ))}
    </div>
  );
}

export { Icon };
