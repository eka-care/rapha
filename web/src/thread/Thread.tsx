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
import type { Client } from "../api";
import { OperationPanel } from "../form/Panel";
import { clock, type Ctx, type Msg, type Said } from "../messages";
import type { Operation, Proposal, ThreadView } from "../types";
import { human } from "../words";
import { Message, withMentions } from "./Message";

export function Stream({ msgs, thread, client, ctx, instruments, onDone, children }: {
  msgs: Msg[];
  thread: ThreadView;
  client: Client;
  ctx: Ctx;
  instruments?: Record<string, unknown>;
  onDone: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="thread">
      {msgs.length === 0 && (
        <div className="state-empty">
          Nothing recorded for this visit yet.<br />
          Type a message, @mention someone, use / for an action, or dictate.
        </div>
      )}
      {msgs.map((m) => (
        <Entry key={m.id} m={m} thread={thread} client={client} ctx={ctx}
               instruments={instruments} onDone={onDone} />
      ))}
      {children}
    </div>
  );
}

function Entry({ m, thread, client, ctx, instruments, onDone }: {
  m: Msg; thread: ThreadView; client: Client; ctx: Ctx;
  instruments?: Record<string, unknown>; onDone: () => void;
}) {
  if (m.kind === "said") {
    return <Message who={m.who} actor={m.actor} at={clock(m.at)} text={m.text} />;
  }

  if (m.kind === "handover") return <Handover m={m} />;

  if (m.kind === "posted") {
    return (
      <div className="msg">
        <div className="m-av node kept" aria-hidden="true"><span className="u-sr">record</span></div>
        <div className="m-b">
          <div className="m-meta">{m.actor} · {clock(m.at)}</div>
          <div className="bubble">
            <div className="t">
              {m.title}
              {m.tags.map((t) => (
                <span className={`badge ${TAG[t.style] ?? "b-mute"}`} key={t.text}>{t.text}</span>
              ))}
            </div>
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
          </div>
        </div>
      </div>
    );
  }

  if (m.kind === "denied") {
    return (
      <div className="msg">
        <div className="m-av node refused" aria-hidden="true"><span className="u-sr">refused</span></div>
        <div className="m-b">
          <div className="m-meta">{m.actor} · {clock(m.at)}</div>
          <div className="bubble">
            <div className="t">{m.title}<span className="badge b-crit">Refused</span></div>
            {m.reason}
            <div className="fl-e" style={{ padding: "6px 0 0" }}>Nothing was written.</div>
          </div>
        </div>
      </div>
    );
  }

  return <ProposalCard m={m} thread={thread} client={client} ctx={ctx}
                       instruments={instruments} onDone={onDone} />;
}

const TAG: Record<string, string> = { crit: "b-crit", warn: "b-warn", ok: "b-ok", mute: "b-mute" };

/** §12.2, §12.3. The border stays neutral: §57 draws it in the agent colour,
 *  which §50 reserves for AI, and a nurse's note is not model output. */
function Handover({ m }: { m: Extract<Msg, { kind: "handover" }> }) {
  return (
    <div className="msg">
      <div className="m-av node handed" aria-hidden="true"><span className="u-sr">handover</span></div>
      <div className="m-b" style={{ width: "100%" }}>
        <div className="m-meta">{m.from} · {clock(m.at)}</div>
        <div className="bubble">
          <div className="t">
            {m.title}
            <span className={`badge ${STATE[m.state] ?? "b-mute"}`}>{human(m.state)}</span>
            {m.priority !== "normal" && <span className="badge b-warn">{human(m.priority)}</span>}
          </div>
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
      </div>
    </div>
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
