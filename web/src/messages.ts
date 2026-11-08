/** The thread, as a conversation, worked out without a browser.
 *
 *  Everything on the patient screen that is a decision rather than a
 *  rectangle lives here: which messages a thread has and in what order, and
 *  what the agent's last line says. It is pure, it takes the kernel's
 *  ThreadView and the compiled declarations, and messages.check.ts asserts
 *  it. Thread.tsx only draws what comes back.
 *
 *  Two rules this file enforces and must keep enforcing:
 *
 *  - Nothing here can write. It imports no client and no fetch, and the
 *    check asserts the word "commit" and the word "confirm" appear nowhere in
 *    it.
 *  - No proposal is ever returned disabled. An action a person
 *    may not take is not in thread.actions, so it is not here either. The
 *    reason for an absence is said in words, by agentLine(), which is the
 *    replacement for the prototype's greyed-out buttons.
 *
 *  And nothing here names a station, a flag, an operation or a bundle.
 */
import type {
  AuditRecord, Catalogue, Display, Operation, Proposal, Questionnaire, ThreadView, ViewDecl,
} from "./types";
import { provenanceOf } from "./loops.ts";   // pure, type-only imports of its own
import { labelOf, phcOf, walk } from "./validate.ts";   // the extension is for node: messages.check.ts runs this file outside vite
import { human, title } from "./words.ts";

/** A labelled value on a posted or proposed card. */
export type Kv = { link_id: string; label: string; value: string; crit: boolean };

export type Tag = { text: string; style: string };

/** Something a person or the agent said in this browser. The kernel has no
 *  route for an utterance and stores none, so these live in the renderer and
 *  are not part of the record. */
export type Said = {
  id: string; at: string; who: "user" | "agent"; text: string; actor: string;
  /** Who this was said TO, when it was said to a person. A message with an
   *  @mention in it is one colleague writing to another: it is part of the
   *  conversation and it is not a question for the agent. */
  to?: string[];
};

/** The people an utterance is addressed to: every @name that starts the text
 *  or follows a space, so an address mid-word ("a@b.com") is nobody's. Names
 *  are returned as typed, without the @, once each. */
export const mentionsOf = (text: string): string[] =>
  [...new Set([...text.matchAll(/(?:^|\s)@([\w.-]+)/g)].map((m) => m[1]))];

export type Msg =
  | {
      kind: "posted"; id: string; at: string; title: string; actor: string;
      operation: string; tags: Tag[]; values: Kv[]; transcript?: string | null;
      /** The answers exactly as they were committed, so a correction opens
       *  the same form already holding them instead of an empty one. */
      payload: Record<string, unknown>;
      /** This line IS a correction to something recorded earlier on this
       *  visit, rather than the first time it was recorded. */
      edited: boolean;
    }
  | {
      kind: "denied"; id: string; at: string; title: string; actor: string; reason: string;
      /** True when something was posted after this refusal, which is what
       *  makes it old news worth folding away. */
      old: boolean;
    }
  | {
      kind: "proposal"; id: string; at: string; title: string; proposal: Proposal;
      values: Kv[]; by: string; surface: string;
      /** The operation is no longer among the thread's actions, so the guard
       *  would refuse this if it were confirmed. Say so before they tap. */
      stale: boolean;
    }
  | { kind: "said"; id: string; at: string; who: "user" | "agent"; text: string; actor: string;
      to?: string[] }
  /** §12: a handover is a conversation, not a delivery. One object carrying
   *  what was asked, every reply to it, and the state the last reply left it
   *  in. Built from operations whose atom declares `presents: handover`; this
   *  module never names one. */
  | {
      kind: "handover"; id: string; at: string; title: string;
      from: string; to: string; note: string; priority: string;
      state: HandoverState;
      replies: { id: string; at: string; actor: string; comment: string; state: string }[];
    };

/** §12.1. `draft` and `reassigned` are not here: nothing writes a draft, and
 *  reassignment would need a reply to name a new addressee, which no
 *  declaration does yet. Naming a state the product cannot reach would be a
 *  picture of a workflow rather than a workflow. */
