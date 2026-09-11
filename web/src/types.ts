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
  id: string; kind: "queue" | "summary" | "dashboard"; title: string; summary?: string;
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
};

export type QueueRow = {
  thread: string; subject: Record<string, unknown>; station: string | null;
  flags: string[]; badges: Record<string, string>; opened_at: string;
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

export type ViewResult = {
  view: string; kind: "queue" | "summary" | "dashboard";
  rows: unknown[]; generated_at: string; groups?: { key: string | null; count: number }[];
  /** Not on contracts.ViewResult. Nav needs a human title; if the API omits it
   *  we fall back to the view id. */
  title?: string;
};
