/** Mirrors kernel/contracts.py. Field names are frozen there; add, never rename.
 *  Nothing in this file names a station, a flag or a bundle: the renderer draws
 *  whatever the declarations say. */

// ---- questionnaire (CARE Question format, plus our styling_metadata.phc) ----

export type Range = { low: number; high: number };

export type Phc = {
  unit?: string;
  range?: Range;
  /** The range this value is judged against depends on another answer (the
   *  analyte picked). catalogue/validate.py does not resolve it either, so
   *  neither do we: it is shown as a hint and never blocks. */
  range_from?: string;
  critical?: Range;
  flags?: string;
  operation?: string;
};

export type Question = {
  link_id: string;
  text: string;
  /** Help shown under the label on the form only. The posted card repeats the
   *  label, so anything long belongs here rather than in text. */
  description?: string;
  type: string;
  required?: boolean;
  repeats?: boolean;
  answer_option?: { value: string }[];
  /** The value set this question's ANSWER is drawn from, when the answer
   *  carries the concept. A question that binds one declares no
   *  `answer_option`: the codes live in the value set and writing them into
   *  the questionnaire would be the same list twice. See declarations.ts for
   *  where the options a picker draws come from instead. */
  answer_value_set?: string;
  structured_type?: string;
  /** Ask this question only when every condition holds. In the questionnaires
   *  since they were written, in no code until now; catalogue/validate.py does
   *  not read it either, so it governs what is offered, not what is accepted. */
  enable_when?: { question: string; operator: string; answer: unknown }[];
  questions?: Question[];
  styling_metadata?: { phc?: Phc };
};

export type Questionnaire = {
  slug: string;
  title: string;
  subject_type: string;
  questions: Question[];
  styling_metadata?: { phc?: Phc };
};

export type Payload = Record<string, unknown>;

/** The line a thread walks. The palette needs steps[0].operations[0]: the
 *  first thing a bundle does to a brand new thread. */
export type Workflow = {
  id: string; title: string; summary?: string; subject?: string;
  /** The field on `subject` naming what continues across threads. Absent when
   *  the bundle declares none, and then there is no patient screen to link
   *  to -- which is the correct answer, not a missing feature. */
  spine?: string | null;
  steps: { station: string; done_when: string; applies_when: string | null; operations: string[] }[];
};

// ---- compiled declarations ----

export type Operation = {
  id: string;
  kind: "read" | "write";
  short: string;
  title: string;
  summary: string;
  capability: string;
  station: string;
  instrument: string;
  preconditions: string[];
  irreversibility: "reversible" | "correctable" | "irreversible";
  input: string;
  writes: string[];
  emits: string[];
  verified: string;
  /** §10: which of the thread's first-class objects this operation's record is
   *  drawn as. From the atom's own `presents:`; "event" when it declares none.
   *  The renderer cannot derive this -- a handover and a vitals reading are
   *  both "an operation committed a row". */
  presents?: "event" | "artifact" | "handover" | "task" | "comment";
  tool: string;
  description: string;
  /** How this operation's payload becomes rows, from the atom's own
   *  frontmatter (kernel/mapping.py). A structured question has no sub schema,
   *  so the `{item: [...]}` sources here are the only declaration of which
   *  sub fields one of its rows may carry. See structured.ts. */
  mapping?: MappingRecord[];
};

export type MappingRecord = {
  resource: string;
  per_item?: string | null;
  per_question?: string[] | null;
  fields: Record<string, Record<string, unknown>>;
};

export type ViewDecl = {
  id: string; kind: "queue" | "summary" | "dashboard" | "tasklist"; title: string; summary?: string;
  /** A queue view says which subject fields matter and how a flag is styled.
   *  The thread header and the palette read both, so that neither has to
   *  guess at a subject's shape. `/facility` sends a short form of a view
   *  without them; `/catalogue` sends them. */
  columns?: string[];
  badges?: Record<string, string>;
  workflow?: string | null;
  group_by?: string | null;
  scope?: string;
  capability?: string;
  metrics?: string[];
  /** The colour law's declared wait limits, in minutes. Both optional; a
   *  bundle that declares neither renders pure monochrome. See
   *  QueueRow.entered_at. */
  target_minutes?: number | null;
  escalate_minutes?: number | null;
};

