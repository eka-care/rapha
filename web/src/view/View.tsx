/** The four declared view kinds. A queue is a grid of patient CARDS, which is
 *  the prototype's shape and the right one: a queue is scanned for a person,
 *  not read across like a spreadsheet.
 *
 *  Columns, badge tones and the view's title are all the declaration's.
 */
import { initialsOf } from "../agent";
import { Icon } from "../icons";
import type {
  MetricValue, QueueRow, SectionResult, StepStatus, TaskRow, ViewDecl, ViewResult,
} from "../types";
import { human, title } from "../words";

const TONE: Record<string, string> = { crit: "b-crit", warn: "b-warn", ok: "b-ok", mute: "b-mute" };

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
  if (result.kind === "dashboard") return <Dashboard rows={(result.rows ?? []) as MetricValue[]} />;
  return <Sections sections={(result.rows ?? []) as SectionResult[]} />;
}

/** The subject fields this card shows: the declaration's columns, or whatever
 *  the subject carries when the short form of a view omitted them. */
function fields(decl: ViewDecl | undefined, row: QueueRow): { name: string; meta: string } {
  const keys = (decl?.columns ?? []).length
    ? (decl!.columns as string[])
    : Object.keys(row.subject ?? {}).filter((k) => !/(^|_)id$|_date$|_by$/.test(k));
  const values = keys.map((k) => row.subject?.[k]).filter((v) => v !== null && v !== undefined && v !== "");
  const name = String(values[0] ?? row.thread);
  return { name, meta: values.slice(1, 4).map(String).join(" · ") };
}

