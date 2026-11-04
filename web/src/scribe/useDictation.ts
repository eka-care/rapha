/** The half of dictation that needs a browser and a microphone.
 *
 *  The rules are in dictate.ts and are checked without either. This is the
 *  wiring: listen for the key anywhere on the page, remember which field had
 *  the cursor at the moment it went down, record, and put the words in.
 *
 *  WHY THE TARGET IS CAPTURED ON KEYDOWN and not read again when the words
 *  come back: between speaking and the transcript arriving a person may have
 *  clicked somewhere else, and putting a sentence about a patient's chest
 *  into whatever field they happened to move to afterwards is worse than
 *  putting it nowhere. The field they were in when they started talking is
 *  the one they meant.
 *
 *  WHAT THIS COSTS TODAY, said plainly. The kernel's recording route refuses
 *  a session that does not name a template to fill, so a dictation names the
 *  operation whose form is open and throws the filled draft away, keeping
 *  only the transcript. That is one wasted extraction per dictation. A
 *  transcribe-only route is the fix and it is a kernel change; it is not
 *  pretended away here.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { canRecord, recordReading, type Reading } from "./reading";
import { dictateKey, gesture, insert, isTarget, labelFor, type Press } from "./dictate";

/** What the person is shown while this is happening. `field` is null when
 *  nothing editable had the cursor, which is the case the words come back as
 *  copyable text for. */
export type Dictation =
  | { phase: "idle" }
  | { phase: "listening"; field: string | null; handsfree: boolean }
  | { phase: "thinking"; field: string | null }
  | { phase: "loose"; text: string }
  | { phase: "failed"; why: string };

/** Set a React-controlled field's value so React hears about it.
 *
 *  Assigning `.value` on a controlled input updates the DOM and React never
 *  learns, so the next render puts the old value back and the words
 *  disappear a frame after they appear. The native setter plus a bubbling
 *  `input` event is how you reach React's own onChange from outside it. */
function write(el: HTMLInputElement | HTMLTextAreaElement, value: string, caret: number) {
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  setter?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  try { el.setSelectionRange(caret, caret); } catch { /* a field with no selection */ }
  el.focus();
}

export function useDictation({ thread, operation, enabled = true }: {
  /** The visit the recording belongs to. The kernel refuses the upload
   *  without this visit's own recording consent, which is its check and not
   *  this file's: a second consent test written in a browser is a second one
   *  to keep in step. */
  thread: string | null;
  /** The form that is open. See the note above on why a dictation has to
   *  name one at all. */
  operation: string | null;
  enabled?: boolean;
}): { state: Dictation; dismiss: () => void; supported: boolean } {
  const [state, setState] = useState<Dictation>({ phase: "idle" });
  const presses = useRef<Press[]>([]);
  const live = useRef<{ reading: Reading; target: Element | null; handsfree: boolean } | null>(null);
  const running = useRef<"hold" | "handsfree" | null>(null);
  const supported = canRecord();

  const finish = useCallback(async (reading: Reading, target: Element | null) => {
    const label = labelFor(target);
    setState({ phase: "thinking", field: label });
    reading.stop();
    const heard = await reading.heard;
    live.current = null;
    running.current = null;
    presses.current = [];
    const said = heard.transcript.trim();
    if (!said) {
      // The reason is the kernel's own sentence, which already says what to
      // do instead. An empty one means the person stopped before speaking,
      // and being told off for that would be absurd.
      if (heard.reason) setState({ phase: "failed", why: heard.reason });
      else setState({ phase: "idle" });
      return;
    }
    if (target && isTarget(target) && (target instanceof HTMLInputElement
                                    || target instanceof HTMLTextAreaElement)) {
      const { value, caret } = insert(target.value, target.selectionStart ?? target.value.length,
                                      target.selectionEnd ?? target.value.length, said);
      write(target, value, caret);
      setState({ phase: "idle" });
      return;
    }
    // NOTHING TO PUT IT IN, so the words are handed back rather than thrown
    // away. A shortcut that silently does nothing teaches a person the
    // feature is broken; this teaches them where the cursor has to be.
    setState({ phase: "loose", text: said });
  }, []);

  useEffect(() => {
    if (!enabled || !supported) return;
    const key = dictateKey();

    const begin = (how: "hold" | "handsfree") => {
      if (live.current) return;
      if (!thread || !operation) {
        setState({ phase: "failed", why: "Open a visit to dictate into it." });
        return;
      }
      const target = isTarget(document.activeElement) ? document.activeElement : null;
      running.current = how;
      const reading = recordReading(thread, operation);
      live.current = { reading, target, handsfree: how === "handsfree" };
      setState({ phase: "listening", field: labelFor(target), handsfree: how === "handsfree" });
    };

    const down = (e: KeyboardEvent) => {
      if (e.key !== key || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      // The key is the shortcut and never a character. Without this it is
      // also typed into the field it is dictating into.
      e.preventDefault();
      presses.current = [...presses.current.slice(-3), { at: performance.now() }];
      const what = gesture(presses.current, performance.now(), running.current);
      if (what === "stop") {
        const open = live.current;
        if (open) void finish(open.reading, open.target);
        presses.current = [];
        return;
      }
      // A hold is only a hold once it has lasted; the timer is what tells a
      // hold from the first half of a double press.
      window.setTimeout(() => {
        if (live.current || running.current) return;
        const last = presses.current[presses.current.length - 1];
        if (!last || last.released !== undefined) return;
        if (gesture(presses.current, performance.now(), running.current) === "hold") begin("hold");
      }, 0 + 230);
    };

    const up = (e: KeyboardEvent) => {
      if (e.key !== key) return;
      e.preventDefault();
      const last = presses.current[presses.current.length - 1];
      if (last && last.released === undefined) last.released = performance.now();
      const open = live.current;
      // Letting go ends a hold. It does not end hands-free, which is the
      // whole point of hands-free.
      if (open && !open.handsfree) { void finish(open.reading, open.target); return; }
      if (open) return;
      // Two taps, and nothing running: start listening until the next press.
      window.setTimeout(() => {
        if (live.current || running.current) return;
        if (gesture(presses.current, performance.now(), null) === "handsfree") begin("handsfree");
      }, 0);
    };

    addEventListener("keydown", down, true);
    addEventListener("keyup", up, true);
    return () => {
      removeEventListener("keydown", down, true);
      removeEventListener("keyup", up, true);
      // Leaving the screen mid-recording keeps nothing: the microphone
      // stops and the audio is never sent.
      live.current?.reading.abandon();
      live.current = null;
      running.current = null;
    };
  }, [enabled, supported, thread, operation, finish]);

  return { state, supported, dismiss: () => setState({ phase: "idle" }) };
}