export type HandoverState = "open" | "acknowledged" | "in_progress" | "resolved" | "reopened";
const HANDOVER_STATES: HandoverState[] = ["open", "acknowledged", "in_progress", "resolved", "reopened"];

const str = (v: unknown) => (v === null || v === undefined ? "" : String(v));

export type Ctx = {
  operations: Record<string, Operation>;
  /** questionnaire(op.input). Passed in rather than imported, because
   *  declarations.ts is a Vite glob and this module has to run under node. */
  schema: (input: string | undefined) => Questionnaire | null;
  /** flag to badge style, from the queue view that declares this workflow. */
  badges: Record<string, string>;
  /** What a declared answer is called. Passed in for the same reason `schema`
   *  is: this module runs under node in its own check, where importing the
   *  registry would read an empty one and check the fallback. */
  display: Display;
};

const DENIED = "denied:";

/** Audit rows carry `user:<role>` or `agent`. Neither is a name, and there is
 *  no people directory to look one up in, so neither is invented. */
export const actorOf = (actor: string | null | undefined): string => {
  if (!actor) return "unattributed";
  // The kernel seeds an agent account as `agent:<role>`. Which account a
  // machine used is audit detail; on a card it is one word, because the thing
  // a person needs from it is that a machine, not a colleague, asked.
  if (/^agent(:|$)/.test(actor)) return "agent";
  return human(actor.replace(/^user:/, ""));
};

const titleOf = (ctx: Ctx, op: string) => ctx.operations[op]?.title ?? title(op);

/** The payload, labelled by the questionnaire the operation names. An answer
 *  the questionnaire does not have is still shown, under its raw key: a value
 *  that reached the store is a value the person is owed sight of. */
export function valuesOf(ctx: Ctx, op: string, payload: Record<string, unknown> | undefined): Kv[] {
  const given = payload ?? {};
  const schema = ctx.schema(ctx.operations[op]?.input);
  const out: Kv[] = [];
  const seen = new Set<string>();

  for (const q of schema ? walk(schema.questions) : []) {
    if (q.type === "group" || q.type === "display") continue;
    seen.add(q.link_id);
    if (!(q.link_id in given)) continue;
    const phc = phcOf(q);
    const raw = given[q.link_id];
    // A posted card draws a declared answer under the word its declaration
    // gives it, the same as the queue row and the header beside it. This card
    // said `ncd` two inches under a header saying NCD, off one answer of one
    // record.
    //
    // Only for a PLAIN answer. A structured one is a list of rows that `fmt`
    // has already composed into a sentence, so there is no single stored
    // value left to give a name to, and handing that sentence to a lookup
    // would be asking what a paragraph is called.
    const plain = typeof raw === "string" || typeof raw === "number";
    const shown = fmt(raw);
    out.push({
      link_id: q.link_id,
      label: labelOf(q),
      value: (plain ? ctx.display(q.link_id, shown) : shown) + (phc.unit ? ` ${phc.unit}` : ""),
      crit: outsideCritical(phc.critical, raw),
    });
  }
  for (const [k, v] of Object.entries(given)) {
    if (seen.has(k)) continue;
    // An override reason is not a clinical value and it is not optional
    // reading: it is the sentence someone typed to get past a range block.
    out.push({ link_id: k, label: title(k), value: fmt(v), crit: k === "override_reason" });
  }
  return out;
}

function outsideCritical(crit: { low: number; high: number } | undefined, v: unknown): boolean {
  if (!crit || v === undefined || v === null || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && !(crit.low <= n && n <= crit.high);
}

/** A structured answer is a list of CARE resources, one row per resource, and
 *  each row carries the sub fields the operation's mapping named. Those names
 *  are the only thing that makes the row readable, so a card keeps them: a
 *  prescription read back as "Amoxicillin 500mg 1 cap TDS" is a string, and
 *  "Medication: Amoxicillin 500mg, Dosage instruction: 1 cap TDS" is a record.
 *
 *  A row with one field is just its value: naming the single column adds a
 *  word and no information.
 */
export const fmt = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  if (Array.isArray(v)) return v.map(fmt).join("; ");
  if (typeof v === "object") {
    const entries = Object.entries(v as Record<string, unknown>).filter(([, x]) => fmt(x) !== "");
    if (entries.length === 1) return fmt(entries[0][1]);
    return entries.map(([k, x]) => `${title(k)}: ${fmt(x)}`).join(", ");
  }
  return String(v);
};

