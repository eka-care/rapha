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
import { Icon, type IconName } from "../icons";
import { clock, type Msg, type Said } from "../messages";
import type { Operation, Proposal } from "../types";
import { human, title } from "../words";
import { Message, Turn, roleVar, withMentions } from "./Message";
import { blocks, split, type Block } from "./fold";

export function Stream({ msgs, editable, onEdit, onReview, children }: {
  msgs: Msg[];
  editable?: Set<string>;
  onEdit?: (m: Extract<Msg, { kind: "posted" }>) => void;
  onReview?: (m: Extract<Msg, { kind: "proposal" }>) => void;
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
      <Body msgs={msgs} editable={editable} onEdit={onEdit} onReview={onReview} />
      {children}
    </div>
  );
}

function Entry({ m, editable, onEdit, onReview }: {
  m: Msg;
  editable?: Set<string>;
  onEdit?: (m: Extract<Msg, { kind: "posted" }>) => void;
  onReview?: (m: Extract<Msg, { kind: "proposal" }>) => void;
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
            icon="alert" summary={m.reason}
            badges={<span className="badge b-crit">Refused</span>}>
        <div className="bubble">
          {m.reason}
          <div className="fl-e" style={{ padding: "6px 0 0" }}>Nothing was written.</div>
        </div>
      </Fold>
    );
  }

  return <ProposalCard m={m} onReview={onReview} />;
}

/** A value on one folded line. A consultation's history runs to a sentence
 *  and three of them would push the time off the row before the ellipsis
 *  caught them, so each is cut to its first clause. The whole value is one
 *  tap away, which is the point of the fold. */
