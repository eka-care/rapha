/** The universal control surface (§2.5, §16, §17).
 *
 *  One bar carries every way into the product: a sentence for the agent, `@`
 *  for people and roles, `/` for the actions this thread will actually accept,
 *  and the microphone (§2.6 -- scribe has no page of its own, so this is the
 *  only place it can be started from).
 *
 *  The trigger for a menu is the last run of non-space characters, and only
 *  when it opens with / or @. An address mid-sentence never opens a menu.
 */
import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { NAME } from "../brand";
import type { Operation } from "../types";
import type { Verb } from "./commands";
import { raphaQuestion } from "./mention";
import { Menu, atItems, slashItems, type Item } from "./Menu";
import { canRecord, recordReading, type Reading } from "../scribe/reading";

/* No cap. The menu is 360px tall and scrolls, and typing narrows it, so a
   slice here only hides the last item without saying it did -- which is how a
   bundle's ninth role became invisible while the other eight looked complete. */
const clamp = (n: number, len: number) => ((n % len) + len) % len;

/** Take the command the person was typing back out of the box, leaving
 *  anything they had written around it. A whole-line command leaves nothing;
 *  a `/` typed after a sentence leaves the sentence. */
const strip = (text: string) =>
  /^\//.test(text) ? "" : text.replace(/(^|\s)[/][^\s]*$/, "$1");

export type Recording = {
  seconds: number; paused: boolean; onStop: () => void; onPause: () => void; onResume: () => void;
} | null;