/** Tags on a posted card's meta line: whether it was rejected and whatever it
 *  raised. Who posted it and which instrument they used are already named by
 *  the actor line and the folded summary; a badge repeating either is
 *  decoration on a card that already says it in words. */
function tagsFor(ctx: Ctx, a: AuditRecord, raised: string[]): Tag[] {
  const tags: Tag[] = [];
  if (a.outcome === "rejected") tags.push({ text: "rejected", style: "mute" });
  for (const flag of raised) tags.push({ text: human(flag), style: ctx.badges[flag] ?? "warn" });
  return tags;
}

/** One time-sorted list. The agent's closing line is not in it: that one is
 *  composed from the thread at render time and is always last. */
export function messages(thread: ThreadView, ctx: Ctx, said: Said[] = []): Msg[] {
  const audit = thread.audit ?? [];
  // A proposal's own "proposed" audit row is the same event as the proposal
  // card, so it would draw the same values twice.
  const posted = audit.filter((a) => a.outcome !== "proposed" && !a.outcome.startsWith(DENIED));
  const lastPostedAt = posted.length ? posted[posted.length - 1].at : "";

  const out: Msg[] = [];

  for (const a of audit) {
    if (a.outcome.startsWith(DENIED)) {
      out.push({
        kind: "denied", id: a.id, at: a.at, title: titleOf(ctx, a.operation),
        actor: actorOf(a.actor), reason: a.outcome.slice(DENIED.length).trim(),
        old: !!lastPostedAt && a.at < lastPostedAt,
      });
    } else if (a.outcome !== "proposed") {
      const raised = (thread.proposals ?? []).find((p) => p.id === a.proposal)?.flags_raised ?? [];
      out.push({
        kind: "posted", id: a.id, at: a.at, title: titleOf(ctx, a.operation),
        actor: actorOf(a.actor), operation: a.operation, tags: tagsFor(ctx, a, raised),
        values: a.outcome === "rejected" ? [] : valuesOf(ctx, a.operation, a.payload),
        payload: (a.payload ?? {}) as Record<string, unknown>,
        edited: a.outcome === "amended",
        transcript: (thread.proposals ?? []).find((p) => p.id === a.proposal)?.transcript ?? null,
      });
    }
  }

  const live = new Set((thread.actions ?? []).map((op) => op.id));
  for (const p of thread.proposals ?? []) {
    if (p.status !== "pending") continue;
    out.push({
      kind: "proposal", id: p.id, at: p.created_at, title: titleOf(ctx, p.operation),
      proposal: p, values: valuesOf(ctx, p.operation, p.payload),
      by: actorOf(p.proposed_by), surface: p.surface, stale: !live.has(p.operation),
    });
  }

  for (const s of said) out.push({ kind: "said", ...s });

  return collapseHandovers(out, ctx).sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}

/** §12.2 and §12.3. Every committed record from an operation declaring
 *  `presents: handover` becomes one object: the first is what was asked, the
 *  rest are replies, and the state is the last one anybody set.
 *
 *  THE HONEST LIMIT, and it is in the atom too. The kernel stores a reply as a
 *  questionnaire response with no reference to WHICH handover it answers, so
 *  two concurrent handovers on one visit would share one conversation. One at
 *  a time is what this supports. Threading them needs the reply to carry the
 *  id of what it answers, which is a declaration change, not a render change.
 */
