/** What the thread folds together, decided outside the component.
 *
 *  A visit that ran long drew one row per event, and on a busy afternoon
 *  that is most of the page. Three things fold, and all three are decided
 *  here so `fold.check.ts` can run them under plain node:
 *
 *  - A RUN OF REFUSALS is one row. An agent that proposes three operations
 *    and has all three refused in the same second is an agent doing its job.
 *  - A MACHINE'S refusal and a PERSON'S are not the same news. The agent
 *    guessing wrong is noise and folds even when it happens once; a refusal
 *    of something a person did is news and keeps its own row.
 *  - CONSECUTIVE TALK from one person is one turn with one header, the way
 *    every chat has done it since chat existed.
 *
 *  And the older part of a long visit goes behind one control, because what
 *  a clinician is reading is the bottom of the list.
 *
 *  Nothing here names a station, a flag, an operation or a capability: it
 *  reads the kinds the message model already declares and the actor the
 *  audit record already carries.
 */
import type { Msg } from "../messages.ts";

export type Denied = Extract<Msg, { kind: "denied" }>;
export type Spoken = Extract<Msg, { kind: "said" }>;

export type Block =
  /** One or more refusals in a row, from one side. */
  | { kind: "refusals"; id: string; rows: Denied[]; machine: boolean }
  /** One person or the agent talking, without being interrupted. */
  | { kind: "turn"; id: string; msgs: Spoken[] }
  /** Anything else, exactly as it was. */
  | { kind: "one"; id: string; msg: Msg };

/** Two messages from the same actor further apart than this are two turns.
 *  A nurse who says something, is answered by the kernel, and says something
 *  else twenty minutes later has said two things. */
export const TALK_GAP = 4 * 60 * 1000;

/** How much of the foot of a long visit stays drawn. */
export const KEEP_OPEN = 8;

/** Fewer than this behind the control is not worth a control. */
export const FOLD_EARLIER = 3;

/** actorOf() answers this one word for every machine account. */
const MACHINE = "agent";

export function blocks(msgs: Msg[]): Block[] {
  const out: Block[] = [];
  const last = () => out[out.length - 1];

  for (const m of msgs) {
    if (m.kind === "denied") {
      const machine = m.actor === MACHINE;
      const prev = last();
      if (prev && prev.kind === "refusals" && prev.machine === machine) prev.rows.push(m);
      else out.push({ kind: "refusals", id: m.id, rows: [m], machine });
      continue;
    }
    if (m.kind === "said") {
      const prev = last();
      if (prev && prev.kind === "turn" && joins(prev.msgs[prev.msgs.length - 1], m)) prev.msgs.push(m);
      else out.push({ kind: "turn", id: m.id, msgs: [m] });
      continue;
    }
    out.push({ kind: "one", id: m.id, msg: m });
  }

  // A LONE REFUSAL OF SOMETHING A PERSON DID IS NEWS, so it goes back to
  // being its own row. Only a machine's single refusal stays folded.
  return out.map((b) =>
    b.kind === "refusals" && !b.machine && b.rows.length === 1
      ? { kind: "one", id: b.id, msg: b.rows[0] } as Block
      : b);
}

function joins(a: Spoken, b: Spoken): boolean {
  if (a.who !== b.who || a.actor !== b.actor) return false;
  const gap = Date.parse(b.at) - Date.parse(a.at);
  return Number.isFinite(gap) && gap >= 0 && gap <= TALK_GAP;
}

/** The head of a long visit, and the foot that stays drawn. */
export function split(bs: Block[]): { earlier: Block[]; recent: Block[] } {
  const cut = bs.length - KEEP_OPEN;
  if (cut < FOLD_EARLIER) return { earlier: [], recent: bs };
  return { earlier: bs.slice(0, cut), recent: bs.slice(cut) };
}
