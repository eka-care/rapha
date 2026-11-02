/** §9: the thread, in the prototype's shape.
 *
 *  A committed operation is a bubble with a title, its values in a kvbox and
 *  its provenance on the meta line. A refusal is the same bubble saying what
 *  the guard said and that nothing was written. A proposal is the review panel
 *  inline, because §23 forbids anything else. A handover is one object
 *  carrying every reply (§12.3).
 *
 *  §10 lists eight object types. Task and Comment are not here: the kernel has
 *  no row behind either, and drawing one would be a picture of a product.
 */
import { useState } from "react";
import type { Client } from "../api";
import { OperationPanel } from "../form/Panel";
import { clock, type Ctx, type Msg, type Said } from "../messages";
import type { Operation, Proposal, ThreadView } from "../types";
import { human } from "../words";
import { Message, withMentions } from "./Message";

export function Stream({ msgs, thread, client, ctx, instruments, editable, onEdit, onDone, children }: {
  msgs: Msg[];
  thread: ThreadView;
  client: Client;
  ctx: Ctx;
  instruments?: Record<string, unknown>;
  /** The ids of the records this person may still correct. Decided by the
   *  screen above, from the visit's state and the operation's own
   *  reversibility, never here: this file draws what it is given. */
  editable?: Set<string>;
  onEdit?: (m: Extract<Msg, { kind: "posted" }>) => void;
  onDone: () => void;
  children?: React.ReactNode;
}) {
  // EVERY STATION BEHIND THIS ONE IS A LINE. Not the last record open and
  // the rest folded -- the last record is still a station somebody finished,
  // and leaving it open put a six value card between the doctor and the one
  // thing they are here to do. What is open is what is happening now, which
  // is the agent's own node at the foot of this list, and nothing else.
  //
  // The line carries what was recorded, so folding costs nothing anybody was
  // reading: a nurse's blood pressure is on it, in the words the kernel drew
  // it in, and the card is one tap under it.
  return (
    <div className="thread">
      <div className="tether" aria-hidden="true" />
      {msgs.length === 0 && (
        <div className="state-empty">
          Nothing recorded for this visit yet.<br />
          Type a message, @mention someone, use / for an action, or dictate.
        </div>
      )}
      {msgs.map((m) => (
        <Entry key={m.id} m={m} thread={thread} client={client} ctx={ctx}
               editable={editable} onEdit={onEdit}
               instruments={instruments} onDone={onDone} />
      ))}
      {children}
    </div>
  );
}

function Entry({ m, thread, client, ctx, instruments, editable, onEdit, onDone }: {
  m: Msg; thread: ThreadView; client: Client; ctx: Ctx;
  instruments?: Record<string, unknown>;
  editable?: Set<string>;
  onEdit?: (m: Extract<Msg, { kind: "posted" }>) => void;
  onDone: () => void;
}) {
  if (m.kind === "said") {
    return <Message who={m.who} actor={m.actor} at={clock(m.at)} text={m.text} />;
  }

  if (m.kind === "handover") return <Handover m={m} />;

  if (m.kind === "posted") {
    return <Posted m={m} onEdit={editable?.has(m.id) && onEdit ? () => onEdit(m) : undefined} />;
  }

  if (m.kind === "denied") {
    return (
      <Fold tone="refused" who={m.actor} title={m.title} at={clock(m.at)}
            summary={m.reason}
            badges={<span className="badge b-crit">Refused</span>}>
        <div className="bubble">
          {m.reason}
          <div className="fl-e" style={{ padding: "6px 0 0" }}>Nothing was written.</div>
        </div>
      </Fold>
    );
  }

  return <ProposalCard m={m} thread={thread} client={client} ctx={ctx}
                       instruments={instruments} onDone={onDone} />;
}

/** A value on one folded line. A consultation's history runs to a sentence
 *  and three of them would push the time off the row before the ellipsis
 *  caught them, so each is cut to its first clause. The whole value is one
 *  tap away, which is the point of the fold. */
function brief(value: string): string {
  const text = String(value);
  if (text.length <= 32) return text;
  const stop = text.slice(0, 32).lastIndexOf(" ");
  return text.slice(0, stop > 12 ? stop : 32) + "…";
}

/** A finished station: one line, and whatever it holds when opened.
 *
 *  THE RULE THIS KEEPS. Everything already done on this visit is a line, and
 *  the only thing open on the screen is what is happening now. A record, a
 *  handover and a refusal are all things somebody finished, so all three come
 *  through here; a fourth kind cannot arrive as a full card by forgetting to
 *  fold itself.
 *
 *  The line says who, what, a summary of it, and when, so folding costs
 *  nothing anybody was reading.
 */
function Fold({ tone, who, title, summary, at, badges, children }: {
  tone: "kept" | "refused" | "handed";
  who: string;
  title: string;
  summary?: string;
  at: string;
  badges?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className={`ev${shown ? " on" : ""}`}>
      <div className={`m-av node ${tone}`} aria-hidden="true" />
      <div className="m-b">
        <button className="ev-h" aria-expanded={shown} onClick={() => setShown((v) => !v)}>
          <span className="chev" aria-hidden="true">›</span>
          <span className="ev-st">{who}</span>
          <span className="ev-t">{title}</span>
          {badges}
          {!shown && summary && <span className="ev-sum">{summary}</span>}
          <span className="ev-time">{at}</span>
        </button>
        {shown && children}
      </div>
    </div>
  );
}

