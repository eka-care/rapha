/** §35: ⌘K. One box over patients, lists and destinations.
 *
 *  §2.9 and §36: find before create. A miss does not become a registration --
 *  it offers one, explicitly, as a button somebody has to press. The rows and
 *  the create label both come from search.ts, which is checked without a
 *  browser.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { createLabel, isAsk, rows as searchRows, type Row } from "../search";
import type { Catalogue, ViewDecl, ViewResult } from "../types";
import { displayFor } from "../declarations";

export function Khoj({ queues, nav, cat, workflow, onClose, onOpenThread, onGoView, onAsk, onCreate }: {
  queues: { decl: ViewDecl; result: ViewResult }[];
  nav: ViewDecl[];
  cat: Catalogue;
  workflow?: string;
  onClose: () => void;
  onOpenThread: (thread: string) => void;
  onGoView: (view: string) => void;
  onAsk: (question: string) => void;
  onCreate: () => void;
}) {
  const [q, setQ] = useState("");
  const [pick, setPick] = useState(0);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => { box.current?.focus(); }, []);

  // The FULL declaration for each queue, not the short form.
  //
  // `/facility` sends a view as four fields -- id, kind, title, capability --
  // and `/catalogue` sends the rest, which is why every other screen reads
  // its view out of `cat`. This list was drawing from the short form, so it
  // had no `columns` to order itself by, no `labels` and no `provenance`:
  // it fell back to whatever keys the subject happened to carry, in whatever
  // order the adapter built them, and drew the provenance value as a word
  // because nothing had told it there was one. The rules were not being
  // ignored here so much as never delivered.
  const full = useMemo(
    () => queues.map(({ decl, result }) => ({ decl: cat.views?.[decl.id] ?? decl, result })),
    [queues, cat],
  );
  const rows = useMemo(() => searchRows(q, full, nav, displayFor), [q, full, nav]);
  useEffect(() => { setPick(0); }, [q]);

  const choose = (r: Row) => {
    onClose();
    if (r.kind === "thread") onOpenThread(r.id);
    else if (r.kind === "view") onGoView(r.id);
    else if (r.kind === "ask") onAsk(r.name);
    else onGoView("");
  };

  const groups: { name: string; rows: { r: Row; i: number }[] }[] = [];
  rows.forEach((r, i) => {
    const last = groups[groups.length - 1];
    if (last && last.name === r.group) last.rows.push({ r, i });
    else groups.push({ name: r.group, rows: [{ r, i }] });
  });

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="khoj" role="dialog" aria-modal="true" aria-label="Search">
        <input
          ref={box}
          className="khoj__input"
          value={q}
          placeholder="Search patients, lists, or ask a question"
          aria-label="Search patients, lists, or ask a question"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
            if (!rows.length) return;
            if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => (p + 1) % rows.length); }
            if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => (p - 1 + rows.length) % rows.length); }
            if (e.key === "Enter") { e.preventDefault(); choose(rows[pick]); }
          }}
        />
        <div className="khoj__list" role="listbox">
          {groups.map((g) => (
            <div key={g.name}>
              <div className="composer-menu__section">{g.name}</div>
              {g.rows.map(({ r, i }) => (
                <button
                  key={r.kind + r.id}
                  role="option"
                  aria-selected={i === pick}
                  data-active={i === pick}
                  className="khoj__item"
                  onMouseDown={(e) => { e.preventDefault(); choose(r); }}
                >
                  <span>{r.name}</span>
                  {r.meta && <span className="khoj__item-sub">{r.meta}</span>}
                </button>
              ))}
            </div>
          ))}

          {/* §2.9: a search miss must not silently become a creation. */}
          {!rows.length && (
            <div className="khoj__empty">
              <div className="t-strong">
                {q.trim() ? "No matching patient." : "Type a name, phone number or token."}
              </div>
              {q.trim() && !isAsk(q) && (
                <>
                  <div className="t-body u-mute">Search by name, phone, ABHA, village or token.</div>
                  <button className="btn" data-variant="primary" onClick={() => { onClose(); onCreate(); }}>
                    {createLabel(cat, workflow)}
                  </button>
                </>
              )}
              {q.trim() && isAsk(q) && (
                <button className="btn" onClick={() => { onClose(); onAsk(q.trim()); }}>
                  Ask the agent
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
