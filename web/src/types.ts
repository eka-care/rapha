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
  /** The operation(s) this form serves: one id, or a list when several
   *  operations share one form. Nothing reads it. */
  operation?: string | string[];
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
  /** A closed list declared inline. `display` is what the value is CALLED;
   *  the stored answer is always `value`. A question that declares no display
   *  is drawn as its own code, which is what every one of them did before any
   *  of them carried a word. */
  answer_option?: { value: string; display?: string }[];
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
  /** How each of this workflow's states is decided. `{stored: true}` means
   *  somebody asserted it; every other shape (`exists`, `all_of`, `gte`) is
   *  the kernel working it out from the records it already holds. The queue
   *  needs the difference, because a label the system worked out is drawn
   *  dashed and a person's decision is not. See loops.derivedStates. */
  states?: Record<string, unknown>;
  /** The declared order of those states, which is the order a row's labels
   *  are read in. */
  state_order?: string[];
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

/** What a declared answer is CALLED: a stored value in, the word a person
 *  reads out.
 *
 *  A FUNCTION passed in, never an import, and that is the whole point of it.
 *  `declarations.displayFor` answers out of a registry the app fetches before
 *  the first screen draws, so it is loaded state; the modules that work out
 *  what a row says (messages.ts, search.ts) are pure by instruction and run
 *  under plain node in their own checks. If they imported it they would get
 *  an EMPTY registry there, every display would fall back to the stored code,
 *  and the check would pass green over exactly the defect it exists to catch
 *  while the browser drew something else. Taking it as an argument is the
 *  same move `optionsFrom` makes with its value sets and `kernel/terminology`
 *  makes with its terminology, for the same reason: a check can hand over a
 *  fake and assert the thing was really consulted.
 *
 *  It has no default. A new caller has to decide, because every one that
 *  silently drew the stored code got there by not thinking about it.
 */
export type Display = (column: string, value: string) => string;

export type ViewDecl = {
  id: string; kind: "queue" | "summary" | "dashboard" | "tasklist" | "calendar"; title: string; summary?: string;
  /** A queue view says which subject fields matter and how a flag is styled.
   *  The thread header and the palette read both, so that neither has to
   *  guess at a subject's shape. `/facility` sends a short form of a view
   *  without them; `/catalogue` sends them. */
  columns?: string[];
  /** Which of those columns are LABELS rather than details: drawn as a pill
   *  on the row and given a filter chip, instead of going into the line of
   *  text under the name. A subset of `columns`, and the declaration lint
   *  refuses a label this view does not carry.
   *
   *  It has to be said rather than worked out. This renderer draws a health
   *  centre's line and a laboratory's bench from the same file and may not
   *  know that one of the six columns is a national programme; it was briefly
   *  inferred from whether the question that collects the answer was an
   *  optional closed choice, which happened to pick the right column in this
   *  bundle and would have picked a second one the moment another was added. */
  labels?: string[];
  /** How a row reached this queue, when the view distinguishes it. Three
   *  things, all declared: `column` is which of `columns` carries the fact,
   *  `mark` is the single value that earns a mark on the row's number, and
   *  `label` is what a filter chip over those rows is called.
   *
   *  This renderer is told the column, the value and the word, and nothing at
   *  all about what any of them mean. It draws a mark where the column equals
   *  the value and offers one chip under that word; it does not know that the
   *  value means a poster by a door, and a centre with no poster declares no
   *  provenance and loses both with no edit here.
   *
   *  Not a `label`, deliberately: a mark on the number rather than a pill,
   *  because it is the least important thing on the row. The declaration lint
   *  refuses a column that is both. */
  provenance?: { column: string; mark: string; label: string };
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
  /** What each station may record into, and the examples its screen shows
   *  somebody who has just pressed record. bundle.yaml's own `scribe` key,
   *  passed through whole; the nudges are sentences, never a form. */
  scribe?: Record<string, {
    default: string | null;
    choose: string[];
    nudges?: { field: string; say: string }[];
  }>;
  /** role id to the capabilities it holds. vocab.BUNDLES, one list for the
   *  whole kernel, so a bundle's menu may name a role it has no use for. */
  bundles?: Record<string, string[]>;
  /** A named group of this bundle's own capabilities, with the bundle's own
   *  word for the group. The same declaration a facility switches off, so it
   *  is the grouping a centre already thinks in; the role editor reads it
   *  rather than inventing headings of its own. */
  plugins?: Record<string, { title: string; always?: boolean; capabilities?: string[] }>;
  /** The LOADED bundle's own words, as opposed to `capabilities` and
   *  `bundles` above, which GET /catalogue narrows but catalogue.json keeps as
   *  the union over every bundle. Only the two title maps are read here: what
   *  a person reads for a capability and for a role, declared in bundle.yaml
   *  beside the id. A bundle that declares a plain list of ids sends neither,
   *  and the screens that print them say what they do instead. */
  vocabulary?: {
    capability_titles?: Record<string, string>;
    role_titles?: Record<string, string>;
  };
};

