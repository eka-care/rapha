/** The patient thread screen. Adapted from care_phc_fe ThreadPanel.tsx, with
 *  the fixtures cut out and the hard-coded line removed: the steps drawn here
 *  are thread.line, which the workflow declaration produced. This file names
 *  no station and no flag.
 *
 *  What the panel shows is not a UI choice: an action is absent, not greyed
 *  out, until its precondition is met, and that decision is the guard's, made
 *  on the server, arriving in thread.actions.
 */
import type { AuditRecord, Operation, Proposal, ThreadView } from "./types";
import { AuditRow, Line, ProposalRow } from "./ViewRenderer";
import { Badge, human } from "./ui";

/** The renderer's one heuristic, and a gap worth closing: a flag is drawn as
 *  clinical risk if it says so in its name. contracts.View.badges lets a queue
 *  declare this properly; a workflow cannot yet, so a thread guesses. */
const risky = (flag: string) => /critical|flagged|overdue|refused/.test(flag);
const identity = (k: string) => /abha|abdm/i.test(k);

function initialsOf(name: string) {
  return name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
}

/** Who touched this thread, in the order they first did. Derived from the
 *  audit trail because the audit trail is the only record of it. */
function team(audit: AuditRecord[]): [string, string][] {
  const seen = new Map<string, string>();
  for (const a of audit) {
    if (a.actor && !seen.has(a.actor)) seen.set(a.actor, a.operation);
  }
  return [...seen.entries()];
}

export function Thread({
  thread, onAction, onReview,
}: {
  thread: ThreadView;
  onAction: (op: Operation) => void;
  onReview: (p: Proposal) => void;
}) {
  const subject = thread.subject ?? {};
  const entries = Object.entries(subject).filter(([, v]) => v !== null && v !== undefined && v !== "");
  const nameKey = entries.find(([k]) => k === "name") ?? entries.find(([, v]) => typeof v === "string");
  const name = nameKey ? String(nameKey[1]) : thread.id;
  // The subject is whatever the workflow's subject resource holds, which
  // includes plumbing: row ids, who wrote the row and when. The test is the
  // shape of the key, not its meaning, so this stays bundle agnostic. The
  // whole record is one tab away, in the summary view.
  const plumbing = (k: string) => /(^|_)id$|_date$|_by$|^status$/.test(k) || k === thread.workflow;
  const meta = entries
    .filter(([k]) => k !== nameKey?.[0] && !identity(k) && !plumbing(k))
    .map(([, v]) => String(v));
  const abha = entries.find(([k]) => identity(k));
  const at = thread.line.find((s) => s.status === "now");
  const pending = (thread.proposals ?? []).filter((p) => p.status === "pending");

  return (
    <div className="phc chatgrid">
      <div className="card chatcard">
        <div className="pt-head">
          <div className="avatar">{initialsOf(name)}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="pt-name">{name}</div>
            <div className="pt-meta">{meta.join(" · ")}</div>
            <div style={{ display: "flex", gap: 6, marginTop: 7, flexWrap: "wrap" }}>
              {abha ? (
                <span className="id-badge">
                  <span className="id-lab">{human(abha[0])}</span>
                  <span className="id-val">{String(abha[1])}</span>
                </span>
              ) : null}
              <Badge style="blue">{at ? human(at.station) : "Line complete"}</Badge>
              {thread.flags.filter(risky).map((f) => <Badge key={f} style="crit">{human(f)}</Badge>)}
            </div>
          </div>
        </div>

        <div className="thread">
          {pending.length > 0 && (
            <div className="msg">
              <div className="m-av agent">*</div>
              <div style={{ display: "grid", gap: 8 }}>
                <div className="bubble">
                  {pending.length} proposal{pending.length === 1 ? "" : "s"} waiting for a person.
                  Nothing in {pending.length === 1 ? "it" : "them"} has been recorded.
                </div>
                {pending.map((p) => <ProposalRow key={p.id} p={p} onReview={onReview} />)}
              </div>
            </div>
          )}

          {thread.audit.map((a) => (
            <div className="msg" key={a.id}>
              <div className="m-av">{a.outcome.startsWith("denied") ? "x" : "+"}</div>
              <div className="opcard">
                <div className="op-t">
                  {human(a.operation)}
                  <span className="ml-auto">
                    <Badge style={a.outcome.startsWith("denied") ? "crit" : a.outcome === "proposed" ? "warn" : "ok"}>
                      {a.outcome}
                    </Badge>
                  </span>
                </div>
                <div className="op-m">{a.at} · {a.actor ?? "unattributed"} · {a.surface}</div>
              </div>
            </div>
          ))}

          {thread.audit.length === 0 && pending.length === 0 && (
            <div className="empty">Nothing has happened on this thread yet.</div>
          )}
        </div>

        <div className="composer">
          <div className="cbar wrap">
            {thread.actions.length === 0 && (
              <span className="f-hint" style={{ padding: "6px 2px" }}>
                Nothing for you to do here. An action does not appear before its precondition is
                met, and it does not appear at all without the capability.
              </span>
            )}
            {thread.actions.map((op, i) => (
              <button
                key={op.id}
                className={`cq${i === 0 && op.station === thread.station ? " rose" : ""}`}
                onClick={() => onAction(op)}
                title={`${op.summary}\n${op.instrument}${op.irreversibility === "irreversible" ? " · irreversible" : ""}`}
              >
                {op.irreversibility === "irreversible" && "! "}
                {op.short}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="card">
          <div className="card-h">
            <div>
              <div className="eyebrow">{human(thread.workflow)}</div>
              <div className="card-t" style={{ marginTop: 2 }}>Where this stands</div>
            </div>
            <span className="badge b-mute ml-auto">{at ? human(at.station) : "Complete"}</span>
          </div>
          <Line line={thread.line} />
          {thread.nudge && <div className="nudge">{thread.nudge}</div>}
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-t">Flags</div>
            <span className="badge b-mute ml-auto">{thread.flags.length}</span>
          </div>
          <div className="caps">
            {thread.flags.length
              ? thread.flags.map((f) => <span key={f} className={`cap on${risky(f) ? " risk" : ""}`}>{f}</span>)
              : <span className="f-hint">None true yet.</span>}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-t">Who touched this</div>
            <span className="badge b-mute ml-auto">{team(thread.audit).length}</span>
          </div>
          <div className="team">
            {team(thread.audit).length ? (
              team(thread.audit).map(([actor, first]) => (
                <div className="tm" key={actor}>
                  <span className="p-av">{initialsOf(actor)}</span>
                  {actor}
                  <span className="r">{human(first)}</span>
                </div>
              ))
            ) : (
              <span className="f-hint">Nobody yet.</span>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-t">Capabilities held</div>
            <span className="badge b-mute ml-auto">{thread.held.length}/{thread.capabilities.length}</span>
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
            {thread.audit.length
              ? [...thread.audit].reverse().map((a) => <AuditRow key={a.id} a={a} />)
              : <span className="f-hint">No operations posted.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