function brief(value: string): string {
  const text = String(value);
  if (text.length <= 90) return text;
  const stop = text.slice(0, 90).lastIndexOf(" ");
  return text.slice(0, stop > 30 ? stop : 90) + "…";
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
/** One row of the log, in two columns: who posted it and when, then what they
 *  posted. A row opens to show everything it holds; closed it shows the first lines. */
function Fold({ tone, who, title, summary, lines, at, badges, icon = "doc", children }: {
  tone: "kept" | "refused" | "handed";
  who: string;
  title: string;
  summary?: string;
  lines?: { k: string; v: string }[];
  at: string;
  badges?: React.ReactNode;
  icon?: IconName;
  children: React.ReactNode;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className={`lg2 ${tone}${shown ? " on" : ""}`}>
      <div className="lg2-who" style={{ color: roleVar(who) }}>
        {who}
        <time>{at}</time>
      </div>
      <div className="lg2-body">
        <button className="lg2-h" aria-expanded={shown} onClick={() => setShown((v) => !v)}>
          <Icon name={icon} className="i sm lg2-i" />
          <span className="lg2-t">{title}</span>
          {badges}
          <Icon name="chev" className={`i sm lg2-c${shown ? " open" : ""}`} />
        </button>
        {!shown && summary && <div className="lg2-line">{summary}</div>}
        {!shown && lines?.map((l) => (
          <div className="lg2-line" key={l.k}><b>{l.k}</b>{l.v}</div>
        ))}
        {shown && children}
      </div>
    </div>
  );
}

function Posted({ m, onEdit }: {
  m: Extract<Msg, { kind: "posted" }>;
  /** Absent when this record can no longer be changed -- the visit is over,
   *  or something later replaced it -- and the row then shows no control,
   *  because an Edit button that refuses is worse than none. */
  onEdit?: () => void;
}) {
  return (
    <Fold tone="kept" who={m.actor} title={m.title} at={clock(m.at)}
          icon={m.transcript ? "mic" : "doc"}
          lines={m.values.slice(0, 3).map((v) => ({ k: v.label, v: brief(v.value) }))}
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
/** The visit, as blocks: what folds is decided in fold.ts, and this draws
 *  the answer. The older part sits behind one control, because the thing
 *  being read on a long visit is the bottom of the list.
 */
function Body({ msgs, editable, onEdit, onReview }: {
  msgs: Msg[];
  editable?: Set<string>;
  onEdit?: (m: Extract<Msg, { kind: "posted" }>) => void;
  onReview?: (m: Extract<Msg, { kind: "proposal" }>) => void;
}) {
  const [all, setAll] = useState(false);
  const { earlier, recent } = split(blocks(msgs));
  const draw = (b: Block) => {
    if (b.kind === "refusals") return <Refusals key={b.id} rows={b.rows} machine={b.machine} />;
    if (b.kind === "turn") {
      const first = b.msgs[0];
      return <Turn key={b.id} who={first.who} actor={first.actor} at={clock(first.at)}
                   to={first.to} texts={b.msgs.map((m) => m.text)} />;
    }
    return <Entry key={b.id} m={b.msg} editable={editable} onEdit={onEdit} onReview={onReview} />;
  };
  return (
    <>
      {earlier.length > 0 && !all && (
        <button type="button" className="cq earlier" onClick={() => setAll(true)}>
          Show {earlier.length} earlier
        </button>
      )}
      {(all ? earlier : []).map(draw)}
      {recent.map(draw)}
    </>
  );
}

/** A refusal is not a patient problem, and a machine's refusal is not even a
 *  person's. The agent's fold says how many and nothing else; a person's
 *  names what was refused, because somebody is waiting on it.
 */
function Refusals({ rows, machine }: { rows: Extract<Msg, { kind: "denied" }>[]; machine: boolean }) {
  const [shown, setShown] = useState(false);
  const one = rows.length === 1;
  const who = machine ? "" : rows[0].actor;
  return (
    <div className={`lg2 refused${shown ? " on" : ""}`}>
      <div className="lg2-who" style={{ color: roleVar(who) }}>
        {who}
        <time>{clock(rows[rows.length - 1].at)}</time>
      </div>
      <div className="lg2-body">
        <button className="lg2-h" aria-expanded={shown} onClick={() => setShown((v) => !v)}>
          <Icon name="alert" className="i sm lg2-i" />
          <span className="lg2-t">{one ? rows[0].title : `${rows.length} refused`}</span>
          <Icon name="chev" className={`i sm lg2-c${shown ? " open" : ""}`} />
        </button>
        {!shown && <div className="lg2-line">{one ? rows[0].reason : "Nothing was written."}</div>}
        {shown && (
          <div className="bubble">
            {rows.map((r) => (
              <div className="ref-1" key={r.id}>
                <b>{r.title}</b>
                <span>{r.reason}</span>
              </div>
            ))}
            <div className="fl-e" style={{ padding: "6px 0 0" }}>Nothing was written.</div>
          </div>
        )}
      </div>
    </div>
  );
}

function Handover({ m }: { m: Extract<Msg, { kind: "handover" }> }) {
  return (
    <Fold tone="handed" who={m.from} title={m.title} at={clock(m.at)} icon="refer"
          summary={`→ @${human(m.to)} · ${m.note}`}
          badges={<>
            <span className={`badge ${STATE[m.state] ?? "b-mute"}`}>{title(m.state)}</span>
            {m.priority !== "normal" && <span className="badge b-warn">{title(m.priority)}</span>}
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
                  {r.state && <span className="fl-e" style={{ padding: 0 }}>set to {title(r.state)}</span>}
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

/** A PROPOSAL IS A LINE IN THE THREAD, AND ITS FORM IS ON THE SCRIBE TAB.
 *
 *  The review panel used to be drawn here, whole, between two messages: a
 *  six-field form inside a conversation. Owner, 2026-11-04: "all of the note
 *  structuring should happen on the scribe tab, not on the thread". The
 *  thread says that something is waiting and who asked; one tap takes the
 *  reader to where it is structured. */
function ProposalCard({ m, onReview }: {
  m: Extract<Msg, { kind: "proposal" }>;
  onReview?: (m: Extract<Msg, { kind: "proposal" }>) => void;
}) {
  const who = (
    <div className="lg2-who" style={{ color: "var(--color-agent)" }}>
      {m.by}
      <time>{clock(m.at)}</time>
    </div>
  );
  if (m.stale) {
    return (
      <div className="lg2">
        {who}
        <div className="lg2-body">
          <div className="lg2-t"><Icon name="spark" className="i sm lg2-i" />{m.title}<span className="badge b-mute">Stale</span></div>
          <div className="lg2-line">The visit has moved past this. Confirming it would be refused.</div>
        </div>
      </div>
    );
  }
  return (
    <div className="lg2">
      {who}
      <div className="lg2-body">
        <div className="lg2-line">Proposed for review</div>
        <div className="props">
          <button type="button" className="prop primary" onClick={() => onReview?.(m)}>
            <span className="p-b"><span className="p-l">Review {m.title}</span></span>
          </button>
        </div>
      </div>
    </div>
  );
}

/** The operation a proposal names, or a stand in for one this facility no
 *  longer declares, so the Scribe tab can still say it refuses. */
export function operationFor(p: Proposal, ops: Record<string, Operation>): Operation {
  return ops[p.operation] ?? ({
    id: p.operation, kind: "write", short: p.operation, title: p.operation,
    summary: "", capability: "", station: "", instrument: "form",
    preconditions: [], irreversibility: "correctable", input: "",
    writes: [], emits: [], verified: "unverified", tool: "", description: "",
  } as Operation);
}

export type { Said };
