import { useEffect, useMemo, useRef, useState } from "react";
import { displayFor } from "../declarations";
import { Icon } from "../icons";
import {
  filterOptions, filterRows, labelColumns, narrowings, sameFilter, sortByColumn,
  type ColumnKey, type Filter, type Sort,
} from "../loops";
import type { QueueRow, ViewDecl, ViewResult, Workflow } from "../types";
import { View } from "../view/View";
import { human, title } from "../words";

/** What a person had set on a list when they went to a patient and came back. */
type State = { q: string; sort: Sort; tab: string; extra: Filter };
const memory: Record<string, State> = {};

/** The tab for people with no station: they have finished. The word is the
 *  renderer's, like "Everyone". */
const DONE = "\u0000done";
const ALL = "\u0000all";

/** The Lines screen: every patient at the centre today, in one table.
 *
 *  Tabs say where they are, a search finds a name or a token, a filter menu
 *  narrows by programme and by flag, and every column header sorts. Nothing
 *  here knows the order a patient moves through the centre, because there is
 *  none: the tabs are places, not steps. */
export function ListScreen({ result, decl, workflow, onOpenThread }: {
  result: ViewResult;
  decl?: ViewDecl;
  workflow?: Pick<Workflow, "states">;
  onOpenThread?: (thread: string) => void;
}) {
  const key = result.view;
  const [state, setState] = useState<State>(
    () => memory[key] ?? { q: "", sort: { key: "number", dir: "asc" }, tab: ALL, extra: null },
  );
  const set = (next: Partial<State>) => {
    const merged = { ...state, ...next };
    memory[key] = merged;
    setState(merged);
  };
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  const isQueue = result.kind === "queue";
  const rows = (result.rows ?? []) as QueueRow[];

  const tabs = useMemo(() => {
    if (!isQueue) return [];
    const stations = filterOptions(decl, rows, labelColumns(decl)).stations;
    const out = stations.map((s) => ({
      id: s, label: title(human(s)), n: rows.filter((r) => r.station === s).length,
    }));
    const done = rows.filter((r) => !r.station).length;
    if (out.length && done) out.push({ id: DONE, label: "Done", n: done });
    return out;
  }, [decl, rows, isQueue]);

  // Everything that is not a station: programmes, how somebody arrived, flags.
  // Stations are the tabs, so they are not offered twice.
  const menu = useMemo(() => {
    if (!isQueue) return [];
    return narrowings(decl, rows, displayFor, (w) => title(human(w)))
      .map((g) => ({ ...g, items: g.items.filter((i) => !(i.filter && "station" in i.filter)) }))
      .filter((g) => g.items.length);
  }, [decl, rows, isQueue]);
  const chosen = menu.flatMap((g) => g.items).find((i) => sameFilter(i.filter, state.extra));

  const shown = useMemo(() => {
    let out = rows;
    if (state.tab === DONE) out = out.filter((r) => !r.station);
    else if (state.tab !== ALL) out = out.filter((r) => r.station === state.tab);
    out = filterRows(out, state.extra);
    const q = state.q.trim().toLowerCase();
    if (q) {
      out = out.filter((r) => Object.values(r.subject ?? {}).some((v) => String(v ?? "").toLowerCase().includes(q)));
    }
    return sortByColumn(out, state.sort.key, state.sort.dir, decl);
  }, [rows, state, decl]);

  const onSort = (k: ColumnKey) =>
    set({ sort: state.sort.key === k ? { key: k, dir: state.sort.dir === "asc" ? "desc" : "asc" } : { key: k, dir: "asc" } });

  if (!isQueue) {
    return <div style={{ paddingBottom: 20 }}><View result={result} decl={decl} workflow={workflow} onOpenThread={onOpenThread} /></div>;
  }
  return (
    <div className="ls">
      {rows.length > 0 && (
        <>
          <div className="ls-bar">
            <div className="ls-search">
              <Icon name="search" className="i sm" />
              <input
                className="input" type="search" value={state.q}
                placeholder="Find a patient or token…" aria-label="Find a patient or token"
                onChange={(e) => set({ q: e.target.value })}
                // A token typed and Enter opens that person, which is what "call a
                // token" was for. Only when the search has narrowed to one.
                onKeyDown={(e) => { if (e.key === "Enter" && shown.length === 1) onOpenThread?.(shown[0].thread); }}
              />
            </div>
            {menu.length > 0 && (
              <div className="lf" ref={box}>
                <button type="button" className={`lf-btn${chosen ? " on" : ""}`} aria-haspopup="true" aria-expanded={open}
                        onClick={() => setOpen((v) => !v)}>
                  <Icon name="sliders" className="i sm" />
                  {chosen ? chosen.label : "Filters"}
                </button>
                {open && (
                  <div className="lf-menu">
                    {menu.map((g) => (
                      <div className="lf-grp" key={g.title}>
                        <div className="lf-h">{g.title}</div>
                        {g.items.map((i) => (
                          <button type="button" key={i.key}
                                  className={`lf-item${sameFilter(i.filter, state.extra) ? " on" : ""}${i.risk ? " risk" : ""}`}
                                  onClick={() => { set({ extra: sameFilter(i.filter, state.extra) ? null : i.filter }); setOpen(false); }}>
                            <span>{i.label}</span><span className="lf-c">{i.n}</span>
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {(state.extra || state.q || state.tab !== ALL) && (
              <button type="button" className="lf-clear" onClick={() => set({ q: "", extra: null, tab: ALL })}>
                Clear
              </button>
            )}
          </div>
          {tabs.length > 0 && (
            <div className="ltabs" role="tablist" aria-label="Where they are">
              {[{ id: ALL, label: "Everyone", n: rows.length }, ...tabs].map((t) => (
                <button type="button" role="tab" key={t.id} aria-selected={state.tab === t.id}
                        className={`ltab${state.tab === t.id ? " on" : ""}`} onClick={() => set({ tab: t.id })}>
                  {t.label}<span className="ltab-n">{t.n}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
      {shown.length === 0 && rows.length > 0 ? (
        <div className="state-empty">Nobody matches. <button type="button" className="lf-clear" onClick={() => set({ q: "", extra: null, tab: ALL })}>Clear the search and filters</button></div>
      ) : (
        <View result={{ ...result, rows: shown }} decl={decl} workflow={workflow} onOpenThread={onOpenThread}
              sort={state.sort} onSort={onSort} />
      )}
    </div>
  );
}