function collapseHandovers(msgs: Msg[], ctx: Ctx): Msg[] {
  const isHandover = (op: string) => ctx.operations[op]?.presents === "handover";
  const parts = msgs.filter(
    (m): m is Extract<Msg, { kind: "posted" }> => m.kind === "posted" && isHandover(m.operation));
  if (!parts.length) return msgs;

  parts.sort((a, b) => (a.at < b.at ? -1 : 1));
  const [first, ...rest] = parts;
  const answer = (m: Extract<Msg, { kind: "posted" }>, link: string) =>
    str(m.values.find((v) => v.link_id === link)?.value);

  const replies = rest.map((m) => ({
    id: m.id, at: m.at, actor: m.actor,
    comment: answer(m, "comment") || answer(m, "note"),
    state: answer(m, "state"),
  }));
  // The last reply that actually named a state. A reply that only commented
  // leaves the state where it was rather than silently reopening it.
  const named = [...replies].reverse().find((r) => HANDOVER_STATES.includes(r.state as HandoverState));
  const state: HandoverState =
    (named?.state as HandoverState) ?? (replies.length ? "in_progress" : "open");

  const object: Msg = {
    kind: "handover", id: first.id, at: first.at, title: first.title,
    from: first.actor, to: answer(first, "to"), note: answer(first, "note"),
    priority: answer(first, "priority") || "normal",
    state, replies,
  };
  const folded = new Set(parts.map((m) => m.id));
  return [...msgs.filter((m) => !folded.has(m.id)), object];
}

// ----------------------------------------------------------- the agent line

export type AgentLine = { sentences: string[]; actions: Operation[] };

/** The two sentences the agent closes every thread with: what last happened,
 *  and the kernel's own wayfinding.
 *
 *  The prototype had nine hand-written sentences keyed to PHC states. There is
 *  no declaration field carrying per-state prose (a `says:` on each workflow
 *  state would be the place, and contracts are frozen), so these are composed
 *  from the record instead. They are true for any bundle.
 *
 *  There was a third, "Here is what you can do as X", above a row of buttons
 *  that already say so. A sentence nobody reads is not honesty.
 */
