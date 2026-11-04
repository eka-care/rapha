/** The four declared view kinds. A queue is a LIST of numbered rows, which is
 *  what docs/reference/front-desk/queue-labels.html draws and what a phone can
 *  hold: a token, a name, what the row is in, and the time. The card grid it
 *  replaced needed 268px a card, so a phone got one card a screen.
 *
 *  Columns, badge tones and the view's title are all the declaration's.
 */
import { Lotus } from "../abha/Lotus";
import { ABHA_LINKED } from "../abha/sdk";
import { currentRole } from "../api";
import { Icon } from "../icons";
import { displayFor } from "../declarations";
import { derivedStates, labelColumns, marked, provenanceOf, RISK_TONE } from "../loops";
import { clock } from "../messages";
import type {
  MetricValue, QueueRow, SectionResult, StepStatus, TaskRow, ViewDecl, ViewResult,
} from "../types";
import { human, title } from "../words";
import { Calendar } from "./Calendar";

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
        labelCols={labelColumns(decl)}
        provenance={provenanceOf(decl)}
        onOpenThread={onOpenThread}
      />
    );
  }
  if (result.kind === "calendar") {
    return (
      <Calendar
        result={result} role={currentRole()}
        nameOf={(subject) => fields(decl, { subject } as unknown as QueueRow).name}
        onOpenPatient={(id) => { location.hash = `/patients/${id}`; }}
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
/** What a row with nobody on it is called. One place, so the desk, the queue
 *  and the rail cannot drift apart again. */
export const NO_NAME = "No name yet";

export function fields(
  decl: ViewDecl | undefined,
  row: QueueRow,
  labelCols: string[] = [],
  /** The provenance column, if the view declared one. Kept out of the line
   *  under the name for the same reason a label is: it is drawn elsewhere on
   *  the row, and a fact drawn twice is a row saying the same thing twice.
   *  Here it would be worse than a repeat, because the stored value is a code
   *  nobody at a desk has ever been shown. */
  provenanceCol?: string,
): {
  name: string; meta: string; token: string; named: boolean;
} {
  const subject = row.subject ?? {};
  const has = (k: string) => subject[k] !== null && subject[k] !== undefined && subject[k] !== "";
  const keys = (decl?.columns ?? []).length
    ? (decl!.columns as string[])
    : Object.keys(subject).filter((k) => !/(^|_)id$|_date$|_by$/.test(k));
  // The number is a column like any other, and it is drawn as the row's own
  // square rather than repeated in the line underneath.
  const tokenKey = keys.find((k) => /token/i.test(k) && has(k));
  // A label column is drawn as a pill on the right, so repeating it in the
  // line underneath would put the same word on the row twice.
  const rest = keys.filter((k) => k !== tokenKey && k !== provenanceCol
    && !labelCols.includes(k) && has(k));
  const nameKey = rest[0];
  return {
    // A THREAD NOBODY HAS REGISTERED YET HAS NO NAME, and this used to fall
    // back to the thread id: an internal code, on screen, where a clerk reads
    // a patient's name. The front desk already said "No name yet" in its own
    // copy of this rule while the queue and the rail printed `enc-001`, which
    // is three surfaces disagreeing about the same row. The rule is here now,
    // once, and `named` is how a caller draws it differently without having
    // to compare the name against an id to find out.
    name: nameKey ? String(subject[nameKey]) : NO_NAME,
    named: !!nameKey,
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

function Queue({ rows, decl, derived, labelCols, provenance, onOpenThread }: {
  rows: QueueRow[]; decl?: ViewDecl; derived: Set<string>;
  /** The columns the VIEW declared as labels. This file is told which they
   *  are and nothing about what any of them means. */
  labelCols: string[];
  /** Which column says how a row got here, and which of its values earns the
   *  mark. Both the view's. This file draws a dot where they agree and has no
   *  idea what the dot is about; the word for it is on the filter chip, which
   *  is also the declaration's, and the legend under the list explains it in
   *  whatever the declaration called it. */
  provenance: { column: string; mark: string; label: string } | null;
  onOpenThread?: (t: string) => void;
}) {
  if (!rows.length) {
    return <div className="state-empty">Nobody is waiting. This list fills as people are registered.</div>;
  }
  return (
    <div className="qlist">
      {rows.map((r) => {
        const f = fields(decl, r, labelCols, provenance?.column);
        const wears = marked(r, provenance);
        return (
          <button className="qr" key={r.thread} onClick={() => onOpenThread?.(r.thread)}>
            {/* The mark rides on the number because that is the one thing on
                this row the patient and the desk are both looking at. It is a
                dot and not a word: it was the least important thing on the
                line and as a word it shouted. It is never the only way the
                fact is conveyed -- the number's accessible name carries the
                declaration's own word for it, and the chip above filters by
                it -- because a dot alone is invisible to a screen reader and
                to anybody who has not read the legend. */}
            {f.token && (
              <span
                className={`qr-tk${wears ? " qr-tk-mark" : ""}`}
                aria-label={wears ? `${f.token}, ${provenance!.label}` : undefined}
              >
                {f.token}
              </span>
            )}
            <span className="qr-bd">
              <span className="qr-l1">
                <span className="qr-nm">{f.name}</span>
                {(r.flags ?? []).includes(ABHA_LINKED) && <Lotus className="qr-lotus" />}
              </span>
              {f.meta && <span className="qr-sb">{f.meta}</span>}
            </span>
            <span className="qr-tags">
              {/* The programme first, because it is a standing fact about the
                  person, and monochrome, because it is not a risk: in this
                  system red means a clinician should look sooner and nothing
                  else. The word is whatever the declaration calls the stored
                  value, and it is set in the reading face rather than the
                  flag face, because it is a name a person says out loud and
                  not a state the engine worked out. */}
              {labelCols.map((col) => {
                const value = String(r.subject?.[col] ?? "");
                return value ? (
                  <span className="qr-pg dsp" key={col}>{displayFor(col, value)}</span>
                ) : null;
              })}
              {labels(r, derived).map((l) => (
                <span
                  className={`qr-pg${l.risk ? " risk" : ""}${l.der ? " der" : ""}`}
                  key={l.flag}
                >
                  {title(l.flag)}
                </span>
              ))}
            </span>
            <span className="qr-at">{clock(r.opened_at)}</span>
          </button>
        );
      })}
      {/* What the dot means, in the declaration's own word, and only when some
          row on the list actually wears one. A mark nobody can decode is a
          mark that is not conveying anything, and the mockup
          (docs/reference/front-desk/queue-labels.html) carries the same
          legend for the same reason. */}
      {provenance && rows.some((r) => marked(r, provenance)) && (
        <div className="qkey">
          <span className="qkey-dot" aria-hidden="true" />
          {provenance.label}
        </div>
      )}
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
        {(rows as string[]).map((f) => <span className="badge b-mute" key={f}>{title(f)}</span>)}
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
          {title(s.label || s.station)}
          {s.status === "skipped" && <span className="ml-auto fl-e">not this visit</span>}
        </div>
      ))}
    </div>
  );
}
