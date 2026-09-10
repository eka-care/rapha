import type { PatientRow } from "../data";

const CATS = ["all", "General", "ANC", "NCD", "TB"];

export function Directory({
  patients, query, cat, onQuery, onCat, onOpen,
}: {
  patients: PatientRow[];
  query: string;
  cat: string;
  onQuery: (q: string) => void;
  onCat: (c: string) => void;
  onOpen: (p: PatientRow) => void;
}) {
  const q = query.toLowerCase();
  const list = patients.filter(
    (p) =>
      (cat === "all" || p.cat === cat) &&
      (!q || p.name.toLowerCase().includes(q) || p.village.toLowerCase().includes(q) ||
        p.phone.includes(q) || (p.abha ?? "").includes(q)),
  );

  return (
    <div className="phc">
      <div className="dir-bar">
        <input
          className="dir-in" value={query} onChange={(e) => onQuery(e.target.value)}
          placeholder="Search name, village, phone or ABHA"
        />
        {CATS.map((c) => (
          <button key={c} className={`f-chip${cat === c ? " on" : ""}`} onClick={() => onCat(c)}>
            {c === "all" ? "All" : c}
          </button>
        ))}
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Patient</th><th>Category</th><th>Village</th>
              <th>ABHA</th><th>Active problem</th><th className="num">Last visit</th>
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.name} onClick={() => onOpen(p)}>
                <td className="n">
                  {p.name}
                  <div style={{ fontSize: 10.5, color: "var(--ink-3)", fontWeight: 400, marginTop: 2 }}>
                    {p.age}{p.sex} · {p.phone}
                  </div>
                </td>
                <td><span className="badge b-mute">{p.cat}</span></td>
                <td>{p.village}</td>
                <td>
                  {p.abha ? (
                    <span style={{ fontFamily: "ui-monospace,monospace", fontSize: 11 }}>{p.abha}</span>
                  ) : (
                    <span className="badge b-warn">Pending</span>
                  )}
                </td>
                <td>{p.dx}</td>
                <td className="num">{p.last}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!list.length && (
          <div style={{ padding: 34, textAlign: "center", color: "var(--ink-3)", fontSize: 12.5 }}>
            No patients match.
          </div>
        )}
      </div>
    </div>
  );
}

export default Directory;