/** One committed record on the thread: a line, and its card when opened.
 *
 *  The line is the record -- who, what, when, and what it said -- so a visit
 *  reads as a list of stations rather than as a stack of forms. It starts
 *  closed, every one of them: a record on the thread is something somebody
 *  already finished, and the only thing that should be open on this screen is
 *  what is happening now.
 */
function Posted({ m, onEdit }: {
  m: Extract<Msg, { kind: "posted" }>;
  /** Absent when this record can no longer be changed -- the visit is over,
   *  or something later replaced it -- and the row then shows no control,
   *  because an Edit button that refuses is worse than none. */
  onEdit?: () => void;
}) {
  return (
    <Fold tone="kept" who={m.actor} title={m.title} at={clock(m.at)}
          summary={m.values.slice(0, 3).map((v) => `${v.label} ${brief(v.value)}`).join(" · ")}
          badges={<>
            {m.edited && <span className="badge b-mute">Edited</span>}
            {m.tags.map((t) => (
              <span className={`badge ${TAG[t.style] ?? "b-mute"}`} key={t.text}>{t.text}</span>
            ))}
          </>}>
      <div className="bubble">
        {m.values.length > 0 && (
          <div className="kvbox">
            {m.values.map((v) => (
              <div className={`kv${v.crit ? " crit" : ""}`} key={v.link_id}>
                <span>{v.label}</span>
                <b>{v.value}{v.crit ? " · critical" : ""}</b>
              </div>
            ))}
          </div>
        )}
        {m.transcript && <div className="quote">{m.transcript}</div>}
        {onEdit && (
          <div className="kept-do">
            <button type="button" className="cq" onClick={onEdit}>Edit this</button>
          </div>
        )}
      </div>
    </Fold>
  );
}

const TAG: Record<string, string> = { crit: "b-crit", warn: "b-warn", ok: "b-ok", mute: "b-mute" };

/** §12.2, §12.3. The border stays neutral: §57 draws it in the agent colour,
 *  which §50 reserves for AI, and a nurse's note is not model output. */
function Handover({ m }: { m: Extract<Msg, { kind: "handover" }> }) {
  return (
    <Fold tone="handed" who={m.from} title={m.title} at={clock(m.at)}
          summary={`→ @${human(m.to)} · ${m.note}`}
          badges={<>
            <span className={`badge ${STATE[m.state] ?? "b-mute"}`}>{human(m.state)}</span>
            {m.priority !== "normal" && <span className="badge b-warn">{human(m.priority)}</span>}
          </>}>
      <div className="bubble">
        <div style={{ display: "flex", alignItems: "center", gap: 7, fontWeight: 600,
                      color: "var(--color-text-primary)", marginBottom: 6 }}>
          {m.from}<span aria-hidden="true">→</span>
          <span className="mention">@{human(m.to)}</span>
        </div>
        {withMentions(m.note)}
        {m.replies.length > 0 && (
          <div style={{ marginTop: 11, borderTop: "1px solid var(--color-border-subtle)", paddingTop: 10,
                        display: "grid", gap: 10 }}>
            {m.replies.map((r) => (
              <div key={r.id}>
                <div className="m-meta">
                  {r.actor} · {clock(r.at)}
                  {r.state && <span className="fl-e" style={{ padding: 0 }}>set to {human(r.state)}</span>}
                </div>
                {withMentions(r.comment)}
              </div>
            ))}
          </div>
        )}
      </div>
    </Fold>
  );
}

const STATE: Record<string, string> = {
  open: "b-warn", reopened: "b-warn", acknowledged: "b-mute",
  in_progress: "b-mute", resolved: "b-ok",
};

function ProposalCard({ m, thread, client, ctx, instruments, onDone }: {
  m: Extract<Msg, { kind: "proposal" }>;
  thread: ThreadView; client: Client; ctx: Ctx;
  instruments?: Record<string, unknown>; onDone: () => void;
}) {
  if (m.stale) {
    return (
      <div className="msg">
        <div className="m-av agent" aria-hidden="true" />
        <div className="m-b">
          <div className="m-meta">Proposed by {m.by} · {clock(m.at)}</div>
          <div className="bubble">
            <div className="t">{m.title}<span className="badge b-mute">Stale</span></div>
            The visit has moved past this. Confirming it would be refused.
          </div>
        </div>
      </div>
    );
  }
  return (
    <OperationPanel
      op={operationFor(m.proposal, ctx.operations)}
      thread={thread.id}
      client={client}
      proposal={m.proposal}
      instruments={instruments}
      flags={thread.flags}
      inline
      onDone={onDone}
    />
  );
}

function operationFor(p: Proposal, ops: Record<string, Operation>): Operation {
  return ops[p.operation] ?? ({
    id: p.operation, kind: "write", short: p.operation, title: p.operation,
    summary: "", capability: "", station: "", instrument: "form",
    preconditions: [], irreversibility: "correctable", input: "",
    writes: [], emits: [], verified: "unverified", tool: "", description: "",
  } as Operation);
}

export type { Said };