export type Catalogue = {
  capabilities?: string[];
  operations: Record<string, Operation>;
  views?: Record<string, ViewDecl>;
  metrics?: Record<string, { id: string; title: string }>;
  workflows?: Record<string, Workflow>;
  instruments?: Record<string, { id: string; title: string; summary?: string; operations: string[]; kind: string; fields?: string[] }>;
  manifest?: { id: string; title: string; version: string; views: string[] };
  /** role id to the capabilities it holds. vocab.BUNDLES, one list for the
   *  whole kernel, so a bundle's menu may name a role it has no use for. */
  bundles?: Record<string, string[]>;
};

/** GET /facility: which bundle this kernel loaded, and who is asking. */
export type Facility = {
  bundle: { id: string; title: string; version: string; workflow: string };
  capabilities: string[];
  views: ViewDecl[];
  roles: string[];
  user: { id: string; role: string; capabilities: string[] };
};

// ---- kernel records ----

export type StepStatus = { station: string; label: string; status: "done" | "now" | "pending" | "skipped" };

export type AuditRecord = {
  id: string; thread: string; operation: string; actor: string | null;
  surface: string; payload: Payload; outcome: string; at: string; proposal?: string | null;
};

export type Proposal = {
  id: string; thread: string; operation: string; payload: Payload;
  proposed_by: string | null; surface: string; status: string; created_at: string;
  flags_raised?: string[]; decided_by?: string | null; decided_at?: string | null;
  final_payload?: Payload | null;
  /** Per link_id, 0 to 1. Not on contracts.Proposal, it is on contracts.Draft;
   *  an instrument-produced proposal may carry it and the renderer highlights
   *  anything under 0.9 for re-reading. Absent is treated as certain. */
  confidence?: Record<string, number>;
  transcript?: string | null;
};

export type ThreadView = {
  id: string; workflow: string; subject: Record<string, unknown>;
  flags: string[]; station: string | null; line: StepStatus[];
  actions: Operation[]; proposals: Proposal[]; audit: AuditRecord[];
  capabilities: string[]; held: string[]; nudge?: string;
  /** The operation whose commit ends this role's task at this station, from
   *  the step's own done_when. The renderer never derives this: `applies_when`
   *  steps mean only the kernel knows which station is current. */
  closes: string | null;
};

export type QueueRow = {
  thread: string; subject: Record<string, unknown>; station: string | null;
  flags: string[]; badges: Record<string, string>; opened_at: string;
  /** When this row entered its current station, if the store tracks it.
   *  elapsed = now - (entered_at ?? opened_at). Not populated today. */
  entered_at?: string | null;
};

export type MetricValue = {
  metric: string; value: number; numerator: number; denominator: number | null;
  unit: string; window: string; window_start: string;
  /** Not on contracts.MetricValue. If the API sends it we show it, otherwise
   *  the metric id is the label. */
  title?: string;
};

export type SectionResult = {
  title: string; show?: string; resource?: string; rows: unknown[];
};

/** A tasklist row: a title and a count, no prose. `operation` present makes
 *  the row actionable; absent, it is a worklist to open, not tap. */
export type TaskRow = {
  title: string; count: number; threads: string[]; operation?: string | null;
};

export type ViewResult = {
  view: string; kind: "queue" | "summary" | "dashboard" | "tasklist";
  rows: unknown[]; generated_at: string; groups?: { key: string | null; count: number }[];
  /** Not on contracts.ViewResult. Nav needs a human title; if the API omits it
   *  we fall back to the view id. */
  title?: string;
};

/** GET /subjects/{id}: the spine. One subject, every thread that shares it,
 *  newest first. `spine` names the field the workflow declared as the join,
 *  so a screen can say what it is grouping by without assuming "patient". */
export type SubjectView = {
  subject: Record<string, unknown>;
  spine: string;
  encounters: {
    thread: string; opened_at: string; status: string; token: string;
    flags: string[]; station: string | null;
    /** What this visit actually committed, titled by the operation's own
     *  declaration, deduplicated, refusals excluded. §26's timeline entry. */
    did: { operation: string; title: string }[];
  }[];
};
