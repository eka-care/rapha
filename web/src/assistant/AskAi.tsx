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
import { useEffect, useRef, useState } from "react";
import { Loading } from "../parts";
import { assistantConfig, STARTERS } from "./config";
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
  // WHETHER THE PANEL IS THERE YET. The widget is 200KB fetched on the first
  // ask, so between somebody opening the assistant and the panel existing
  // there is a real gap on a health centre's line, and until now that gap
  // drew nothing at all: they asked, and the screen did not change. The
  // skeleton stands where the panel will be.
  const [ready, setReady] = useState(false);
  const made = useRef<Widget | null>(null);
  const asked = useRef(0);
  const quieted = useRef(false);

  // THE ELEMENT IS MADE BEFORE THE SCRIPT LOADS. The bundle, the moment it
  // runs, looks for an `<eka-ask-ai>` in the page and makes its own, pointed
  // at the developer docs' agent, if there is none; that is the "Ask AI" bar
  // that appeared at the foot of every screen. With ours already in the
  // document it finds ours and makes nothing.
  useEffect(() => {
    if (!CONFIG.ready || !open) return;
    let live = true;
    if (!made.current && host.current) {
      const el = document.createElement("eka-ask-ai") as Widget;
      el.setAttribute("agent-id", CONFIG.agentId);
      if (CONFIG.authToken) el.setAttribute("auth-token", CONFIG.authToken);
      // The reader's own conversations, kept on this origin. A shared
      // counter machine is the wrong place for them, by the same
      // reasoning that turned the records SDK's offline store off.
      el.setAttribute("history", "off");
      // Not the docs site's pills, which are what it opens with otherwise.
      el.setAttribute("starters", STARTERS);
      host.current.append(el);
      // The widget removes `open` itself when a reader closes the panel,
      // so that is what this app listens to rather than keeping its own
      // idea of whether it is showing.
      new MutationObserver(() => {
        if (!el.hasAttribute("open")) onClose();
      }).observe(el, { attributes: true, attributeFilter: ["open"] });
      made.current = el;
    }
    void load().then(() => {
      const el = made.current;
      if (!live || !el) return;
      // ITS OWN FLOATING BAR STAYS DOWN. This app has a composer on every
      // thread and a command bar over everything, so a third place to ask
      // is a third place to look. One rule, into its shadow root, which is
      // reaching into somebody else's component and is written down here:
      // if the widget ever grows an attribute for this, that attribute
      // replaces these lines.
      if (!quieted.current && el.shadowRoot) {
        const quiet = document.createElement("style");
        quiet.textContent = ".ask-ai__float { display: none !important; }";
        el.shadowRoot.append(quiet);
        quieted.current = true;
      }
      el.setAttribute("open", "");
      setReady(true);
      seed(el);
    });
    return () => { live = false; };
  }, [open, onClose]);

  // A question only seeds the composer once per asking (`n`), so asking the
  // same thing twice works and a re-render does not ask again.
  //
  // The visit's details are not pasted into the box. They are attached as a
  // chip the reader can see and remove, and the widget sends them with the
  // first message. The widget is made after a script load, so the question
  // can arrive before it exists: `latest` lets the load seed it once there.
  const latest = useRef<Question | null>(null);
  latest.current = question;
  const seed = (el: Widget) => {
    const q = latest.current;
    const page = (el as Widget & { attachPage?: (p: unknown) => void }).attachPage;
    // Before the script has run the element is a plain tag with no methods;
    // wait for the load to seed it, rather than counting this as asked.
    if (!q || asked.current === q.n || typeof page !== "function") return;
    asked.current = q.n;
    page.call(el, q.context
      ? { title: q.context.title, markdown: q.context.text, context: q.context.text }
      : null);
    el.setAttribute("question", q.text);
  };
  useEffect(() => {
    if (made.current && open) seed(made.current);
  }, [open, question]);

  useEffect(() => {
    if (open || !made.current) return;
    made.current.removeAttribute("open");
  }, [open]);

  // The element outlives a close, so a second open has nothing to wait for
  // and must not flash a skeleton over a panel that is already there.
  useEffect(() => { if (!open && made.current) setReady(true); }, [open]);

  if (!CONFIG.ready) return null;
  return (
    <>
      <div ref={host} />
      {open && !ready && (
        <div className="assist-wait">
          <Loading what="the assistant" shape="messages" rows={3} />
        </div>
      )}
    </>
  );
}
