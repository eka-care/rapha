/** §9: the thread. The conversational representation of clinical work.
 *
 *  Four kinds come out of messages.ts, and each is drawn as the §10 object it
 *  actually is:
 *
 *    said (user)   -> Message            a person talking
 *    said (agent)  -> Message            an agent insight (§21)
 *    posted        -> ThreadObject       a committed operation: the clinical
 *                                        event or artifact it wrote (§27)
 *    proposal      -> the review panel   read/propose/REVIEW/commit (§23)
 *    denied        -> ThreadObject       a refusal, with the guard's reason
 *
 *  §10 lists eight first-class objects. Handover, Task and Comment are the
 *  three not here, and their absence is deliberate: the kernel has no object
 *  behind any of them yet -- a handover is presently a note, and there is no
 *  task row and no comment row at all. Drawing an acknowledged-and-resolved
 *  handover over a stateless note would be a picture of a product rather than
 *  a product. They arrive with the kernel work that backs them.
 */
import type { Client } from "../api";
import { OperationPanel } from "../form/Panel";
import { clock, type Ctx, type Msg, type Said } from "../messages";
import type { Operation, Proposal, ThreadView } from "../types";
import { human } from "../words";
import { Message } from "./Message";
import { ThreadObject, Values } from "./ThreadObject";

export function Stream({
  msgs, thread, client, ctx, instruments, onDone, emptyHint,
}: {
  msgs: Msg[];
  thread: ThreadView;
  client: Client;
  ctx: Ctx;
  instruments?: Record<string, unknown>;
  onDone: () => void;
  emptyHint?: React.ReactNode;
}) {
  if (!msgs.length) {
    return (
      <div className="thread">
        <div className="empty">
          <div className="t-strong">Start the encounter.</div>
          <div className="t-body u-mute">
            Type a message, @mention someone, use / for an action, or dictate.
          </div>
          {emptyHint}
        </div>
      </div>
    );
  }
  return (
    <div className="thread">
      {msgs.map((m) => (
        <Entry
          key={m.id} m={m} thread={thread} client={client} ctx={ctx}
          instruments={instruments} onDone={onDone}
        />
      ))}
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
      <ThreadObject
        label={m.title}
        end={clock(m.at)}
        footer={<span>{m.actor}</span>}
      >
        <Values rows={m.values} />
        {m.transcript && (
          <details style={{ marginTop: "var(--space-3)" }}>
            {/* §19: the transcript is evidence, not the record. It is one
                click away rather than in the way. */}
            <summary className="t-meta u-faint" style={{ cursor: "pointer" }}>Transcript</summary>
            <div className="transcript" style={{ marginTop: "var(--space-2)" }}>{m.transcript}</div>
          </details>
        )}
      </ThreadObject>
    );
  }

  if (m.kind === "denied") {
    // §75: what failed, whether anything changed, what to do. A refusal wrote
    // nothing, and that is the sentence people most need.
    return (
      <ThreadObject
        label={m.title}
        end={clock(m.at)}
        tone="critical"
        footer={<span>{m.actor}</span>}
      >
        <div className="t-body">{m.reason}</div>
        <div className="t-meta u-faint" style={{ marginTop: "var(--space-1)" }}>
          Nothing was written.
        </div>
      </ThreadObject>
    );
  }

  // A proposal. Never committed here; read, edited and confirmed by a person.
  return (
    <ProposalCard
      m={m} thread={thread} client={client} ctx={ctx}
      instruments={instruments} onDone={onDone}
    />
  );
}

function ProposalCard({ m, thread, client, ctx, instruments, onDone }: {
  m: Extract<Msg, { kind: "proposal" }>;
  thread: ThreadView; client: Client; ctx: Ctx;
  instruments?: Record<string, unknown>; onDone: () => void;
}) {
  const op = operationFor(m.proposal, ctx.operations);
  if (m.stale) {
    return (
      <ThreadObject label={m.title} end={clock(m.at)} footer={<span>Proposed by {m.by}</span>}>
        <Values rows={m.values} />
        <div className="t-meta u-faint" style={{ marginTop: "var(--space-3)" }}>
          The visit has moved past this. Confirming it would be refused.
        </div>
      </ThreadObject>
    );
  }
  return (
    <OperationPanel
      op={op}
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

/** §12.2 and §12.3: what was asked, who of, every reply, and the state the
 *  last reply left it in. The border stays neutral: §57 draws it in the agent
 *  colour, which §50 reserves for AI, and a nurse's note is not model output.
 */
function Handover({ m }: { m: Extract<Msg, { kind: "handover" }> }) {
  return (
    <ThreadObject
      className="handover"
      label={m.title}
      end={clock(m.at)}
      footer={
        <>
          {/* §95: the state is a word first. The tone only reinforces it. */}
          <span className="status" data-tone={TONE[m.state]}>{human(m.state)}</span>
          {m.priority !== "normal" && (
            <span className="status" data-tone="warning">{human(m.priority)}</span>
          )}
          <span className="handover__state">
            {m.replies.length === 0
              ? "No reply yet"
              : m.replies.length === 1 ? "1 reply" : `${m.replies.length} replies`}
          </span>
        </>
      }
    >
      <div className="handover__route">
        <span>{m.from}</span>
        <span aria-hidden="true">&rarr;</span>
        <span className="mention">@{human(m.to)}</span>
      </div>
      <div className="handover__message">{m.note}</div>
      {m.replies.length > 0 && (
        <div className="handover__replies">
          {m.replies.map((r) => (
            <div className="handover__reply" key={r.id}>
              <div className="message__meta">
                <strong style={{ color: "var(--color-text-secondary)" }}>{r.actor}</strong>
                <span aria-hidden="true">&middot;</span>
                <time>{clock(r.at)}</time>
                {r.state && <span className="u-faint">set to {human(r.state)}</span>}
              </div>
              <div className="message__body">{r.comment}</div>
            </div>
          ))}
        </div>
      )}
    </ThreadObject>
  );
}

/** §12.1's states, and the only tone each one earns. Resolved is the single
 *  success in this product's whole vocabulary; open and reopened are waiting
 *  on somebody, which is attention, not alarm. */
const TONE: Record<string, string | undefined> = {
  open: "warning", reopened: "warning", acknowledged: undefined,
  in_progress: undefined, resolved: "success",
};

/** The operation a proposal is for. A proposal the catalogue has no
 *  declaration for is a kernel bug, not something to paper over with a blank
 *  card, so the placeholder says exactly that. */
function operationFor(p: Proposal, ops: Record<string, Operation>): Operation {
  const known = ops[p.operation];
  if (known) return known;
  return {
    id: p.operation, kind: "write", short: p.operation, title: p.operation,
    summary: "", capability: "", station: "", instrument: "form",
    preconditions: [], irreversibility: "correctable", input: "",
    writes: [], emits: [], verified: "unverified", tool: "", description: "",
  } as Operation;
}

export type { Said };
