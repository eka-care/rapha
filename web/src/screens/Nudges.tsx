/** What the recording screen suggests, station by station, editable here.
 *
 *  THIS IS THE REASON THEY WERE DECLARED RATHER THAN TYPED. A line like
 *  "Burning when she passes urine, four days now" is a fact about how the
 *  doctors at THIS centre talk. A centre in Jharkhand and a centre in
 *  Chennai should not read the same examples, and neither of them should
 *  have to ask us to change them.
 *
 *  SENTENCES ONLY. Nothing here can name an operation, a capability or a
 *  flag, so the worst a bad edit does is put unhelpful words on a screen.
 *  That is why it needs no confirmation and no lint beyond both boxes being
 *  filled, and it is why an administrator can be trusted with it.
 *
 *  Saving is per station, so changing the doctor's prompts leaves the
 *  nurse's exactly as they shipped.
 */
import { useMemo, useState } from "react";
import { ApiError, type Client } from "../api";
import { Icon } from "../icons";
import type { Catalogue } from "../types";
import { human, title } from "../words";

type Nudge = { field: string; say: string };

export function Nudges({ cat, client }: { cat: Catalogue; client: Client }) {
  const stations = useMemo(() => Object.keys(cat.scribe ?? {}).sort(), [cat.scribe]);
  const [station, setStation] = useState(stations[0] ?? "");
  const shipped = cat.scribe?.[station]?.nudges ?? [];

  // Keyed by station so switching away and back does not lose an edit that
  // has not been saved yet.
  const [edits, setEdits] = useState<Record<string, Nudge[]>>({});
  const rows = edits[station] ?? shipped;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState("");

  const put = (next: Nudge[]) => {
    setEdits((all) => ({ ...all, [station]: next }));
    setSaved("");
  };
  const change = (i: number, key: keyof Nudge, value: string) =>
    put(rows.map((r, n) => (n === i ? { ...r, [key]: value } : r)));

  const save = async () => {
    setBusy(true);
    setErr("");
    try {
      const keep = rows.filter((r) => r.field.trim() && r.say.trim());
      await client.setNudges(station, keep);
      setEdits((all) => ({ ...all, [station]: keep }));
      setSaved(`Saved. ${stationWord(station)} will see these.`);
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.message} ${e.next ?? ""}`.trim() : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!stations.length) {
    return <p className="cp-empty">This facility records nothing by voice yet.</p>;
  }

  return (
    <div className="cp-body">
      <div className="cp-row">
        <label className="cp-pick">
          <span className="cp-pick-l">Station</span>
          <select value={station} onChange={(e) => { setStation(e.target.value); setErr(""); setSaved(""); }}>
            {stations.map((s) => <option key={s} value={s}>{stationWord(s)}</option>)}
          </select>
          <Icon name="chev" className="i sm" />
        </label>
      </div>

      <ul className="cp-nudges">
        {rows.map((r, i) => (
          <li className="cp-nudge" key={i}>
            <input className="cp-in field" value={r.field} placeholder="Part of the record"
                   aria-label="Part of the record"
                   onChange={(e) => change(i, "field", e.target.value)} />
            <input className="cp-in say" value={r.say} placeholder="Something somebody would say"
                   aria-label="Example sentence"
                   onChange={(e) => change(i, "say", e.target.value)} />
            <button type="button" className="cp-drop" aria-label="Remove this example"
                    onClick={() => put(rows.filter((_, n) => n !== i))}>
              <Icon name="plus" className="i sm" />
            </button>
          </li>
        ))}
      </ul>

      <div className="cp-acts">
        <button type="button" className="cp-quiet"
                onClick={() => put([...rows, { field: "", say: "" }])}>
          <Icon name="plus" className="i sm" />
          Add an example
        </button>
        <span className="cp-acts-end">
          <button type="button" className="cp-quiet" disabled={busy || !edits[station]}
                  onClick={() => { setEdits((all) => { const n = { ...all }; delete n[station]; return n; }); setSaved(""); }}>
            Undo my changes
          </button>
          <button type="button" className="cp-go" disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </button>
        </span>
      </div>

      {err && <p className="cp-bad">{err}</p>}
      {saved && <p className="cp-ok">{saved}</p>}
      <p className="cp-note">
        These are examples, not a form. Anything said is recorded whether it
        is listed or not.
      </p>
    </div>
  );
}

const stationWord = (id: string) => title(human(id));
