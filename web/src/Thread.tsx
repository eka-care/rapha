/** The patient screen, which is a conversation.
 *
 *  A patient is a thread. The record accumulates as posted messages, the agent
 *  speaks last and says where the visit stands, and you either tap one of its
 *  offers or type a question. The forms are not on this screen: they open in a
 *  modal from it and post back into it.
 *
 *  Which messages there are, what the agent says and which pills the composer
 *  carries are all decided in messages.ts, which is pure and checked. This
 *  file draws them and nothing else. It names no station, no flag and no
 *  operation, and it cannot write: every write leaves through a callback to
 *  the shell, which opens the modal.
 *
 *  A pending proposal is the one message that is not read-only. It carries the
 *  commit surface itself, drawn inside the bubble, so the values a machine
 *  filled in are read, corrected and confirmed without leaving the thread. This
 *  file does not draw it and cannot: the shell passes it in as renderProposal,
 *  so the only thing on this screen that can write is a thing this screen did
 *  not build.
 *
 *  The rule that matters most here is the one you cannot see: an action whose
 *  precondition is unmet, or whose capability is not held, is absent. Nothing
 *  below can render a disabled pill, because thread.actions never contains
 *  one. The reason for an absence is the agent's second sentence.
 */
import { useEffect, useRef, useState } from "react";
import { Icon, iconFor } from "./icons";
import { weigh } from "./loops";
import {
  agentLine, clock, composer, header, messages, queueViewFor,
  type Ctx, type Kv, type Msg, type Pill, type Said, type Tag,
} from "./messages";
import type { AuditRecord, Catalogue, Operation, Proposal, ThreadView, ViewDecl } from "./types";
import { Badge, human } from "./ui";
import { Line } from "./ViewRenderer";

export function Thread({
  thread, cat, ctx, said, asking, onSay, onAction, renderProposal, onReject, onSummary, onMore,
}: {
  thread: ThreadView;
  cat: Catalogue;
  ctx: Ctx;
  said: Said[];
  /** An utterance is in flight. The input stays usable; only the send button
   *  says so, because a chat that freezes has lost the person's sentence. */
  asking?: boolean;
  onSay: (text: string) => void;
  onAction: (op: Operation) => void;
  /** The commit surface for one pending proposal, built by the shell. */
  renderProposal: (p: Proposal) => React.ReactNode;
  onReject: (p: Proposal) => void;
  onSummary: (v: ViewDecl) => void;
  onMore: () => void;
}) {
  const queue = queueViewFor(cat, thread.workflow);
  const head = header(thread, queue);
  const msgs = messages(thread, ctx, said);
  const line = agentLine(thread, ctx);
  // The agent's bubble now carries the one primary action and its overflow;
  // an operation pill down here would be the same operation offered twice.
  // A summary is a view, not an operation, so it still belongs in the bar.
  const summaries = composer(thread, cat).pills.filter((p) => p.kind === "summary");

  return (
    <div className="chatgrid">
      <div className="card chatcard">
        <div className="pt-head">
          <div className="avatar">{head.initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="pt-name">{head.name}</div>
            <div className="pt-meta">{head.meta.join(" · ")}</div>
            <div style={{ display: "flex", gap: 6, marginTop: 7, flexWrap: "wrap" }}>
              {head.identity && (
                <span className="id-badge">
                  <span className="id-lab">{head.identity.label}</span>
                  <span className="id-val">{head.identity.value}</span>
                </span>
              )}
              {head.badges.map((b, i) => (
                <Badge key={`${b.text}-${i}`} style={b.style}>{b.text}</Badge>
              ))}
            </div>
          </div>
        </div>

        <Scroll msgs={msgs}>
          <Refusals msgs={msgs} />
          {msgs
            .filter((m) => !(m.kind === "denied" && m.old))
            .map((m) => (
              <Message key={m.id} m={m} renderProposal={renderProposal} onReject={onReject} />
            ))}
          <AgentBubble line={line} closes={thread.closes} onAction={onAction} onMore={onMore} />
        </Scroll>

        <div className="composer">
          {summaries.length > 0 && (
            <div className="cbar">
              {summaries.map((p) => (
                <PillButton
                  key={`${p.kind}-${p.view?.id ?? p.label}`}
                  p={p}
                  onAction={onAction}
                  onSummary={onSummary}
                  onMore={onMore}
                />
              ))}
            </div>
          )}
          <Ask asking={asking} onSay={onSay} about={head.name} />
        </div>
      </div>

      <Panel thread={thread} />
    </div>
  );
}

/** Newest at the bottom, and the bottom is where you are put. */
function Scroll({ msgs, children }: { msgs: Msg[]; children: React.ReactNode }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (el.current) el.current.scrollTop = el.current.scrollHeight;
  }, [msgs.length]);
  return <div className="thread" ref={el}>{children}</div>;
}

// ------------------------------------------------------------------ messages

