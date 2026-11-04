/** The questionnaire renderer. Given a compiled questionnaire it draws the
 *  form, and it validates the way the server validates, which is the only
 *  reason it is allowed to say anything about a value at all.
 *
 *  It knows nothing about vitals, or a PHC, or any particular field. Every
 *  behaviour below is driven by the declaration: type, required,
 *  answer_option, and styling_metadata.phc range / critical / unit.
 */
import type { CSSProperties } from "react";
import type { Operation, Payload, Question, Questionnaire } from "../types";
import { blankRow, itemFields, toRow, type ItemField } from "../structured";
import { options } from "../declarations";
import { capFor, weightFor } from "./span";
import { Pick } from "../ui/Picker";
import { Check } from "../ui/Check";
import { enabled, isRowGroup, labelOf, phcOf, prune, rowQuestions, validate, raisedFlags, rangeBlocked, walk } from "../validate";

export { validate, rangeBlocked, raisedFlags };

/** A value below this arrived from an instrument that is not sure it heard
 *  right. contracts.Draft says the renderer must highlight it for re-reading. */
const SURE = 0.9;

/** Zero does not mean "nought per cent sure". It means the instrument that
 *  produced this value reports no score at all, which is the scribe's case:
 *  Eka returns no per field recognition confidence. The only confidence in its
 *  response is a boolean about whether a diagnosis was matched to a code, and
 *  audio_matrix is about the recording, not the words. Drawing "0%" claimed a
 *  measurement that does not exist. The field stays marked unconfirmed either
 *  way, because unconfirmed is the part that matters.
 *
 *  A value the scribe filled lands here with a score the kernel capped below
 *  the sure threshold, so it reads as unconfirmed however plainly it was
 *  said. Zero means the service scored nothing, and the words are shown
 *  instead of a percentage nobody measured. */
const unsureHint = (score: number) =>
  score > 0 ? `Unconfirmed · ${Math.round(score * 100)}%` : "Unconfirmed";

/** The one answer that is not a clinical value: the sentence someone typed to
 *  get past a range block. catalogue/validate.py knows it by this name too. */
const OVERRIDE = "override_reason";

const answeredHere = (v: unknown) => v !== undefined && v !== null && v !== "";

/** How much of a line this question's answer is worth. A choice is measured
 *  on the displays the terminology gave its codes, which is what the picker
 *  will actually show; everything else is measured on its declared type. See
 *  span.ts for why a form that gives every field the same width is the form
 *  that looks unaligned. */
const weight = (q: Question) =>
  weightFor(q.type, q.type === "choice" ? options(q).map((o) => o.display) : []);

/** The style one field carries: its share of a row, and -- when it stands
 *  alone rather than in a row -- the width past which it stops growing. */
const sized = (q: Question, alone: boolean): CSSProperties => {
  const w = weight(q);
  const cap = alone ? capFor(w) : null;
  return cap === null
    ? ({ "--w": w } as CSSProperties)
    : ({ "--w": w, "--cap": `${cap}ch` } as CSSProperties);
};

/** The columns of a table of rows: each sub question's declared weight is its
 *  share of the width, and the last column is the way out of the row. */
const cols = (subs: Question[]): CSSProperties => ({
  gridTemplateColumns: `${subs.map((q) => `minmax(0, ${weight(q)}fr)`).join(" ")} 28px`,
});

