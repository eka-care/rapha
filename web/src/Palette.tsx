/** The command palette. Find first, create only on miss.
 *
 *  Rows in three groups, arrow keys, a preview beside them, and one button at
 *  the bottom of an empty result that says what creating costs before it
 *  creates anything.
 *
 *  The preview's quick actions are one `GET /threads/{id}`, debounced. What
 *  comes back is already filtered by the role's capabilities and the guard's
 *  preconditions, so the palette draws what it was given and disables nothing.
 *  The prototype greyed out the actions the role lacked; that is the one thing
 *  in it this file deliberately does not copy.
 */
import { useEffect, useRef, useState } from "react";
import type { Client } from "./api";
import { Icon, iconFor } from "./icons";
import { createLabel, rows, type Row } from "./search";
import type { Catalogue, Operation, ThreadView, ViewDecl, ViewResult } from "./types";
import { Badge, human } from "./ui";

export function Palette({
  cat, client, queues, nav, onClose, onOpenThread, onGo, onAsk, onRegister, onAction,
}: {
  cat: Catalogue;
  client: Client;
  queues: { decl: ViewDecl; result: ViewResult }[];
  nav: ViewDecl[];
  onClose: () => void;
  onOpenThread: (id: string) => void;
  onGo: (hash: string) => void;
  onAsk: (q: string) => void;
  /** What the clerk typed goes with it. The journey the next screen opens can
   *  use a mobile number, and the clerk has already typed it once. */
  onRegister: (typed: string) => void;
  onAction: (thread: string, op: Operation) => void;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const found = rows(q, queues, nav);
  const cur = found[Math.min(sel, found.length - 1)];
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);
  useEffect(() => setSel(0), [q]);

  const run = (r: Row | undefined) => {
    if (!r) return;
    if (r.kind === "thread") return onOpenThread(r.id);
    if (r.kind === "ask") return onAsk(r.name);
    if (r.kind === "home") return onGo("#/home");
    onGo(`#/views/${r.id}`);
  };

  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, found.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); run(cur); }
    else if (e.key === "Escape") onClose();
  };

  const missed = q.trim().length > 0 && !found.some((r) => r.kind === "thread");
  const word = createLabel(cat);

  let last = "";
  return (
    <div className="spot" onKeyDown={key}>
      <div className="spot-in">
        <Icon name="search" />
        <input
          ref={input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search or ask"
        />
      </div>

      {missed && !found.length ? (
        <div style={{ padding: "38px 22px", textAlign: "center", width: "100%", color: "var(--ink-3)" }}>
          <Icon name="search" size="lg" />
          <p style={{ fontSize: 12.5, margin: "12px 0 14px", lineHeight: 1.6 }}>
            No match for "<b>{q.trim()}</b>". Opening a new one creates a permanent record.
          </p>
          <button className="btn btn-b" style={{ margin: "0 auto" }} onClick={() => onRegister(q.trim())}>
            <Icon name="plus" size="sm" />{word}
          </button>
        </div>
      ) : (
        <div className="spot-body">
          <div className="spot-list">
            {found.map((r, i) => {
              const head = r.group !== last ? r.group : null;
              last = r.group;
              return (
                <div key={r.kind + r.id}>
                  {head && <div className="spot-sec">{head}</div>}
                  <div
                    className={`sr${i === sel ? " sel" : ""}`}
                    onMouseEnter={() => setSel(i)}
                    onClick={() => run(r)}
                  >
                    <span className="sr-ic">
                      <Icon name={r.kind === "ask" ? "spark" : r.kind === "thread" ? "user" : "list"} size="sm" />
                    </span>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <div className="sr-n" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.name}
                      </div>
                      <div className="sr-m">{r.meta}</div>
                    </span>
                  </div>
                </div>
              );
            })}
            {missed && (
              <div style={{ padding: "8px 9px", marginTop: 4, borderTop: "1px solid var(--border)" }}>
                <button className="qa-b" style={{ width: "100%" }} onClick={() => onRegister(q.trim())}>
                  <Icon name="plus" size="sm" />{word}
                </button>
              </div>
            )}
          </div>
          <div className="spot-prev">
            <Preview r={cur} client={client} onOpenThread={onOpenThread} onAction={onAction} />
          </div>
        </div>
      )}

      <div className="spot-foot">
        <span><span className="kbd">↑↓</span> navigate</span>
        <span><span className="kbd">↵</span> run</span>
        <span><span className="kbd">esc</span> dismiss</span>
      </div>
    </div>
  );
}

/** One thread read per highlighted row, debounced, cached for the life of
 *  this palette. Without it the quick actions would be a guess, and a guess
 *  about what a person may do is exactly what the guard exists to stop. */
function Preview({
  r, client, onOpenThread, onAction,
}: {
  r: Row | undefined;
  client: Client;
  onOpenThread: (id: string) => void;
  onAction: (thread: string, op: Operation) => void;
}) {
  const [seen, setSeen] = useState<Record<string, ThreadView>>({});
  const id = r?.kind === "thread" ? r.id : "";

  useEffect(() => {
    if (!id || seen[id]) return;
    let live = true;
    const t = setTimeout(() => {
      client.thread(id).then(
        (data) => live && setSeen((was) => ({ ...was, [id]: data })),
        () => {},                       // a preview that cannot load is just empty
      );
    }, 150);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [id, client, seen]);

  if (!r) return null;

  if (r.kind === "ask") {
    return (
      <>
        <div className="pv-top">
          <div className="pv-av"><Icon name="spark" size="lg" /></div>
          <div>
            <div className="pv-n">Ask the agent</div>
          </div>
        </div>
        <div className="pv-rows">
          <div className="pv-r"><span>Question</span><b style={{ maxWidth: 200 }}>{r.name}</b></div>
        </div>
      </>
    );
  }

  if (r.kind !== "thread") {
    return (
      <>
        <div className="pv-top">
          <div className="pv-av"><Icon name="list" size="lg" /></div>
          <div>
            <div className="pv-n">{r.name}</div>
            <div className="pv-s">{r.meta}</div>
          </div>
        </div>
      </>
    );
  }

  const t = seen[r.id];
  const badges = Object.entries(r.row.badges ?? {});
  return (
    <>
      <div className="pv-top">
        <div className="pv-av">{r.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}</div>
        <div>
          <div className="pv-n">{r.name}</div>
          <div className="pv-s">{r.meta}</div>
        </div>
      </div>
      <div className="pv-rows">
        {Object.entries(r.row.subject ?? {}).map(([k, v]) =>
          v === null || v === undefined || v === "" ? null : (
            <div className="pv-r" key={k}><span>{human(k)}</span><b>{String(v)}</b></div>
          ),
        )}
      </div>
      {badges.length > 0 && (
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 15 }}>
          {badges.map(([flag, style]) => <Badge key={flag} style={style}>{human(flag)}</Badge>)}
        </div>
      )}
      <div className="pv-lab">Quick actions</div>
      <div className="qa-grid">
        <button className="qa-b" onClick={() => onOpenThread(r.id)}>
          <Icon name="folder" size="sm" />Open thread
        </button>
        {(t?.actions ?? []).slice(0, 3).map((op) => (
          <button key={op.id} className="qa-b" onClick={() => onAction(r.id, op)}>
            <Icon name={iconFor(op)} size="sm" />{op.short}
          </button>
        ))}
      </div>
      {!t && <div className="hint" style={{ marginTop: 12 }}>Reading...</div>}
    </>
  );
}
