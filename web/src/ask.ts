/** The ask box. A sentence in, proposals out, and nothing else.
 *
 *  It posts to the kernel's own `POST /api/v1/phc/agent/say`, which calls
 *  agent.turn -> agent.planner -> kernel.proposals.propose on guard.MCP. That
 *  route takes no `confirmed` argument and there is no branch on it that
 *  reaches confirm or commit, so the worst a sentence can do is put a card in
 *  front of a person. The tap on that card is still what writes.
 *
 *  There is no second process and no VITE_AGENT_BASE. The agent lives on the
 *  kernel because the propose path already does; a second port would be a
 *  second CORS surface and a second copy of the same call.
 *
 *  This module has no commit and no confirm path, on purpose, and
 *  messages.check.ts asserts that it never grows one.
 */
import { API_BASE, currentRole } from "./api";

const SAY = "/api/v1/phc/agent/say";

/** What the kernel sends back per proposal. Only the fields this box reads. */
type Card = { proposal_id: string | null; title?: string; verdict?: { reason?: string } };

export const NO_AGENT =
  "The kernel did not answer. Start it (sh api/run.sh) and try again. Nothing was proposed and " +
  "nothing was written.";

export type Answer = { said: string; proposed: number };

/** One turn. Returns what to put in the agent's bubble and how many proposals
 *  landed, so the caller knows whether to re-read the thread. */
export async function ask(body: { utterance: string; thread?: string; role: string }): Promise<Answer> {
  if (!body.thread) {
    return { said: "Open a thread first. A sentence is about somebody, and the kernel needs to know who.", proposed: 0 };
  }
  try {
    const res = await fetch(`${API_BASE}${SAY}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-PHC-Role": body.role || currentRole() },
      body: JSON.stringify({ thread: body.thread, utterance: body.utterance }),
    });
    if (!res.ok) {
      return {
        said: `The kernel answered ${res.status}. Nothing was proposed and nothing was written.`,
        proposed: 0,
      };
    }
    const data = (await res.json()) as { said?: string; proposals?: Card[] };
    const cards = data.proposals ?? [];
    return { said: data.said ?? "", proposed: cards.filter((p) => p.proposal_id).length };
  } catch {
    return { said: NO_AGENT, proposed: 0 };
  }
}
