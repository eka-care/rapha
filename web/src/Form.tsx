/** The questionnaire renderer. Given a compiled questionnaire it draws the
 *  form, and it validates the way the server validates, which is the only
 *  reason it is allowed to say anything about a value at all.
 *
 *  It knows nothing about vitals, or a PHC, or any particular field. Every
 *  behaviour below is driven by the declaration: type, required,
 *  answer_option, and styling_metadata.phc range / critical / unit.
 */
import type { Payload, Question, Questionnaire } from "./types";
import { phcOf, validate, raisedFlags, rangeBlocked, walk } from "./validate";

export { validate, rangeBlocked, raisedFlags };

/** A value below this arrived from an instrument that is not sure it heard
 *  right. contracts.Draft says the renderer must highlight it for re-reading. */
const SURE = 0.9;

function outsideCritical(q: Question, v: unknown): boolean {
  const crit = phcOf(q).critical;
  if (!crit || v === undefined || v === null || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && !(crit.low <= n && n <= crit.high);
}

function Widget({
  q, value, onChange, disabled,
}: {
  q: Question; value: unknown; onChange: (v: unknown) => void; disabled?: boolean;
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
      return <textarea className="f-in" rows={4} value={str} disabled={disabled}
                       onChange={(e) => set(e.target.value)} />;
    case "integer":
    case "decimal":
      return (
        <input className="f-in" inputMode="decimal" value={str} disabled={disabled}
               step={q.type === "integer" ? 1 : "any"} type="number"
               onChange={(e) => set(e.target.value === "" ? undefined : e.target.value)} />
      );
    case "structured":
      return <Structured q={q} value={value} onChange={set} disabled={disabled} />;
    default:
      return <input className="f-in" value={str} disabled={disabled} onChange={(e) => set(e.target.value)} />;
  }
}

/** A structured answer is a CARE resource, not a string: a medication request
 *  wants a drug from a catalogue, a dose and a duration. There is no such
 *  catalogue on this machine, so this is a repeating free-text list and it
 *  says so. It is honest, it round-trips, and it is not a prescribing UI. */
function Structured({
  q, value, onChange, disabled,
}: {
  q: Question; value: unknown; onChange: (v: unknown) => void; disabled?: boolean;
}) {
  const rows: string[] = Array.isArray(value) ? (value as string[]) : value ? [String(value)] : [""];
  const write = (next: string[]) => onChange(next.filter((r) => r.trim() !== ""));
  return (
    <div className="f-rows">
      {rows.map((row, i) => (
        <input key={i} className="f-in" value={row} disabled={disabled}
               placeholder={`${q.structured_type ?? "entry"} ${i + 1}`}
               onChange={(e) => write(rows.map((r, j) => (j === i ? e.target.value : r)))} />
      ))}
      <button type="button" className="cq" disabled={disabled} onClick={() => onChange([...rows.filter(Boolean), ""])}>
        Add another
      </button>
      <div className="f-hint">
        Typed as free text. A {q.structured_type ?? "structured"} picker is not built, so what you
        write here is what is sent.
      </div>
    </div>
  );
}

export function Form({
  schema, value, onChange, problems, confidence, disabled,
}: {
  schema: Questionnaire;
  value: Payload;
  onChange: (next: Payload) => void;
  /** Shown only once the person has tried to commit, so a form does not
   *  scold someone for not having typed yet. */
  problems: { link_id: string; message: string }[];
  confidence?: Record<string, number>;
  disabled?: boolean;
}) {
  const set = (link_id: string, v: unknown) => {
    const next = { ...value };
    if (v === undefined) delete next[link_id];
    else next[link_id] = v;
    onChange(next);
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

    const phc = phcOf(q);
    const mine = problems.filter((p) => p.link_id === q.link_id);
    const unsure = confidence?.[q.link_id] !== undefined && confidence[q.link_id] < SURE;
    const critical = outsideCritical(q, value[q.link_id]);
    return (
      <div className={`f-field${mine.length ? " bad" : ""}${unsure ? " unsure" : ""}`} key={q.link_id}>
        <label className="f-lab">
          {q.text}
          {q.required && <span className="f-req">required</span>}
          {phc.unit && <span className="f-unit">{phc.unit}</span>}
        </label>
        <Widget q={q} value={value[q.link_id]} onChange={(v) => set(q.link_id, v)} disabled={disabled} />
        {phc.range && (
          <div className="f-hint">Usual range {phc.range.low} to {phc.range.high}{phc.unit ? ` ${phc.unit}` : ""}</div>
        )}
        {phc.range_from && (
          <div className="f-hint">Range depends on {phc.range_from}. Not checked here or on the server.</div>
        )}
        {unsure && (
          <div className="f-hint unsure">
            Heard, not certain ({Math.round((confidence?.[q.link_id] ?? 0) * 100)}%). Read it back before you commit.
          </div>
        )}
        {critical && !mine.length && (
          <span className="badge b-crit">Outside the safe band{phc.flags ? `, raises ${phc.flags}` : ""}</span>
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
                    value={String(value.override_reason ?? "")}
                    onChange={(e) => set("override_reason", e.target.value || undefined)} />
          <div className="f-hint">
            A value outside the usual range is not refused, it is recorded with your reason.
            The reason is written to the audit trail and cannot be removed later.
          </div>
        </div>
      )}

      {flags.length > 0 && (
        <div className="f-flags">
          This will raise {flags.join(", ")}. A flag does not block the entry; it is what makes the
          next station look.
        </div>
      )}
    </div>
  );
}

/** Which questions this schema actually has, for a read-only rendering of a
 *  payload somebody else produced. */
export function labelled(schema: Questionnaire, payload: Payload): [string, string, unknown][] {
  return walk(schema.questions)
    .filter((q) => q.type !== "group" && q.type !== "display")
    .map((q) => [q.link_id, q.text, payload[q.link_id]] as [string, string, unknown]);
}
