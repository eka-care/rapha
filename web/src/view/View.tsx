/** The four declared view kinds. A queue is a LIST of numbered rows, which is
 *  what docs/reference/front-desk/queue-labels.html draws and what a phone can
 *  hold: a token, a name, what the row is in, and the time. The card grid it
 *  replaced needed 268px a card, so a phone got one card a screen.
 *
 *  Columns, badge tones and the view's title are all the declaration's.
 */
import { Lotus } from "../abha/Lotus";
import { ABHA_LINKED, ABHA_PENDING } from "../abha/sdk";
import { currentRole } from "../api";
import { Icon } from "../icons";
import { displayFor } from "../declarations";
import { derivedStates, labelColumns, marked, provenanceOf, RISK_TONE, type ColumnKey, type Sort } from "../loops";
import { initialsOf } from "../agent";
import { clock, waited } from "../messages";
import type {
  MetricValue, QueueRow, SectionResult, StepStatus, TaskRow, ViewDecl, ViewResult,
} from "../types";
import { human, title, NO_NAME } from "../words";
import { Calendar } from "./Calendar";

export function View({ result, decl, workflow, onOpenThread, sort, onSort }: {
  result: ViewResult;
  decl?: ViewDecl;
  /** The workflow this view's rows walk, when the caller has it. The queue
   *  needs its state declarations to know which labels the kernel worked out
   *  and which a person asserted. Absent draws every label solid. */
  workflow?: Parameters<typeof derivedStates>[0];
  onOpenThread?: (thread: string) => void;
  /** The column the list is sorted by, and what a click on a header does. A
   *  caller that passes neither gets a list with no header. */
  sort?: Sort;
  onSort?: (key: ColumnKey) => void;
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
        sort={sort}
        onSort={onSort}
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
export { NO_NAME };

export function fields(
  decl: ViewDecl | undefined,
  /** Only the subject and station are read, so a caller with just a subject
   *  (a calendar row's record) passes that and nothing is cast. */
  row: Pick<QueueRow, "station"> & { subject?: QueueRow["subject"] },
  labelCols: string[] = [],
  /** The provenance column, if the view declared one. Kept out of the line
   *  under the name for the same reason a label is: it is drawn elsewhere on
   *  the row, and a fact drawn twice is a row saying the same thing twice.
   *  Here it would be worse than a repeat, because the stored value is a code
   *  nobody at a desk has ever been shown. */
  provenanceCol?: string,
): {
  name: string; meta: string; station: string; token: string; named: boolean;
  /** The values `meta` joins, before they are joined, so a caller can take
   *  some of them without splitting a value that contains the separator. */
  facts: string[];
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
    facts: rest.slice(1, 4).map((k) => String(subject[k])),
    // Commas, not middle dots: a dot is for separating things that are not a
    // sentence, and a person's age, sex and village read as one.
    meta: rest.slice(1, 4).map((k) => String(subject[k])).filter(Boolean).join(", "),
    // Where they are is its own column on a wide row, not the tail of the
    // demographics line, because it is the thing a queue is read for.
    station: title(human(row.station)),
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

function Queue({ rows, decl, derived, labelCols, provenance, onOpenThread, sort, onSort }: {
  rows: QueueRow[]; decl?: ViewDecl; derived: Set<string>;
  /** The columns the VIEW declared as labels. This file is told which they
   *  are and nothing about what any of them means. */
  labelCols: string[];
  /** Which column says how a row got here, and which of its values earns the
   *  mark. Both the view's. This file draws a dot where they agree and has no
   *  idea what the dot is about; the word for it is on the filter, which is
   *  also the declaration's, and the legend under the list explains it in
   *  whatever the declaration called it. */
  provenance: { column: string; mark: string; label: string } | null;
  onOpenThread?: (t: string) => void;
  sort?: Sort;
  onSort?: (key: ColumnKey) => void;
}) {
  if (!rows.length) {
    return <div className="state-empty">Nobody is waiting. This list fills as people are registered.</div>;
  }
  const target = decl?.target_minutes ?? null;
  const tokenCol = (decl?.columns ?? []).find((c) => /token/i.test(c));
  const hasToken = !!tokenCol;
  // Token first, because it is the number called out in the waiting room.
  const heads: { key: ColumnKey; label: string; end?: boolean }[] = [
    ...(hasToken && tokenCol ? [{ key: "number" as ColumnKey, label: title(human(tokenCol)) }] : []),
    { key: "name", label: "Patient" },
    { key: "station", label: "Where" },
    ...(labelCols.length ? [{ key: "label" as ColumnKey, label: "Programme and flags" }] : []),
    { key: "wait", label: "Waiting", end: true },
  ];
  const anyLinked = rows.some((r) => (r.flags ?? []).includes(ABHA_LINKED));
  const anyDerived = rows.some((r) => labels(r, derived).some((l) => l.der));
  const anyMarked = !!provenance && rows.some((r) => marked(r, provenance));
  return (
    <div className="qlist">
      {onSort && (
        <div className="qh" role="row">
          {heads.map((h) => {
            const on = sort?.key === h.key;
            return (
              <span key={h.key} role="columnheader" className={`qh-c${h.end ? " end" : ""}`}
                    aria-sort={on ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"}>
                <button type="button" className="qh-b" onClick={() => onSort(h.key)}>
                  {h.label}
                  <Icon name="chev" className={`i sm qh-ar${on ? " on" : ""}${on && sort!.dir === "asc" ? " up" : ""}`} />
                </button>
              </span>
            );
          })}
        </div>
      )}
      {rows.map((r) => {
        const f = fields(decl, r, labelCols, provenance?.column);
        const wears = marked(r, provenance);
        // A row that carries a risk flag gets a bar on its edge as well as the
        // red pill, so it is found without reading the pills.
        const risky = labels(r, derived).some((l) => l.risk);
        const waitedFor = waited(r.opened_at);
        const mins = r.opened_at ? (Date.now() - Date.parse(r.opened_at)) / 60000 : 0;
        const over = target !== null && Number.isFinite(mins) && mins > target;
        return (
          <button className={`qr${risky ? " risk" : ""}`} key={r.thread} onClick={() => onOpenThread?.(r.thread)}>
            {/* The token is a column of its own. The mark for how somebody got
                here rides on it as a dot, and the number's accessible name
                carries the declaration's own word for it, because a dot alone
                is invisible to a screen reader and to anybody who has not read
                the legend. */}
            {f.token && (
              <span className="qr-tkw">
                <span
                  className="ticket qr-tk"
                  aria-label={wears ? `${f.token}, ${provenance!.label}` : undefined}
                >
                  <Icon name="ticket" className="i tk-i" />
                  {f.token}
                </span>
                {/* The mark rides beside the ticket, never on it: the ticket's
                    perforated edge is a mask, and a dot inside it is cut by it. */}
                {wears && <span className="qr-dot" aria-hidden="true" />}
              </span>
            )}
            <span className="qr-bd">
              <span className={`qr-av${f.named ? "" : " none"}`} aria-hidden="true">
                {f.named ? initialsOf(f.name) : "?"}
              </span>
              <span className="qr-tx">
                <span className="qr-l1">
                  <span className="qr-nm">{f.name}</span>
                  {/* No lotus means no ABHA yet. That is said once, in the legend,
                      and not as a pill on every such row. */}
                  {(r.flags ?? []).includes(ABHA_LINKED) && <Lotus className="qr-lotus" />}
                </span>
                {(f.meta || f.station) && (
                  <span className="qr-sb">
                    {f.meta}
                    {/* The station is a column of its own from 560px up. Below it
                        the row has no room for a column, so it rejoins this line. */}
                    {f.station && <span className="qr-sb-st">{f.meta ? ", " : ""}{f.station}</span>}
                  </span>
                )}
              </span>
            </span>
            <span className="qr-st">{f.station}</span>
            <span className="qr-tags">
              {/* The programme first, because it is a standing fact about the
                  person, and monochrome, because it is not a risk: in this
                  system red means a clinician should look sooner and nothing
                  else. The word is whatever the declaration calls the stored
                  value, in the reading face. */}
              {labelCols.map((col) => {
                const value = String(r.subject?.[col] ?? "");
                return value ? (
                  <span className="qr-pg dsp" key={col}>{displayFor(col, value)}</span>
                ) : null;
              })}
              {labels(r, derived).filter((l) => l.flag !== ABHA_PENDING).map((l) => (
                <span
                  className={`qr-pg${l.risk ? " risk" : ""}${l.der ? " der" : ""}`}
                  key={l.flag}
                >
                  {title(l.flag)}
                </span>
              ))}
            </span>
            {/* How long they have waited first, because that is what a person
                triages by, and since when under it. Amber once past the
                view's own declared target. */}
            <span className={`qr-at${over ? " over" : ""}`}>
              {waitedFor && <span className="qr-w">{waitedFor}</span>}
              <span className="qr-ar">since {clock(r.opened_at)}</span>
            </span>
          </button>
        );
      })}
      {(anyMarked || anyDerived || anyLinked) && (
        <div className="qkey">
          {anyLinked && <span><Lotus className="qr-lotus" />Linked to ABHA. No mark means not yet.</span>}
          {anyMarked && <span><i className="qkey-dot" aria-hidden="true" />{provenance!.label}</span>}
          {anyDerived && <span><i className="qkey-dash" aria-hidden="true" />Worked out from the records</span>}
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