/** GET /facility: which bundle this kernel loaded, and who is asking. */
export type Facility = {
  /** Who covers which habitation at this centre, as its own declaration
   *  wrote it. Absent for a centre that declares none. */
  catchment?: {
    column: string;
    areas: { area: string; anm: string; villages: Record<string, string> }[];
  } | null;
  bundle: { id: string; title: string; version: string; workflow: string };
  /** Which shape of this facility the kernel is running, and what that shape
   *  withholds: `withheld` is capability to the plugin withholding it,
   *  `without` is plugin to its declared title. `capabilities` stays the whole
   *  of what the BUNDLE declares, which is why a screen needs these two to
   *  tell a capability this centre has from one it has declined. */
  facility: string | null;
  withheld: Record<string, string>;
  without: Record<string, string>;
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
  /** Which columns the section declared, in the order it declared them. The
   *  store already narrows a row to these, so this is only about which one a
   *  row leads with -- which the renderer used to decide for itself from a
   *  list of field names it had typed out. Empty for a section that shows the
   *  line, the flags or the audit rather than a resource. */
  fields?: string[];
};

/** A tasklist row: a title and a count, no prose. `operation` present makes
 *  the row actionable; absent, it is a worklist to open, not tap. */
export type TaskRow = {
  title: string; count: number; threads: string[]; operation?: string | null;
};

/** A calendar row: one contact owed on the day asked about. `owner` is a ROLE,
 *  never a person; there is no staff register to name one from. `subject_row`
 *  is that patient's record, drawn the way a queue draws a subject. */
export type CalendarRow = Contact & {
  subject: string;
  subject_row: Record<string, unknown>;
  /** The day this row is drawn on in a range answer: its due day, or today
   *  for a missed contact due before the range. Absent on a single-day answer. */
  cell?: string;
};

export type ViewResult = {
  view: string; kind: "queue" | "summary" | "dashboard" | "tasklist" | "calendar";
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
  /** The level between a person and a visit: one course of care that
   *  starts, runs and ends. Empty for a bundle that declares no episode and
   *  for a person who has had none. */
  episodes: Episode[];
  /** The kernel's clock when this was answered, the way a view answer has. */
  generated_at?: string;
};

/** One episode, and what it owes. `contacts` is DERIVED by the kernel from
 *  a schedule declaration and the episode's own date, so this screen draws
 *  an answer and never computes one: an episode that has ended carries no
 *  contacts at all, which is the whole safety property. */
export type Episode = {
  id: string;
  type: string;
  status: string;
  opened_at: string;
  ended_at: string;
  outcome: string;
  anchor_date: string;
  anchor_basis: string;
  encounters: string[];
  contacts: Contact[];
  /** Why there is nothing due, in the kernel's words, or "" when there is.
   *  An empty list is several different situations and a screen that cannot
   *  tell them apart says "nothing due" to a woman nobody has dated. */
  nothing_due: string;
};

export type Contact = {
  contact: string;
  title: string;
  schedule: string;
  episode: string;
  opens: string;
  due: string;
  closes: string;
  /** upcoming, due, done or missed. The kernel's vocabulary, the same way a
   *  line step's status is. */
  state: string;
  owner: string;
  operation: string;
  authority: string;
  reports_as: string;
  /** The programme's own phrasing for this contact, shown on hover while
   *  `title` is the plain words. "" when the programme has none. */
  programme_title?: string;
  done_at: string;
  basis: string;
};

/** The register: a person, and how many times they have been. The visits
 *  themselves come from `GET /subjects/{id}` when a row is opened, so this
 *  list and the thread's own spine cannot disagree about somebody's
 *  history. */
export type RegisterRow = {
  id: string;
  subject: Record<string, unknown>;
  visits: number;
  /** When they were last here. Empty for somebody registered and not seen. */
  last: string;
};

export type Register = { patients: RegisterRow[]; total: number };

/** Audit outcomes that mean A CLINICAL FACT WAS WRITTEN.
 *
 *  catalogue/vocab.py WROTE, and ui.check.ts holds the two together. It was
 *  three copies of a regular expression in this tree and two tuples in the
 *  kernel, and when "amended" was added on 2026-11-02 four of them silently
 *  went on showing the value from before the correction. A screen that
 *  disagrees with the record about a patient's pulse is the worst drift
 *  there is.
 *
 *  `proposed` is a request and not a write; a denial is the opposite of one.
 */
export const WROTE = ["committed", "confirmed", "allowed", "amended"] as const;

/** Did this audit line write something? */
export const wrote = (outcome: string) => WROTE.some((w) => outcome.startsWith(w));
