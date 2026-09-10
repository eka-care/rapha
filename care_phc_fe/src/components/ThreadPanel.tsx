import { Fragment } from "react";

import type { Action, Thread } from "../types";

// Two vocabularies, as in the prototype, and they are not interchangeable.
// `label` is the step: past tense, what has been done. `at` is the place the
// patient is standing. "Dispensed" as a location would tell a pharmacist the
// medicine has already been handed over.
// Which station the patient is AT is decided by the backend, in thread.station.
const LINE = [
  { key: "reception", label: "Registered", at: "Reception", done: "registered" },
  { key: "nurse", label: "Vitals", at: "Vitals", done: "vitals.recorded" },
  { key: "doctor", label: "Consultation", at: "Doctor", done: "consult.documented" },
  { key: "lab", label: "Investigation", at: "Lab", done: "lab.resulted", needs: "lab.ordered" },
  { key: "pharmacy", label: "Dispensed", at: "Pharmacy", done: "dispensed.complete", needs: "rx.confirmed" },
] as const;

const INSTRUMENT: Record<Action["instrument"], string> = {
  form: "Form", device: "Device or form", "constrained-voice": "Voice, read back",
  scribe: "Scribe draft", palette: "Search",
};

const RISK: Record<string, string> = {
  "vitals.flagged": "Vitals flagged",
  "lab.critical": "Critical result",
};

const CAP = 6; // addendum §D: six on screen, the rest behind the palette.

export function ThreadPanel({
  thread, bundleLabel, onAction,
}: {
  thread: Thread;
  bundleLabel: string;
  /** Required: a thread panel whose buttons quietly do nothing is worse than
   *  one that has none. */
  onAction: (action: Action) => void;
}) {
  const flags = new Set(thread.flags);
  const { patient } = thread;
  const initials = patient.name.split(" ").map((w) => w[0]).slice(0, 2).join("");
  const shown = thread.actions.slice(0, CAP);
  const overflow = thread.actions.length - shown.length;
  const at = LINE.find((s) => s.key === thread.station)?.at;
  const abha = flags.has("abha.linked");

  return (
    <div className="phc chatgrid">
      <div className="card chatcard">
        <div className="pt-head">
          <div className="avatar">{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="pt-name">{patient.name}</div>
            <div className="pt-meta">
              {patient.age}
              {patient.sex} · {patient.village} · {patient.note}
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 7, flexWrap: "wrap" }}>
              {abha ? (
                <span className="id-badge">
                  <span className="id-lab">ABHA</span>
                  <span className="id-val">linked</span>
                </span>
              ) : (
                <span className="badge b-warn">ABHA pending</span>
              )}
              <span className="badge b-blue">{at ?? "Visit complete"}</span>
              {Object.keys(RISK)
                .filter((f) => flags.has(f))
                .map((f) => (
                  <span key={f} className="badge b-crit">{RISK[f]}</span>
                ))}
            </div>
          </div>
        </div>

        <div className="thread">
          {thread.audit.map(([time, op, by], i) => (
            <div className="msg" key={`${time}-${i}`}>
              <div className="m-av">✓</div>
              <div className="opcard">
                <div className="op-t">
                  {op.replace("phc.op.", "").replace(/-/g, " ")}
                  <span className="badge b-ok ml-auto">posted</span>
                </div>
                <div className="op-m">
                  {time} · {by}
                </div>
              </div>
            </div>
          ))}
          {thread.audit.length === 0 && (
            <div className="empty">Nothing posted for this visit yet.</div>
          )}
          <div className="msg">
            <div className="m-av agent">✦</div>
            <div className="bubble">
              {thread.agent} Currently at <b>{at ?? "nothing outstanding"}</b>.
              Here is what you can do as {bundleLabel.toLowerCase()}.
            </div>
          </div>
        </div>

        <div className="composer">
          <div className="cbar">
            {shown.length === 0 && (
              <span style={{ fontSize: 11.5, color: "var(--ink-3)", padding: "6px 2px" }}>
                Nothing for {bundleLabel.toLowerCase()} to do here. An action does not
                appear before its precondition is met.
              </span>
            )}
            {shown.map((a, i) => (
              <button
                key={a.id}
                className={`cq${i === 0 && a.station === thread.station ? " rose" : ""}`}
                onClick={() => onAction(a)}
                title={`${a.summary}\n${INSTRUMENT[a.instrument]}${
                  a.irreversibility === "irreversible" ? " · irreversible" : ""
                }`}
              >
                {a.irreversibility === "irreversible" && "⚠ "}
                {a.short}
              </button>
            ))}
            {overflow > 0 && <span className="cq" style={{ opacity: 0.6 }}>+{overflow} in ⌘K</span>}
          </div>
          <div className="crow">
            <input placeholder={`Ask about ${patient.name.split(" ")[0]}`} readOnly />
            <button className="send" title="No agent in Phase 0">›</button>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="card">
          <div className="card-h">
            <div>
              <div className="eyebrow">Visit</div>
              <div className="card-t" style={{ marginTop: 2 }}>Patient state</div>
            </div>
            <span className="badge b-mute ml-auto">{at ?? "Closed"}</span>
          </div>
          <div className="states">
            {LINE.map((s, i) => {
              const skipped = "needs" in s && s.needs ? !flags.has(s.needs) : false;
              const done = flags.has(s.done);
              const now = s.key === thread.station;
              return (
                <div key={s.key} className={`st${done ? " done" : ""}${now ? " now" : ""}${
                  skipped && !done ? " skip" : ""}`}>
                  <span className="n">{done ? "✓" : i + 1}</span>
                  {s.label}
                  {skipped && !done && (
                    <span className="ml-auto" style={{ fontSize: 9.5 }}>not this visit</span>
                  )}
                </div>
              );
            })}
          </div>
          <div className="nudge">{thread.nudge}</div>
        </div>

        <div className="card">
          <div className="card-h">
            <div>
              <div className="eyebrow">Per patient</div>
              <div className="card-t" style={{ marginTop: 2 }}>Care unit</div>
            </div>
            <span className="badge b-mute ml-auto">{thread.team.length}</span>
          </div>
          <div className="team">
            {thread.team.length ? (
              thread.team.map(([init, name, role]) => (
                <div className="tm" key={name}>
                  <span className="p-av">{init}</span>
                  {name}
                  <span className="r">{role}</span>
                </div>
              ))
            ) : (
              <div style={{ fontSize: 11.5, color: "var(--ink-3)", padding: "4px 0" }}>
                Nobody joined yet. Members accrue as stations touch the patient.
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-t">Capabilities held</div>
            <span className="badge b-mute ml-auto">
              {thread.held.length}/{thread.capabilities.length}
            </span>
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
              [...thread.audit].reverse().map(([time, op, by], i) => (
                <div className="au" key={`${time}-${i}`}>
                  <span>{time}</span>
                  <b>{op.replace("phc.op.", "")}</b>
                  <span className="ml-auto">{by}</span>
                </div>
              ))
            ) : (
              <div style={{ padding: "10px 2px", fontSize: 11, color: "var(--gray-400)" }}>
                No operations posted.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ThreadPanel;
