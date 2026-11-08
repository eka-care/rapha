/** §5, rebuilt to the prototype.
 *
 *  A hero that says what kind of shift this is and offers the questions worth
 *  asking; the line in motion; then attention and
 *  the facility's pulse side by side. None of it is a list of nouns, which is
 *  what the first two attempts at this screen were.
 *
 *  Every word and number comes from a declaration or a live row. agent.ts
 *  composes the prose; this file lays it out.
 */
import { useEffect, useState, type CSSProperties } from "react";
import { api, currentRole } from "../api";
import { facilityAsks, initialsOf, line, type Loaded } from "../agent";
import { NAME } from "../brand";
import { Icon } from "../icons";
import { Garland } from "../auth/Bloom";
import type { Recent } from "../loops";
import { waited } from "../messages";
import { Loading } from "../parts";
import type { CalendarRow, Catalogue, QueueRow, TaskRow } from "../types";
import { Cards } from "../view/Cards";
import { step } from "../view/cells";
import { cardHash, dateOf, EVERYONE, forRole, stack } from "../view/day";
import { fields } from "../view/View";
import { human, title, NO_NAME } from "../words";

/** How many names a flow column shows before it says how many more. */
const SHOWN = 4;

/** What a full bar means.
 *
 *  Not "the busiest station", which is what it was: on a quiet morning the
 *  busiest station might hold two people, and scaling to it painted two
 *  people the same red as twenty. The bar would be at its loudest every
 *  day, which is the same as having no colour at all.
 *
 *  So the scale has a floor. Below it the line is read against a steady
 *  idea of a heavy queue and most of the card stays green; above it the
 *  busiest station sets the scale and the comparison between stations is
 *  what the colour shows. Five is a judgement about a primary health
 *  centre, not a declared capacity -- no bundle declares one -- so it is
 *  written here, once, where it can be argued with.
 */
const HEAVY = 5;

/** How full one station's bar runs, and how loaded it is from 0 to 1. A
 *  station with anybody in it keeps a visible floor on its width, so "one
 *  person waiting" never draws as an empty bar. */
const scaleOf = (busiest: number) => Math.max(busiest, HEAVY);

const load = (n: number, busiest: number): number =>
  n === 0 ? 0 : Math.min(1, n / scaleOf(busiest));

const fill = (n: number, busiest: number): number =>
  n === 0 ? 0 : Math.max(12, Math.round(load(n, busiest) * 100));

