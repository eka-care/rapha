/** The assistant outside a patient: a centred overlay.
 *
 *  Inside a visit it is a tab (see Encounter); everywhere else there is no
 *  visit to put a tab in, so it comes forward in the middle of the page, the
 *  way Fern's docs bring their assistant forward.
 *
 *  KEPT ONCE OPENED. Closing hides it rather than unmounting it, so a person
 *  who looks something up, closes it to read the list behind, and opens it
 *  again finds the conversation where they left it.
 */
import { useEffect, useRef } from "react";
import { Icon } from "../icons";
import { trapTab } from "../parts";
import { AssistantPanel } from "./Lazy";

export function AssistantOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const shell = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  // Take the keyboard when it opens, hand it back to whatever opened it.
  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement as HTMLElement | null;
    // The question box if it is already there; else the dialog itself, so
    // Escape works while the assistant is still loading.
    (shell.current?.querySelector<HTMLElement>("input") ?? shell.current)?.focus();
    return () => { opener.current?.focus(); opener.current = null; };
  }, [open]);

  return (
    <div hidden={!open}>
      <div className="scrim" onClick={onClose} />
      <div className="assist assist--overlay" role="dialog" aria-modal="true" aria-label="Medical assistant"
        ref={shell} tabIndex={-1}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
          trapTab(e, shell.current);
        }}>
        <header className="assist__bar">
          <Icon name="spark" className="i sm" />
          <span className="assist__title">Medical assistant</span>
          <button type="button" className="icon-btn ml-auto" onClick={onClose} aria-label="Close">
            <Icon name="plus" className="i sm assist__x" />
          </button>
        </header>
        <AssistantPanel />
      </div>
    </div>
  );
}
