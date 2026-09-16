/** §6.2: a declared view as a working surface, with the prototype's filter
 *  tabs across the top. §88 asks that returning to a list restores it, so the
 *  filter, sort and search are held per view for the session.
 */
import { useMemo, useState } from "react";
import { filterOptions, filterRows, sortOptions, sortRows, type Filter, type SortKey } from "../loops";
import type { QueueRow, ViewDecl, ViewResult } from "../types";
import { View } from "../view/View";
import { human } from "../words";

const memory: Record<string, { q: string; sort: SortKey; filter: Filter }> = {};

export function ListScreen({ result, decl, onOpenThread }: {
  result: ViewResult;
  decl?: ViewDecl;
  onOpenThread?: (thread: string) => void;
}) {
  const key = result.view;
  const [state, setState] = useState(() => memory[key] ?? { q: "", sort: "recent" as SortKey, filter: null as Filter });
  const set = (next: Partial<typeof state>) => {
    const merged = { ...state, ...next };
    memory[key] = merged;
    setState(merged);
  };

  const isQueue = result.kind === "queue";
  const rows = (result.rows ?? []) as QueueRow[];
  const sorts = useMemo(() => sortOptions(decl), [decl]);

  /** One tab per declared badge and per station present, each with the count
   *  it would show. A tab that would be empty still appears with a 0, because
   *  "pharmacy 0" is information. */
  const tabs = useMemo(() => {
    if (!isQueue) return [];
    const { flags, stations } = filterOptions(decl, rows);
    const made: { label: string; filter: Filter; n: number }[] = [
      { label: "All", filter: null, n: rows.length },
    ];
    for (const s of stations) made.push({ label: human(s), filter: { station: s }, n: rows.filter((r) => r.station === s).length });
    for (const f of flags) made.push({ label: human(f), filter: { flag: f }, n: rows.filter((r) => r.flags.includes(f)).length });
    return made;
  }, [rows, decl, isQueue]);

  const shown = useMemo(() => {
    if (!isQueue) return result;
    let out = filterRows(rows, state.filter);
    const q = state.q.trim().toLowerCase();
    if (q) {
      out = out.filter((r) => Object.values(r.subject ?? {}).some((v) => String(v ?? "").toLowerCase().includes(q)));
    }
    return { ...result, rows: sortRows(out, state.sort, decl) };
  }, [result, rows, state, decl, isQueue]);

  return (
    <div style={{ paddingBottom: 20 }}>
      {isQueue && rows.length > 0 && (
        <>
          <div className="qtabs">
            {tabs.map((t) => (
              <button
                key={t.label}
                className={`qtab${JSON.stringify(state.filter) === JSON.stringify(t.filter) ? " on" : ""}`}
                onClick={() => set({ filter: t.filter })}
              >
                {t.label}
                <span className="n">{t.n}</span>
              </button>
            ))}
          </div>
          <div className="tabs">
            <input
              className="input" type="search" value={state.q}
              placeholder="Search this list" aria-label="Search this list"
              style={{ maxWidth: 280 }}
              onChange={(e) => set({ q: e.target.value })}
            />
            {sorts.length > 1 && (
              <select
                className="input" style={{ width: "auto" }}
                value={state.sort} aria-label="Sort"
                onChange={(e) => set({ sort: e.target.value as SortKey })}
              >
                {sorts.map((s) => <option value={s.key} key={s.key}>{s.label}</option>)}
              </select>
            )}
          </div>
        </>
      )}
      <View result={shown} decl={decl} onOpenThread={onOpenThread} />
    </div>
  );
}
