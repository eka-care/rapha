/** §6.2: a declared view as a working surface.
 *
 *  §88 asks that returning to a list restores it. Filter, sort and search are
 *  held per view id, so walking into a thread and coming back lands where you
 *  left rather than at the top of an unsorted list.
 */
import { useMemo, useState } from "react";
import { filterOptions, filterRows, sortOptions, sortRows, type Filter, type SortKey } from "../loops";
import type { QueueRow, ViewDecl, ViewResult } from "../types";
import { View } from "../view/View";
import { human } from "../words";

/** Per view id, for this session. Deliberately module state and not
 *  localStorage: a filter is where you were a minute ago, not a preference,
 *  and one that outlives the browser tab surprises people. */
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
  const filters = useMemo(() => {
    if (!isQueue) return [] as { label: string; filter: Filter }[];
    const { flags, stations } = filterOptions(decl, rows);
    return [
      ...flags.map((f) => ({ label: human(f), filter: { flag: f } as Filter })),
      ...stations.map((s) => ({ label: human(s), filter: { station: s } as Filter })),
    ];
  }, [rows, decl, isQueue]);

  const shown = useMemo(() => {
    if (!isQueue) return result;
    let out = filterRows(rows, state.filter);
    const q = state.q.trim().toLowerCase();
    if (q) {
      out = out.filter((r) =>
        Object.values(r.subject ?? {}).some((v) => String(v ?? "").toLowerCase().includes(q)));
    }
    return { ...result, rows: sortRows(out, state.sort, decl) };
  }, [result, rows, state, decl, isQueue]);

  const count = ((shown.rows ?? []) as unknown[]).length;

  return (
    <>
      <div className="list-head">
        <h1 className="t-page" style={{ margin: 0 }}>{result.title ?? decl?.title ?? human(result.view)}</h1>
        <span className="list-count t-meta">{count === 1 ? "1 record" : `${count} records`}</span>
      </div>

      {isQueue && rows.length > 0 && (
        <div className="list-tools">
          <input
            className="input list-tools__search"
            type="search"
            value={state.q}
            placeholder="Search this list"
            aria-label="Search this list"
            onChange={(e) => set({ q: e.target.value })}
          />
          {filters.length > 0 && (
            <>
              <button
                className="chip" data-role="button" data-selected={state.filter === null}
                onClick={() => set({ filter: null })}
              >
                All
              </button>
              {filters.map((f) => (
                <button
                  key={f.label}
                  className="chip" data-role="button"
                  data-selected={JSON.stringify(state.filter) === JSON.stringify(f.filter)}
                  onClick={() => set({ filter: f.filter })}
                >
                  {f.label}
                </button>
              ))}
            </>
          )}
          {sorts.length > 1 && (
            <label className="t-meta u-faint" style={{ marginLeft: "auto", display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
              Sort
              <select
                className="input" style={{ width: "auto", minHeight: 32 }}
                value={state.sort}
                onChange={(e) => set({ sort: e.target.value as SortKey })}
              >
                {sorts.map((s) => <option value={s.key} key={s.key}>{s.label}</option>)}
              </select>
            </label>
          )}
        </div>
      )}

      <View result={shown} decl={decl} onOpenThread={onOpenThread} />
    </>
  );
}
