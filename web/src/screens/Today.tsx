/** §5. One question: what requires my attention right now?
 *
 *  Not a KPI dashboard -- §5 says so explicitly, and the temptation is real
 *  because the metrics are already there. The counts below are a sentence, not
 *  a set of tiles, and everything under them is a thing you can act on.
 */
import type { QueueRow, TaskRow, ViewDecl, ViewResult } from "../types";
import { Empty } from "../parts";
import type { Recent } from "../loops";

export function Today({ loaded, recents, onOpenThread, onGoView }: {
  loaded: { decl: ViewDecl; result: ViewResult }[];
  recents: Recent[];
  onOpenThread: (thread: string) => void;
  onGoView: (view: string) => void;
}) {
  const queues = loaded.filter((l) => l.decl.kind === "queue");
  const tasklists = loaded.filter((l) => l.decl.kind === "tasklist");

  const people = new Set<string>();
  let flagged = 0;
  for (const { result } of queues) {
    for (const r of (result.rows ?? []) as QueueRow[]) {
      people.add(r.thread);
      if (r.flags?.length) flagged++;
    }
  }
  const tasks = tasklists.flatMap((l) => (l.result.rows ?? []) as TaskRow[]);
  const outstanding = tasks.reduce((n, t) => n + (t.count ?? 0), 0);

  const today = new Date().toLocaleDateString(undefined, {
    day: "numeric", month: "short", weekday: "long",
  });

  return (
    <div style={{ display: "grid", gap: "var(--space-8)", maxWidth: 880 }}>
      <header>
        <h1 className="t-display" style={{ margin: 0 }}>Today</h1>
        <div className="t-meta u-faint">{today}</div>
        <div className="t-body u-mute" style={{ marginTop: "var(--space-3)", display: "grid", gap: 2 }}>
          <span>{count(people.size, "person", "people")} in the workspace</span>
          {flagged > 0 && <span>{count(flagged, "needs", "need")} attention</span>}
          {outstanding > 0 && <span>{count(outstanding, "task", "tasks")} outstanding</span>}
        </div>
      </header>

      <section>
        <h2 className="t-section" style={{ margin: "0 0 var(--space-3)" }}>Needs you</h2>
        {tasks.length === 0 ? (
          <Empty title="You're clear.">Nothing needs your attention.</Empty>
        ) : (
          <div className="patient-list">
            {tasks.map((t) => (
              <div
                className="patient-row"
                style={{ gridTemplateColumns: "1fr auto auto", cursor: "default" }}
                key={t.title}
              >
                <span className="patient-cell patient-name">{t.title}</span>
                <span className="patient-cell t-num u-mute">{t.count}</span>
                {t.threads?.[0]
                  ? <button className="btn" onClick={() => onOpenThread(t.threads[0])}>Open</button>
                  : <span />}
              </div>
            ))}
          </div>
        )}
      </section>

      {queues.length > 0 && (
        <section>
          <h2 className="t-section" style={{ margin: "0 0 var(--space-3)" }}>Lists</h2>
          <div className="patient-list">
            {queues.map(({ decl, result }) => (
              <button
                className="patient-row"
                style={{ gridTemplateColumns: "1fr auto" }}
                key={decl.id}
                onClick={() => onGoView(decl.id)}
              >
                <span className="patient-cell patient-name">{decl.title}</span>
                <span className="patient-cell t-num u-mute u-right">
                  {((result.rows ?? []) as unknown[]).length}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {recents.length > 0 && (
        <section>
          <h2 className="t-section" style={{ margin: "0 0 var(--space-3)" }}>Recent</h2>
          <div className="patient-list">
            {recents.slice(0, 4).map((r) => (
              <button
                className="patient-row"
                style={{ gridTemplateColumns: "1fr" }}
                key={r.id}
                onClick={() => onOpenThread(r.id)}
              >
                <span className="patient-cell patient-name">{r.name}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
