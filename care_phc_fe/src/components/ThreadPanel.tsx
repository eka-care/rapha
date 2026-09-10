import { Fragment } from "react";

import type { Action, Thread } from "../types";

// The outpatient line, for the stepper. Mirrors care_phc/thread.py's LINE, and
// only for drawing: which station the patient is AT is decided by the backend
// and arrives in thread.station.
const LINE: { key: string; label: string; done: string; needs?: string }[] = [
  { key: "reception", label: "Reception", done: "registered" },
  { key: "nurse", label: "Vitals", done: "vitals.recorded" },
  { key: "doctor", label: "Doctor", done: "consult.documented" },
  { key: "lab", label: "Lab", done: "lab.resulted", needs: "lab.ordered" },
  { key: "pharmacy", label: "Pharmacy", done: "dispensed.complete", needs: "rx.confirmed" },
];

const INSTRUMENT: Record<Action["instrument"], string> = {
  form: "Form",
  device: "Device or form",
  "constrained-voice": "Voice, read back",
  scribe: "Scribe draft",
  palette: "Search",
};

// Colour means clinical risk, never decoration.
const RISK_FLAGS: Record<string, string> = {
  "vitals.flagged": "Vitals flagged",
  "lab.critical": "Critical result",
};

const VISIBLE_CAP = 6; // addendum §D: six on screen, the rest behind the palette.

function Chip({ kind, children }: { kind?: string; children: React.ReactNode }) {
  return <span className={`phc-chip${kind ? " " + kind : ""}`}>{children}</span>;
}

function Step({ step, flags, here }: { step: (typeof LINE)[number]; flags: Set<string>; here: string | null }) {
  const skipped = step.needs ? !flags.has(step.needs) : false;
  const state = flags.has(step.done) ? "done" : step.key === here ? "here" : skipped ? "skip" : "";
  return (
    <div className={`phc-step ${state}`} title={skipped ? "Not part of this visit" : undefined}>
      <span className="dot" />
      {step.label}
    </div>
  );
}

export function ThreadPanel({
  thread,
  bundleLabel,
  onAction,
}: {
  thread: Thread;
  bundleLabel: string;
  /** Called when a clinician picks an action. Required: a thread panel whose
   *  buttons quietly do nothing is worse than one that has none. */
  onAction: (action: Action) => void;
}) {
  const flags = new Set(thread.flags);
  const { patient } = thread;
  const initials = patient.name.split(" ").map((w) => w[0]).slice(0, 2).join("");
  const shown = thread.actions.slice(0, VISIBLE_CAP);
  const overflow = thread.actions.length - shown.length;
  const risks = Object.keys(RISK_FLAGS).filter((f) => flags.has(f));
  const stationLabel = LINE.find((s) => s.key === thread.station)?.label;

  return (
    <div className="phc phc-card">
      <div className="phc-head">
        <div className="phc-av">{initials}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="phc-name">{patient.name}</div>
          <div className="phc-sub">
            {patient.age} · {patient.sex} · {patient.village} — {patient.note}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {flags.has("abha.linked") && <Chip kind="abdm">ABHA linked</Chip>}
          {flags.has("abha.pending") && <Chip kind="warn">ABHA pending</Chip>}
          {risks.map((f) => (
            <Chip key={f} kind="risk">{RISK_FLAGS[f]}</Chip>
          ))}
          {thread.station === null && <Chip kind="done">Visit complete</Chip>}
        </div>
      </div>

      <div className="phc-line">
        {LINE.map((step, i) => (
          <Fragment key={step.key}>
            {i > 0 && <span className="phc-rule" />}
            <Step step={step} flags={flags} here={thread.station} />
          </Fragment>
        ))}
      </div>

      <div className="phc-body">
        <div className="phc-label">
          {bundleLabel} · {stationLabel ? `patient is at ${stationLabel}` : "nothing outstanding"}
        </div>

        {shown.length === 0 ? (
          <div className="phc-empty">
            Nothing for <b>{bundleLabel}</b> to do here.
            <div style={{ marginTop: 6, fontSize: 12 }}>
              An action does not appear before its precondition is met.
            </div>
          </div>
        ) : (
          <div className="phc-actions">
            {shown.map((a, i) => (
              <button
                key={a.id}
                className={`phc-act${i === 0 && a.station === thread.station ? " primary" : ""}`}
                onClick={() => onAction(a)}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="phc-act-t">{a.title}</div>
                  <div className="phc-act-s">{a.summary}</div>
                  <div className="phc-act-m">
                    <Chip>{INSTRUMENT[a.instrument]}</Chip>
                    {a.irreversibility === "irreversible" && <Chip kind="risk">Irreversible</Chip>}
                    {a.verified !== "verified" && <Chip kind="warn">{a.verified}</Chip>}
                  </div>
                </div>
                <span className="phc-act-n">›</span>
              </button>
            ))}
          </div>
        )}

        {overflow > 0 && (
          <div style={{ marginTop: 10, fontSize: 12, color: "var(--ink-3)" }}>
            {overflow} more behind search (⌘K)
          </div>
        )}

        <div className="phc-flags">
          {thread.flags.map((f) => (
            <Chip key={f}>{f}</Chip>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ThreadPanel;
