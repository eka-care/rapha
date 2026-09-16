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
import type { Operation } from "../types";
import { Menu, atItems, slashItems, type Item } from "./Menu";

/* No cap. The menu is 360px tall and scrolls, and typing narrows it, so a
   slice here only hides the last item without saying it did -- which is how a
   bundle's ninth role became invisible while the other eight looked complete. */
const clamp = (n: number, len: number) => ((n % len) + len) % len;

export type Recording = { seconds: number; onStop: () => void } | null;

export function Composer({
  about, context, actions, roles, asking, recording,
  onSay, onAction, onStartScribe, micReason,
}: {
  about: string;
  /** §16's context line: who and what this composer is pointed at. */
  context?: string;
  actions: Operation[];
  roles: string[];
  asking?: boolean;
  recording?: Recording;
  onSay: (text: string) => void;
  onAction: (op: Operation, mention?: string) => void;
  onStartScribe?: () => void;
  /** Why the microphone is unavailable, if it is. An icon that does nothing
   *  and says nothing is worse than one that is absent. */
  micReason?: string;
}) {
  const [text, setText] = useState("");
  const [pick, setPick] = useState(0);
  const box = useRef<HTMLTextAreaElement>(null);
  const listId = "composer-menu";

  // grow with the content, to a ceiling, per §16's single-line default
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [text]);

  const tail = /(^|\s)([/@])([^\s]*)$/.exec(text);
  const kind = tail?.[2];
  const query = (tail?.[3] ?? "").toLowerCase();
  const items: Item[] = !kind
    ? []
    : kind === "/" ? slashItems(actions, query) : atItems(roles, query);

  const choose = (it: Item) => {
    if (it.op) {
      // §15: `/handover @Priya repeat BP` and `@Priya please repeat BP` resolve
      // to the same operation, so an @ already in the box travels with it.
      const mention = /(^|\s)@([^\s]+)/.exec(text)?.[2];
      setText(text.replace(/(^|\s)[/][^\s]*$/, "$1"));
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
    onSay(t);
  };

  if (recording) {
    return (
      <div className="composer" data-state="recording">
        <div className="composer__expanded">
          <div className="composer__expanded-row">
            <span className="composer__recording">
              <span className="recording-dot" aria-hidden="true" />
              Listening
              <span className="composer__recording-time">{mmss(recording.seconds)}</span>
            </span>
            <button className="btn" style={{ marginLeft: "auto" }} onClick={recording.onStop}>
              Stop
            </button>
          </div>
          <div className="t-meta u-faint">The consultation is being captured.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="composer" data-state={asking ? "generating" : "idle"}>
      {context && <div className="composer__context">{context}</div>}
      <div style={{ position: "relative", maxWidth: 900, margin: "0 auto" }}>
        <Menu items={items} pick={pick} onChoose={choose} id={listId} />
        <div className="composer__inner">
          <textarea
            ref={box}
            className="composer__input"
            rows={1}
            value={text}
            aria-label={`Message about ${about}`}
            aria-autocomplete="list"
            aria-controls={items.length ? listId : undefined}
            aria-activedescendant={items.length ? `${listId}-${pick}` : undefined}
            placeholder="Ask, type @someone, or /command..."
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
          {onStartScribe && (
            <button
              type="button"
              className="composer__mic"
              onClick={onStartScribe}
              disabled={!!micReason}
              title={micReason || "Dictate"}
              aria-label={micReason || "Dictate"}
            >
              <Icon name="mic" />
            </button>
          )}
          <button
            type="button"
            className="composer__send"
            data-ready={text.trim().length > 0 && !asking}
            onClick={send}
            disabled={!text.trim() || asking}
            aria-label={asking ? "Working" : "Send"}
            title={asking ? "Working" : "Send"}
          >
            <Icon name={asking ? "spark" : "send"} />
          </button>
        </div>
      </div>
    </div>
  );
}

const mmss = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
