/** §5. One question: what requires my attention right now?
 *
 *  §5 also says: do not make this a KPI dashboard. The first version obeyed
 *  that so literally it became a list of nouns and counts, which is a slide,
 *  not a workspace. What the prototype had and that lost is the agent's own
 *  presence: a brief that reads the facility and says something about it, and
 *  questions worth asking placed where you can ask them.
 *
 *  Every sentence and every chip below is composed from declarations and live
 *  rows by agent.ts. Nothing here is written down.
 */
import { brief, facilityAsks, type Loaded } from "../agent";
import { Icon } from "../icons";
import { Empty } from "../parts";
import type { Recent } from "../loops";
import type { QueueRow, TaskRow } from "../types";
import { human } from "../words";

export function Today({ loaded, recents, onOpenThread, onGoView, onAsk, role }: {
  loaded: Loaded[];
  recents: Recent[];
  role?: string;
  onOpenThread: (thread: string) => void;
  onGoView: (view: string) => void;
  onAsk: (question: string) => void;
}) {
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const sentences = brief(loaded);
  const asks = facilityAsks(loaded);

  const queues = loaded.filter((l) => l.decl.kind === "queue");
  const tasklists = loaded.filter((l) => l.decl.kind === "tasklist");
  const tasks = tasklists.flatMap((l) => (l.result.rows ?? []) as TaskRow[]).filter((t) => t.count > 0);

  return (
    <div className="today">
      <header className="today__head">
        <div className="t-meta u-faint">
          {role ? `${human(role)} · ` : ""}
          {now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
        </div>
        <h1 className="t-display" style={{ margin: "var(--space-1) 0 0" }}>{greeting}.</h1>
      </header>

      {/* The brief. An agent block, marked as one, saying something the
          numbers alone do not: where the line is thick and what is worst. */}
      <section className="brief">
        <span className="brief__mark" aria-hidden="true"><Icon name="spark" /></span>
        <div>
          <div className="t-micro u-faint" style={{ letterSpacing: ".06em", textTransform: "uppercase" }}>
            Brief
          </div>
          <p className="brief__text">
            {sentences.map((s, i) =>
              s.go ? (
                <a className="brief__link" href={s.go} key={i}>{s.text}</a>
              ) : (
                <span key={i}>{s.text}</span>
              ))}
          </p>
          {asks.length > 0 && (
            <div className="brief__asks">
              {asks.map((q) => (
                <button className="chip" data-role="button" key={q} onClick={() => onAsk(q)}>
                  <Icon name="chat" />
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <section>
        <h2 className="t-section today__h2">Needs you</h2>
        {tasks.length === 0 ? (
          <Empty title="You're clear.">Nothing needs your attention.</Empty>
        ) : (
          <div className="patient-list">
            {tasks.map((t) => (
              <div className="attention" key={t.title}>
                <span className="attention__n t-num">{t.count}</span>
                <span className="attention__body">
                  <span className="patient-name">{t.title}</span>
                  {/* §77: a notification resolves to an object. Name who, so
                      the row is a thing rather than a number. */}
                  <span className="patient-sub">{whoIn(t, loaded)}</span>
                </span>
                {t.threads?.[0] && (
                  <button className="btn" onClick={() => onOpenThread(t.threads[0])}>Open</button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {queues.length > 0 && (
        <section>
          <h2 className="t-section today__h2">Lists</h2>
          <div className="patient-list">
            {queues.map(({ decl, result }) => {
              const rows = (result.rows ?? []) as QueueRow[];
              return (
                <button className="attention" key={decl.id} onClick={() => onGoView(decl.id)}>
                  <span className="attention__n t-num">{rows.length}</span>
                  <span className="attention__body">
                    <span className="patient-name">{decl.title}</span>
                    <span className="patient-sub">{stations(rows)}</span>
                  </span>
                  <Icon name="refer" />
                </button>
              );
            })}
          </div>
        </section>
      )}

      {recents.length > 0 && (
        <section>
          <h2 className="t-section today__h2">Recent</h2>
          <div className="patient-list">
            {recents.slice(0, 4).map((r) => (
              <button className="attention" key={r.id} onClick={() => onOpenThread(r.id)}>
                <span className="attention__body">
                  <span className="patient-name">{r.name}</span>
                </span>
                <Icon name="refer" />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/** Who this worklist is actually about. The declaration gives a tasklist row
 *  its threads, and a queue gives those threads a name, so a row can say
 *  "Kamala Devi and two others" instead of "3". */
function whoIn(t: TaskRow, loaded: Loaded[]): string {
  const names = new Map<string, string>();
  for (const l of loaded.filter((x) => x.decl.kind === "queue")) {
    for (const r of (l.result.rows ?? []) as QueueRow[]) {
      // `decl.columns` is only on the catalogue's copy of a view; /facility
      // sends a short form without it (types.ts says so). Reading it here
      // returned undefined for every row and every subtitle came out empty,
      // so fall back to the subject's own first readable value -- the kernel
      // already ordered those keys by the declaration.
      const ordered = (l.decl.columns ?? []).length
        ? (l.decl.columns as string[]).map((c) => r.subject?.[c])
        : Object.values(r.subject ?? {});
      const first = ordered.find((v) => typeof v === "string" && v.trim());
      if (first) names.set(r.thread, String(first));
    }
  }
  const named = (t.threads ?? []).map((th) => names.get(th)).filter(Boolean) as string[];
  if (!named.length) return "";
  if (named.length === 1) return named[0];
  if (named.length === 2) return `${named[0]} and ${named[1]}`;
  return `${named[0]} and ${named.length - 1} others`;
}

/** Where the people in this list are standing, most first. */
function stations(rows: QueueRow[]): string {
  const tally = new Map<string, number>();
  for (const r of rows) if (r.station) tally.set(r.station, (tally.get(r.station) ?? 0) + 1);
  return [...tally.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([s, n]) => `${human(s)} ${n}`)
    .join(" · ");
}