function Queue({ rows, decl, onOpenThread }: {
  rows: QueueRow[]; decl?: ViewDecl; onOpenThread?: (t: string) => void;
}) {
  if (!rows.length) {
    return <div className="state-empty">Nobody is waiting. This list fills as people are registered.</div>;
  }
  return (
    <div className="qgrid">
      {rows.map((r) => {
        const f = fields(decl, r);
        const token = Object.entries(r.subject ?? {}).find(([k, v]) => /token/i.test(k) && v);
        // A thread late in the line carries every flag it has ever raised, and
        // all of them on a card is a wall nobody reads. The declaration already
        // says which are worth calling out (`badges`), so those lead and the
        // rest are a count.
        const called = (r.flags ?? []).filter((fl) => r.badges?.[fl]);
        const plain = (r.flags ?? []).filter((fl) => !r.badges?.[fl]);
        const shown = [...called, ...plain].slice(0, 3);
        const rest = (r.flags ?? []).length - shown.length;
        return (
          <button className="qc" key={r.thread} onClick={() => onOpenThread?.(r.thread)}>
            <div className="qc-top">
              <span className="avatar sm">{initialsOf(f.name)}</span>
              <div className="qc-b">
                <div className="qc-n">{f.name}</div>
                {f.meta && <div className="qc-m">{f.meta}</div>}
              </div>
              {token && <span className="qc-tok">{String(token[1])}</span>}
            </div>
            <div className="qc-chips">
              {r.station && <span className="badge b-ink">{human(r.station)}</span>}
              {shown.map((fl) => (
                <span className={`badge ${TONE[r.badges?.[fl] ?? ""] ?? "b-mute"}`} key={fl}>
                  {human(fl)}
                </span>
              ))}
              {rest > 0 && <span className="badge b-mute">+{rest}</span>}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function Tasks({ rows, onOpenThread }: { rows: TaskRow[]; onOpenThread?: (t: string) => void }) {
  if (!rows.length) return <div className="state-empty">You're clear. Nothing needs your attention.</div>;
  return (
    <div className="card">
      <div className="att">
        {rows.map((r) => (
          <button className="at" key={r.title} onClick={() => r.threads?.[0] && onOpenThread?.(r.threads[0])}>
            <span className={`at-ic${r.operation ? " amb" : " ink"}`}>
              <Icon name={r.operation ? "alert" : "clip"} className="i sm" />
            </span>
            <span className="at-b"><span className="at-t">{r.title}</span></span>
            <span className="badge b-mute">{r.count}</span>
            {r.threads?.[0] && <span className="at-go">Open</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function Dashboard({ rows }: { rows: MetricValue[] }) {
  if (!rows.length) return <div className="state-empty">No measurements yet.</div>;
  return (
    <div className="qgrid">
      {rows.map((m) => (
        <div className="card" key={m.metric}>
          <div className="pulse">
            <div>
              <div className="pu-r"><span>{m.title ?? human(m.metric)}</span></div>
              <div className="pu-v">
                {m.unit === "percent" ? Math.round(m.value) : m.value}
                {m.unit === "percent" && <small>%</small>}
              </div>
              {m.denominator !== null && m.denominator !== undefined && (
                <>
                  <div className="split">
                    <i style={{ width: `${m.denominator ? (m.numerator / m.denominator) * 100 : 0}%`,
                                background: "var(--color-accent)" }} />
                    <i style={{ flex: 1, background: "var(--color-border-subtle)" }} />
                  </div>
                  <div className="leg"><span>{m.numerator} of {m.denominator}</span></div>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Sections({ sections }: { sections: SectionResult[] }) {
  if (!sections.length) return <div className="state-empty">Nothing recorded yet.</div>;
  return (
    <div style={{ display: "grid", gap: 16 }}>
      {sections.map((s) => (
        <div className="card" key={s.title}>
          <div className="card-h">
            <div className="card-t">{s.title}</div>
            <span className="badge b-mute ml-auto">{s.rows?.length ?? 0}</span>
          </div>
          <div style={{ padding: "10px 14px" }}>
            <SectionRows section={s} />
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionRows({ section }: { section: SectionResult }) {
  const rows = section.rows ?? [];
  if (!rows.length) return <div className="fl-e">None.</div>;
  if (section.show === "line") return <Line line={rows as StepStatus[]} />;
  if (section.show === "flags") {
    return (
      <div className="qc-chips">
        {(rows as string[]).map((f) => <span className="badge b-mute" key={f}>{human(f)}</span>)}
      </div>
    );
  }
  return (
    <>
      {(rows as Record<string, unknown>[]).map((r, i) => (
        <div className="kv" key={i}>
          <span>{describe(r, section.fields)}</span><b>{when(r)}</b>
        </div>
      ))}
    </>
  );
}

/** What a row leads with.
 *
 *  The section's own `fields:`, in the order it declared them. This used to be
 *  a list of six field names written here -- title, text, name, code,
 *  operation, status -- which meant a bundle that put its own column first
 *  got whichever of those six it happened to carry instead, and no amount of
 *  reordering the declaration changed the screen. The fallback below is for a
 *  section that declares no fields (the line, the flags, the audit), and it
 *  reads the row rather than a word list.
 */
function describe(r: Record<string, unknown>, fields?: string[]): string {
  for (const k of fields ?? []) {
    if (r[k]) return String(r[k]);
  }
  const first = Object.entries(r).find(([k, v]) => !/(^|_)id$/.test(k) && v);
  return first ? `${title(human(first[0]))}: ${first[1]}` : "—";
}
const when = (r: Record<string, unknown>) => {
  const k = Object.keys(r).find((x) => /_date$|^at$|_at$/.test(x));
  return k && r[k] ? new Date(String(r[k])).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "";
};

/** §81: where the subject is. The prototype's vertical numbered stepper. */
export function Line({ line }: { line: StepStatus[] }) {
  return (
    <div className="states">
      {line.map((s, i) => (
        <div className={`st ${s.status === "done" ? "done" : s.status === "now" ? "now" : s.status === "skipped" ? "skip" : ""}`} key={s.station}>
          <span className="n">{s.status === "done" ? "✓" : i + 1}</span>
          {human(s.label || s.station)}
          {s.status === "skipped" && <span className="ml-auto fl-e">not this visit</span>}
        </div>
      ))}
    </div>
  );
}
