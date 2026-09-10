import { useEffect, useState } from "react";

import ThreadPanel from "./components/ThreadPanel";
import type { Thread } from "./types";
import "./theme.css";

/** The care_fe mount point. Fetches the thread and renders it.
 *
 *  Note what this does NOT do: decide which actions to show, or in what order.
 *  That is the guard's, so there is one implementation of the rules and it is
 *  the one that enforces them. This component draws whatever it is handed. */
export default function ThreadTab({ encounter }: { encounter: { id: string } }) {
  const [thread, setThread] = useState<Thread | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`/api/v1/phc/threads/${encounter.id}/`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((t) => live && setThread(t))
      .catch((e) => live && setError(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [encounter.id]);

  if (error) {
    return (
      <div className="phc phc-empty">
        Could not load this patient's thread ({error}).
        <div style={{ marginTop: 6, fontSize: 12 }}>
          Every station still works from its own forms. Try again, or continue on paper
          and record it when this comes back.
        </div>
      </div>
    );
  }
  if (!thread) return <div className="phc phc-empty">Loading the thread…</div>;
  if (pending) {
    // The form itself is CARE's questionnaire renderer, not ours. Until that is
    // wired, say so rather than opening something that cannot save.
    return (
      <div className="phc phc-empty">
        <b>{pending}</b> opens the CARE questionnaire for this operation.
        <div style={{ marginTop: 6, fontSize: 12 }}>Not wired yet.</div>
      </div>
    );
  }
  return (
    <ThreadPanel
      thread={thread}
      bundleLabel="Your actions"
      onAction={(a) => setPending(a.id)}
    />
  );
}
