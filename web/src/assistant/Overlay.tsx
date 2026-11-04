/** The assistant outside a patient: a centred overlay.
 *
 *  Inside a visit it is a tab (see Encounter); everywhere else there is no
 *  visit to put a tab in, so it comes forward in the middle of the page, the
 *  way Fern's docs bring their assistant forward.
 *
 *  AT THE SIDE, for `@rapha` in a visit: the same assistant docked to the right
 *  edge, so the patient stays in view and nothing is held back behind a scrim.
 *
 *  KEPT ONCE OPENED. Closing hides it rather than unmounting it, so a person
 *  who looks something up, closes it to read the list behind, and opens it
 *  again finds the conversation where they left it.
 */
import { useEffect, useRef } from "react";
import { Icon } from "../icons";
import { trapTab } from "../parts";
import { AssistantPanel, type Question } from "./Lazy";

export function AssistantOverlay({ open, question, side, onClose }: {
  open: boolean; question: Question | null;
  /** At the side of the screen, with the page still usable beside it, rather
   *  than in the middle with the page held back. */
  side: boolean; onClose: () => void;
}) {
  const shell = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  // Take the keyboard when it opens, hand it back to whatever opened it.
  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement as HTMLElement | null;
    // The question box if it is already there; else the dialog itself, so
    // Escape works while the assistant is still loading.
    // At the side the dialog itself is never focused: a ring around a whole
    // column is not a focus indicator, and it is not modal anyway.
    const into = shell.current?.querySelector<HTMLElement>("input") ?? (side ? null : shell.current);
    into?.focus();
    return () => { opener.current?.focus(); opener.current = null; };
  }, [open, side]);

  // Escape closes the side panel from anywhere, since nothing in it need hold
  // the focus.
  useEffect(() => {
    if (!open || !side) return;
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", on);
    return () => removeEventListener("keydown", on);
  }, [open, side, onClose]);

  return (
    <div hidden={!open} className={side ? "assist-slot--side" : undefined}>
      {!side && <div className="scrim" onClick={onClose} />}
      <div className={`assist ${side ? "assist--side" : "assist--overlay"}`}
        role="dialog" aria-modal={!side} aria-label="Medical assistant"
        ref={shell} tabIndex={-1}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
          if (!side) trapTab(e, shell.current);
        }}>
        <header className="assist__bar">
          <Icon name="spark" className="i sm" />
          <span className="assist__title">Medical assistant</span>
          <button type="button" className="icon-btn ml-auto" onClick={onClose} aria-label="Close">
            <Icon name="plus" className="i sm assist__x" />
          </button>
        </header>
        <AssistantPanel question={question} />
      </div>
    </div>
  );
}
