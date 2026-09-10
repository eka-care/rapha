import { useEffect, useMemo, useRef, useState } from "react";

import { STATION_LABELS, type PatientRow } from "../data";

/** ⌘K. Search is the default surface and create is the exception.
 *
 *  The empty state is the point of this component, not a fallback: it is where
 *  addendum §B's rule becomes visible. Registering is offered only after a
 *  search has missed, it is never pre-filled, and it says plainly that the
 *  record cannot be undone. */

type Row =
  | { type: "ask"; n: string; m: string }
  | { type: "patient"; n: string; m: string; p: PatientRow }
  | { type: "cmd"; n: string; m: string; view: string };

const CMDS: Row[] = [
  { type: "cmd", view: "queue", n: "Go to Queue", m: "Patients today by station" },
  { type: "cmd", view: "directory", n: "Go to Patient directory", m: "All patients in this facility" },
];

const isAsk = (q: string) =>
  /\?|^(how|what|which|who|when|why|show|list|count|find all|any )/i.test(q) && q.length > 4;

export function Spotlight({
  patients, onPatient, onView, onClose,
}: {
  patients: PatientRow[];
  onPatient: (p: PatientRow) => void;
  onView: (view: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);

  const rows = useMemo<Row[]>(() => {
    const lo = q.trim().toLowerCase();
    const out: Row[] = [];
    if (lo && isAsk(q)) out.push({ type: "ask", n: q, m: "Ask the agent. Not built in Phase 0" });
    // Tolerant of the actual mess: transliteration, no fixed surname order,
    // shared household phones, approximate ages.
    const hits = lo
      ? patients.filter((p) =>
          p.name.toLowerCase().includes(lo) || p.phone.includes(lo) ||
          (p.abha ?? "").includes(lo) || p.village.toLowerCase().includes(lo) ||
          String(p.token ?? "") === lo)
      : patients.filter((p) => p.today);
    hits.forEach((p) =>
      out.push({
        type: "patient", p, n: p.name,
        m: `${p.age}${p.sex} · ${p.village} · ${p.station ? STATION_LABELS[p.station] : "Complete"}`,
      }));
    CMDS.filter((c) => !lo || c.n.toLowerCase().includes(lo)).forEach((c) => out.push(c));
    return out;
  }, [q, patients]);

  useEffect(() => setSel(0), [q]);

  const run = (r: Row) => {
    if (r.type === "patient") onPatient(r.p);
    else if (r.type === "cmd") onView(r.view);
    onClose();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return onClose();
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, rows.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && rows[sel]) run(rows[sel]);
  };

  const cur = rows[sel];
  let lastGroup = "";

  return (
    <div className="ov phc" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="spot" onKeyDown={onKey}>
        <div className="spot-in">
          <span style={{ color: "var(--gray-400)", fontSize: 17 }}>⌕</span>
          <input
            ref={input} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search patients, jump to a view, or ask the agent"
          />
        </div>

        {q.trim() && rows.length === 0 ? (
          <div style={{ padding: "38px 22px", textAlign: "center" }}>
            <p style={{ fontSize: 12.5, margin: "0 0 14px", lineHeight: 1.6, color: "var(--ink-3)" }}>
              No patient matches “<b style={{ color: "var(--ink)" }}>{q}</b>”.
              <br />
              Registering creates a permanent record that cannot be undone, only deprecated.
            </p>
            <button className="btn btn-b" style={{ margin: "0 auto" }} onClick={onClose}>
              Register new patient
            </button>
          </div>
        ) : (
          <div className="spot-body">
            <div className="spot-list">
              {rows.map((r, i) => {
                const g = r.type === "ask" ? "Ask the agent"
                  : r.type === "patient" ? (q.trim() ? "Patients" : "Today's queue") : "Go to";
                const head = g !== lastGroup ? ((lastGroup = g), g) : null;
                return (
                  <div key={`${r.type}-${r.n}-${i}`}>
                    {head && <div className="spot-sec">{head}</div>}
                    <button
                      className={`sr${i === sel ? " sel" : ""}`}
                      onMouseEnter={() => setSel(i)}
                      onClick={() => run(r)}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div className="sr-n">{r.n}</div>
                        <div className="sr-m">{r.m}</div>
                      </div>
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="spot-prev">
              {cur?.type === "patient" ? (
                <>
                  <div className="pt-name">{cur.p.name}</div>
                  <div className="pt-meta">
                    {cur.p.age}
                    {cur.p.sex} · {cur.p.village} · {cur.p.phone}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "12px 0" }}>
                    <span className="badge b-mute">{cur.p.cat}</span>
                    {cur.p.abha ? (
                      <span className="id-badge">
                        <span className="id-lab">ABHA</span>
                        <span className="id-val">{cur.p.abha}</span>
                      </span>
                    ) : (
                      <span className="badge b-warn">ABHA pending</span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-2)" }}>{cur.p.dx}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 6 }}>
                    Last visit {cur.p.last}
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.6 }}>
                  Disambiguation preview. Age, village and last visit are shown before you
                  open anyone, because shared household phones and transliterated names make
                  two records look alike.
                </div>
              )}
            </div>
          </div>
        )}

        <div className="spot-foot">
          <span><span className="kbd">↑↓</span> navigate</span>
          <span><span className="kbd">↵</span> run</span>
          <span><span className="kbd">esc</span> dismiss</span>
          <span style={{ marginLeft: "auto", color: "var(--rose-ink)", fontWeight: 600 }}>
            Find first · create only on miss
          </span>
        </div>
      </div>
    </div>
  );
}

export default Spotlight;
