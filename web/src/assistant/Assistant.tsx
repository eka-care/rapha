/** The medical assistant: Eka MedAssist, drawn in this app's own parts.
 *
 *  NOT THE THREAD AGENT. Rapha's own agent reads the declared operations and
 *  refuses when a capability is missing; it is the kernel's and stays so.
 *  This one answers medical questions in general. It is given nothing about
 *  a patient -- no name, no visit, no record -- so what a person types is the
 *  only thing that leaves the page.
 *
 *  It is loaded on first use (see Lazy.tsx), because the package connects the
 *  moment its provider mounts. A screen nobody asked the assistant on makes
 *  no connection.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  MEDASSIST_COMPONENTS, MedAssistProvider, useMedAssist,
  type Elicitation, type TOption,
} from "@eka-care/medassist-react";
import { Icon } from "../icons";
import { assistantConfig } from "./config";

const CONFIG = assistantConfig(import.meta.env as Record<string, string | undefined>);

export default function Assistant() {
  if (!CONFIG.ready) return <p className="assist__note">{CONFIG.why}</p>;
  return (
    <MedAssistProvider
      agentId={CONFIG.agentId}
      environment={CONFIG.environment}
      authToken={CONFIG.authToken}
    >
      <Chat />
    </MedAssistProvider>
  );
}

function Chat() {
  const {
    messages, isConnected, isStreaming, isWaitingForResponse, progressMessage, initialMessage,
    error, canRetry, needsNewSession, authExpired, elicitation,
    sendMessage, sendSuggestion, retry, startNewChat,
  } = useMedAssist();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); },
    [messages.length, progressMessage, elicitation?.tool_id, isWaitingForResponse]);

  if (authExpired) return <p className="assist__note">The medical assistant's sign-in ran out. Reload the page.</p>;
  if (!isConnected && messages.length === 0 && !error) return <p className="assist__note">Connecting…</p>;

  const empty = messages.length === 0;
  const busy = isWaitingForResponse || isStreaming;
  return (
    <div className="assist__chat">
      <div className="assist__log" role="log" aria-live="polite">
        {empty && initialMessage?.text && <p className="assist__msg" data-role="assistant">{initialMessage.text}</p>}
        {empty && !!initialMessage?.suggestions?.length && (
          <div className="assist__chips">
            {initialMessage.suggestions.map((s) => (
              <button key={s.value} type="button" className="chip"
                onClick={() => void sendSuggestion(s.value ?? "")}>
                {s.label ?? s.value}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <p key={m.id} className="assist__msg" data-role={m.role === "user" ? "user" : "assistant"}>
            {m.content}
          </p>
        ))}
        {(progressMessage || (busy && messages.length > 0)) && (
          <p className="assist__hint">{progressMessage ?? "Thinking…"}</p>
        )}
        {error && (
          <div className="assist__error" role="alert">
            <strong>{error.message}</strong>
            {error.description && <span> {error.description}</span>}
            {needsNewSession
              ? <button type="button" className="btn btn-g" onClick={() => void startNewChat()}>Start a new chat</button>
              : canRetry && <button type="button" className="btn btn-g" onClick={() => void retry()}>Try again</button>}
          </div>
        )}
        {elicitation && !elicitation.disabled && <Question elicitation={elicitation} />}
        <div ref={end} />
      </div>
      <Entry disabled={isWaitingForResponse} onSend={(t) => void sendMessage(t)}
        onNew={messages.length ? () => void startNewChat() : undefined} />
    </div>
  );
}

function Entry({ disabled, onSend, onNew }: {
  disabled: boolean; onSend: (text: string) => void; onNew?: () => void;
}) {
  const [text, setText] = useState("");
  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText("");
  };
  return (
    <form className="assist__entry" onSubmit={send}>
      {onNew && (
        <button type="button" className="icon-btn" onClick={onNew} aria-label="Start a new chat">
          <Icon name="plus" className="i sm" />
        </button>
      )}
      <input className="input" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Ask a medical question" aria-label="Ask a medical question" disabled={disabled} autoFocus />
      <button type="submit" className="btn btn-b" disabled={disabled || !text.trim()} aria-label="Send">
        <Icon name="send" className="i sm" />
      </button>
    </form>
  );
}

/** One branch per component the assistant can ask with. `input` says what to
 *  draw; `respond` says what to send back. Display-only ones draw nothing. */
