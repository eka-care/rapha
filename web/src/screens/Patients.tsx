/** The register: every patient this centre holds, and under each of them the
 *  visits they have had.
 *
 *  A HIERARCHY, AND THE WORK IS AT THE BOTTOM OF IT. A person is a row. Open
 *  it and their visits unfold, newest first, each one dated and saying what
 *  it did. Open a visit and it is the thread, which is where the records are.
 *  So the page answers "who" without loading "what", and nobody waits for two
 *  thousand people's history to read one line.
 *
 *  The visits come from `GET /subjects/{id}`, which is the same endpoint the
 *  thread's own spine reads, so this screen and that one cannot disagree
 *  about somebody's history.
 *
 *  Nothing here names a field. What a patient is called and what is said
 *  under their name is the queue view's `columns:`, through the same
 *  `header()` the thread and the rail use.
 */
import { useState } from "react";
import { initialsOf } from "../agent";
import { api, useAsync } from "../api";
import { displayFor } from "../declarations";
import { Icon } from "../icons";
import { header, queueViewFor } from "../messages";
import { Failed, Loading } from "../parts";
import type { Catalogue, RegisterRow, SubjectView, ThreadView } from "../types";
import { human } from "../words";

export function Patients({ cat, onOpenThread, onOpenSubject }: {
  cat: Catalogue;
  onOpenThread: (thread: string) => void;
  onOpenSubject: (subject: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.register(), []);
  const [open, setOpen] = useState<string>("");

  if (loading) return <Loading what="the register" shape="rows" rows={6} />;
  if (error) return <Failed error={error} what="read the register" onRetry={reload} />;
  const rows = data!.patients;

  return (
    <div className="reg-page">
      <div className="reg-h">
        <h2 className="reg-t">Patients</h2>
        <span className="reg-n">{data!.total}</span>
      </div>
      {rows.length === 0 && (
        <div className="state-empty">Nobody is registered here yet.</div>
      )}
      <div className="reg-list">
        {rows.map((r) => (
          <Person
            key={r.id}
            row={r}
            cat={cat}
            open={open === r.id}
            onToggle={() => setOpen(open === r.id ? "" : r.id)}
            onOpenThread={onOpenThread}
            onOpenSubject={onOpenSubject}
          />
        ))}
      </div>
    </div>
  );
}

function Person({ row, cat, open, onToggle, onOpenThread, onOpenSubject }: {
  row: RegisterRow; cat: Catalogue; open: boolean;
  onToggle: () => void;
  onOpenThread: (thread: string) => void;
  onOpenSubject: (subject: string) => void;
}) {
  const head = header(
    { id: row.id, workflow: "", subject: row.subject, flags: [] } as unknown as ThreadView,
    queueViewFor(cat, Object.values(cat.workflows ?? {})[0]?.id ?? ""),
    displayFor,
  );
  return (
    <div className={`reg-p${open ? " on" : ""}`}>
      <button className="reg-row" aria-expanded={open} onClick={onToggle}>
        <span className="chev" aria-hidden="true"><Icon name="chev" className="i sm" /></span>
        <span className="reg-av">{initialsOf(head.name)}</span>
        <span className="reg-b">
          <span className="reg-nm">{head.name}</span>
          {head.meta.length > 0 && <span className="reg-meta">{head.meta.join(" · ")}</span>}
        </span>
        <span className="reg-v">{row.visits === 1 ? "1 visit" : `${row.visits} visits`}</span>
      </button>
      {open && <Visits id={row.id} onOpenThread={onOpenThread} onOpenSubject={onOpenSubject} />}
    </div>
  );
}

/** One person's visits, read when their row opens and not before. */
function Visits({ id, onOpenThread, onOpenSubject }: {
  id: string;
  onOpenThread: (thread: string) => void;
  onOpenSubject: (subject: string) => void;
}) {
  const { data, error, loading, reload } = useAsync<SubjectView>(() => api.subject(id), [id]);
  if (loading) return <div className="reg-visits"><div className="fl-e">Reading their visits…</div></div>;
  if (error) return <div className="reg-visits"><Failed error={error} what="read their visits" onRetry={reload} /></div>;

  const visits = data!.encounters;
  return (
    <div className="reg-visits">
      {visits.length === 0 && <div className="fl-e">No visits yet.</div>}
      {visits.map((e) => (
        <button className="reg-visit" key={e.thread} onClick={() => onOpenThread(e.thread)}>
          <span className="reg-d">{day(e.opened_at)}</span>
          <span className="reg-did">
            {e.did.length
              ? e.did.map((d) => d.title).join(" · ")
              : <span className="u-mute">Nothing recorded</span>}
          </span>
          {e.station && <span className="reg-at">{human(e.station)}</span>}
        </button>
      ))}
      <button className="reg-all" onClick={() => onOpenSubject(id)}>
        <Icon name="folder" className="i sm" />
        Open their whole record
      </button>
    </div>
  );
}

const day = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
