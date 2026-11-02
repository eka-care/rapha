/** §5, rebuilt to the prototype.
 *
 *  A hero that says what kind of shift this is and offers the questions worth
 *  asking; the brief the agent wrote; the line in motion; then attention and
 *  the facility's pulse side by side. None of it is a list of nouns, which is
 *  what the first two attempts at this screen were.
 *
 *  Every word and number comes from a declaration or a live row. agent.ts
 *  composes the prose; this file lays it out.
 */
import { brief, facilityAsks, initialsOf, line, type Loaded } from "../agent";
import { NAME } from "../brand";
import { Icon } from "../icons";
import type { Recent } from "../loops";
import { Loading } from "../parts";
import type { Catalogue, QueueRow, TaskRow } from "../types";
import { human, title } from "../words";

/** How many names a flow column shows before it says how many more. */
const SHOWN = 4;

export function Today({ loaded, loading, recents, cat, onOpenThread, onGoView, onAsk }: {
  loaded: Loaded[];
  /** Whether the four view reads are still running. Without it this screen
   *  draws an empty facility -- nobody here, every station clear -- which is
   *  a confident lie and looks exactly like a kernel that is down. */
  loading: boolean;
  recents: Recent[];
  cat: Catalogue;
  onOpenThread: (thread: string) => void;
  onGoView: (view: string) => void;
  onAsk: (question: string) => void;
}) {
  if (loading && !loaded.length) return <Loading what="the facility" shape="blocks" rows={4} />;
  const now = new Date();
  const h = now.getHours();
  const greeting = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";

  /** The centre's own name, from the bundle that is loaded. Never typed
   *  here: a laboratory running this kernel reads its own title. */
  const facility = cat.manifest?.title ?? "";
  const queues = loaded.filter((l) => l.decl.kind === "queue");
  const rows = queues.flatMap((l) => (l.result.rows ?? []) as QueueRow[]);
  const done = rows.filter((r) => !r.station).length;
  const tasks = loaded
    .filter((l) => l.decl.kind === "tasklist")
    .flatMap((l) => (l.result.rows ?? []) as TaskRow[])
    .filter((t) => t.count > 0);

  // Station order is the workflow's, never this file's.
  // SHOWN caps each column. A station with sixty-eight people in it was
  // sixty-eight chips down the page, so the two cards under this one were
  // several screens below a wall of names nobody reads. A flow diagram
  // answers "where is the line heavy", which the count and the rail already
  // say; the names are the queue's job, one tap away.
  const wf = Object.values(cat.workflows ?? {})[0];
  const stations = (wf?.steps ?? []).map((s) => s.station);
  const badges = queues[0]?.decl.badges ?? {};
  const columns = line(loaded, stations, badges);

  // The session clock. The prototype's OPD window; there is no declaration
  // for a facility's hours, so this shows the time and the day's progress
  // through it rather than inventing an opening hour.
  const mins = h * 60 + now.getMinutes();
  const span = { from: 9 * 60, to: 14 * 60 };
  const pct = Math.max(0, Math.min(100, ((mins - span.from) / (span.to - span.from)) * 100));
  const left = Math.round(((span.to - mins) / 60) * 10) / 10;

  return (
    <div className="home">
      <section className="hero">
        <svg className="hero-mark" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-mark-lg" /></svg>
        <div className="arc">
          <div className="arc-l">Session</div>
          <div className="arc-t">
            {String(h).padStart(2, "0")}:{String(now.getMinutes()).padStart(2, "0")}
          </div>
          <div className="arc-bar"><i style={{ width: `${pct}%` }} /></div>
          <div className="arc-s">
            {pct <= 0 ? "not started" : pct >= 100 ? "session closed" : `${left} h left`}
          </div>
        </div>

        {/* The artifact's hero: what the centre is, what day it is, and the
            two numbers a person arriving at a shift wants. The greeting led
            here and said nothing; it is the eyebrow's "good evening" now,
            under the one line that matters. */}
        <div className="hero-eye">
          {facility} · {now.toLocaleDateString(undefined,
            { weekday: "long", day: "numeric", month: "long" })} · {greeting.toLowerCase()}
        </div>

        <h2 className="hero-h">
          {rows.length} in the workspace.<br />
          <span>
            {tasks.length === 0
              ? `${done} complete.`
              : `${tasks.reduce((n, t) => n + t.count, 0)} ${
                  tasks.reduce((n, t) => n + t.count, 0) === 1 ? "thing needs" : "things need"} you.`}
          </span>
        </h2>

        {/* WHAT WAS HERE: "Every record here was committed by a person who
            was there. Nothing on this screen was written by the system."
            True, and the whole point of the guard -- and it was two
            sentences of reassurance over a list of people waiting, aimed at
            a doubt nobody standing at a health centre has. The property is
            enforced in catalogue/guard.py and proved in the kernel's own
            checks, which is where it belongs; a screen does not earn trust
            by claiming it. */}

        {/* A button that OPENS the command bar, so what looked like a field
            was a read-only input nested inside it: a second stop for the
            keyboard that accepts nothing, and no accessible name on either.
            It is now the button's own label. */}
        <button className="hero-ask" onClick={() => onAsk("")}>
          <Icon name="search" className="i lg" />
          {/* The same box the command bar opens, so it is called the same
              thing. Two names for one control is two controls. */}
          <span className="hero-ask-l">Ask {NAME}, or find a patient</span>
          <span className="kbd">⌘K</span>
        </button>
        <div className="chips">
          {facilityAsks(loaded).map((q) => (
            <button className="chip" key={q} onClick={() => onAsk(q)}>{q}</button>
          ))}
        </div>
      </section>

      <div className="card">
        <div className="brief">
          <span className="brief-av"><Icon name="spark" className="i sm" /></span>
          <div>
            <div className="m-meta">Shift brief · {now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</div>
            <p className="brief-t">
              {brief(loaded).map((s, i) =>
                s.go
                  ? <button className="go" key={i} onClick={() => onGoView(s.go!.replace("#/views/", ""))}>{s.text}</button>
                  : <span key={i}>{s.text}</span>)}
            </p>
          </div>
        </div>
      </div>

      {columns.length > 0 && (
        <div className="card">
          <div className="card-h">
            <div className="card-t">Patient flow</div>
          </div>
          <div className="flow">
            {columns.map((c) => (
              <div className={`fl-col${c.jam ? " jam" : ""}`} key={c.station}>
                <div className="fl-h">
                  <span className="fl-n">{human(c.station)}</span>
                  <span className="fl-c">{c.people.length}</span>
                </div>
                <div className="fl-rail">{c.people.length > 0 && <i />}</div>
                {c.people.length === 0
                  ? <div className="fl-e">Clear</div>
                  : c.people.slice(0, SHOWN).map((p) => (
                      <button
                        className={`fl-p${p.alert ? " alert" : ""}`}
                        key={p.thread}
                        onClick={() => onOpenThread(p.thread)}
                      >
                        <span className="fl-av">{p.initials}</span>
                        <span className="fl-nm">{p.name}</span>
                        {/* SC 1.4.1: the tone alone carried this, so a person
                            who cannot see that red saw an ordinary row. The
                            mark is the second carrier and the declared flag
                            is its name. */}
                        {p.alert && (
                          <>
                            <Icon name="alert" className="i sm" />
                            <span className="u-sr">{p.alerts.map((f) => title(human(f))).join(", ")}</span>
                          </>
                        )}
                      </button>
                    ))}
                {c.people.length > SHOWN && (
                  <button className="fl-e fl-more"
                          onClick={() => queues[0] && onGoView(queues[0].decl.id)}>
                    {c.people.length - SHOWN} more
                  </button>
                )}
                {c.jam && (
                  <div className="fl-jam">
                    <Icon name="alert" className="i sm" />
                    heaviest here
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="hgrid">
        <div className="card">
          <div className="card-h">
            <div className="card-t">Needs you</div>
            <span className="badge b-mute ml-auto">{tasks.reduce((n, t) => n + t.count, 0)}</span>
          </div>
          <div className="att">
            {tasks.length === 0 ? (
              <div className="state-empty">You're clear. Nothing needs your attention.</div>
            ) : tasks.map((t) => (
              <button className="at" key={t.title} onClick={() => t.threads?.[0] && onOpenThread(t.threads[0])}>
                <span className={`at-ic${t.operation ? " amb" : " ink"}`}>
                  <Icon name={t.operation ? "alert" : "clip"} className="i sm" />
                </span>
                <span className="at-b">
                  <span className="at-t">{t.title}</span>
                  <span className="at-s">{whoIn(t, loaded)}</span>
                </span>
                <span className="badge b-mute">{t.count}</span>
                <span className="at-go">Open</span>
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div className="card-t">Facility pulse</div></div>
          <div className="pulse">
            <div>
              <div className="pu-r">
                <span>Seen today</span>
                <span>{rows.length} in the workspace</span>
              </div>
              <div className="pu-v">{done}<small>complete</small></div>
              <div className="split">
                <i style={{ width: `${rows.length ? (done / rows.length) * 100 : 0}%`, background: "var(--color-accent)" }} />
                <i style={{ flex: 1, background: "var(--color-border-subtle)" }} />
              </div>
              <div className="leg">
                <span><i className="dt" style={{ background: "var(--color-accent)" }} />Complete {done}</span>
                <span><i className="dt" style={{ background: "var(--color-border-strong)" }} />In progress {rows.length - done}</span>
              </div>
            </div>

            {recents.length > 0 && (
              <div>
                <div className="pu-r"><span>Recent</span></div>
                <div style={{ display: "grid", gap: 6, marginTop: 7 }}>
                  {recents.slice(0, 4).map((r) => (
                    <button className="fl-p" key={r.id} onClick={() => onOpenThread(r.id)}>
                      <span className="fl-av">{initialsOf(r.name)}</span>
                      <span className="fl-nm">{r.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** §77: a row about somebody, not a number. */
function whoIn(t: TaskRow, loaded: Loaded[]): string {
  const names = new Map<string, string>();
  for (const l of loaded.filter((x) => x.decl.kind === "queue")) {
    for (const r of (l.result.rows ?? []) as QueueRow[]) {
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
