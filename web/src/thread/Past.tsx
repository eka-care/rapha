/** The carry forward strip, the trend and the care team: what earlier visits
 *  say about this one. The deciding is all in past.ts, where a check runs it;
 *  this file fetches and draws.
 *
 *  THE KERNEL HAS NO ROUTE FOR "THE VALUES OF AN EARLIER VISIT". It serves a
 *  subject's encounters, and each thread's own audit carries the payloads, so
 *  this reads the earlier threads and takes the values out of them with the
 *  same resolver the thread itself draws with. That is a few requests on a
 *  screen that already made one, and it is honest: nothing is cached across
 *  patients and nothing is invented when a visit is missing.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { displayFor, questionnaire } from "../declarations";
import { valuesOf } from "../messages";
import type { Catalogue, ThreadView } from "../types";
import { human } from "../words";
import {
  carriedForward, covers, heights, series, team, trendable,
  type Catchment, type Visit,
} from "./earlier";

/** How far back to read. A PHC patient can have years of visits and this
 *  screen wants a trend, not an archive. */
const BACK = 6;

export function usePast(thread: ThreadView, cat: Catalogue, spineId: string) {
  const [visits, setVisits] = useState<Visit[]>([]);
  useEffect(() => {
    let alive = true;
    setVisits([]);
    if (!spineId) return;
    void (async () => {
      try {
        const subject = await api.subject(spineId);
        const earlier = subject.encounters
          .filter((e) => e.thread !== thread.id)
          .slice(-BACK);
        const read = await Promise.all(earlier.map((e) =>
          api.thread(e.thread).then((t) => ({ t, when: e.opened_at })).catch(() => null)));
        if (!alive) return;
        setVisits(read.filter((x): x is NonNullable<typeof x> => !!x)
          .map((x) => visitOf(x.t, cat, x.when)));
      } catch {
        if (alive) setVisits([]);        // no spine, or it is this patient's first
      }
    })();
    return () => { alive = false; };
  }, [spineId, thread.id, cat]);
  return visits;
}

/** One visit's committed values, by the operation's own questionnaire. */
export function visitOf(view: ThreadView, cat: Catalogue, when = ""): Visit {
  const ctx = { operations: cat.operations ?? {}, schema: questionnaire, badges: {}, display: displayFor };
  const values = [];
  for (const row of view.audit) {
    if (!/^(committed|confirmed|allowed)/.test(row.outcome)) continue;
    values.push(...valuesOf(ctx, row.operation, row.payload));
  }
  return { thread: view.id, when: when ? day(when) : "Today", values };
}

const day = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/** Under the name: what this visit's own values were last time. */
export function Carry({ now, visits }: { now: Visit; visits: Visit[] }) {
  const rows = carriedForward(now, visits[visits.length - 1] ?? null);
  if (!rows.length) return null;
  return (
    <div className="carry">
      {rows.map((c) => (
        <div className={`cf${c.crit ? " crit" : ""}`} key={c.link_id}>
          <div className="eyebrow">{c.label}</div>
          <div className="cf-r">
            <span className="then">{c.then}</span>
            <span className="arr" aria-hidden="true">→</span>
            <span className="now">{c.now}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

/** In the rail: one value, across the visits that took it. */
export function Trend({ now, visits }: { now: Visit; visits: Visit[] }) {
  const all = [...visits, now];
  const id = trendable(all);
  if (!id) return null;
  const points = series(all, id);
  if (points.length < 2) return null;
  const bars = heights(points);
  const label = all.flatMap((v) => v.values).find((v) => v.link_id === id)?.label ?? id;
  return (
    <div className="card">
      <div className="card-h"><div className="card-t">{label}, over time</div></div>
      <div style={{ padding: "11px 12px" }}>
        <div className="spark">
          {points.map((p, i) => (
            <i key={`${p.when}-${i}`}
               className={`${i === points.length - 1 ? "last" : ""}${p.crit ? " hi" : ""}`}
               style={{ height: `${Math.round(bars[i] * 100)}%` }}
               title={`${p.when} · ${p.value}`} />
          ))}
        </div>
        <div className="sparkx">
          <span>{points[0].when}</span><span>{points[points.length - 1].when}</span>
        </div>
        <div className="prov">
          {points.length} readings a person took and committed
        </div>
      </div>
    </div>
  );
}

/** In the rail: who covers this patient, and who has been near this visit.
 *
 *  The two halves are different kinds of fact and are drawn as such. The
 *  catchment is who is RESPONSIBLE for them between visits -- their ASHA and
 *  the ANM on their sub-centre -- read off the centre's own declaration from
 *  the village already on their record. The record is who actually saw them
 *  today. A centre that declares no catchment draws only the second.
 */
export function Team({ thread, cat, catchment }: {
  thread: ThreadView; cat: Catalogue; catchment?: Catchment | null;
}) {
  const who = covers(catchment, thread.subject);
  const members = team(
    thread.audit,
    (op) => cat.operations?.[op]?.title ?? human(op),
    (actor) => human(actor.replace(/^user:/, "")),
  );
  if (!members.length && !who) return null;
  return (
    <div className="card">
      <div className="card-h"><div className="card-t">Who reaches them</div></div>
      <div style={{ padding: "6px 12px 10px" }}>
        {who && (
          <>
            <div className="team">
              <span className="av">{initials(who.asha || "?")}</span>
              <span style={{ minWidth: 0 }}>
                <b>{who.asha || "Nobody assigned"}</b>
                <span className="team-s">{who.village}</span>
              </span>
              <span className="team-r">ASHA</span>
            </div>
            <div className="team">
              <span className="av">{initials(who.anm)}</span>
              <span style={{ minWidth: 0 }}>
                <b>{who.anm}</b>
                <span className="team-s">{who.area}</span>
              </span>
              <span className="team-r">ANM</span>
            </div>
          </>
        )}
        {members.map((m) => (
          <div className="team" key={m.actor}>
            <span className="av">{initials(m.actor)}</span>
            <span style={{ minWidth: 0 }}>
              <b>{m.role}</b>
              <span className="team-s">{m.did}</span>
            </span>
            <span className="team-r">Today</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const initials = (name: string) =>
  name.split(/[\s._-]+/).slice(0, 2).map((w) => w[0] ?? "").join("").toUpperCase();
