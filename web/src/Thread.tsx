/** The patient screen, which is a conversation.
 *
 *  A patient is a thread. The record accumulates as posted messages, the agent
 *  speaks last and says where the visit stands, and you either tap one of its
 *  offers or type a question. The forms are not on this screen: they open in a
 *  modal from it and post back into it.
 *
 *  Which messages there are and what the agent says are decided in
 *  messages.ts, which is pure and checked. This file draws them and nothing
 *  else. It names no station, no flag and no
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
import { mine, records, weigh } from "./loops";
import {
  agentLine, clock, header, messages, queueViewFor, summariesFor,
  type Ctx, type Kv, type Msg, type Said, type Tag,
} from "./messages";
import type { Catalogue, Operation, Proposal, SectionResult, ThreadView, ViewDecl } from "./types";
import { Badge, human } from "./ui";
import { Line } from "./ViewRenderer";

export function Thread({
  thread, cat, ctx, said, sections, asking, onSay, onAction, renderProposal, onReject, onSummary, onMore,
}: {
  thread: ThreadView;
  cat: Catalogue;
  ctx: Ctx;
  said: Said[];
  /** The summary view's own sections, for this thread. The rail's Records
   *  panel is these, filtered to what read a resource and produced rows. */
  sections: SectionResult[];
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
  // The one summary view this workflow declares. Its sections are also the
  // rail's records: what the thread produced, not what it is allowed to do.
  const summaryView = summariesFor(cat, thread.workflow)[0];
  const rs = records(sections);

  return (
    <div className="chatgrid">
      <div className="card chatcard">
        <div className="pt-head">
          <div className="avatar">{head.initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Name and station are the topbar's heading; this card names only
                what the topbar does not: age, sex, village. */}
            <div className="pt-meta">{head.meta.join(" · ")}</div>
            <div style={{ display: "flex", gap: 4, marginTop: 8, flexWrap: "wrap" }}>
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
              <Message
                key={m.id} m={m} cat={cat} station={thread.station}
                renderProposal={renderProposal} onReject={onReject}
              />
            ))}
          <AgentBubble line={line} closes={thread.closes} onAction={onAction} onMore={onMore} />
        </Scroll>

        <div className="composer">
          <Ask asking={asking} onSay={onSay} about={head.name} />
        </div>
      </div>

      <Panel thread={thread} recs={rs} summaryView={summaryView} onSummary={onSummary} />
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
  m, cat, station, renderProposal, onReject,
}: {
  m: Msg;
  cat: Catalogue;
  station: string | null;
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
        meta={<>System · {clock(m.at)}</>}
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
            Agent · {clock(m.at)}
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
  const card = (
    <Bubble
      av="check"
      meta={
        <>
          {m.actor} · {clock(m.at)}
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

  // Another station's finished work is context, not this screen's task: fold
  // it to one line rather than open it above whatever this role is here to do.
  const op = cat.operations[m.operation];
  if (op && !mine(op, station)) {
    return (
      <details className="folded">
        <summary>{op.short} · {m.actor} · {clock(m.at)}</summary>
        {card}
      </details>
    );
  }
  return card;
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
              <div key={m.id} style={{ padding: "4px 0" }}>
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
          </button>
          {overflow.length > 0 && (
            <button className="cq" onClick={onMore}>{overflow.length} more</button>
          )}
        </div>
      )}
    </Bubble>
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

function Panel({
  thread, recs, summaryView, onSummary,
}: {
  thread: ThreadView;
  /** The documents this thread produced, from the summary view's own
   *  sections. See loops.ts:records(). */
  recs: { title: string; count: number }[];
  summaryView?: ViewDecl;
  onSummary: (v: ViewDecl) => void;
}) {
  const done = [...thread.line].reverse().find((s) => s.status === "done");

  return (
    <div className="panel">
      <div className="card">
        <div className="card-h" style={{ justifyContent: "space-between" }}>
          <div className="card-t">Where this stands</div>
          <span className="badge">{done ? human(done.label) : "Not started"}</span>
        </div>
        <Line line={thread.line} />
      </div>

      <div className="card">
        <div className="card-t">Records</div>
        {recs.length === 0 ? (
          <div className="close-e">Nothing yet</div>
        ) : (
          recs.map((r) => (
            <button
              key={r.title}
              className="rec"
              onClick={() => summaryView && onSummary(summaryView)}
            >
              <span>{r.title}</span>
              {r.count > 1 && <span className="rec-n">{r.count}</span>}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