function outsideCritical(q: Question, v: unknown): boolean {
  const crit = phcOf(q).critical;
  if (!crit || v === undefined || v === null || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && !(crit.low <= n && n <= crit.high);
}

function Widget({
  q, op, value, onChange, disabled, ids, autoFocus,
}: {
  q: Question; op?: Operation; value: unknown; onChange: (v: unknown) => void;
  disabled?: boolean; ids: string;
  /** Whether this is the first question this schema actually rendered, so it
   *  takes focus without a click. Computed once per render by the caller,
   *  which is the only place that knows what got skipped. */
  autoFocus?: boolean;
}) {
  const set = (v: unknown) => onChange(v);
  const str = value === undefined || value === null ? "" : String(value);
  /** SC 1.3.1 and 4.1.2: the id the question's own label points at.
   *
   *  Every branch below carries it, and that is the point. Three of them did
   *  and three did not, and the three that did not were the plain string
   *  field, the closed choice and the checkbox -- which between them are
   *  every field on the registration form this product is actually used
   *  through. The visible label was drawn above each one and attached to
   *  none, so a person using a screen reader was asked to fill in seven
   *  blanks. The id was already being computed for a different reason (an
   *  instrument that refuses to guess hands the cursor back to a field by
   *  it), so this is the same string doing both jobs. */
  const id = `${ids}-${q.link_id}`;

  switch (q.type) {
    case "boolean":
      return (
        <Check id={id} checked={value === true} disabled={disabled} autoFocus={autoFocus}
               onChange={set}>Yes</Check>
      );
    case "choice":
      // The values the form declared, or the codes of the value set this
      // question bound its answer to. The option's label is the display the
      // terminology gave the code, because nobody reads 229799001; the value
      // posted is still the code, so what is stored is what was confirmed.
      // A SHORT LIST IS A MENU AND A LONG ONE IS SEARCHED, and which this is
      // comes off the list itself (ui/pick.ts). The native control could do
      // neither well: it opens a menu this product cannot draw, it clips a
      // long option to the width of the box, and picking one of eleven
      // similar laboratory phrases meant reading all eleven.
      return (
        <Pick id={id} value={str} options={options(q)} disabled={disabled}
              autoFocus={autoFocus} onChange={set} />
      );
    case "text":
      return <textarea className="f-in" id={id} rows={4} value={str} disabled={disabled}
                       autoFocus={autoFocus} onChange={(e) => set(e.target.value)} />;
    // A DECLARED DATE GETS A CALENDAR. It fell through to the plain string
    // box below, so a form asking a nurse for the first day of a last
    // period gave her an empty rectangle and no hint of what to type in it.
    // The browser's own control knows the person's locale and writes the
    // one unambiguous form underneath, which is also the only form the
    // kernel should ever be sent: 03/04 is two different days in two
    // countries and a pregnancy is dated off this field.
    case "date":
      return (
        <input className="f-in" id={id} type="date" value={str} disabled={disabled}
               autoFocus={autoFocus}
               onChange={(e) => set(e.target.value || undefined)} />
      );
    case "integer":
    case "decimal":
      // The id is how an instrument that refused to guess hands the cursor
      // back to this field. inputMode makes it a keypad on a phone.
      return (
        <input className="f-in" id={id} inputMode="decimal" value={str} disabled={disabled}
               step={q.type === "integer" ? 1 : "any"} type="number" autoFocus={autoFocus}
               onChange={(e) => set(e.target.value === "" ? undefined : e.target.value)} />
      );
    case "structured":
      return <Structured q={q} op={op} value={value} onChange={set} disabled={disabled} autoFocus={autoFocus} />;
    default:
      return <input className="f-in" id={id} value={str} disabled={disabled} autoFocus={autoFocus}
                    onChange={(e) => set(e.target.value)} />;
  }
}

/** A structured answer is a CARE resource, not a string: a medication request
 *  wants a drug and a dose, a dispense wants a drug and a quantity. Which sub
 *  fields those are is declared, in the operation's own mapping, so each row
 *  is one labelled input per field the kernel will read off it. See
 *  structured.ts.
 *
 *  There is still no catalogue of drugs or tests on this machine, so each
 *  field is typed rather than picked, and the hint says so. An operation that
 *  declares no mapping for this question falls back to the single free text
 *  row, which is what every one of them drew before.
 */
function Structured({
  q, op, value, onChange, disabled, autoFocus,
}: {
  q: Question; op?: Operation; value: unknown; onChange: (v: unknown) => void; disabled?: boolean;
  autoFocus?: boolean;
}) {
  const fields = itemFields(op, q.link_id);
  const listed = Array.isArray(value) ? value : value === undefined || value === "" ? [] : [value];
  const rows = (listed.length ? listed : [""]).map((v) => toRow(v, fields));
  const write = (next: Record<string, unknown>[]) => onChange(next.filter((r) => !blankRow(r)));
  const edit = (i: number, key: string, text: string) =>
    write(rows.map((r, j) => (j === i ? { ...r, [key]: text } : r)));

  if (!fields.length) {
    // Nothing declares this answer's shape, so it stays what it was: one line
    // per item, which kernel/mapping.py reads as {code: <it>}.
    return (
      <div className="f-rows">
        {rows.map((row, i) => (
          <input key={i} className="f-in" value={String(row.code ?? "")} disabled={disabled}
                 autoFocus={autoFocus && i === 0}
                 placeholder={`${q.structured_type ?? "entry"} ${i + 1}`}
                 onChange={(e) => edit(i, "code", e.target.value)} />
        ))}
        <Add disabled={disabled} onClick={() => onChange([...rows.filter((r) => !blankRow(r)), {}])} />
      </div>
    );
  }

  return (
    <div className="f-rows">
      {rows.map((row, i) => (
        <div className="f-item" key={i}>
          <span className="f-item-n">{i + 1}</span>
          {fields.map((f: ItemField, j: number) => (
            <label className="f-sub" key={f.key}>
              <span>{f.label}</span>
              <input className="f-in" value={String(row[f.key] ?? "")} disabled={disabled}
                     autoFocus={autoFocus && i === 0 && j === 0}
                     onChange={(e) => edit(i, f.key, e.target.value)} />
            </label>
          ))}
        </div>
      ))}
      <Add disabled={disabled} onClick={() => onChange([...rows.filter((r) => !blankRow(r)), {}])} />
    </div>
  );
}

function Add({ disabled, onClick, what }: { disabled?: boolean; onClick: () => void; what?: string }) {
  return (
    <button type="button" className="cq" disabled={disabled} onClick={onClick}>
      {what ? `Add another ${what}` : "Add another"}
    </button>
  );
}

export function Form({
  schema, op, value, onChange, problems, confidence, sources, evidence, disabled, ids = "f",
}: {
  schema: Questionnaire;
  /** The operation this form commits. Only a structured question needs it, to
   *  find the sub fields its rows carry. */
  op?: Operation;
  value: Payload;
  onChange: (next: Payload) => void;
  /** Shown only once the person has tried to commit, so a form does not
   *  scold someone for not having typed yet. */
  problems: { link_id: string; message: string }[];
  confidence?: Record<string, number>;
  /** Where a value came from, per field, when it was not typed here: the ABHA
   *  journey's name for itself. Same highlight the unconfirmed instrument
   *  values get, because it is the same instruction to the reader, and the
   *  chip says which instrument rather than making them guess. */
  sources?: Record<string, string>;
  /** The words a recording took each value from, drawn under the field so the
   *  person checks the value against what was said rather than against memory. */
  evidence?: Record<string, string>;
  disabled?: boolean;
  /** The prefix for every field's DOM id. Two of these forms can be on screen
   *  at once now, one per pending proposal, so the ids cannot be the link_id
   *  alone: the instrument that hands the cursor back would find the first
   *  form on the page rather than its own. */
  ids?: string;
}) {
  const set = (link_id: string, v: unknown) => {
    const next = { ...value };
    if (v === undefined) delete next[link_id];
    else next[link_id] = v;
    // An answer that switches a question off takes that question's answer with
    // it. The server does not, so leaving it would commit a glucose on a CBC.
    onChange(prune(schema, next));
  };
  const blocked = rangeBlocked(schema, value);
  const flags = raisedFlags(schema, value);
  // The clerk's cursor lands on the first question this render actually
  // draws, not the first in the schema: a group, a display, or a switched-off
  // question is not where a click would have gone either. Set once, by
  // whichever question clears every skip check first.
  let focused = false;

  /** One sub value of one row of a repeating group. The row's own index is in
   *  the id, so the problem, the words it was heard from and the tick it is
   *  owed all belong to this value and not to the question. */
  const setRow = (gid: string, index: number, sub: string, v: unknown) => {
    const listed = Array.isArray(value[gid]) ? [...(value[gid] as unknown[])] : [];
    while (listed.length <= index) listed.push({});
    const row = { ...((listed[index] ?? {}) as Record<string, unknown>) };
    if (v === undefined) delete row[sub];
    else row[sub] = v;
    listed[index] = row;
    onChange(prune(schema, { ...value, [gid]: listed }));
  };

  const dropRow = (gid: string, index: number) => {
    const listed = (Array.isArray(value[gid]) ? [...(value[gid] as unknown[])] : [])
      .filter((_, j) => j !== index);
    const next = { ...value };
    if (listed.length) next[gid] = listed;
    else delete next[gid];
    onChange(prune(schema, next));
  };

  /** A repeating group: one block per row, one labelled widget per sub
   *  question. Nothing here is specific to a diagnosis or a medicine; the sub
   *  questions, their types and their value sets are all declared.
   *
   *  An empty row is DRAWN and not stored. So a form nobody has typed into
   *  says "medications is required", which is what is wrong, rather than
   *  naming seven fields of a row that does not exist yet.
   */
  const rowsOf = (q: Question) => {
    const stored = Array.isArray(value[q.link_id]) ? (value[q.link_id] as unknown[]) : [];
    const drawn = stored.length ? stored : [{}];
    const subs = [...rowQuestions(q).values()];
    const mine = problems.filter((p) => p.link_id === q.link_id);
    return (
      <fieldset className="f-group" key={q.link_id}>
        {/* The declared help says "one row per medicine, each row needs all
            six answers", which a header of six columns now says by being
            there. It stays reachable -- on the title, for a pointer and a
            screen reader -- and off the screen. */}
        <legend title={phcOf(q).help}>{q.text}</legend>
        {/* A TABLE, NOT A STACK OF CARDS. A prescription is a list of lines
            that all say the same six things, and six labelled boxes per
            medicine repeated three times is a form; a header once and a row
            per medicine is a table, which is how a prescription has always
            been read. The columns divide the width by the same declared
            weights the cards used, so a drug name still gets more room than
            a dose.

            The header is for the eye. Each cell is still a label of its own
            for a screen reader, so a row read aloud says what each box is. */}
        <div className="f-tbl">
          <div className="f-tr f-th" aria-hidden="true" style={cols(subs)}>
            {subs.map((sub) => (
              <span key={sub.link_id}>
                {labelOf(sub)}{phcOf(sub).unit ? ` (${phcOf(sub).unit})` : ""}
              </span>
            ))}
            <span />
          </div>
          {drawn.map((row, i) => {
            const given = (row ?? {}) as Record<string, unknown>;
            return (
              <div className="f-tr" key={i} style={cols(subs)}>
                {subs.map((sub) => {
                  const id = `${q.link_id}[${i}].${sub.link_id}`;
                  const bad = mine.filter((p) => p.message.startsWith(`${id} `));
                  const heard = evidence?.[id];
                  const score = confidence?.[id];
                  const unsure = score !== undefined && score < SURE;
                  return (
                    <label className={`f-td${bad.length ? " bad" : ""}${unsure ? " unsure" : ""}`}
                           key={sub.link_id}>
                      <span className="u-sr">
                        {labelOf(sub)}{phcOf(sub).unit ? ` (${phcOf(sub).unit})` : ""}
                      </span>
                      <Widget q={sub} op={op} ids={`${ids}-${q.link_id}-${i}`}
                              value={given[sub.link_id]}
                              onChange={(v) => setRow(q.link_id, i, sub.link_id, v)}
                              disabled={disabled} />
                      {unsure && <span className="f-hint unsure">{unsureHint(score ?? 0)}</span>}
                      {heard && <span className="f-hint heard">“{heard}”</span>}
                      {bad.map((b) => <span className="f-bad" key={b.message}>{b.message}</span>)}
                    </label>
                  );
                })}
                {stored.length > 1 ? (
                  <button type="button" className="f-x" disabled={disabled}
                          aria-label={`Remove ${phcOf(q).row ?? "row"} ${i + 1}`}
                          onClick={() => dropRow(q.link_id, i)}>×</button>
                ) : <span />}
              </div>
            );
          })}
        </div>
        <Add disabled={disabled} what={phcOf(q).row ?? "row"}
             onClick={() => onChange(prune(schema, { ...value, [q.link_id]: [...drawn, {}] }))} />
        {mine.filter((p) => p.message === `${q.link_id} is required`)
             .map((p) => <div className="f-bad" key={p.message}>{p.message}</div>)}
      </fieldset>
    );
  };

  const field = (q: Question) => {
    if (isRowGroup(q)) return rowsOf(q);
    if (q.type === "group") {
      return (
        <fieldset className="f-group" key={q.link_id}>
          <legend>{q.text}</legend>
          {(q.questions ?? []).map(field)}
        </fieldset>
      );
    }
    if (q.type === "display") return <div className="f-hint" key={q.link_id}>{q.text}</div>;
    // A question this payload has switched off is not asked. It is still drawn
    // if it somehow holds an answer, because a value that would be sent must
    // never be off screen: that is the whole difference between hiding a
    // question and hiding a value.
    // A required question is always asked: see prune() on why.
    if (!q.required && !enabled(q, value) && !answeredHere(value[q.link_id])) return null;
    // The override reason has one control on this form and it is below, next to
    // the sentence saying what an override costs. A schema that declares the
    // question as well is not drawn twice.
    if (q.link_id === OVERRIDE) return null;

    const phc = phcOf(q);
    const mine = problems.filter((p) => p.link_id === q.link_id);
    const from = sources?.[q.link_id];
    const unsure = from !== undefined || (confidence?.[q.link_id] !== undefined && confidence[q.link_id] < SURE);
    const critical = outsideCritical(q, value[q.link_id]);
    const first = !focused;
    focused = true;
    return (
      <div className={`f-field${mine.length ? " bad" : ""}${unsure ? " unsure" : ""}`}
           style={sized(q, true)} key={q.link_id}>
        {/* A structured answer is a GROUP of fields, not one field, and each
            of its own sub widgets is already inside its own label. Pointing
            this one at an id that is not in the document would be worse than
            leaving it as the caption it is. */}
        <label className="f-lab" htmlFor={q.type === "structured" ? undefined : `${ids}-${q.link_id}`}>
          {q.text}
          {phc.unit && <span className="f-unit">{phc.unit}</span>}
        </label>
        {q.description && <div className="f-hint">{q.description}</div>}
        {/* THE SENTENCE THE BUNDLE WROTE FOR THIS FIELD. A group drew its
            declared help and a plain field threw it away, so "A remembered
            period and a scan are not equally reliable, and every date after
            this one is measured from whichever you pick" was written,
            compiled, served -- and never once put on a screen. That is most
            of why these forms read as though they were written for whoever
            built them: the part written for the nurse was being dropped on
            the floor. */}
        {phc.help && <div className="f-hint">{phc.help}</div>}
        <Widget q={q} op={op} ids={ids} value={value[q.link_id]} autoFocus={first}
                onChange={(v) => set(q.link_id, v)} disabled={disabled} />
        {phc.range && (
          <div className="f-hint">Usual range {phc.range.low} to {phc.range.high}{phc.unit ? ` ${phc.unit}` : ""}</div>
        )}
        {phc.range_from && (
          <div className="f-hint">Range depends on {phc.range_from}</div>
        )}
        {unsure && (
          <div className="f-hint unsure">{from ?? unsureHint(confidence?.[q.link_id] ?? 0)}</div>
        )}
        {evidence?.[q.link_id] && <div className="f-hint heard">“{evidence[q.link_id]}”</div>}
        {critical && !mine.length && (
          <span className="badge b-crit" data-act="">Outside range{phc.flags ? ` · ${phc.flags}` : ""}</span>
        )}
        {mine.map((p) => <div className="f-bad" key={p.message}>{p.message}</div>)}
      </div>
    );
  };

  return (
    <div className="f-form">
      {schema.questions.map(field)}

      {blocked && (
        <div className="f-field override">
          <label className="f-lab" htmlFor={`${ids}-${OVERRIDE}`}>
            Reason for overriding the range
          </label>
          <textarea className="f-in" id={`${ids}-${OVERRIDE}`} rows={2} disabled={disabled}
                    value={String(value[OVERRIDE] ?? "")}
                    onChange={(e) => set(OVERRIDE, e.target.value || undefined)} />
        </div>
      )}

      {flags.length > 0 && (
        <div className="f-flags">Raises {flags.join(", ")}</div>
      )}
    </div>
  );
}

/** Which questions this schema actually has, for a read-only rendering of a
 *  payload somebody else produced. */
export function labelled(schema: Questionnaire, payload: Payload): [string, string, unknown][] {
  return walk(schema.questions)
    .filter((q) => q.type !== "group" && q.type !== "display")
    .map((q) => [q.link_id, labelOf(q), payload[q.link_id]] as [string, string, unknown]);
}
