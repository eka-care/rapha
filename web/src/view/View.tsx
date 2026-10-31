/** The four declared view kinds. A queue is a LIST of numbered rows, which is
 *  what docs/reference/front-desk/queue-labels.html draws and what a phone can
 *  hold: a token, a name, what the row is in, and the time. The card grid it
 *  replaced needed 268px a card, so a phone got one card a screen.
 *
 *  Columns, badge tones and the view's title are all the declaration's.
 */
import { Lotus } from "../abha/Lotus";
import { ABHA_LINKED } from "../abha/sdk";
import { Icon } from "../icons";
import { derivedStates, RISK_TONE } from "../loops";
import { clock } from "../messages";
import type {
  MetricValue, QueueRow, SectionResult, StepStatus, TaskRow, ViewDecl, ViewResult,
} from "../types";
import { human, title } from "../words";

export function View({ result, decl, workflow, onOpenThread }: {
  result: ViewResult;
  decl?: ViewDecl;
  /** The workflow this view's rows walk, when the caller has it. The queue
   *  needs its state declarations to know which labels the kernel worked out
   *  and which a person asserted. Absent draws every label solid. */
  workflow?: Parameters<typeof derivedStates>[0];
  onOpenThread?: (thread: string) => void;
}) {
  if (result.kind === "queue") {
    return (
      <Queue
        rows={(result.rows ?? []) as QueueRow[]}
        decl={decl}
        derived={derivedStates(workflow)}
        onOpenThread={onOpenThread}
      />
    );
  }
  if (result.kind === "tasklist") {
    return <Tasks rows={(result.rows ?? []) as TaskRow[]} onOpenThread={onOpenThread} />;
  }
  if (result.kind === "dashboard") return <Dashboard rows={(result.rows ?? []) as MetricValue[]} />;
  return <Sections sections={(result.rows ?? []) as SectionResult[]} />;
}

/** What a row leads with, what it says underneath, and which field is the
 *  number.
 *
 *  All three come from the view's own `columns:`, in the order it declared
 *  them. The short form of a view omits them, and then the row shows whatever
 *  the subject carries, minus the plumbing. Nothing here decides what a
 *  patient is.
 */
function fields(decl: ViewDecl | undefined, row: QueueRow): {
  name: string; meta: string; token: string;
} {
  const subject = row.subject ?? {};
  const has = (k: string) => subject[k] !== null && subject[k] !== undefined && subject[k] !== "";
  const keys = (decl?.columns ?? []).length
    ? (decl!.columns as string[])
    : Object.keys(subject).filter((k) => !/(^|_)id$|_date$|_by$/.test(k));
  // The number is a column like any other, and it is drawn as the row's own
  // square rather than repeated in the line underneath.
  const tokenKey = keys.find((k) => /token/i.test(k) && has(k));
  const rest = keys.filter((k) => k !== tokenKey && has(k));
  const nameKey = rest[0];
  return {
    name: nameKey ? String(subject[nameKey]) : row.thread,
    meta: [...rest.slice(1, 4).map((k) => String(subject[k])), human(row.station)]
      .filter(Boolean).join(" · "),
    token: tokenKey ? String(subject[tokenKey]) : "",
  };
}

/** The labels on the right of a row.
 *
 *  Only the flags the view gave a tone to. A flag it did not name is a state
 *  of the line, not a thing to shout on a row -- the same rule the thread
 *  header follows. Risk leads, because it is the one of them that means a
 *  clinician should look sooner.
 */
function labels(row: QueueRow, derived: Set<string>): { flag: string; risk: boolean; der: boolean }[] {
  return (row.flags ?? [])
    .filter((f) => row.badges?.[f])
    .map((f) => ({ flag: f, risk: row.badges[f] === RISK_TONE, der: derived.has(f) }))
    .sort((a, b) => Number(b.risk) - Number(a.risk));
}

function Queue({ rows, decl, derived, onOpenThread }: {
  rows: QueueRow[]; decl?: ViewDecl; derived: Set<string>;
  onOpenThread?: (t: string) => void;
}) {
  if (!rows.length) {
    return <div className="state-empty">Nobody is waiting. This list fills as people are registered.</div>;
  }
  return (
    <div className="qlist">
      {rows.map((r) => {
        const f = fields(decl, r);
        return (
          <button className="qr" key={r.thread} onClick={() => onOpenThread?.(r.thread)}>
            {f.token && <span className="qr-tk">{f.token}</span>}
            <span className="qr-bd">
              <span className="qr-l1">
                <span className="qr-nm">{f.name}</span>
                {(r.flags ?? []).includes(ABHA_LINKED) && <Lotus className="qr-lotus" />}
              </span>
              {f.meta && <span className="qr-sb">{f.meta}</span>}
            </span>
            <span className="qr-tags">
              {labels(r, derived).map((l) => (
                <span
                  className={`qr-pg${l.risk ? " risk" : ""}${l.der ? " der" : ""}`}
                  key={l.flag}
                >
                  {human(l.flag)}
                </span>
              ))}
            </span>
            <span className="qr-at">{clock(r.opened_at)}</span>
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
