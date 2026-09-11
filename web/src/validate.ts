/** The client half of catalogue/validate.py.
 *
 *  The server stays the authority: nothing here decides anything, it only
 *  tells the person what the guard is about to say, before they tap. So it
 *  has to say the SAME thing. The messages below are the Python strings
 *  character for character, and validate.check.ts runs both implementations
 *  over the same cases and diffs them. If you change one, change the other or
 *  the check fails.
 */
import type { Payload, Question, Questionnaire, Range } from "./types";

export type Problem = { link_id: string; message: string };

const NUMERIC = new Set(["integer", "decimal"]);

export function walk(questions: Question[]): Question[] {
  const out: Question[] = [];
  for (const q of questions) {
    out.push(q);
    out.push(...walk(q.questions ?? []));
  }
  return out;
}

export function phcOf(q: { styling_metadata?: { phc?: unknown } }): Record<string, any> {
  return ((q.styling_metadata ?? {}).phc ?? {}) as Record<string, any>;
}

const answered = (v: unknown) => v !== undefined && v !== null && v !== "";

/** python int() and float() on the value, or null when they would raise.
 *  int() accepts a float and truncates it; int("12.9") raises. */
function cast(type: string, v: unknown): number | null {
  if (type === "integer") {
    if (typeof v === "boolean") return v ? 1 : 0;
    if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : null;
    if (typeof v === "string" && /^\s*[+-]?\d+\s*$/.test(v)) return parseInt(v, 10);
    return null;
  }
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v.trim()))) {
    return Number(v.trim());
  }
  return null;
}

export function validate(schema: Questionnaire, payload: Payload): Problem[] {
  const questions = walk(schema.questions);
  const byId = new Map(questions.map((q) => [q.link_id, q]));
  const problems: Problem[] = [];
  const override = String(payload["override_reason"] ?? "").trim();

  for (const [link_id, q] of byId) {
    const has = link_id in payload && answered(payload[link_id]);
    if (q.required && !has) {
      problems.push({ link_id, message: `${link_id} is required` });
      continue;
    }
    if (!has) continue;

    let value: unknown = payload[link_id];
    const numeric = NUMERIC.has(q.type);
    if (numeric) {
      const n = cast(q.type, value);
      if (n === null) {
        problems.push({ link_id, message: `${link_id} must be ${q.type}` });
        continue;
      }
      value = n;
    } else if (q.type === "boolean" && typeof value !== "boolean") {
      problems.push({ link_id, message: `${link_id} must be boolean` });
      continue;
    } else if (q.type === "choice") {
      const allowed = (q.answer_option ?? []).map((o) => o.value);
      if (allowed.length && !allowed.includes(value as string)) {
        const sorted = [...allowed].sort();
        problems.push({
          link_id,
          message: `${link_id} must be one of [${sorted.map((s) => `'${s}'`).join(", ")}]`,
        });
        continue;
      }
    }

    // The range rule. A value outside physiological range blocks the commit
    // and requires an explicit override carrying a reason. The override is
    // recorded, not waived.
    const rng: Range | undefined = phcOf(q).range;
    if (rng && numeric) {
      const n = value as number;
      if (!(rng.low <= n && n <= rng.high)) {
        if (override) continue;
        problems.push({
          link_id,
          message: `${link_id} is ${py(n, q.type)}, outside ${py(rng.low, "raw")} to ${py(rng.high, "raw")}. ` +
            "Enter a reason to override, or correct the value.",
        });
      }
    }
  }

  const unknown = Object.keys(payload)
    .filter((k) => !byId.has(k) && k !== "override_reason")
    .sort();
  for (const k of unknown) problems.push({ link_id: k, message: `${k} is not a question on this form` });
  return problems;
}

/** State flags this payload raises. A critical value that is still inside the
 *  physiological range does not block; it raises a flag and the flag promotes
 *  an action elsewhere. */
export function raisedFlags(schema: Questionnaire, payload: Payload): string[] {
  const out = new Set<string>();
  for (const q of walk(schema.questions)) {
    const phc = phcOf(q);
    const v = payload[q.link_id];
    if (!phc.flags || v === undefined || v === null || v === "") continue;
    // A question with `flags` and no `critical` band is a consent: it has no
    // physiological range to be outside of, and it raises its flag when the
    // answer is yes. Mirrors catalogue/validate.flags() and is as strict: only
    // a real boolean true, so a missing answer or the string "yes" raises
    // nothing. The server is authoritative either way; this keeps the form's
    // preview badge honest.
    if (!phc.critical) {
      if (v === true) out.add(phc.flags);
      continue;
    }
    const n = typeof v === "boolean" ? null : Number(typeof v === "string" ? v.trim() : v);
    if (n === null || !Number.isFinite(n)) continue;
    if (!(phc.critical.low <= n && n <= phc.critical.high)) out.add(phc.flags);
  }
  return [...out];
}

/** True when the only thing standing between this payload and the server is an
 *  override reason. Drives the override box appearing, and nothing else. */
export function rangeBlocked(schema: Questionnaire, payload: Payload): boolean {
  const { override_reason: _drop, ...rest } = payload as Record<string, unknown>;
  return validate(schema, rest).some((p) => p.message.includes(", outside "));
}

/** str() of a Python number. float(38) prints "38.0"; int(38) and a bound
 *  loaded straight from JSON print "38". The message text has to match the
 *  server's exactly, so the caller says which one it is. */
function py(n: number, kind: string): string {
  return kind === "decimal" && Number.isInteger(n) ? `${n}.0` : String(n);
}

// -------------------------------------------------------------- enable_when

/** Whether a question is asked at all, given what is answered so far.
 *
 *  `enable_when` is in the questionnaires and was in no code: every analyte of
 *  every panel drew at once, with critical band warnings on fields the chosen
 *  panel does not use. catalogue/validate.py does not read it either
 *  (bundles/LAB-LOG.md 13: a glucose on a CBC still commits), so this is the
 *  renderer refusing to offer the field, not the server refusing the value.
 *
 *  An operator this renderer does not know never hides a question. Hiding on a
 *  guess is how a required field disappears.
 */
export function enabled(q: Question, payload: Payload): boolean {
  for (const c of q.enable_when ?? []) {
    const v = payload[c.question];
    const has = answered(v);
    if (c.operator === "exists") {
      if (has !== (c.answer !== false)) return false;
    } else if (c.operator === "equals") {
      if (!has || String(v) !== String(c.answer)) return false;
    } else if (c.operator === "not_equals") {
      if (has && String(v) === String(c.answer)) return false;
    }
  }
  return true;
}

/** The payload with the answers to switched-off questions removed. Changing
 *  the panel from cbc to bmp leaves a haemoglobin behind, and the server does
 *  not refuse it, so what is not on screen must not be in the payload either.
 *  Loops because one hidden question can hide the next; each pass removes at
 *  least one key, so it ends. */
export function prune(schema: Questionnaire, payload: Payload): Payload {
  // A required question is never dropped and never hidden. The server asks for
  // it whatever else is answered (catalogue/validate.py does not read
  // enable_when), so clearing it would build a form that cannot be committed
  // and will not say why. A questionnaire that declares one both required and
  // conditional is contradicting itself, and this is the side to err on.
  const questions = walk(schema.questions).filter((q) => !q.required);
  let out = payload;
  for (;;) {
    const drop = questions.filter((q) => q.link_id in out && !enabled(q, out));
    if (!drop.length) return out;
    out = { ...out };
    for (const q of drop) delete out[q.link_id];
  }
}
