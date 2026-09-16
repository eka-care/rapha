/** The composer's @ and / menus (§60).
 *
 *  Neither list is written down anywhere in this file. `/` is the thread's own
 *  actions, which the kernel has already narrowed by capability, precondition,
 *  actor and surface -- so the menu cannot offer something the guard would
 *  refuse, which is what §14's "do not display unusable commands" asks for.
 *  `@` is the roles the bundle declared. Point this renderer at a laboratory
 *  and both menus fill with the laboratory's words.
 */
import type { Operation } from "../types";
import { human, title } from "../words";

export type Item = { key: string; label: string; sub?: string; group: string; op?: Operation };

/** Group the offered operations under their own declared station. A station is
 *  the bundle's word for where work happens, so it is the bundle that decides
 *  the headings, not this file. */
export function slashItems(actions: Operation[], query: string): Item[] {
  return actions
    .filter((o) => `${o.short} ${o.title}`.toLowerCase().includes(query))
    .map((o) => ({
      key: o.id,
      label: o.title,
      sub: o.short && o.short !== o.title ? o.short : undefined,
      group: o.station ? human(o.station) : "Actions",
      op: o,
    }));
}

export function atItems(roles: string[], query: string): Item[] {
  return roles
    .filter((r) => r.toLowerCase().includes(query))
    .map((r) => ({ key: r, label: human(r), group: "Roles" }));
}

export function Menu({ items, pick, onChoose, id }: {
  items: Item[]; pick: number; id: string;
  onChoose: (it: Item) => void;
}) {
  if (!items.length) return null;
  const groups: { name: string; items: { it: Item; i: number }[] }[] = [];
  items.forEach((it, i) => {
    const last = groups[groups.length - 1];
    if (last && last.name === it.group) last.items.push({ it, i });
    else groups.push({ name: it.group, items: [{ it, i }] });
  });
  return (
    <div className="composer-menu" role="listbox" id={id} aria-label="Suggestions">
      {groups.map((g) => (
        <div key={g.name}>
          <div className="composer-menu__section">{title(g.name)}</div>
          {g.items.map(({ it, i }) => (
            <button
              key={it.key}
              type="button"
              role="option"
              id={`${id}-${i}`}
              aria-selected={i === pick}
              data-active={i === pick}
              className="composer-menu__item"
              onMouseDown={(e) => { e.preventDefault(); onChoose(it); }}
            >
              <span>{it.label}</span>
              {it.sub && <span className="composer-menu__item-sub">{it.sub}</span>}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
