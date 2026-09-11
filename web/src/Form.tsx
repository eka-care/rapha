/** The questionnaire renderer. Given a compiled questionnaire it draws the
 *  form, and it validates the way the server validates, which is the only
 *  reason it is allowed to say anything about a value at all.
 *
 *  It knows nothing about vitals, or a PHC, or any particular field. Every
 *  behaviour below is driven by the declaration: type, required,
 *  answer_option, and styling_metadata.phc range / critical / unit.
 */
import type { Operation, Payload, Question, Questionnaire } from "./types";
import { blankRow, itemFields, toRow, type ItemField } from "./structured";
import { enabled, labelOf, phcOf, prune, validate, raisedFlags, rangeBlocked, walk } from "./validate";

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
 *  Nothing on the voice path lands here: packages/voice fails closed below its
 *  own floor, so every value it hands over carries a real score above zero. */
const unsureHint = (score: number) =>
  score > 0 ? `Unconfirmed · ${Math.round(score * 100)}%` : "Unconfirmed";

/** The one answer that is not a clinical value: the sentence someone typed to
 *  get past a range block. catalogue/validate.py knows it by this name too. */
const OVERRIDE = "override_reason";

const answeredHere = (v: unknown) => v !== undefined && v !== null && v !== "";

function outsideCritical(q: Question, v: unknown): boolean {
  const crit = phcOf(q).critical;
  if (!crit || v === undefined || v === null || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && !(crit.low <= n && n <= crit.high);
}

function Widget({
  q, op, value, onChange, disabled, ids,
}: {
  q: Question; op?: Operation; value: unknown; onChange: (v: unknown) => void;
  disabled?: boolean; ids: string;
}) {
  const set = (v: unknown) => onChange(v);
  const str = value === undefined || value === null ? "" : String(value);

  switch (q.type) {
    case "boolean":
      return (
        <label className="f-check">
          <input type="checkbox" checked={value === true} disabled={disabled}
                 onChange={(e) => set(e.target.checked)} />
          <span>Yes</span>
        </label>
      );
    case "choice":
      return (
        <select className="f-in" value={str} disabled={disabled} onChange={(e) => set(e.target.value || undefined)}>
          <option value="">Choose</option>
          {(q.answer_option ?? []).map((o) => (
            <option key={o.value} value={o.value}>{o.value}</option>
          ))}
        </select>
      );
    case "text":
      return <textarea className="f-in" id={`${ids}-${q.link_id}`} rows={4} value={str} disabled={disabled}
                       onChange={(e) => set(e.target.value)} />;
    case "integer":
    case "decimal":
      // The id is how an instrument that refused to guess hands the cursor
      // back to this field. inputMode makes it a keypad on a phone.
      return (
        <input className="f-in" id={`${ids}-${q.link_id}`} inputMode="decimal" value={str} disabled={disabled}
               step={q.type === "integer" ? 1 : "any"} type="number"
               onChange={(e) => set(e.target.value === "" ? undefined : e.target.value)} />
      );
    case "structured":
      return <Structured q={q} op={op} value={value} onChange={set} disabled={disabled} />;
    default:
      return <input className="f-in" value={str} disabled={disabled} onChange={(e) => set(e.target.value)} />;
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
  q, op, value, onChange, disabled,
}: {
  q: Question; op?: Operation; value: unknown; onChange: (v: unknown) => void; disabled?: boolean;
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
          {fields.map((f: ItemField) => (
            <label className="f-sub" key={f.key}>
              <span>{f.label}</span>
              <input className="f-in" value={String(row[f.key] ?? "")} disabled={disabled}
                     onChange={(e) => edit(i, f.key, e.target.value)} />
            </label>
          ))}
        </div>
      ))}
      <Add disabled={disabled} onClick={() => onChange([...rows.filter((r) => !blankRow(r)), {}])} />
    </div>
  );
}

function Add({ disabled, onClick }: { disabled?: boolean; onClick: () => void }) {
  return (
    <button type="button" className="cq" disabled={disabled} onClick={onClick}>Add another</button>
  );
}

export function Form({
  schema, op, value, onChange, problems, confidence, sources, disabled, ids = "f",
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

  const field = (q: Question) => {
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
    return (
      <div className={`f-field${mine.length ? " bad" : ""}${unsure ? " unsure" : ""}`} key={q.link_id}>
        <label className="f-lab">
          {q.text}
          {q.required && <span className="f-req">required</span>}
          {phc.unit && <span className="f-unit">{phc.unit}</span>}
        </label>
        {q.description && <div className="f-hint">{q.description}</div>}
        <Widget q={q} op={op} ids={ids} value={value[q.link_id]}
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
        {critical && !mine.length && (
          <span className="badge b-crit">Outside range{phc.flags ? ` · ${phc.flags}` : ""}</span>
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
          <label className="f-lab">
            Reason for overriding the range<span className="f-req">required</span>
          </label>
          <textarea className="f-in" rows={2} disabled={disabled}
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