export function Composer({
  about, actions, roles, verbs, asking, recording, working, quick,
  onSay, onAction, onStartScribe, onAskRapha, micReason, dictate, onAttach, attachReason,
}: {
  about: string;
  actions: Operation[];
  roles: string[];
  /** What the SCREEN can do, beside what the kernel can record. Built in
   *  thread/commands.ts and passed in, because which tabs exist and whether
   *  the microphone may start are the screen's own facts. */
  verbs?: Verb[];
  asking?: boolean;
  recording?: Recording;
  /** Scribe has stopped listening and is writing the notes. Shown on its own button. */
  working?: string;
  onSay: (text: string) => void;
  onAction: (op: Operation, mention?: string) => void;
  onStartScribe?: () => void;
  /** A line addressed to the assistant (`@rapha ...`). It is not a message
   *  in the visit: it opens the assistant at the side and is never posted. */
  onAskRapha?: (question: string) => void;
  /** §34's quick actions, rendered inside the composer row the way the
   *  prototype does: the things you can do sit beside the box you say things
   *  in, not in a toolbar at the top of the screen. */
  quick?: React.ReactNode;
  /** Why the microphone is unavailable, if it is. An icon that does nothing
   *  and says nothing is worse than one that is absent. */
  micReason?: string;
  /** Speak a message into the box. The words are transcribed by the same
   *  service that writes the notes, and land in the box to be read and sent. */
  dictate?: { thread: string; operation: string; reason?: string };
  /** The plus: attach a file or photo. Absent when the station cannot file one. */
  onAttach?: () => void;
  attachReason?: string;
}) {
  const [text, setText] = useState("");
  const [pick, setPick] = useState(0);
  const box = useRef<HTMLTextAreaElement>(null);
  const listId = "composer-menu";

  // DICTATION INTO THE BOX. One press starts, the next ends and sends the
  // audio to be written down; the words are added where the cursor was.
  const [dict, setDict] = useState<"idle" | "listening" | "thinking">("idle");
  const [dictWhy, setDictWhy] = useState("");
  const reading = useRef<Reading | null>(null);
  const toggleDictate = async () => {
    if (!dictate) return;
    if (dict === "listening" && reading.current) {
      const r = reading.current; reading.current = null;
      setDict("thinking"); r.stop();
      const heard = await r.heard;
      const said = heard.transcript.trim();
      setDict("idle");
      if (!said) { setDictWhy(heard.reason || ""); return; }
      setText((t) => (t && !/\s$/.test(t) ? t + " " : t) + said);
      box.current?.focus();
      return;
    }
    if (dict !== "idle") return;
    setDictWhy("");
    reading.current = recordReading(dictate.thread, dictate.operation);
    setDict("listening");
  };
  useEffect(() => () => reading.current?.abandon(), []);

  // grow with the content, to a ceiling, per §16's single-line default
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [text]);

  // A COMMAND IS A PHRASE, NOT A WORD. The trigger is still the last run of
  // non-space characters -- an address mid-sentence never opens a menu --
  // with one exception: a slash at the very start of the box takes the whole
  // rest of the line as its query. Without that, typing the second word of
  // "Go to earlier visits" closed the menu and sent the command to the agent
  // as a sentence, which is what every slash menu anywhere else does not do.
  const whole = /^\/(.*)$/.exec(text);
  const tail = /(^|\s)([/@])([^\s]*)$/.exec(text);
  const kind = whole ? "/" : tail?.[2];
  // §15 keeps working: `/handover @Priya repeat BP` carries an addressee and
  // a note, neither of which is part of the command's name. The address and
  // anything after the words that still match are dropped from the query,
  // and a phrase that narrows to nothing falls back to its first word rather
  // than to an empty menu.
  const phrase = (whole ? whole[1].replace(/(^|\s)@[^\s]+/g, " ") : tail?.[3] ?? "")
    .trim().toLowerCase();
  const query = phrase;
  const narrowed = kind === "/" ? slashItems(actions, query, verbs) : [];
  const items: Item[] = !kind
    ? []
    : kind === "/"
      ? (narrowed.length || !query
          ? narrowed
          : slashItems(actions, query.split(/\s+/)[0], verbs))
      : [...(NAME.toLowerCase().includes(query)
          ? [{ key: "assistant", label: NAME, sub: "Ask the medical assistant", group: "Assistant" }]
          : []),
         ...atItems(roles, query)];

  const choose = (it: Item) => {
    if (it.verb) {
      // The screen's own verb: take the command off the box and do it. No
      // mention travels with it -- a tab does not have an addressee.
      setText(strip(text));
      it.verb.run();
    } else if (it.op) {
      // §15: `/handover @Priya repeat BP` and `@Priya please repeat BP` resolve
      // to the same operation, so an @ already in the box travels with it.
      const mention = /(^|\s)@([^\s]+)/.exec(text)?.[2];
      setText(strip(text));
      onAction(it.op, mention);
    } else {
      setText(text.replace(/(^|\s)@[^\s]*$/, `$1@${it.label} `));
    }
    setPick(0);
    box.current?.focus();
  };

  const send = () => {
    const t = text.trim();
    if (!t || asking) return;
    setText("");
    setPick(0);
    const q = onAskRapha ? raphaQuestion(t, NAME) : null;
    if (q) onAskRapha!(q); else onSay(t);
  };

  return (
    <div className="composer-wrap">
      {/* The questions worth asking sit in their own row above the box they
          would be asked in. Inline beside it they strangled the input, which
          is what happens when a chip's label is a sentence. */}
      {quick && <div className="composer-quick">{quick}</div>}
      <div className="composer">
      <Menu items={items} pick={pick} onChoose={choose} id={listId} />
      <div className={`composer-bar${dict === "listening" ? " listening" : ""}`}>
      {onAttach && (
        <button type="button" className="cb-i" onClick={onAttach} disabled={!!attachReason}
                aria-label={attachReason || "Attach a file or photo"} title={attachReason || "Attach a file or photo"}>
          <Icon name="plus" className="i sm" />
        </button>
      )}
      <textarea
            ref={box}
            rows={1}
            value={text}
            aria-label={`Message about ${about}`}
            aria-autocomplete="list"
            aria-controls={items.length ? listId : undefined}
            aria-activedescendant={items.length ? `${listId}-${pick}` : undefined}
            placeholder={dict === "listening" ? "Listening… press the microphone again when you are done" : dict === "thinking" ? "Writing down what you said…" : dictWhy || "Ask, type @someone, or /command…"}
            onChange={(e) => { setText(e.target.value); setPick(0); }}
            onKeyDown={(e) => {
              if (items.length) {
                if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => clamp(p + 1, items.length)); return; }
                if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => clamp(p - 1, items.length)); return; }
                if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); choose(items[pick]); return; }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setText(text.replace(/(^|\s)[/@][^\s]*$/, "$1"));
                  return;
                }
              }
              // Enter sends; Shift+Enter is a newline, which is what every
              // other composer a clinician uses already does.
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
          />
      {dictate && canRecord() && (
        <button type="button" className={`cb-i${dict === "listening" ? " rec" : ""}`} onClick={() => void toggleDictate()}
                disabled={!!dictate.reason || dict === "thinking"}
                aria-label={dictate.reason || (dict === "listening" ? "Stop dictating" : "Dictate a message")}
                title={dictate.reason || (dict === "listening" ? "Stop dictating" : "Dictate a message")}>
          <Icon name="mic" className="i sm" />
        </button>
      )}
      <button
        type="button"
        className="btn btn-b send"
        onClick={send}
        disabled={!text.trim() || asking}
        aria-label={asking ? "Working" : "Send"}
        title={asking ? "Working" : "Send"}
      >
        <Icon name={asking ? "spark" : "send"} className="i sm" />
      </button>
      </div>
      {/* Scribe lives outside the bar and keeps its own state, so a recording carries
          on while the rest of this box is used. */}
      {working ? (
        <button type="button" className="scribe-btn busy" disabled aria-label={working} title={working}>
          <span className="rec-dot calm" aria-hidden="true" />
          {working}
        </button>
      ) : recording ? (
        <div className="scribe-grp">
          <button type="button" className="scribe-btn" onClick={recording.paused ? recording.onResume : recording.onPause}
                  aria-label={recording.paused ? "Continue recording" : "Pause recording"}>
            {recording.paused ? "Continue" : "Pause"}
          </button>
          <button type="button" className={`scribe-btn rec${recording.paused ? " held" : ""}`} onClick={recording.onStop}
                  aria-label="Stop recording" title="Stop recording">
            <span className="rec-dot" aria-hidden="true" />
            <span className="rec-t">{mmss(recording.seconds)}</span>
            Stop
          </button>
        </div>
      ) : onStartScribe && (
        <button
          type="button"
          className="scribe-btn"
          onClick={onStartScribe}
          disabled={!!micReason}
          title={micReason || "Record the consultation with Scribe"}
          aria-label={micReason || "Dictate"}
        >
          <Icon name="mic" className="i sm" />
          Scribe
        </button>
      )}
      </div>
    </div>
  );
}

const mmss = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
