/** The role editor: a facility's own grant or removal of a function, per
 *  role, away from the presets bundle.yaml ships.
 *
 *  Granting `vitals.record` to frontdesk is a capability grant and nothing
 *  else: the vitals pad and the loop follow from it with no change here,
 *  because the thread screen already derives everything it draws from the
 *  capabilities a role holds. So this screen is a list of switches, one per
 *  capability, and the only prose is the reason a switch is disabled.
 *
 *  WHAT A SWITCH IS CALLED, and why this file names nothing. A capability id
 *  is a machine name; an administrator reads the declaration's own words or
 *  reads nothing. Four sources, in order, and all four are the kernel's:
 *
 *    the capability's own `title`  -> that word
 *    one operation holds it        -> that operation's `title`
 *    several hold it               -> each operation's `short`, joined
 *    no operation, but a view      -> the view's own `title`
 *
 *  THE FIRST ONE IS NEW AND IT IS THE ONE THAT SHOULD ANSWER. A capability
 *  declares its own `title:` in bundle.yaml, so a switch is named by the thing
 *  it switches rather than by whatever happens to hold it. The three
 *  derivations below it were the whole answer until now and they failed at
 *  both ends: nothing named `assessment.record`, `appointment.book`,
 *  `facility.admin` or `lab.result.validate`, so all four printed raw; and too
 *  much named `patient.find` and `encounter.document`, so those printed three
 *  and five screen names joined with a dot. They are kept only for a bundle
 *  that declares no titles, which is bundles/lab.
 *
 *  A capability nothing declares a word for still falls through to its
 *  identifier, drawn in the mono face so it is visibly an identifier and not a
 *  name. That is a MISSING DECLARATION rather than a licence to type a word
 *  here. The same is true of a role: the picker reads the role's declared
 *  `title:` and can still only case an id when a bundle declares none.
 *
 *  HOW THEY ARE GROUPED. By the plugin that declares them, under the plugin's
 *  own `title:`. A plugin is already "a named group of this bundle's own
 *  words" (bundles/phc/bundle.yaml), which is exactly the grouping a centre
 *  thinks in, and it is the same declaration the facility switches off. A
 *  bundle that declares no plugins gets one ungrouped list, which is the
 *  correct answer and not a missing feature.
 */
import { useEffect, useState } from "react";
import type { Client } from "../api";
import { inert, inertReason, type Withheld } from "../grants";
import type { Catalogue } from "../types";
import { title } from "../words";

/** One switch. `label` is always the best declared words available; `declared`
 *  says whether they ARE declared words, so the identifier is drawn once and
 *  not twice. `hasOp` is kept because a capability no operation names gates a
 *  view or nothing yet: the workflow has no opinion about it, so it is never
 *  inert for the workflow's reason. */
type Row = { cap: string; label: string; declared: boolean; hasOp: boolean };

function rowFor(cap: string, cat: Catalogue): Row {
  const ops = Object.values(cat.operations ?? {}).filter((o) => o.capability === cap);
  const views = Object.values(cat.views ?? {}).filter((v) => v.capability === cap);
  // Whether an operation names this capability is a fact about the
  // declarations and NOT about what the row is called, so it is settled before
  // the label and never from it. Deriving it from whichever naming source won
  // would make a declared title say "an operation holds this", and the
  // workflow would then be asked why a capability it has never heard of is
  // inert.
  const hasOp = ops.length > 0;
  const declaredTitle = cat.vocabulary?.capability_titles?.[cap];
  if (declaredTitle) return { cap, label: declaredTitle, declared: true, hasOp };
  if (ops.length === 1) return { cap, label: ops[0].title, declared: true, hasOp };
  if (ops.length > 1) {
    return { cap, label: ops.map((o) => o.short).join(" · "), declared: true, hasOp };
  }
  if (views.length) {
    return { cap, label: views.map((v) => v.title).join(" · "), declared: true, hasOp };
  }
  return { cap, label: cap, declared: false, hasOp };
}

/** What a role is called: its own declared `title:`, or a cased id when the
 *  bundle declares none. Nothing is typed here either way, which is why the
 *  picker offered "Anm" and "Mo" until the declaration carried the words. */
function roleName(role: string, cat: Catalogue): string {
  return cat.vocabulary?.role_titles?.[role] || title(role);
}

type Group = { key: string; title: string | null; rows: Row[] };

