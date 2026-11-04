/** The assistant, fetched when somebody first opens it.
 *
 *  Two reasons, and either is enough. The package is a third-party chat
 *  client that connects the instant it mounts, so mounting it on every page
 *  load would open a connection nobody asked for. And it is code that no
 *  screen needs until a person asks a medical question, so it should not sit
 *  in the bundle every screen pays for.
 */
import { lazy, Suspense } from "react";

const Assistant = lazy(() => import("./Assistant"));

/** A question carried in from outside, e.g. the command bar. `n` tells two
 *  identical questions apart, so asking the same thing twice sends twice. */
export type Question = {
  text: string; n: number;
  /** What the visit already knows, shown as a chip in the widget and sent
   *  with the first message instead of being pasted into the box. */
  context?: { title: string; text: string };
};

export function AssistantPanel({ question }: { question?: Question | null }) {
  return (
    <Suspense fallback={<p className="assist__note">Opening…</p>}>
      <Assistant question={question} />
    </Suspense>
  );
}
