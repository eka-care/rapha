/** The role editor: a facility's own grant or removal of a function, per
 *  role, away from the presets bundle.yaml ships.
 *
 *  Granting `vitals.record` to frontdesk is a capability grant and nothing
 *  else: the vitals pad and the loop follow from it with no change here,
 *  because the thread screen already derives everything it draws from the
 *  capabilities a role holds. So this screen is a list of switches, one per
 *  capability, and the only prose is the reason a switch is disabled.
 */
import { useEffect, useState } from "react";
import type { Client } from "./api";
import { inert, inertReason } from "./grants";
import type { Catalogue, Operation } from "./types";
import { human } from "./ui";

export { inert } from "./grants";

type Group = { title: string; rows: { cap: string; op?: Operation }[] };

/** One row per capability the bundle declares, grouped by the operation it
 *  unlocks. A capability no operation names (it gates a view, or nothing yet)
 *  keeps its own row under its own name: `drawn_by` has no opinion about it,
 *  so it is never disabled here. */
function groupsFor(cat: Catalogue): Group[] {
  const ops = Object.values(cat.operations ?? {});
  const groups: Group[] = [];
  for (const cap of cat.capabilities ?? []) {
    const op = ops.find((o) => o.capability === cap);
    const title = op?.title ?? human(cap);
    let g = groups.find((x) => x.title === title);
    if (!g) { g = { title, rows: [] }; groups.push(g); }
    g.rows.push({ cap, op });
  }
  return groups;
}

export function Roles({
  cat, roleIds, client, onClose,
}: {
  cat: Catalogue;
  /** /facility's role list: the nine presets plus the demo union. Demo is not
   *  a preset a facility can deviate from, so it is not offered here. */
  roleIds: string[];
  client: Client;
  onClose: () => void;
}) {
  const editable = roleIds.filter((r) => r !== "demo");
  const [role, setRole] = useState(editable[0] ?? "");
  const [presets, setPresets] = useState<Record<string, string[]>>({});
  const [caps, setCaps] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    client.roles().then((got) => setPresets(got.presets)).catch(() => {});
  }, [client]);

  useEffect(() => {
    setCaps(new Set(presets[role] ?? []));
  }, [role, presets]);

  const groups = groupsFor(cat);

  const toggle = (cap: string) => {
    setCaps((was) => {
      const next = new Set(was);
      if (next.has(cap)) next.delete(cap); else next.add(cap);
      return next;
    });
  };

  const save = async () => {
    setBusy(true);
    setErr("");
    try {
      const saved = await client.setRole(role, [...caps]);
      setCaps(new Set(saved.capabilities));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mod">
      <div className="mod-bar" />
      <div className="mod-h" style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <div className="mod-t">Roles</div>
        <select
          className="f-in"
          style={{ width: "auto", marginLeft: "auto" }}
          value={role}
          disabled={!editable.length}
          onChange={(e) => setRole(e.target.value)}
        >
          {editable.length
            ? editable.map((r) => <option key={r} value={r}>{human(r)}</option>)
            : <option>No roles to edit</option>}
        </select>
      </div>

      <div className="mod-b">
        {groups.map((g) => (
          <div key={g.title}>
            <div className="eyebrow">{g.title}</div>
            {g.rows.map(({ cap, op }) => {
              const off = op ? inert(cap, cat) : false;
              return (
                <label className="f-check" key={cap} style={off ? { opacity: 0.5 } : undefined}>
                  <input
                    type="checkbox"
                    checked={caps.has(cap)}
                    disabled={off || busy || !role}
                    onChange={() => toggle(cap)}
                  />
                  <span>{human(cap)}</span>
                  {off && <span className="f-hint">{inertReason(cap, cat)}</span>}
                </label>
              );
            })}
          </div>
        ))}
        {err && <div className="f-bad block">{err}</div>}
      </div>

      <div className="mod-f">
        <button
          className="cq"
          disabled={busy || !role}
          onClick={() => setCaps(new Set(presets[role] ?? []))}
        >
          Reset to preset
        </button>
        <div className="ml-auto" style={{ display: "flex", gap: 6 }}>
          <button className="cq" onClick={onClose} disabled={busy}>Close</button>
          <button className="cq rose" onClick={save} disabled={busy || !role}>Save</button>
        </div>
      </div>
    </div>
  );
}
