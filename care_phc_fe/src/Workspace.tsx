import { useEffect, useState } from "react";

import Directory from "./components/Directory";
import Queue from "./components/Queue";
import Spotlight from "./components/Spotlight";
import ThreadPanel from "./components/ThreadPanel";
import {
  BUNDLE_LABELS, BUNDLE_SUBS, STATION_LABELS, stateLabel, threadFor,
  type Facility, type PatientRow,
} from "./data";
import "./theme.css";

/** The workspace shell: sidebar, topbar, palette, views.
 *
 *  This owns the chrome because we render on our own plugin routes rather than
 *  inside a care_fe tab. That is a real trade: users can cross back into CARE's
 *  own navigation and the seam will show. It is the cost of the prototype's
 *  workspace being a workspace. */

const NAV: [string, string, string][] = [
  ["queue", "☰", "Queue"],
  ["directory", "◎", "Patient directory"],
];

const TITLES: Record<string, [string, string]> = {
  queue: ["Queue", "Patients registered or booked today"],
  directory: ["Patient directory", "All patients in this facility"],
  chat: ["Chat", "Patient-scoped thread"],
};

export function Workspace({
  facility,
  bundle,
  onBundleChange,
}: {
  facility: Facility;
  bundle: string;
  /** Only supplied where switching cadre is meaningful, which is the harness.
   *  In care_fe the cadre is whatever bundles the signed-in user holds. */
  onBundleChange?: (b: string) => void;
}) {
  const [view, setView] = useState("queue");
  const [open, setOpen] = useState<PatientRow | null>(null);
  const [spot, setSpot] = useState(false);
  const [menu, setMenu] = useState(false);
  const [dark, setDark] = useState(false);
  const [tab, setTab] = useState("all");
  const [dirQ, setDirQ] = useState("");
  const [dirCat, setDirCat] = useState("all");
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSpot(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openPatient = (p: PatientRow) => {
    setOpen(p);
    setView("chat");
    setPicked(null);
  };

  const today = facility.patients.filter((p) => p.today).length;
  const [title, sub] =
    view === "chat" && open
      ? [open.name, `${open.station ? STATION_LABELS[open.station] : "Complete"} · ${stateLabel(open)}`]
      : TITLES[view];

  return (
    <div className="app phc">
      <aside className="sb">
        <div className="sb-top">
          <div className="brand-mark">✦</div>
          <div>
            <div className="brand-n">PHC Yadiki</div>
            <div className="brand-s">Anantapur · Workspace</div>
          </div>
        </div>
        <div className="sb-pad">
          <button className="sb-btn ghost" onClick={() => setSpot(true)}>
            ⌕ Search<span className="kbd" style={{ marginLeft: "auto" }}>⌘K</span>
          </button>
        </div>
        <div className="sb-nav">
          {NAV.map(([k, icon, label]) => (
            <button
              key={k}
              className={`nv${view === k ? " on" : ""}`}
              onClick={() => setView(k)}
            >
              <span style={{ width: 14 }}>{icon}</span>
              {label}
              <span className="ct">{k === "queue" ? today : facility.patients.length}</span>
            </button>
          ))}
        </div>

        <div className="sb-sec">Open</div>
        <div className="sb-list">
          {open ? (
            <button
              className={`th${view === "chat" ? " on" : ""}`}
              onClick={() => setView("chat")}
            >
              <span>◍</span>
              <span className="th-n">{open.name}</span>
            </button>
          ) : (
            <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--gray-400)", lineHeight: 1.5 }}>
              No patient open. Open one from the queue or the directory.
            </div>
          )}
        </div>

        <div className="sb-foot">
          {menu && onBundleChange && (
            <div className="menu">
              {Object.keys(facility.bundles).map((b) => (
                <button
                  key={b}
                  className={`th${b === bundle ? " on" : ""}`}
                  onClick={() => {
                    onBundleChange(b);
                    setMenu(false);
                  }}
                >
                  <span className="th-n">{BUNDLE_LABELS[b] ?? b}</span>
                  <span style={{ fontSize: 9.5, color: "var(--gray-400)" }}>
                    {facility.bundles[b].length}
                  </span>
                </button>
              ))}
            </div>
          )}
          <button className="rolebtn" onClick={() => onBundleChange && setMenu(!menu)}>
            <span className="rb-av">{(BUNDLE_LABELS[bundle] ?? bundle).slice(0, 2).toUpperCase()}</span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className="rb-n">{BUNDLE_LABELS[bundle] ?? bundle}</span>
              <div className="rb-s">{BUNDLE_SUBS[bundle] ?? ""}</div>
            </span>
            {onBundleChange && <span style={{ color: "var(--ink-3)" }}>⌄</span>}
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div>
            <div className="tb-title">{title}</div>
            <div className="tb-sub">{sub}</div>
          </div>
          <button className="pill" style={{ marginLeft: "auto" }} onClick={() => setSpot(true)}>
            ⌕ Search or ask<span className="kbd">⌘K</span>
          </button>
          <button className="icon-btn" onClick={() => setDark(!dark)} title="Theme">
            {dark ? "☀" : "☾"}
          </button>
        </div>

        <div className="view">
          <div className="wrap">
            {view === "queue" && (
              <Queue patients={facility.patients} tab={tab} onTab={setTab} onOpen={openPatient} />
            )}
            {view === "directory" && (
              <Directory
                patients={facility.patients} query={dirQ} cat={dirCat}
                onQuery={setDirQ} onCat={setDirCat} onOpen={openPatient}
              />
            )}
            {view === "chat" &&
              (open ? (
                <>
                  <ThreadPanel
                    thread={threadFor(open, bundle, facility)}
                    bundleLabel={BUNDLE_LABELS[bundle] ?? bundle}
                    onAction={(a) => setPicked(a.tool)}
                  />
                  {picked && (
                    <p style={{ color: "var(--ink-3)", fontSize: 12.5, marginTop: 14 }}>
                      Would call <code>{picked}</code> on the guard. It opens CARE's questionnaire
                      for this operation, which is not wired yet.
                    </p>
                  )}
                </>
              ) : (
                <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
                  No patient open.
                </div>
              ))}
          </div>
        </div>
      </div>

      {spot && (
        <Spotlight
          patients={facility.patients}
          onPatient={openPatient}
          onView={setView}
          onClose={() => setSpot(false)}
        />
      )}
    </div>
  );
}

export default Workspace;