function Message({
  m, renderProposal, onReject,
}: {
  m: Msg;
  renderProposal: (p: Proposal) => React.ReactNode;
  onReject: (p: Proposal) => void;
}) {
  if (m.kind === "said" && m.who === "user") {
    return (
      <div className="msg right">
        <div className="m-av"><Icon name="user" size="sm" /></div>
        <div className="m-b">
          <div className="m-meta" style={{ justifyContent: "flex-end" }}>
            {m.actor} · {clock(m.at)}
          </div>
          <div className="bubble">{m.text}</div>
        </div>
      </div>
    );
  }
  if (m.kind === "said") {
    return (
      <Bubble av="agent" meta={<>Agent · {clock(m.at)}</>}>
        {m.text}
      </Bubble>
    );
  }
  if (m.kind === "denied") {
    return (
      <Bubble
        av="x"
        meta={<>System · {clock(m.at)} <Badge>{m.actor}</Badge> <Badge>refused</Badge></>}
      >
        <div className="t">{m.title}</div>
        {m.reason}
      </Bubble>
    );
  }
  if (m.kind === "proposal") {
    return (
      <Bubble
        av="agent"
        meta={
          <>
            Agent · {clock(m.at)} <Badge>over {m.surface}</Badge>
            {m.stale
              ? <Badge>superseded</Badge>
              : <Badge style="warn">awaiting a person</Badge>}
          </>
        }
      >
        <div className="t">{m.title}</div>
        {m.stale ? (
          <>
            The visit has moved past it.
            <Values values={m.values} />
            <div className="props">
              <button className="prop" onClick={() => onReject(m.proposal)}>
                <Icon name="alert" />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="p-l">Reject</span>
                </span>
              </button>
            </div>
          </>
        ) : (
          <div className="inlinepanel">{renderProposal(m.proposal)}</div>
        )}
      </Bubble>
    );
  }
  return (
    <Bubble
      av="check"
      meta={
        <>
          System · {clock(m.at)}
          {m.tags.map((t: Tag, i: number) => (
            <Badge key={`${t.text}-${i}`} style={t.style}>{t.text}</Badge>
          ))}
        </>
      }
    >
      <div className="t">{m.title}</div>
      <Values values={m.values} />
      {m.transcript && <div className="quote">"{m.transcript}"</div>}
    </Bubble>
  );
}

function Bubble({
  av, meta, children,
}: { av: "agent" | "check" | "x"; meta: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="msg" style={{ maxWidth: "97%" }}>
      <div className={`m-av${av === "agent" ? " agent" : ""}`}>
        <Icon name={av === "agent" ? "spark" : av === "x" ? "alert" : "check"} size="sm" />
      </div>
      <div className="m-b" style={{ flex: 1 }}>
        <div className="m-meta">{meta}</div>
        <div className="bubble">{children}</div>
      </div>
    </div>
  );
}

/** The values that were recorded, labelled by the questionnaire. A committed
 *  row that shows no values is a receipt for something invisible. */
function Values({ values }: { values: Kv[] }) {
  if (!values.length) return null;
  return (
    <div className="kvbox">
      {values.map((v) => (
        <div className={`kv${v.crit ? " crit" : ""}`} key={v.link_id}>
          <span>{v.label}</span>
          <b>{v.value}</b>
        </div>
      ))}
    </div>
  );
}

/** Refusals matter and they should not drown the record, so the ones older
 *  than the last posted operation fold into one line. */