function Question({ elicitation }: { elicitation: Elicitation }) {
  const input = elicitation.input as Record<string, unknown> | undefined;
  const text = typeof input?.text === "string" ? input.text : undefined;
  const options = (input?.options as TOption[] | undefined) ?? [];
  const C = MEDASSIST_COMPONENTS;

  switch (elicitation.component) {
    case C.MOBILE:
    case C.EMAIL:
      return <TextAnswer label={text ?? (elicitation.component === C.MOBILE ? "Mobile number" : "Email address")}
        pattern={elicitation.pattern} onSubmit={(v) => elicitation.respond(v)} />;
    case C.OTP:
      return <TextAnswer label={text ?? "Enter the code you were sent"} pattern={elicitation.pattern}
        onSubmit={(v) => elicitation.respond(v)}
        extra={<button type="button" className="btn btn-g" onClick={() => void elicitation.resend()}>Send again</button>} />;
    case C.PILL:
      return (
        <div className="assist__ask">
          {text && <p className="assist__q">{text}</p>}
          <div className="assist__chips">
            {options.map((o) => (
              <button key={o.value} type="button" className="chip" onClick={() => void elicitation.respond(o)}>
                {o.label}
              </button>
            ))}
          </div>
        </div>
      );
    case C.MULTI:
      return <ManyAnswer label={text} options={options} onConfirm={(v) => elicitation.respond(v.join(", "))} />;
    case C.CARD: {
      const cards = (input?.cards as { card_id: string; title?: string; description?: string }[] | undefined) ?? [];
      return (
        <div className="assist__ask">
          {cards.map((c) => (
            <button key={c.card_id} type="button" className="assist__card"
              onClick={() => void elicitation.respond({ selectedComponent: c as never, selected_id: c.card_id })}>
              <strong>{c.title}</strong>
              {c.description && <span>{c.description}</span>}
            </button>
          ))}
          <button type="button" className="btn btn-g" onClick={() => void elicitation.decline("none of these")}>
            None of these
          </button>
        </div>
      );
    }
    case C.DOCTOR_CARD: {
      const doctors = (input?.doctors as { doctor_id?: string }[] | undefined) ?? [];
      const details = (input?.doctor_details as Record<string, { name: string; specialty: string }> | undefined) ?? {};
      return (
        <div className="assist__ask">
          {doctors.map((d, i) => {
            const who = d.doctor_id ? details[d.doctor_id] : undefined;
            return (
              <button key={d.doctor_id ?? i} type="button" className="assist__card"
                onClick={() => void elicitation.respond({ selectedComponent: d as never, selected_id: d.doctor_id })}>
                <strong>{who?.name ?? "Doctor"}</strong>
                {who?.specialty && <span>{who.specialty}</span>}
              </button>
            );
          })}
          <button type="button" className="btn btn-g" onClick={() => void elicitation.decline("none of these")}>
            None of these
          </button>
        </div>
      );
    }
    default:
      return null;
  }
}

function TextAnswer({ label, pattern, onSubmit, extra }: {
  label: string; pattern?: string; onSubmit: (v: string) => Promise<void>; extra?: React.ReactNode;
}) {
  const [value, setValue] = useState("");
  let valid = value.length > 0;
  if (pattern) { try { valid = new RegExp(pattern).test(value); } catch { /* a pattern we cannot read does not block the answer */ } }
  return (
    <form className="assist__ask" onSubmit={(e) => {
      e.preventDefault();
      if (valid) void onSubmit(value).then(() => setValue(""));
    }}>
      <label className="assist__q">
        {label}
        <input className="input" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
      </label>
      <div className="assist__row">
        <button type="submit" className="btn btn-b" disabled={!valid}>Send</button>
        {extra}
      </div>
    </form>
  );
}

function ManyAnswer({ label, options, onConfirm }: {
  label?: string; options: TOption[]; onConfirm: (values: string[]) => Promise<void>;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  return (
    <div className="assist__ask">
      {label && <p className="assist__q">{label}</p>}
      <div className="assist__chips">
        {options.map((o) => (
          <button key={o.value} type="button" className="chip" aria-pressed={picked.includes(o.value)}
            data-selected={picked.includes(o.value)}
            onClick={() => setPicked((p) => p.includes(o.value) ? p.filter((v) => v !== o.value) : [...p, o.value])}>
            {o.label}
          </button>
        ))}
      </div>
      <div className="assist__row">
        <button type="button" className="btn btn-b" disabled={!picked.length} onClick={() => void onConfirm(picked)}>
          Send
        </button>
      </div>
    </div>
  );
}
