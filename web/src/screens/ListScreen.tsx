/** §6.2: a declared view as a working surface, with the prototype's filter
 *  tabs across the top. §88 asks that returning to a list restores it, so the
 *  filter, sort and search are held per view for the session.
 */
import { useMemo, useState } from "react";
import {
  filterOptions, filterRows, RISK_TONE, sortOptions, sortRows,
  type Filter, type SortKey,
} from "../loops";
import type { QueueRow, ViewDecl, ViewResult, Workflow } from "../types";
import { View } from "../view/View";
import { title } from "../words";

const memory: Record<string, { q: string; sort: SortKey; filter: Filter }> = {};

export function ListScreen({ result, decl, workflow, onOpenThread }: {
  result: ViewResult;
  decl?: ViewDecl;
  /** The workflow these rows walk, so the row labels can tell a state the
   *  kernel worked out from one a person asserted. */
  workflow?: Pick<Workflow, "states">;
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

  /** One chip per station present and per declared badge, each carrying the
   *  count it would show. A chip that would be empty still appears with a 0,
   *  because "pharmacy 0" is information, and the count is never hidden
   *  behind a hover or a tap: a phone has no hover, so a number that only
   *  appears on one does not exist.
   *
   *  Every label here is `title(human(id))` over a declared station or a
   *  declared flag. "All" is the only word written down, and it names no
   *  station, flag, capability or bundle.
   *
   *  The chip's tone is the view's own, flag by flag, and only the tone that
   *  means clinical risk is allowed to carry colour. */
  const tabs = useMemo(() => {
    if (!isQueue) return [];
    const { flags, stations } = filterOptions(decl, rows);
    const made: { label: string; filter: Filter; n: number; risk?: boolean; sep?: boolean }[] = [
      { label: "All", filter: null, n: rows.length },
    ];
    if (stations.length) made.push({ label: "", filter: null, n: 0, sep: true });
    for (const s of stations) {
      made.push({ label: title(s), filter: { station: s }, n: rows.filter((r) => r.station === s).length });
    }
    if (flags.length) made.push({ label: "", filter: null, n: 0, sep: true });
    for (const f of flags) {
      made.push({
        label: title(f),
        filter: { flag: f },
        n: rows.filter((r) => r.flags.includes(f)).length,
        risk: decl?.badges?.[f] === RISK_TONE,
      });
    }
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
          <div className="qtabs" role="group" aria-label="Filter this list">
            {tabs.map((t, i) => (t.sep ? (
              <span className="qtab-sep" key={`sep-${i}`} aria-hidden="true" />
            ) : (
              <button
                key={t.label}
                className={`qtab${JSON.stringify(state.filter) === JSON.stringify(t.filter) ? " on" : ""}${t.risk ? " risk" : ""}`}
                aria-pressed={JSON.stringify(state.filter) === JSON.stringify(t.filter)}
                onClick={() => set({ filter: t.filter })}
              >
                {t.label}
                <span className="n">{t.n}</span>
              </button>
            )))}
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
      <View result={shown} decl={decl} workflow={workflow} onOpenThread={onOpenThread} />
    </div>
  );
}