export function agentLine(thread: ThreadView, ctx: Ctx): AgentLine {
  // The kernel's nudge is a fragment, not a sentence, and three fragments run
  // together read as one long mistake.
  const stop = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`);
  const audit = thread.audit ?? [];
  const last = audit.length ? audit[audit.length - 1] : null;
  const sentences: string[] = [];

  if (!last) {
    sentences.push("Nothing has been recorded on this visit yet.");
  } else if (last.outcome.startsWith(DENIED)) {
    sentences.push(
      `${titleOf(ctx, last.operation)}, from ${actorOf(last.actor)}, was refused: ` +
        `${stop(last.outcome.slice(DENIED.length).trim())}`,
    );
  } else if (last.outcome === "proposed") {
    sentences.push(
      `${titleOf(ctx, last.operation)} was proposed by ${actorOf(last.actor)} and is waiting for a person.`,
    );
  } else {
    sentences.push(
      `${titleOf(ctx, last.operation)} was ${last.outcome} by ${actorOf(last.actor)} at ${clock(last.at)}.`,
    );
  }

  // The kernel's own wayfinding. This is the sentence that replaces a greyed
  // out button: when the role cannot act here, this says so.
  if (thread.nudge) sentences.push(stop(cap(thread.nudge)));

  return { sentences, actions: (thread.actions ?? []).slice(0, 5) };
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** An ISO timestamp as a wall clock. Anything that is not one is passed
 *  through, because a kernel that sends a different shape should be visible. */
export const clock = (at: string | undefined): string =>
  at && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(at) ? at.slice(11, 16) : (at ?? "");

/** How long ago, in the words a person says it: "42 min", "2 h 5 min". Empty
 *  when there is no time to measure from, so a row without one draws nothing
 *  rather than a wrong number. `now` is a parameter so a check can pin it. */
export function waited(at: string | undefined, now: number = Date.now()): string {
  if (!at) return "";
  const from = Date.parse(at);
  if (!Number.isFinite(from)) return "";
  const mins = Math.max(0, Math.floor((now - from) / 60000));
  if (mins < 1) return "just now";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h === 0 ? `${m} min` : m === 0 ? `${h} h` : `${h} h ${m} min`;
}

/** The flag every scribe declaration gates on. It is a product rule and not a

/** A summary view belongs to a thread, not to the nav. One that names a
 *  workflow belongs only to that workflow's threads. */
export function summariesFor(cat: Catalogue, workflow: string): ViewDecl[] {
  return Object.values(cat.views ?? {}).filter(
    (v) => v.kind === "summary" && (!v.workflow || v.workflow === workflow),
  );
}

/** The queue view whose columns and badges describe this workflow's subject.
 *  The thread header uses it instead of guessing at the subject's shape. */
export function queueViewFor(cat: Catalogue | undefined, workflow: string | undefined): ViewDecl | undefined {
  const queues = Object.values(cat?.views ?? {}).filter((v) => v.kind === "queue");
  return queues.find((v) => v.workflow === workflow) ?? queues[0];
}

// --------------------------------------------------------------- the header

export type Header = {
  name: string;
  initials: string;
  meta: string[];
  identity?: { label: string; value: string };
  badges: Tag[];
  /** The token and the declared word for it, so a screen can put it right after the name. */
  token: string;
  tokenWord: string;
};

const IDENTITY = /abha|abdm/i;

/** Who this thread is about, in the words the declaration chose.
 *
 *  The one accepted hard-code in this renderer is the ABHA regex. ABHA is a
 *  national identifier, not a facility's concept, and the design rule reserves
 *  the only real blue on the screen for it.
 */
export function header(
  thread: ThreadView,
  queue: ViewDecl | undefined,
  /** What a declared value is called. Required: this header drew the stored
   *  code for every column it showed, so a centre's NCD patient read `ncd` on
   *  the one screen a clinician spends the visit looking at. */
  display: Display,
): Header {
  const subject = thread.subject ?? {};
  const has = (k: string) => {
    const v = subject[k];
    return v !== null && v !== undefined && v !== "";
  };
  // The queue view already said which subject fields matter and in which
  // order, so the headline is the first of them the subject actually carries.
  // A laboratory thread has no patient row (bundles/LAB-LOG.md 12), so this
  // falls through to the token, which is the right answer and a declaration
  // to fix rather than a guess to make here.
  const plumbing = (k: string) => /(^|_)id$|_date$|_by$|^status$/.test(k) || k === thread.workflow;
  // How somebody got into the queue is a MARK beside their number and is
  // nowhere a word: the view says so, and web/src/view/View.tsx has always
  // honoured it. Drawing that column here put the stored value on the header
  // in plain text, so a patient who registered themselves at the poster read
  // as "61 · male · Bhagwanpur · poster". The rule is read off the same
  // declaration rather than restated, so a centre that stops declaring
  // provenance loses the mark and this exclusion together.
  const mark = provenanceOf(queue)?.column;
  const drawable = (k: string) => !IDENTITY.test(k) && k !== mark;
  const declared = (queue?.columns ?? []).filter(drawable);
  const fallback = Object.keys(subject).filter((k) => drawable(k) && !plumbing(k));
  const columns = declared.length ? declared : fallback;

  const nameKey = columns.find(has) ?? fallback.find(has);
  const name = nameKey ? display(nameKey, String(subject[nameKey])) : thread.id;

  const identityEntry = Object.entries(subject).find(
    ([k, v]) => IDENTITY.test(k) && v !== null && v !== undefined && v !== "",
  );

  // No station badge here: the topbar already carries station and last step,
  // and a badge repeating it on the card is the duplicate this screen is
  // rid of.
  const badges: Tag[] = [];
  const token = columns.find((k) => /token/i.test(k) && k !== nameKey);
  if (token && has(token)) badges.push({ text: String(subject[token]), style: "mute" });
  for (const flag of thread.flags ?? []) {
    // Only the flags the queue view gave a style to. A flag it did not name is
    // a state of the line, not a thing to shout on a header.
    const style = queue?.badges?.[flag];
    if (style) badges.push({ text: human(flag), style });
  }

  return {
    name,
    initials: name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase(),
    // Every one of these is a declared answer, so every one of them draws
    // under the word its declaration gives it. This line read the stored code
    // back out: the queue beside it said NCD and this said ncd, off the same
    // column of the same row.
    meta: columns.filter((k) => k !== nameKey && k !== token && has(k))
      .map((k) => display(k, String(subject[k]))),
    identity: identityEntry
      ? { label: human(identityEntry[0]), value: String(identityEntry[1]) }
      : undefined,
    badges,
    // The token, on its own, so a screen can put it right after the name.
    token: token && has(token) ? String(subject[token]) : "",
    tokenWord: token ? human(token) : "",
  };
}