/** The bundle's own plugins, in the order it declares them, narrowed to the
 *  capabilities this kernel actually carries. Anything no plugin claims keeps
 *  a group of its own with no heading, because there is no declared word for
 *  it and an invented one would be this file deciding something. */
function groupsFor(cat: Catalogue): Group[] {
  const left = new Set(cat.capabilities ?? []);
  const groups: Group[] = [];
  for (const [key, plugin] of Object.entries(cat.plugins ?? {})) {
    const caps = (plugin.capabilities ?? []).filter((c) => left.has(c));
    if (!caps.length) continue;
    for (const c of caps) left.delete(c);
    groups.push({ key, title: plugin.title, rows: caps.map((c) => rowFor(c, cat)) });
  }
  if (left.size) {
    groups.push({ key: "", title: null, rows: [...left].map((c) => rowFor(c, cat)) });
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
    <div className="mod mod-roles">
      <div className="mod-bar" />
      {/* The one place the tour starts again. Nothing else reopens it: a
          tour that comes back on its own is an interruption. */}
      <button
        className="tour-again"
        onClick={() => { try { localStorage.removeItem("phc.tour.seen"); } catch { /* private window */ }
                         location.hash = "#/"; location.reload(); }}
      >
        Take the tour again
      </button>
      <div className="mod-h">
        <div className="mod-t">Roles</div>
        <p className="mod-sub">
          What a person in each role may do at this centre. Saving applies at
          once to everyone in that role; the shipped list stays untouched, so
          Reset always works.
        </p>
        <label className="f-field roles-pick">
          <span className="f-lab">Role</span>
          <select
            className="f-in"
            value={role}
            disabled={!editable.length}
            onChange={(e) => setRole(e.target.value)}
          >
            {editable.length
              ? editable.map((r) => (
                  <option key={r} value={r}>{roleName(r, cat)}</option>
                ))
              : <option>No roles to edit</option>}
          </select>
        </label>
      </div>

      <div className="mod-b">
        {groups.map((g) => {
          // A capability this centre withholds is dead whether or not an
          // operation names it: the kernel has already taken it off the
          // caller. So the facility is asked first, and only then the
          // workflow, which has nothing to say about a capability that gates
          // a view.
          const marks = g.rows.map(({ cap, hasOp }) => {
            const off = facility.withheld[cap]
              ? true
              : hasOp ? inert(cap, cat, facility) : false;
            return { off, why: off ? inertReason(cap, cat, facility) : "" };
          });
          // A plugin this centre does not run takes its whole group down, for
          // one reason. Said once under the heading rather than three times
          // down the column; a row that is dead on its own still says so
          // beside itself.
          const whole = marks.length > 1
            && marks.every((m) => m.off && m.why === marks[0].why)
            ? marks[0].why : "";
          return (
            <section className="roles-g" key={g.key}>
              {g.title && (
                <h2 className="roles-g-h">
                  <span className="roles-g-t">{g.title}</span>
                  <span className="roles-g-n">
                    {g.rows.filter((r) => caps.has(r.cap)).length}/{g.rows.length}
                  </span>
                </h2>
              )}
              {whole && <p className="f-hint roles-g-why">{whole}</p>}
              <div className="roles-rows">
                {g.rows.map(({ cap, label, declared }, i) => (
                  <label
                    className={marks[i].off ? "f-check roles-row off" : "f-check roles-row"}
                    key={cap}
                  >
                    <input
                      type="checkbox"
                      checked={caps.has(cap)}
                      disabled={marks[i].off || busy || !role}
                      onChange={() => toggle(cap)}
                    />
                    <span className="roles-row-b">
                      <span className={declared ? "roles-row-t" : "roles-row-t raw"}>
                        {label}
                      </span>
                      {declared && <span className="roles-row-id">{cap}</span>}
                      {marks[i].off && !whole && (
                        <span className="f-hint">{marks[i].why}</span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </section>
          );
        })}
        {err && <div className="f-bad block">{err}</div>}
      </div>

      <div className="mod-f">
        <button
          className="cq quiet"
          disabled={busy || !role}
          onClick={() => setCaps(new Set(presets[role] ?? []))}
        >
          Reset to preset
        </button>
        <div className="roles-f-end">
          <button className="cq" onClick={onClose} disabled={busy}>Close</button>
          <button className="cq rose" onClick={save} disabled={busy || !role}>Save</button>
        </div>
      </div>
    </div>
  );
}
