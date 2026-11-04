/** The assistant, drawn by Eka's own Ask AI widget.
 *
 *  `<eka-ask-ai>` is the element the Eka Developer Platform's docs site uses,
 *  built from `ask-ai/` in that repository and vendored here as
 *  `public/ask-ai.js`. It is one self-contained script with its own shadow
 *  root, so none of its styling reaches this product and none of this
 *  product's reaches it.
 *
 *  WHY THE WIDGET RATHER THAN THE PANEL THIS APP HAD. They talk to the same
 *  thing. Rapha's own assistant is `@eka-care/medassist-react` against an
 *  agent id; the widget is `@eka-care/medassist-core` against an agent id,
 *  which is the package the React one wraps. Same backend, same guest
 *  identity, same agent. What differs is everything above that: the widget
 *  already has the streaming pacing, the citations, the history, the file
 *  attachment, the starter pills and a panel a reader can drag wider, all of
 *  which this app would otherwise be reimplementing badly and separately.
 *
 *  Its panel is a native dialog fixed to the right edge, which is where this
 *  app docked its own, so the shell around it does not change. app/App.tsx
 *  marks the page while it is open and the visit's right rail stands down;
 *  see `data-assist` there.
 *
 *  NOTHING HERE IS A SECOND CONFIGURATION. The agent, the environment and the
 *  token are `assistantConfig`'s, the same ones the panel it replaces read,
 *  and a build with no agent id gets no widget at all rather than a mock
 *  pretending to be a medical assistant.
 */
import { useEffect, useRef } from "react";
import { assistantConfig } from "./config";
import type { Question } from "./Lazy";

const CONFIG = assistantConfig(import.meta.env as Record<string, string | undefined>);

/** Where the vendored bundle is served from. Loaded once, on first open, so
 *  a workspace nobody asks a question in never fetches 200KB of assistant. */
const SCRIPT = "/ask-ai.js";
let loading: Promise<void> | null = null;

function load(): Promise<void> {
  if (loading) return loading;
  loading = new Promise<void>((resolve, reject) => {
    if (customElements.get("eka-ask-ai")) { resolve(); return; }
    const tag = document.createElement("script");
    tag.src = SCRIPT;
    tag.defer = true;
    tag.onload = () => resolve();
    tag.onerror = () => reject(new Error("could not load the assistant"));
    document.head.append(tag);
  });
  return loading;
}

/** The element's own methods, which are not in any React typing. */
type Widget = HTMLElement & {
  show?: () => void;
  hide?: () => void;
  ask?: (question: string) => void;
};

export function AskAi({ open, question, onClose }: {
  open: boolean;
  /** A question to open with, from `@rapha` in a thread or from the command
   *  bar. The widget seeds its composer and the reader presses send, which
   *  is its own rule and a good one: nothing is asked on somebody's behalf
   *  without them seeing what is being asked. */
  question: Question | null;
  onClose: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const made = useRef<Widget | null>(null);
  const asked = useRef<string | null>(null);

  useEffect(() => {
    if (!CONFIG.ready || !open) return;
    let live = true;
    void load().then(() => {
      if (!live || !host.current) return;
      let el = made.current;
      if (!el) {
        el = document.createElement("eka-ask-ai") as Widget;
        el.setAttribute("agent-id", CONFIG.agentId);
        if (CONFIG.authToken) el.setAttribute("auth-token", CONFIG.authToken);
        // The reader's own conversations, kept on this origin. A shared
        // counter machine is the wrong place for them, by the same
        // reasoning that turned the records SDK's offline store off.
        el.setAttribute("history", "off");
        host.current.append(el);
        // ITS OWN FLOATING BAR STAYS DOWN. The widget draws a compact "Ask
        // AI" bar at the foot of the page for a docs site that has nothing
        // else to type in. This app has a composer on every thread and a
        // command bar over everything, so a third place to ask would be a
        // third place to look. One rule, into its shadow root, which is
        // reaching into somebody else's component and is written down here
        // rather than discovered later: if the widget ever grows an
        // attribute for this, that attribute replaces these four lines.
        const quiet = document.createElement("style");
        quiet.textContent = ".ask-ai__float { display: none !important; }";
        el.shadowRoot?.append(quiet);
        // The widget removes `open` itself when a reader closes the panel,
        // so that is what this app listens to rather than keeping its own
        // idea of whether it is showing.
        new MutationObserver(() => {
          if (!el!.hasAttribute("open")) onClose();
        }).observe(el, { attributes: true, attributeFilter: ["open"] });
        made.current = el;
      }
      el.setAttribute("open", "");
    });
    return () => { live = false; };
  }, [open, onClose]);

  // A question only seeds the composer once. Asking the same thing again
  // from the same screen is the reader's to do, not this effect's.
  useEffect(() => {
    const el = made.current;
    if (!el || !open || !question) return;
    const text = question.text;
    if (!text || asked.current === text) return;
    asked.current = text;
    el.setAttribute("question", text);
  }, [open, question]);

  useEffect(() => {
    if (open || !made.current) return;
    made.current.removeAttribute("open");
  }, [open]);

  if (!CONFIG.ready) return null;
  return <div ref={host} />;
}
