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
 *  The rule that matters most here is the one you cannot see: an action whose
 *  precondition is unmet, or whose capability is not held, is absent. Nothing
 *  below can render a disabled pill, because thread.actions never contains
 *  one. The reason for an absence is the agent's second sentence.
 */
import { useEffect, useRef, useState } from "react";
import { Icon, iconFor } from "./icons";
import {
  agentLine, clock, composer, header, messages, queueViewFor,
  type Ctx, type Kv, type Msg, type Pill, type Said, type Tag,
} from "./messages";
import type { AuditRecord, Catalogue, Operation, Proposal, ThreadView, ViewDecl } from "./types";
import { Badge, human } from "./ui";
import { Line } from "./ViewRenderer";

export function Thread({
  thread, cat, ctx, role, said, asking, onSay, onAction, onReview, onReject, onSummary, onMore,
}: {
  thread: ThreadView;
  cat: Catalogue;
  ctx: Ctx;
  role: string;
  said: Said[];
  /** An utterance is in flight. The input stays usable; only the send button
   *  says so, because a chat that freezes has lost the person's sentence. */
  asking?: boolean;
  onSay: (text: string) => void;
  onAction: (op: Operation) => void;
  onReview: (p: Proposal) => void;
  onReject: (p: Proposal) => void;
  onSummary: (v: ViewDecl) => void;
  onMore: () => void;
}) {
  const queue = queueViewFor(cat, thread.workflow);
  const head = header(thread, queue);
  const msgs = messages(thread, ctx, said);
  const line = agentLine(thread, ctx, role);
  const bar = composer(thread, cat);

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
            .map((m) => <Message key={m.id} m={m} onReview={onReview} onReject={onReject} />)}
          <AgentBubble line={line} onAction={onAction} consentMissing={bar.consentMissing} />
        </Scroll>

        <div className="composer">
          <div className="cbar">
            {bar.pills.map((p) => (
              <PillButton
                key={`${p.kind}-${p.op?.id ?? p.view?.id ?? p.label}`}
                p={p}
                onAction={onAction}
                onSummary={onSummary}
                onMore={onMore}
              />
            ))}
          </div>
          <Ask asking={asking} onSay={onSay} about={head.name} />
        </div>
      </div>

      <Panel thread={thread} cat={cat} />
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
  m, onReview, onReject,
}: { m: Msg; onReview: (p: Proposal) => void; onReject: (p: Proposal) => void }) {
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
            Proposed by {m.by}, and the visit has moved past it. Confirming it would be refused,
            so there is nothing to review. Rejecting it clears it from the thread.
          </>
        ) : (
          <>Proposed by {m.by}. Nothing in it has been recorded.</>
        )}
        <Values values={m.values} unsure={!m.stale} />
        <div className="props">
          {!m.stale && (
            <button className="prop primary" onClick={() => onReview(m.proposal)}>
              <Icon name="check" />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span className="p-l">Review and commit</span>
                <div className="p-s">Opens the values in editable fields. Your tap is the write.</div>
              </span>
            </button>
          )}
          <button className="prop" onClick={() => onReject(m.proposal)}>
            <Icon name="alert" />
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className="p-l">Reject</span>
              <div className="p-s">Records the refusal against this proposal and writes nothing else.</div>
            </span>
          </button>
        </div>
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
function Values({ values, unsure }: { values: Kv[]; unsure?: boolean }) {
  if (!values.length) return null;
  return (
    <div className="kvbox">
      {values.map((v) => (
        <div className={`kv${v.crit ? " crit" : ""}`} key={v.link_id}>
          <span>{v.label}</span>
          <b>{v.value}</b>
        </div>
      ))}
      {unsure && (
        <div className="kv">
          <span style={{ fontStyle: "italic" }}>Unconfirmed until a person taps</span>
        </div>
      )}
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
  line, onAction, consentMissing,
}: {
  line: ReturnType<typeof agentLine>;
  onAction: (op: Operation) => void;
  consentMissing: boolean;
}) {
  return (
    <Bubble av="agent" meta={<>Agent · now</>}>
      {line.sentences.join(" ")}
      {consentMissing && " Capture consent is not recorded on this visit, so the scribe is off."}
      {line.actions.length > 0 && (
        <div className="props">
          {line.actions.map((op, i) => (
            <button key={op.id} className={`prop${i === 0 ? " primary" : ""}`} onClick={() => onAction(op)}>
              <Icon name={iconFor(op)} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span className="p-l">{op.title}</span>
                <div className="p-s">{first(op.summary)}</div>
              </span>
              <span className={`p-tag ${tagClass(op)}`}>
                {op.irreversibility === "irreversible" ? "irreversible" : op.instrument}
              </span>
            </button>
          ))}
        </div>
      )}
    </Bubble>
  );
}

const first = (s: string) => (s || "").split(/(?<=\.)\s|\n/)[0].trim();
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

function Panel({ thread, cat }: { thread: ThreadView; cat: Catalogue }) {
  const done = [...thread.line].reverse().find((s) => s.status === "done");
  const crew = team(thread.audit ?? []);

  // The doctrine the prototype hard-coded per role is written already, in the
  // instrument declarations, attached to the thing it governs. Showing it here
  // is the same sentence with a reason to believe it.
  const here = new Set((thread.actions ?? []).filter((o) => o.station === thread.station).map((o) => o.id));
  const doctrine = Object.values(cat.instruments ?? {})
    .filter((d) => (d.operations ?? []).some((id) => here.has(id)))
    .map((d) => (d as { summary?: string }).summary)
    .filter((s): s is string => !!s);

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
        {thread.nudge && <div className="nudge">{thread.nudge}</div>}
        {doctrine.map((d) => <div className="nudge" key={d}>{d}</div>)}
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
        <div className="nudge">
          Membership accrues as stations touch the patient. It is scoped to this visit, not to the
          facility, and there is no operation that joins it by hand.
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <Icon name="lock" size="sm" />
          <div className="card-t">Capabilities held</div>
          <span className="badge b-mute ml-auto">at {cat.manifest?.title ?? "this facility"}</span>
        </div>
        <div className="caps">
          {thread.capabilities.map((c) => (
            <span key={c} className={`cap${thread.held.includes(c) ? " on" : ""}`}>{c}</span>
          ))}
        </div>
        <div className="nudge">
          Every action you cannot take is absent from this screen rather than greyed out. This is
          where you can see the shape of what is being hidden, and check it against the role in the
          sidebar foot.
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
            <span className="f-hint">No operations posted.</span>
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