function Refusals({ msgs }: { msgs: Msg[] }) {
  const old = msgs.filter((m) => m.kind === "denied" && m.old);
  const [open, setOpen] = useState(false);
  if (!old.length) return null;
  return (
    <div className="msg" style={{ maxWidth: "97%" }}>
      <div className="m-av"><Icon name="alert" size="sm" /></div>
      <div className="m-b" style={{ flex: 1 }}>
        <button className="cq" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"} {old.length} earlier refusal{old.length === 1 ? "" : "s"}
        </button>
        {open && (
          <div className="bubble" style={{ marginTop: 8 }}>
            {old.map((m) => (
              <div key={m.id} style={{ padding: "3px 0" }}>
                <b>{clock(m.at)} {m.kind === "denied" ? m.title : ""}</b>
                {": "}
                {m.kind === "denied" ? m.reason : ""}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the agent

function AgentBubble({
  line, closes, onAction, onMore,
}: {
  line: ReturnType<typeof agentLine>;
  closes: string | null;
  onAction: (op: Operation) => void;
  onMore: () => void;
}) {
  const { primary, overflow } = weigh(line.actions, closes);
  return (
    <Bubble av="agent" meta={<>Agent · now</>}>
      {line.sentences.join(" ")}
      {primary && (
        <div className="acts">
          <button className="prop primary" style={{ flex: 1, minWidth: 0 }}
                  title={primary.summary} onClick={() => onAction(primary)}>
            <Icon name={iconFor(primary)} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className="p-l">{primary.title}</span>
            </span>
            <span className={`p-tag ${tagClass(primary)}`}>
              {primary.irreversibility === "irreversible" ? "irreversible" : primary.instrument}
            </span>
          </button>
          {overflow.length > 0 && (
            <button className="cq" onClick={onMore}>{overflow.length} more</button>
          )}
        </div>
      )}
    </Bubble>
  );
}

const tagClass = (op: Operation) =>
  op.irreversibility === "irreversible" ? "irr" : op.instrument === "scribe" ? "scribe" : "form";

// -------------------------------------------------------------- the composer

function PillButton({
  p, onAction, onSummary, onMore,
}: {
  p: Pill;
  onAction: (op: Operation) => void;
  onSummary: (v: ViewDecl) => void;
  onMore: () => void;
}) {
  const go = () =>
    p.kind === "more" ? onMore() : p.view ? onSummary(p.view) : p.op ? onAction(p.op) : undefined;
  const icon =
    p.kind === "scribe" ? "mic" : p.kind === "summary" ? "eye" : p.kind === "more" ? "list" : p.op ? iconFor(p.op) : "clip";
  return (
    <button
      className={`cq${p.primary ? " rose" : ""}`}
      onClick={go}
      title={p.op ? `${p.op.summary}\n${p.op.instrument}` : undefined}
    >
      <Icon name={icon as never} size="sm" />
      {p.label}
    </button>
  );
}

/** "Ask about this patient" is the prototype's copy and it is a PHC word. The
 *  thread's own headline is the generic form of the same sentence, and it is
 *  more specific besides. */
function Ask({ asking, onSay, about }: { asking?: boolean; onSay: (t: string) => void; about: string }) {
  const [text, setText] = useState("");
  const send = () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    onSay(t);
  };
  return (
    <div className="crow">
      <input
        value={text}
        placeholder={`Ask about ${about}`}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && send()}
      />
      <button className="btn btn-b send" onClick={send} title={asking ? "Thinking" : "Send"}>
        <Icon name={asking ? "spark" : "send"} />
      </button>
    </div>
  );
}

// -------------------------------------------------------------- the right rail

function Panel({ thread }: { thread: ThreadView }) {
  const done = [...thread.line].reverse().find((s) => s.status === "done");
  const crew = team(thread.audit ?? []);

  return (
    <div className="panel">
      <div className="card">
        <div className="card-h">
          <div>
            <div className="eyebrow">{human(thread.workflow)}</div>
            <div className="card-t" style={{ marginTop: 2 }}>Where this stands</div>
          </div>
          <span className="badge b-mute ml-auto">{done ? human(done.label) : "Not started"}</span>
        </div>
        <Line line={thread.line} />
      </div>

      <div className="card">
        <div className="card-h">
          <div>
            <div className="eyebrow">This visit</div>
            <div className="card-t" style={{ marginTop: 2 }}>Care unit</div>
          </div>
          <span className="badge b-mute ml-auto">{crew.length}</span>
        </div>
        <div className="team">
          {crew.length ? (
            crew.map(([actor, firstOp]) => (
              <div className="tm" key={actor}>
                <span className="p-av" style={{ width: 22, height: 22, fontSize: 9 }}>
                  {actor.slice(0, 2).toUpperCase()}
                </span>
                {actor}
                <span className="r">{human(firstOp)}</span>
              </div>
            ))
          ) : (
            <span className="f-hint">Nobody yet.</span>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <Icon name="lock" size="sm" />
          <div className="card-t">Capabilities held</div>
        </div>
        <div className="caps">
          {thread.capabilities.map((c) => (
            <span key={c} className={`cap${thread.held.includes(c) ? " on" : ""}`}>{c}</span>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <div className="card-t">Audit trail</div>
          <span className="badge b-mute ml-auto">{thread.audit.length}</span>
        </div>
        <div className="audit">
          {thread.audit.length ? (
            [...thread.audit].reverse().map((a) => <Row key={a.id} a={a} />)
          ) : (
            <span className="f-hint">Nothing posted.</span>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ a }: { a: AuditRecord }) {
  const denied = a.outcome.startsWith("denied");
  return (
    <div className="au">
      <span>{clock(a.at)}</span>
      <b>{a.operation.replace(/^[a-z0-9]+\.op\./, "")}</b>
      <span className="ml-auto">{a.actor ?? "unattributed"}</span>
      <Badge style={denied ? "crit" : a.outcome === "proposed" ? "warn" : "ok"}>{a.outcome}</Badge>
    </div>
  );
}

/** Who touched this thread, in the order they first did. The audit trail is
 *  the only record of it. */
function team(audit: AuditRecord[]): [string, string][] {
  const seen = new Map<string, string>();
  for (const a of audit) if (a.actor && !seen.has(a.actor)) seen.set(a.actor, a.operation);
  return [...seen.entries()];
}
