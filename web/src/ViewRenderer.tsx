/** The view renderer. Given a ViewResult it draws it. There are three kinds
 *  and one entry point, because contracts.View is one dataclass with a kind.
 *
 *  It contains no screen. A queue of patients by station and a queue of
 *  samples by bench are the same code; the difference is the declaration.
 */
import { useState } from "react";
import type { AuditRecord, MetricValue, Operation, Proposal, QueueRow, SectionResult, StepStatus, ViewResult } from "./types";
import { Badge, Empty, human, title } from "./ui";

export function ViewRenderer({
  result, titles, onOpenThread, onAction, onReview,
}: {
  result: ViewResult;
  /** Declaration id to human title, for anything the result names by id but
   *  does not label: metrics, today. The declarations carry the words. */
  titles?: Record<string, string>;
  onOpenThread?: (thread: string) => void;
  onAction?: (op: Operation) => void;
  onReview?: (p: Proposal) => void;
}) {
  if (result.kind === "queue") return <QueueView result={result} onOpenThread={onOpenThread} />;
  if (result.kind === "dashboard") return <Dashboard rows={result.rows as MetricValue[]} titles={titles} />;
  if (result.kind === "summary") {
    return <Sections sections={result.rows as SectionResult[]} onAction={onAction} onReview={onReview} />;
  }
  return (
    <Empty>
      This view is a <b>{result.kind}</b>, which this renderer cannot draw. Add it to
      ViewRenderer.tsx, or check the kind in the declaration.
    </Empty>
  );
}

// ---------------------------------------------------------------- queue ----

function QueueView({ result, onOpenThread }: { result: ViewResult; onOpenThread?: (t: string) => void }) {
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
      {list.length ? (
        <div className="qgrid">
          {list.map((r) => <Card key={r.thread} row={r} onOpen={onOpenThread} />)}
        </div>
      ) : (
        <Empty>Nobody here right now.</Empty>
      )}
    </>
  );
}

/** The columns are whatever the view declared, so the card cannot hard-code
 *  them: the first stringy column is the headline, the rest are the line
 *  under it. */
function Card({ row, onOpen }: { row: QueueRow; onOpen?: (t: string) => void }) {
  const cols = Object.entries(row.subject).filter(([, v]) => v !== null && v !== undefined && v !== "");
  const headIdx = Math.max(0, cols.findIndex(([k, v]) => k === "name" || typeof v === "string"));
  const head = cols[headIdx] ? String(cols[headIdx][1]) : row.thread;
  // A token is the kernel's own word for a thread (api ThreadRef carries one),
  // not a bundle's, and the design gives it the corner rather than the line.
  const token = cols.find(([k], i) => i !== headIdx && /token/i.test(k));
  const rest = cols
    .filter(([k], i) => i !== headIdx && k !== token?.[0])
    .map(([, v]) => String(v));
  const initials = head.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <button className="card qc" onClick={() => onOpen?.(row.thread)}>
      <div className="qc-top">
        <div className="avatar" style={{ width: 34, height: 34, fontSize: 11.5 }}>{initials}</div>
        <div style={{ minWidth: 0 }}>
          <div className="qc-n">{head}</div>
          <div className="qc-m">{rest.join(" · ")}</div>
        </div>
        {token && <span className="qc-tok">{String(token[1])}</span>}
      </div>
      <div className="qc-chips">
        <Badge style="blue">{row.station ? human(row.station) : "Complete"}</Badge>
        {Object.entries(row.badges ?? {}).map(([flag, style]) => (
          <Badge key={flag} style={style}>{human(flag)}</Badge>
        ))}
      </div>
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
            <span className="badge b-mute ml-auto">{s.rows?.length ?? 0}</span>
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
          {s.status === "skipped" && <span className="ml-auto" style={{ fontSize: 9.5 }}>not this visit</span>}
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
      {onReview && <button className="cq rose" style={{ marginTop: 8 }} onClick={() => onReview(p)}>Review</button>}
    </div>
  );
}

export function AuditRow({ a }: { a: AuditRecord }) {
  const denied = a.outcome.startsWith("denied");
  return (
    <div className="au">
      <span>{a.at?.slice(11, 16) || a.at}</span>
      <b>{a.operation.replace(/^[a-z0-9]+\.op\./, "")}</b>
      <span className="ml-auto">{a.actor ?? "unattributed"}</span>
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

function Dashboard({ rows, titles }: { rows: MetricValue[]; titles?: Record<string, string> }) {
  if (!rows.length) return <Empty>This dashboard declares no metrics.</Empty>;
  return (
    <>
      <div className="mgrid">
        {rows.map((m) => (
          <div className="card metric" key={m.metric}>
            <div className="eyebrow">{m.title ?? titles?.[m.metric] ?? human(m.metric)}</div>
            <div className="m-val">{metricValue(m)}</div>
            <div className="m-sub">
              {m.denominator === null || m.denominator === undefined
                ? `${m.numerator} in the ${m.window}`
                : `${m.numerator} of ${m.denominator} in the ${m.window}`}
            </div>
            <div className="m-sub dim">since {m.window_start}</div>
          </div>
        ))}
      </div>
      <p className="f-hint" style={{ marginTop: 12 }}>
        Computed on this machine from this machine's records. Nothing here is sent anywhere.
      </p>
    </>
  );
}

function metricValue(m: MetricValue): string {
  if (m.unit === "percent") return `${(m.value ?? 0).toFixed(1)}%`;
  if (m.unit === "ratio") return (m.value ?? 0).toFixed(2);
  return String(m.value ?? 0);
}
