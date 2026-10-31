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
import type { Client } from "../api";
import { inert, inertReason, type Withheld } from "../grants";
import type { Catalogue, Operation } from "../types";
import { human } from "../words";

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
  cat, roleIds, facility, client, onClose,
}: {
  cat: Catalogue;
  /** /facility's role list: the nine presets plus the demo union. Demo is not
   *  a preset a facility can deviate from, so it is not offered here. */
  roleIds: string[];
  /** What this centre does not run, from GET /facility. Not optional: a
   *  default of "nothing is withheld" is exactly the wrong answer at the
   *  centre that withholds something, and it is how this screen came to offer
   *  a switch the guard refuses. */
  facility: Withheld;
  client: Client;
  onClose: () => void;
}) {
  const editable = roleIds.filter((r) => r !== "demo");
  const [role, setRole] = useState(editable[0] ?? "");
  const [presets, setPresets] = useState<Record<string, string[]>>({});
  // A facility's own save, kept apart from `presets` so "Reset to preset"
  // still means the shipped list and not whatever was last saved. Without
  // this the editor has only the preset to seed from, so reopening it after
  // a deliberate removal shows the role as if nothing had changed, and the
  // next unrelated Save silently re-grants what was taken away.
  const [overrides, setOverrides] = useState<Record<string, string[]>>({});
  const [caps, setCaps] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    client.roles().then((got) => {
      setPresets(got.presets);
      setOverrides(got.overrides);
    }).catch(() => {});
  }, [client]);

  useEffect(() => {
    setCaps(new Set(overrides[role] ?? presets[role] ?? []));
  }, [role, presets, overrides]);

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
      setOverrides((was) => ({ ...was, [role]: saved.capabilities }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mod">
      <div className="mod-bar" />
      <div className="mod-h" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div className="mod-t">Roles</div>
        <select
          className="f-in"
          style={{ width: "auto" }}
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
              // A capability this centre withholds is dead whether or not an
              // operation names it: the kernel has already taken it off the
              // caller. So the facility is asked first, and only then the
              // workflow, which has nothing to say about a capability that
              // gates a view.
              const off = facility.withheld[cap] ? true : op ? inert(cap, cat, facility) : false;
              return (
                <label className="f-check" key={cap} style={off ? { opacity: 0.5 } : undefined}>
                  <input
                    type="checkbox"
                    checked={caps.has(cap)}
                    disabled={off || busy || !role}
                    onChange={() => toggle(cap)}
                  />
                  <span>{human(cap)}</span>
                  {off && <span className="f-hint">{inertReason(cap, cat, facility)}</span>}
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
        <div style={{ display: "flex", gap: 4, flex: 1, justifyContent: "flex-end" }}>
          <button className="cq" onClick={onClose} disabled={busy}>Close</button>
          <button className="cq rose" onClick={save} disabled={busy || !role}>Save</button>
        </div>
      </div>
    </div>
  );
}