/** The time, and the day it belongs to. Nothing else.
 *
 *  It ticks, because a clock that is drawn once and then left alone is a
 *  clock that is wrong for most of the shift, and a wrong clock in the
 *  corner of a workspace is worse than an empty corner. Once a minute is
 *  enough for a wall clock and costs nothing.
 */
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
  // The calendar is in `loaded` only if this caller holds its capability and
  // the kernel answered, so a caller without it has no card and no empty frame.
  const cal = loaded.find((l) => l.decl.kind === "calendar");
  const today = cal ? dateOf(cal.result.generated_at) : "";
  // The visits falling due in the coming year, read as a range; late ones the
  // kernel draws on today. Nothing is kept past this render.
  const calId = cal?.decl.id;
  const [owed, setOwed] = useState<CalendarRow[] | "failed" | null>(null);
  useEffect(() => {
    let live = true;
    setOwed(null);
    if (calId && today) api.view(calId, undefined, undefined, { from: today, to: step("day", today, 365) })
      .then((r) => live && setOwed((r.rows ?? []) as CalendarRow[]), () => live && setOwed("failed"));
    return () => { live = false; };
  }, [calId, today]);
  // The stack opens on the viewer's own role; the line under it says how much
  // belongs to others and is the way to see it.
  const [everyone, setEveryone] = useState(false);
  const all = Array.isArray(owed) ? stack(owed, today, EVERYONE) : [];
  const mine = forRole(all, currentRole());
  // A viewer who owns nothing is shown everyone's, and told so: the stack is
  // never empty while somebody is owed, and never says nobody is. That viewer
  // is already seeing everything, so the toggle below is hidden for them: it
  // could only offer them their own, empty, list.
  const noneMine = all.length > 0 && mine.length === 0;
  const cards = everyone || noneMine ? all : mine;
  const others = all.length - mine.length;

  if (loading && !loaded.length) return <Loading what="the facility" shape="blocks" rows={4} />;
  // The greeting and the centre's own name were a line above the heading --
  // "Primary health centre · Monday 2 November · good afternoon". A person
  // standing in the building knows all three, and the date is now part of
  // the clock, where it is a fact rather than a label.
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
  const busiest = columns.reduce((m, c) => Math.max(m, c.people.length), 0);

  return (
    <div className="home">
      <section className="hero">
        {/* The owner's flower tracing, the garland, framing the card: the vine up the
            left edge and the spray in the bottom right. Still, and behind everything. */}
        <Garland kind="vine" />
        <Garland kind="spray" />
        {/* WHAT WAS HERE: "Session", a time, a progress bar and "2.4 h
            left" -- a countdown through a 9-to-2 window this product never
            declared anywhere. It invented a fact, and when the invented
            window ran out the corner of the home screen said "session
            closed" over a centre with eight people still in it. A clock
            cannot be wrong about what it is for. */}
        <h2 className="hero-h">
          {rows.length === 1 ? "1 patient is here." : `${rows.length} patients are here.`}<br />
          <span>
            {tasks.length === 0
              ? (done === 1 ? "1 is finished." : `${done} are finished.`)
              : `${tasks.reduce((n, t) => n + t.count, 0)} ${
                  tasks.reduce((n, t) => n + t.count, 0) === 1 ? "needs" : "need"} you.`}
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

      {columns.length > 0 && (
        <div className="card">
          <div className="card-h">
            <div className="card-t">Patient flow</div>
          </div>
          <div className="flow">
            {columns.map((c) => (
              <div className={`fl-col${c.jam ? " jam" : ""}`} key={c.station}>
                <div className="fl-h">
                  <span className="fl-n">{title(c.station)}</span>
                  <span className="fl-c">{c.people.length}</span>
                </div>
                {/* A STATIC BAR, NOT A SWEEP. This used to be a gradient
                    running left to right on a 2.4s loop, in every station,
                    for as long as the screen was open: five things moving
                    under the one card a person reads to find out where the
                    line is stuck. Motion means something changed, and
                    nothing was changing.
                    It now fills in proportion to the busiest station and
                    takes its colour from the same ratio, so the shape of
                    the queue is readable from across the room and sitting
                    still. `--fill` drives both. */}
                <div className="fl-rail" aria-hidden="true">
                  <i style={{
                    "--fill": `${fill(c.people.length, busiest)}%`,
                    "--load": load(c.people.length, busiest),
                  } as CSSProperties} />
                </div>
                {c.people.length === 0
                  ? <div className="fl-e">Clear</div>
                  : c.people.slice(0, SHOWN).map((p) => (
                      <button
                        className={`fl-p${p.alert ? " alert" : ""}${p.name === NO_NAME ? " none" : ""}`}
                        key={p.thread}
                        onClick={() => onOpenThread(p.thread)}
                      >
                        {p.token && <span className="ticket fl-tk" title="Token" aria-label={`Token ${p.token}`}><Icon name="ticket" className="i tk-i" />{p.token}</span>}
                        <span className="fl-nm">{p.name}</span>
                        {/* SC 1.4.1: the mark is the second carrier of the flag
                            and the declared flag is its name. */}
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
                    Longest wait{c.oldest && waited(c.oldest) ? ` · ${waited(c.oldest)}` : ""}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {cal && (
        <div className="card">
          <div className="card-h"><div className="card-t">Next visits</div></div>
          {owed === "failed" ? (
            <div className="state-empty">Could not load visits</div>
          ) : cards.length === 0 ? (
            owed && <div className="state-empty">No visits coming up</div>
          ) : (
            <>
              {noneMine && <div className="stk-note">{`No visits for you. Showing ${others} for others.`}</div>}
              <Cards key={everyone || noneMine ? "all" : "mine"} rows={cards} now={today} roleName={(r) => cat.vocabulary?.role_titles?.[r] ?? r}
                     nameOf={(s) => fields(cal.decl, { station: null, subject: s }).name}
                     /* The register's own declared columns, the first two values: the
                        renderer may not name a column (age, village), so it takes
                        what the declaration offers. Taken before they are joined. */
                     metaOf={(s) => fields(cal.decl, { station: null, subject: s }).facts.slice(0, 2).join(", ")}
                     onOpen={(r) => { location.hash = cardHash(r); }} />
            </>
          )}
          {/* Outside the empty-or-cards branch, so it does not depend on what is drawn. Hidden when
              the viewer owns nothing (noneMine): they already see everything. */}
          {owed !== "failed" && !noneMine && others > 0 && (
            <button type="button" className="stk-more" onClick={() => setEveryone(!everyone)}>
              {everyone ? "Show only mine" : `${others} more for others. Show all`}
            </button>
          )}
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
                <span>{rows.length === 1 ? "1 patient" : `${rows.length} patients`}</span>
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
