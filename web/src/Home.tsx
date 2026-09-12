/** Home: the shift, at a glance, from one read of each declared view.
 *
 *  Every number on this screen is a sum over the queue view's own groups or a
 *  metric from the dashboard view. There is no session clock, because no
 *  declaration carries opening hours and 09:00 would be the PHC's 09:00. There
 *  is no per-role shift prose, because that was the prototype's PHC writing.
 *  What is left is true under any bundle.
 */
import { Icon } from "./icons";
import type { Catalogue, MetricValue, QueueRow, ViewDecl, ViewResult } from "./types";
import { human, title } from "./ui";
import type { Recent } from "./Shell";

export function Home({
  cat, role, queues, dashboards, recent, onOpenThread, onGo,
}: {
  cat: Catalogue;
  role: string;
  queues: { decl: ViewDecl; result: ViewResult }[];
  dashboards: { decl: ViewDecl; result: ViewResult }[];
  recent: Recent[];
  onOpenThread: (id: string) => void;
  onGo: (hash: string) => void;
}) {
  const first = queues[0];
  const rows = (first?.result.rows ?? []) as QueueRow[];
  const groups = (first?.result.groups ?? []).filter((g) => g.key !== null);
  const heaviest = groups.reduce((a, b) => (b.count > (a?.count ?? -1) ? b : a), groups[0]);
  const workflow = Object.values(cat.workflows ?? {}).find((w) => w.id === first?.decl.workflow)
    ?? Object.values(cat.workflows ?? {})[0];

  const flagged = rows.filter((r) => Object.values(r.badges ?? {}).some((s) => s === "crit" || s === "warn"));

  return (
    <div className="home">
      <div className="hero">
        <svg className="hero-mark" viewBox="0 0 24 24"><use href="#i-mark-lg" /></svg>
        <div className="hero-eye">
          {role === "demo" ? "Every capability" : human(role)} · {cat.manifest?.title ?? "Workspace"}
        </div>
      </div>

      {first && (
        <div className="card">
          <div className="card-h">
            <div>
              <div className="eyebrow">Live</div>
              <div className="card-t" style={{ marginTop: 2 }}>{workflow?.title ?? "The line"}</div>
            </div>
          </div>
          <div className="flow">
            {groups.map((g) => {
              const here = rows.filter((r) => r.station === g.key || (r.flags ?? []).includes(String(g.key)));
              const jam = heaviest && g.key === heaviest.key && heaviest.count > 1;
              return (
                <div className={`fl-col${jam ? " jam" : ""}`} key={String(g.key)}>
                  <div className="fl-h">
                    <div className="fl-n">{title(String(g.key))}</div>
                    <div className="fl-c">{g.count}</div>
                  </div>
                  <div className="fl-rail"><i /></div>
                  {here.length ? (
                    here.map((r) => (
                      <div
                        key={r.thread}
                        className={`fl-p${Object.values(r.badges ?? {}).includes("crit") ? " alert" : ""}`}
                        onClick={() => onOpenThread(r.thread)}
                      >
                        {/* A station's own first letter. An icon per station
                            would be a picture of the PHC in the renderer. */}
                        <span className="fl-av">{String(g.key).slice(0, 1).toUpperCase()}</span>
                        <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {nameOf(r, first.decl)}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="fl-e">nobody</div>
                  )}
                  {jam && <div className="fl-jam"><Icon name="alert" size="sm" />Heaviest</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="hgrid">
        <div className="card">
          <div className="card-h">
            <div className="card-t">Flagged on today's line</div>
            <span className={`badge ${flagged.length ? "b-warn" : "b-ok"} ml-auto`}>
              {flagged.length || "clear"}
            </span>
          </div>
          <div className="att">
            {flagged.length ? (
              flagged.slice(0, 6).map((r) => (
                <div className="at" key={r.thread} onClick={() => onOpenThread(r.thread)}>
                  <span className={`at-ic ${Object.values(r.badges).includes("crit") ? "red" : "amb"}`}>
                    <Icon name="alert" size="sm" />
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <div className="at-t">{nameOf(r, first?.decl)}</div>
                    <div className="at-s">
                      {Object.keys(r.badges).map(human).join(", ")} ·{" "}
                      {r.station ? title(r.station) : "Complete"}
                    </div>
                  </span>
                  <span className="at-go">Open →</span>
                </div>
              ))
            ) : (
              <div style={{ padding: "30px 15px", textAlign: "center", color: "var(--ink-3)", fontSize: 12.5 }}>
                Nothing flagged.
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {dashboards.map(({ decl, result }) => (
            <div className="card" key={decl.id}>
              <div className="card-h">
                <div className="card-t">{decl.title ?? title(decl.id)}</div>
                <button className="cq ml-auto" onClick={() => onGo(`#/views/${decl.id}`)}>Open</button>
              </div>
              <div className="pulse">
                {(result.rows as MetricValue[]).map((m) => <Pulse key={m.metric} m={m} cat={cat} />)}
              </div>
            </div>
          ))}

          {recent.length > 0 && (
            <div className="card">
              <div className="card-h"><div className="card-t">Recent</div></div>
              <div className="cont">
                {recent.slice(0, 4).map((t) => (
                  <div className="cn" key={t.id} onClick={() => onOpenThread(t.id)}>
                    <div className="cn-n">{t.name}</div>
                    <div className="cn-s">{t.id}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** A metric with a denominator is a proportion and draws as a split bar; one
 *  without is a count and draws as a number. The API returns one window, so
 *  there is no sparkline: drawing a trend from a single figure would be a
 *  picture of nothing. */
function Pulse({ m, cat }: { m: MetricValue; cat: Catalogue }) {
  const label = m.title ?? cat.metrics?.[m.metric]?.title ?? human(m.metric);
  const has = m.denominator !== null && m.denominator !== undefined && m.denominator > 0;
  const pct = has ? (m.numerator / (m.denominator as number)) * 100 : 0;
  return (
    <div>
      <div className="pu-r">
        <span>{label}</span>
        <span>{has ? `${m.denominator} in the ${m.window}` : m.window}</span>
      </div>
      <div className="pu-v">
        {m.unit === "percent" ? (m.value ?? 0).toFixed(1) : m.value}
        <small>{m.unit === "percent" ? "%" : m.unit === "count" ? "" : m.unit}</small>
      </div>
      {has && (
        <>
          <div className="split">
            <i style={{ width: `${pct}%`, background: "var(--ink)" }} />
            <i style={{ width: `${100 - pct}%`, background: "var(--gray-300)" }} />
          </div>
          <div className="leg">
            <span><i className="dt" style={{ background: "var(--ink)" }} />{m.numerator}</span>
            <span>
              <i className="dt" style={{ background: "var(--gray-300)" }} />
              {(m.denominator as number) - m.numerator}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

/** The queue view already said which column is the headline. */
function nameOf(r: QueueRow, decl: ViewDecl | undefined): string {
  const cols = decl?.columns?.length ? decl.columns : Object.keys(r.subject ?? {});
  for (const k of cols) {
    const v = r.subject?.[k];
    if (typeof v === "string" && v) return v;
  }
  return r.thread;
}
