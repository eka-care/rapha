/** §7 and §2.3: the subject, and every visit it has had.
 *
 *  What joins two encounters is the workflow's `spine:` declaration, never a
 *  word in this file. A bundle that declares none never reaches this screen.
 *
 *  The owner's own brief for it: "when a visit is over it gets compacted into
 *  a dated collation; on click it shows all actions endured in that visit."
 *  So a visit is a closed card, and opening one reads that thread rather than
 *  pre-loading every visit a person has ever had.
 */
import { Lotus } from "../abha/Lotus";
import { useEffect, useState } from "react";
import { initialsOf } from "../agent";
import { api, useAsync } from "../api";
import { displayFor, questionnaire } from "../declarations";
import { Icon } from "../icons";
import { header, queueViewFor, valuesOf } from "../messages";
import { Failed, Loading } from "../parts";
import { Arc } from "../thread/Arc";
import { atOf, scaleOf, withView } from "../view/day";
import { Grid } from "../view/Grid";
import { ownRows, spanTitle, step, todayOf, type Scale } from "../view/cells";
import type { Catalogue, SubjectView, ThreadView } from "../types";
import { wrote } from "../types";
import { human, title } from "../words";

type Tab = "care" | "overview" | "encounters" | "timeline";

export function Patient({ id, cat, onOpenThread }: {
  id: string; cat: Catalogue; onOpenThread: (thread: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.subject(id), [id]);
  // §2.3: the encounters are what somebody came here for, not the demographics.
  // A PERSON WITH SOMETHING OPEN OPENS ON IT. A pregnancy being followed is
  // the reason this record is being read, and it outranks the list of
  // visits that a person with nothing open has nothing but.
  const [tab, setTab] = useState<Tab | null>(null);

  if (loading) return <Loading what="this patient" shape="blocks" rows={3} />;
  if (error) return <Failed error={error} what="open this patient" onRetry={reload} />;
  const view = data!;
  // The Care tab exists only for somebody who has an episode, because a tab
  // that is always empty for most of a register is furniture. A person with
  // one opens on it; everybody else opens where they always did.
  // A woman with none still has the tab, which says so in a sentence; it
  // simply does not open on it.
  const tabs: Tab[] = view.episodes.length
    ? ["care", "encounters", "overview", "timeline"]
    : ["encounters", "care", "overview", "timeline"];
  const open_tab: Tab = tab ?? tabs[0];

  // Which fields name a subject and which describe one is the queue view's own
  // `columns:` declaration, and messages.header() is where that rule already
  // lives. This screen used to pick the three it wanted -- age, sex and
  // village -- which made it a second place deciding what a subject is, and
  // wrong for any bundle whose subject is not a village outpatient.
  const head = header(
    { id, workflow: "", subject: view.subject, flags: [] } as unknown as ThreadView,
    queueViewFor(cat, Object.values(cat.workflows ?? {})[0]?.id),
    displayFor,
  );
  const name = head.name;
  const meta = head.meta;
  const identity = head.identity;
  const open = view.encounters.find((e) => e.status !== "completed");

  return (
    <div className="home">
      <section className="card">
        <div className="pt-head">
          <span className="avatar">{initialsOf(name)}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="pt-name" style={{ fontSize: 18 }}>{name}</div>
            <div className="pt-meta">{meta.join(", ")}</div>
            <div className="pt-chips">
              {identity && (
                <span className="id-badge">
                  <Lotus className="id-lotus" />
                  <span className="id-lab">{identity.label}</span>
                  <span className="id-val">{identity.value}</span>
                </span>
              )}
              <span className="badge b-mute">
                {view.encounters.length === 1 ? "1 visit" : `${view.encounters.length} visits`}
              </span>
              {open && (
                <button className="btn btn-b" style={{ padding: "5px 11px", fontSize: 11.5 }}
                  onClick={() => onOpenThread(open.thread)}>
                  Open current encounter
                </button>
              )}
            </div>
          </div>
        </div>
        <div className="qtabs" style={{ margin: "12px 14px 14px" }} role="tablist">
          {tabs.map((t) => (
            <button key={t} role="tab" aria-selected={open_tab === t}
              className={`qtab${open_tab === t ? " on" : ""}`} onClick={() => setTab(t)}>
              {t === "care" ? "Care" : title(t)}
            </button>
          ))}
        </div>
      </section>

      {open_tab === "care" && <Care view={view} id={id} name={name} />}
      {open_tab === "encounters" && <Encounters view={view} cat={cat} onOpenThread={onOpenThread} />}
      {open_tab === "overview" && <Overview view={view} />}
      {open_tab === "timeline" && <Timeline view={view} onOpenThread={onOpenThread} />}
    </div>
  );
}

/** Her course of care: the shared calendar grid over HER OWN episodes, then the
 *  plain list of each episode's visits. The rows are made here from what her
 *  record already loaded; nothing is asked of the centre and nothing is kept.
 *  The scale and the date are in the address, so a card from the home page
 *  (`?at=`) lands on the month it names, and back and reload keep the place. */
function Care({ view, id, name }: { view: SubjectView; id: string; name: string }) {
  const [hash, setHash] = useState(() => location.hash);
  useEffect(() => {
    const on = () => setHash(location.hash);
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  if (!view.episodes.length) {
    return <div className="state-empty">Nothing is booked for her yet.</div>;
  }
  // The kernel's date, the same source the facility calendar takes, so the
  // two screens cannot disagree about what day it is.
  const today = todayOf(view.generated_at, new Date().toISOString().slice(0, 10));
  const scale = scaleOf(hash);
  const anchor = atOf(hash) || today;
  const goTo = (change: Parameters<typeof withView>[1]) => { location.hash = withView(location.hash, change).replace(/^#/, ""); };
  const rows = ownRows(view.episodes, id, view.subject);
  const SCALES: { scale: Scale; label: string }[] = [
    { scale: "week", label: "Week" }, { scale: "month", label: "Month" }, { scale: "year", label: "Year" },
  ];
  return (
    <>
      <section className="cal-main" aria-label="Her dates">
        <div className="cal-bar-tools">
          <div className="cal-nav" data-scale={scale}>
            <button type="button" className="gr-arrow" aria-label={`Previous ${scale}`} onClick={() => goTo({ at: step(scale, anchor, -1) })}>
              <Icon name="chev" className="i" />
            </button>
            <button type="button" className="gr-arrow gr-next" aria-label={`Next ${scale}`} onClick={() => goTo({ at: step(scale, anchor, 1) })}>
              <Icon name="chev" className="i" />
            </button>
            <button type="button" className="cal-chip" onClick={() => goTo({ at: "" })}>Today</button>
          </div>
          <h2 className="cal-title">{spanTitle(scale, anchor)}</h2>
          <div className="cal-scales" role="group" aria-label="Scale">
            {SCALES.map((s) => (
              <button key={s.scale} type="button" className="cal-chip" aria-pressed={scale === s.scale} onClick={() => goTo({ scale: s.scale })}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <Grid
          scale={scale} anchor={anchor} today={today} rows={rows} nameOf={() => name} own
          onPickDay={(d) => goTo({ at: d })} onAnchor={(d) => goTo({ at: d })}
        />
      </section>
      <Arc episodes={view.episodes} />
    </>
  );
}

function Overview({ view }: { view: SubjectView }) {
  const rows = Object.entries(view.subject)
    .filter(([k, v]) => !/(^|_)id$|_by$|_date$/.test(k) && v !== null && v !== undefined && v !== "");
  return (
    <div className="card">
      <div className="card-h"><div className="card-t">Details</div></div>
      <div style={{ padding: "10px 14px" }}>
        {rows.map(([k, v]) => (
          <div className="kv" key={k}><span>{title(human(k))}</span><b>{String(v)}</b></div>
        ))}
      </div>
    </div>
  );
}

function Encounters({ view, cat, onOpenThread }: {
  view: SubjectView; cat: Catalogue; onOpenThread: (t: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(
    view.encounters.find((e) => e.status !== "completed")?.thread ?? view.encounters[0]?.thread ?? null);
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {view.encounters.map((e) => (
        <Collation
          key={e.thread} encounter={e} cat={cat}
          open={open === e.thread}
          onToggle={() => setOpen(open === e.thread ? null : e.thread)}
          onOpenThread={onOpenThread}
        />
      ))}
    </div>
  );
}

function Collation({ encounter, cat, open, onToggle, onOpenThread }: {
  encounter: SubjectView["encounters"][number];
  cat: Catalogue; open: boolean;
  onToggle: () => void; onOpenThread: (t: string) => void;
}) {
  // Read the visit only when it is opened.
  const { data } = useAsync(
    () => (open ? api.thread(encounter.thread) : Promise.resolve(null)), [open, encounter.thread]);
  const blocks = data ? committed(data, cat) : [];

  return (
    <section className="visit" data-open={open}>
      <button className="visit__head" onClick={onToggle} aria-expanded={open}>
        <span className="visit__chev" data-open={open} aria-hidden="true"><Icon name="chev" className="i sm" /></span>
        <span className="visit__when">{when(encounter.opened_at)}</span>
        <span className="visit__did">{encounter.did.map((d) => d.title).join(" · ") || "Nothing recorded"}</span>
        {encounter.status !== "completed" && <span className="badge b-warn">Open</span>}
        {encounter.station && <span className="badge b-mute">{title(encounter.station)}</span>}
      </button>

      {open && (
        <div className="visit__body">
          {!data ? (
            <Loading what="this visit" shape="lines" rows={3} />
          ) : blocks.length === 0 ? (
            <div className="fl-e">Nothing was recorded on this visit.</div>
          ) : (
            blocks.map((c) => (
              <div className="visit__block" key={c.id}>
                <div className="eyebrow visit__op">{c.title}</div>
                {c.values.map((v) => (
                  <div className={`kv${v.crit ? " crit" : ""}`} key={v.link_id}>
                    <span>{v.label}</span><b>{v.value}</b>
                  </div>
                ))}
              </div>
            ))
          )}
          <button className="btn btn-g" onClick={() => onOpenThread(encounter.thread)}>
            Open this visit
          </button>
        </div>
      )}
    </section>
  );
}

/** §26: longitudinal, not conversational. */
function Timeline({ view, onOpenThread }: { view: SubjectView; onOpenThread: (t: string) => void }) {
  return (
    <div style={{ display: "grid", gap: 14 }}>
      {view.encounters.map((e) => (
        <div key={e.thread} style={{ display: "grid", gap: 6 }}>
          <div className="eyebrow">{when(e.opened_at)}</div>
          <div className="card">
            <div style={{ padding: "12px 14px", display: "grid", gap: 4 }}>
              {e.did.length === 0
                ? <div className="fl-e">Nothing was recorded on this visit.</div>
                : e.did.map((d) => <div className="t-body" key={d.operation}>{d.title}</div>)}
            </div>
            <div className="card-h" style={{ borderBottom: "none", borderTop: "1px solid var(--color-border-subtle)" }}>
              <button className="btn btn-g" onClick={() => onOpenThread(e.thread)}>Open this visit</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function committed(thread: ThreadView, cat: Catalogue) {
  const ctx = { operations: cat.operations ?? {}, schema: questionnaire, badges: {}, display: displayFor };
  return (thread.audit ?? [])
    .filter((a) => wrote(a.outcome))
    .map((a) => ({
      id: a.id,
      title: ctx.operations[a.operation]?.title ?? human(a.operation),
      values: valuesOf(ctx, a.operation, a.payload),
    }))
    .filter((c) => c.values.length);
}

const when = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
      : "Undated";
