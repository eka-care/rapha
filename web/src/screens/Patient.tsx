/** §7 and §2.3: the subject, and every visit it has had.
 *
 *  A thread is one encounter, which is the right unit for the guard and the
 *  wrong one for a person: the second visit only means anything beside the
 *  first. What joins two encounters is the workflow's `spine:` declaration,
 *  never a word in this file -- a bundle that declares none has no continuing
 *  subject and never reaches this screen.
 *
 *  §26's timeline is the same list read downwards: each visit says when it was
 *  and what it did, and clicking one opens that thread.
 */
import { useState } from "react";
import { api, useAsync } from "../api";
import { Failed, Loading } from "../parts";
import type { SubjectView } from "../types";
import { human, title } from "../words";

type Tab = "overview" | "encounters" | "timeline";

export function Patient({ id, onOpenThread }: {
  id: string;
  onOpenThread: (thread: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.subject(id), [id]);
  const [tab, setTab] = useState<Tab>("overview");

  if (loading) return <Loading what="this patient" />;
  if (error) return <Failed error={error} what="open this patient" onRetry={reload} />;
  const view = data!;

  const name = String(view.subject.name ?? view.subject.id ?? id);
  const meta = ["age", "sex", "village"]
    .map((k) => view.subject[k])
    .filter((v) => v !== null && v !== undefined && v !== "")
    .map(String);
  const identity = Object.entries(view.subject)
    .find(([k, v]) => /abha|abdm/i.test(k) && v);
  const open = view.encounters.find((e) => e.status !== "completed");

  return (
    <div style={{ display: "grid", gap: "var(--space-6)", maxWidth: 900 }}>
      <header>
        <div className="subject__row">
          <h1 className="t-display" style={{ margin: 0 }}>{name}</h1>
          {identity && (
            <span className="status" data-tone="abdm">
              {title(human(identity[0]))} {String(identity[1])}
            </span>
          )}
        </div>
        <div className="t-meta u-faint">{meta.join(" · ")}</div>
        <div className="quick" style={{ marginTop: "var(--space-4)" }}>
          {open ? (
            <button className="btn" data-variant="primary" onClick={() => onOpenThread(open.thread)}>
              Open current encounter
            </button>
          ) : (
            <span className="t-meta u-faint">No encounter is open.</span>
          )}
          <span className="t-meta u-faint">
            {view.encounters.length === 1 ? "1 visit" : `${view.encounters.length} visits`}
          </span>
        </div>
      </header>

      <div className="quick" role="tablist" aria-label="Patient sections">
        {(["overview", "encounters", "timeline"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className="chip"
            data-role="button"
            data-selected={tab === t}
            onClick={() => setTab(t)}
          >
            {title(t)}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview view={view} />}
      {tab === "encounters" && <Encounters view={view} onOpenThread={onOpenThread} />}
      {tab === "timeline" && <Timeline view={view} onOpenThread={onOpenThread} />}
    </div>
  );
}

function Overview({ view }: { view: SubjectView }) {
  const rows = Object.entries(view.subject)
    .filter(([k, v]) => !/(^|_)id$|_by$|_date$/.test(k) && v !== null && v !== undefined && v !== "");
  return (
    <div className="thread-object">
      <div className="thread-object__body">
        <div className="kv">
          {rows.map(([k, v]) => (
            <div className="kv__row" key={k}>
              <span className="kv__label">{title(human(k))}</span>
              <span className="kv__value">{String(v)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Encounters({ view, onOpenThread }: { view: SubjectView; onOpenThread: (t: string) => void }) {
  return (
    <div className="patient-list">
      {view.encounters.map((e) => (
        <button
          className="patient-row"
          style={{ gridTemplateColumns: "minmax(0,1.4fr) minmax(0,1fr) auto" }}
          key={e.thread}
          onClick={() => onOpenThread(e.thread)}
        >
          <span className="patient-cell">
            <span className="patient-name">{when(e.opened_at)}</span>
            {e.station && <span className="patient-sub"> · {human(e.station)}</span>}
          </span>
          <span className="patient-cell patient-sub">
            {e.did.map((d) => d.title).join(" · ") || "Nothing recorded"}
          </span>
          <span className="patient-cell patient-cell--tags">
            {e.status !== "completed" && <span className="status" data-tone="warning">Open</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

/** §26: longitudinal, not conversational. Dates down the left, what happened
 *  beside them, and a click jumps to that thread. */
function Timeline({ view, onOpenThread }: { view: SubjectView; onOpenThread: (t: string) => void }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-5)" }}>
      {view.encounters.map((e) => (
        <div key={e.thread} style={{ display: "grid", gap: "var(--space-2)" }}>
          <div className="t-label">{when(e.opened_at)}</div>
          <div className="thread-object">
            <div className="thread-object__body">
              {e.did.length === 0 ? (
                <div className="t-meta u-faint">Nothing was recorded on this visit.</div>
              ) : (
                <div style={{ display: "grid", gap: "var(--space-1)" }}>
                  {e.did.map((d) => <div className="t-body" key={d.operation}>{d.title}</div>)}
                </div>
              )}
            </div>
            <div className="thread-object__footer">
              <button className="btn" data-variant="ghost" onClick={() => onOpenThread(e.thread)}>
                Open this visit
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

const when = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
      : "Undated";
