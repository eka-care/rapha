/** §6.2: a declared view as a working surface. §88 asks that returning to a
 *  list restores it, so the sort and the search are held per view for the
 *  session.
 *
 *  THE FILTER IS NOT HELD HERE ANY MORE. It used to be, as a strip of chips
 *  across the top: one per station, one per programme, one for how somebody
 *  arrived, and the flags behind a button. The second panel beside this one
 *  drew its own menu over the programmes and the flags at the same time, so
 *  one screen had two controls over one question, offering different
 *  narrowings and unable to move each other -- and this strip was taller
 *  than the list under it. The question has one home now, in the panel
 *  beside the people, and this screen is handed the answer.
 */
import { useMemo, useState } from "react";
import { displayFor } from "../declarations";
import {
  filterRows, narrowings, sameFilter, sortOptions, sortRows,
  type Filter, type SortKey,
} from "../loops";
import type { QueueRow, ViewDecl, ViewResult, Workflow } from "../types";
import { View } from "../view/View";
import { human, title } from "../words";

const memory: Record<string, { q: string; sort: SortKey }> = {};

export function ListScreen({ result, decl, workflow, filter, onOpenThread }: {
  result: ViewResult;
  decl?: ViewDecl;
  /** How the shell's one narrowing control has narrowed today's line. Set in
   *  the second panel, obeyed here. */
  filter: Filter;
  /** The workflow these rows walk, so the row labels can tell a state the
   *  kernel worked out from one a person asserted. */
  workflow?: Pick<Workflow, "states">;
  onOpenThread?: (thread: string) => void;
}) {
  const key = result.view;
  const [state, setState] = useState(() => memory[key] ?? { q: "", sort: "recent" as SortKey });
  const set = (next: Partial<typeof state>) => {
    const merged = { ...state, ...next };
    memory[key] = merged;
    setState(merged);
  };

  const isQueue = result.kind === "queue";
  const rows = (result.rows ?? []) as QueueRow[];
  const sorts = useMemo(() => sortOptions(decl), [decl]);

  /** WHAT THIS LIST IS NOT SHOWING, and said so on the list.
   *
   *  The control is in the panel beside this one, and on a phone that panel
   *  is a drawer -- so without this a person arrives at a list that is
   *  quietly missing two thirds of the day with nothing on screen saying
   *  why. The word is the same declared one the control used, read the same
   *  way, so the two can never disagree about what the narrowing is called.
   */
  const narrowedBy = useMemo(() => {
    if (!filter) return null;
    return narrowings(decl, rows, displayFor, (w) => title(human(w)))
      .flatMap((g) => g.items)
      .find((i) => sameFilter(i.filter, filter)) ?? null;
  }, [decl, rows, filter]);

  const shown = useMemo(() => {
    if (!isQueue) return result;
    let out = filterRows(rows, filter);
    const q = state.q.trim().toLowerCase();
    if (q) {
      out = out.filter((r) => Object.values(r.subject ?? {}).some((v) => String(v ?? "").toLowerCase().includes(q)));
    }
    return { ...result, rows: sortRows(out, state.sort, decl) };
  }, [result, rows, state, filter, decl, isQueue]);

  return (
    <div style={{ paddingBottom: 20 }}>
      {isQueue && rows.length > 0 && (
        <>
          {narrowedBy && (
            <div className="narrowed" role="status">
              Showing {narrowedBy.label} only.
            </div>
          )}
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
