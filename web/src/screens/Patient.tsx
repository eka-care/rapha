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
import { questionnaire } from "../declarations";
import { Icon } from "../icons";
import { valuesOf, type Ctx } from "../messages";
import type { ThreadView } from "../types";
import { Failed, Loading } from "../parts";
import type { Catalogue, SubjectView } from "../types";
import { human, title } from "../words";

type Tab = "overview" | "encounters" | "timeline";

export function Patient({ id, cat, onOpenThread }: {
  id: string;
  cat: Catalogue;
  onOpenThread: (thread: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.subject(id), [id]);
  // Encounters first. §2.3: "The current encounter is always the primary
  // workspace." What a person came here for is the visits, not the demographics.
  const [tab, setTab] = useState<Tab>("encounters");

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
      {tab === "encounters" && <Encounters view={view} cat={cat} onOpenThread={onOpenThread} />}
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

/** §2.3, and the owner's own words: "when a visit is over it gets compacted
 *  into a dated collation; on click it shows all actions endured in that
 *  visit." So a visit is a closed card until somebody opens it, and opening
 *  one reads the thread rather than pre-loading every visit a person has had.
 */
function Encounters({ view, cat, onOpenThread }: { view: SubjectView; cat: Catalogue; onOpenThread: (t: string) => void }) {
  const [open, setOpen] = useState<string | null>(
    view.encounters.find((e) => e.status !== "completed")?.thread ?? view.encounters[0]?.thread ?? null);
  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      {view.encounters.map((e) => (
        <Collation
          key={e.thread}
          encounter={e}
          cat={cat}
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
  cat: Catalogue;
  open: boolean;
  onToggle: () => void;
  onOpenThread: (t: string) => void;
}) {
  // Read the visit only when it is opened. A person with a decade of visits
  // should not fetch a decade to look at one.
  const { data } = useAsync(
    () => (open ? api.thread(encounter.thread) : Promise.resolve(null)),
    [open, encounter.thread]);

  return (
    <section className="visit" data-open={open}>
      <button className="visit__head" onClick={onToggle} aria-expanded={open}>
        <span className="visit__chev" data-open={open} aria-hidden="true"><Icon name="chev" /></span>
        <span className="visit__when">{when(encounter.opened_at)}</span>
        <span className="visit__did">
          {encounter.did.map((d) => d.title).join(" · ") || "Nothing recorded"}
        </span>
        {encounter.status !== "completed" && (
          <span className="status" data-tone="warning">Open</span>
        )}
        {encounter.station && (
          <span className="t-meta u-faint">{human(encounter.station)}</span>
        )}
      </button>

      {open && (
        <div className="visit__body">
          {!data ? (
            <div className="skeleton" style={{ height: 48 }} />
          ) : (
            <>
              {committed(data, cat).map((c) => (
                <div className="visit__block" key={c.id}>
                  <div className="t-micro u-faint visit__op">{c.title}</div>
                  <div className="kv">
                    {c.values.map((v) => (
                      <div className="kv__row" key={v.link_id} data-critical={v.crit}>
                        <span className="kv__label">{v.label}</span>
                        <span className="kv__value">{v.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {committed(data, cat).length === 0 && (
                <div className="t-meta u-faint">Nothing was recorded on this visit.</div>
              )}
              <button className="btn" data-variant="ghost" onClick={() => onOpenThread(encounter.thread)}>
                Open this visit
              </button>
            </>
          )}
        </div>
      )}
    </section>
  );
}

/** Everything this visit actually committed, with the values, labelled by the
 *  questionnaire each operation declares. */
function committed(thread: ThreadView, cat: Catalogue) {
  const ctx: Ctx = { operations: cat.operations ?? {}, schema: questionnaire, badges: {} };
  return (thread.audit ?? [])
    .filter((a) => /^(committed|confirmed|allowed)/.test(a.outcome))
    .map((a) => ({
      id: a.id,
      title: ctx.operations[a.operation]?.title ?? human(a.operation),
      values: valuesOf(ctx, a.operation, a.payload),
    }))
    .filter((c) => c.values.length);
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
