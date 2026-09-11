/** The loop rules. Pure, so they are checkable without a browser.
 *
 *  `thread.actions` is already filtered by the kernel: an action whose
 *  precondition is unmet or whose capability is not held is absent, never
 *  disabled. So everything here is a question of weight, not permission.
 */
import type { Operation, QueueRow } from "./types";

/** One filled button, everything else one level down.
 *
 *  Two things of equal visual weight means we have not decided which is the
 *  point. The kernel already says which operation ends this station's task;
 *  when it is not on offer (its precondition is unmet, or the line is
 *  complete) the step's own ordering has put the next thing first.
 */
export function weigh(
  actions: Operation[],
  closes: string | null,
): { primary?: Operation; overflow: Operation[] } {
  const primary = actions.find((op) => op.id === closes) ?? actions[0];
  return { primary, overflow: actions.filter((op) => op.id !== primary?.id) };
}

/** What a role is offered once its task at a station is done.
 *
 *  Two shapes, because there are two kinds of role: one that starts new
 *  subjects (it holds the workflow's opener) and one that works a queue. The
 *  difference is derived from the declarations, not from a list of job titles.
 */
export type Cue =
  | { kind: "open"; op: Operation; label: string }
  | { kind: "next"; thread: string; label: string }
  | { kind: "empty"; label: string };

/** Whether arriving at a thread should open this operation's instrument
 *  straight away, rather than draw a button that offers to.
 *
 *  Everything correctable opens. An irreversible operation does not: opening a
 *  national identity journey over the screen every time someone arrives is how
 *  a person learns to dismiss it, and dismissing is the habit that makes the
 *  confirm step meaningless.
 */
export function opensOnArrival(op: Operation | undefined): boolean {
  return !!op && op.irreversibility !== "irreversible";
}

/** Whether a committed operation's card belongs open on this screen.
 *
 *  The nurse opening onto reception's six-row registration form is workflow
 *  fragmentation: someone else's completed context, above her own task. It
 *  collapses to one line she can expand. Once the line is complete there is no
 *  current station and nothing collapses, because the whole visit is the
 *  subject then.
 */
export function mine(op: Operation, station: string | null): boolean {
  return station === null || op.station === station;
}

export function cue(a: {
  station: string | null;
  opener: Operation | null;
  queue: QueueRow[];
  /** The thread whose loop just closed. It may still be in the queue result,
   *  which was read before the commit; offering it back is a loop with no
   *  exit. */
  closed: string;
}): Cue {
  if (a.opener) return { kind: "open", op: a.opener, label: a.opener.title };
  const waiting = a.queue.filter((r) => r.station === a.station && r.thread !== a.closed);
  const first = waiting[0];
  if (!first) return { kind: "empty", label: "Nobody waiting" };
  const name = typeof first.subject.name === "string" && first.subject.name
    ? first.subject.name
    : String(first.subject.token ?? first.thread);
  return { kind: "next", thread: first.thread, label: name };
}
