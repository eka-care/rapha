import { STATION_LABELS, stateLabel, type PatientRow } from "../data";

const TABS: [string, string][] = [
  ["all", "All"], ["reception", "Reception"], ["nurse", "Vitals"],
  ["doctor", "Doctor"], ["lab", "Lab"], ["pharmacy", "Pharmacy"], ["done", "Complete"],
];

const at = (p: PatientRow, k: string) =>
  k === "done" ? p.station === null : p.station === k;

export function Queue({
  patients, tab, onTab, onOpen,
}: {
  patients: PatientRow[];
  tab: string;
  onTab: (t: string) => void;
  onOpen: (p: PatientRow) => void;
}) {
  const today = patients.filter((p) => p.today);
  const list = tab === "all" ? today : today.filter((p) => at(p, tab));

  return (
    <div className="phc">
      <div className="qtabs">
        {TABS.map(([k, label]) => (
          <button key={k} className={`qtab${tab === k ? " on" : ""}`} onClick={() => onTab(k)}>
            {label}
            <span className="n">{k === "all" ? today.length : today.filter((p) => at(p, k)).length}</span>
          </button>
        ))}
      </div>

      {list.length ? (
        <div className="qgrid">
          {list.map((p) => (
            <button className="card qc" key={p.name} onClick={() => onOpen(p)}>
              <div className="qc-top">
                <div className="avatar" style={{ width: 34, height: 34, fontSize: 11.5 }}>{p.init}</div>
                <div>
                  <div className="qc-n">{p.name}</div>
                  <div className="qc-m">{p.age}{p.sex} · {p.village}</div>
                </div>
                {p.token && <span className="qc-tok">T{p.token}</span>}
              </div>
              <div className="qc-chips">
                <span className="badge b-blue">
                  {p.station ? STATION_LABELS[p.station] : "Complete"}
                </span>
                <span className="badge b-mute">{stateLabel(p)}</span>
                <span className="badge b-mute">{p.cat}</span>
                {!p.abha && <span className="badge b-warn">ABHA pending</span>}
                {p.flags.includes("vitals.flagged") && <span className="badge b-crit">BP flagged</span>}
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 12.5 }}>
          Nobody at this station right now.
        </div>
      )}
    </div>
  );
}

export default Queue;
