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

/** What a question is called on a card. `phc.short` exists for the two
 *  questions whose text is a script read to a patient: the script belongs on
 *  the form, and the record needs a label, not a paragraph. */
export const labelOf = (q: { text?: string; styling_metadata?: { phc?: unknown } }): string =>
  phcOf(q).short ?? q.text ?? "";

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

/** Does this question hold a list of rows? A `group` that repeats. Mirrors
 *  catalogue/validate.is_row_group. */
export const isRowGroup = (q: Question): boolean =>
  q.type === "group" && Boolean(q.repeats);

/** Every repeating group on this form, by link_id. */
export function rowGroups(schema: Questionnaire): Map<string, Question> {
  return new Map(walk(schema.questions).filter(isRowGroup).map((q) => [q.link_id, q]));
}

/** One repeating group's sub questions, by link_id. */
export function rowQuestions(group: Question): Map<string, Question> {
  return new Map(walk(group.questions ?? []).map((q) => [q.link_id, q]));
}

/** What one row of this group is called, in a sentence a clinician reads. */
export const rowLabel = (group: Question): string => phcOf(group).row ?? "row";

/** Type, choice and range failures for one answered value. `where` says which
 *  row it was in and is empty at the top level. */
function answerProblems(q: Question, given: unknown, where: string, override: string): Problem[] {
  const link_id = where + q.link_id;
  let value = given;
  const numeric = NUMERIC.has(q.type);
  if (numeric) {
    const n = cast(q.type, value);
    if (n === null) return [{ link_id, message: `${link_id} must be ${q.type}` }];
    value = n;
  } else if (q.type === "boolean" && typeof value !== "boolean") {
    return [{ link_id, message: `${link_id} must be boolean` }];
  } else if (q.type === "choice") {
    const allowed = (q.answer_option ?? []).map((o) => o.value);
    if (allowed.length && !allowed.includes(value as string)) {
      const sorted = [...allowed].sort();
      return [{
        link_id,
        message: `${link_id} must be one of [${sorted.map((s) => `'${s}'`).join(", ")}]`,
      }];
    }
  }

  // The range rule. A value outside physiological range blocks the commit
  // and requires an explicit override carrying a reason. The override is
  // recorded, not waived.
  const rng: Range | undefined = phcOf(q).range;
  if (rng && numeric) {
    const n = value as number;
    if (!(rng.low <= n && n <= rng.high)) {
      if (override) return [];
      return [{
        link_id,
        message: `${link_id} is ${py(n, q.type)}, outside ${py(rng.low, "raw")} to ${py(rng.high, "raw")}. ` +
          "Enter a reason to override, or correct the value.",
      }];
    }
  }
  return [];
}

/** Every failure in one repeating group's answer, row by row. The row number
 *  is in every sentence: "medications is invalid" does not say which line. */
function rowProblems(link_id: string, group: Question, payload: Payload, override: string): Problem[] {
  const subs = rowQuestions(group);
  const label = rowLabel(group);
  const value = payload[link_id];
  const empty = value === undefined || value === null || value === "" ||
    (Array.isArray(value) && !value.length);
  if (empty) return group.required ? [{ link_id, message: `${link_id} is required` }] : [];
  if (!Array.isArray(value)) {
    return [{ link_id, message: `${link_id} is a list of rows, one per ${label}` }];
  }
  const problems: Problem[] = [];
  value.forEach((row, index) => {
    const where = `${link_id}[${index}].`;
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      problems.push({
        link_id,
        message: `${link_id}[${index}] is not a ${label}: a ${label} is a set of answers, not a single value`,
      });
      return;
    }
    const given = row as Record<string, unknown>;
    for (const [sub_id, q] of subs) {
      const has = sub_id in given && answered(given[sub_id]);
      if (q.required && !has) {
        problems.push({ link_id, message: `${where}${sub_id} is required` });
        continue;
      }
      if (!has) continue;
      problems.push(...answerProblems(q, given[sub_id], where, override).map(
        (p) => ({ link_id, message: p.message })));
    }
    for (const extra of Object.keys(given).filter((k) => !subs.has(k)).sort()) {
      problems.push({ link_id, message: `${where}${extra} is not a question on this ${label}` });
    }
  });
  return problems;
}

export function validate(schema: Questionnaire, payload: Payload): Problem[] {
  const groups = rowGroups(schema);
  const inside = new Set<string>();
  for (const group of groups.values()) for (const k of rowQuestions(group).keys()) inside.add(k);
  // A repeating group's sub questions are answered inside its rows and never
  // at the top level, so they are not top level questions here either. The
  // server says the same, and this file exists to say the same thing.
  const byId = new Map(walk(schema.questions)
    .filter((q) => !inside.has(q.link_id) && !groups.has(q.link_id))
    .map((q) => [q.link_id, q]));
  const problems: Problem[] = [];
  const override = String(payload["override_reason"] ?? "").trim();

  for (const [link_id, q] of byId) {
    const has = link_id in payload && answered(payload[link_id]);
    if (q.required && !has) {
      problems.push({ link_id, message: `${link_id} is required` });
      continue;
    }
    if (!has) continue;
    problems.push(...answerProblems(q, payload[link_id], "", override));
  }

  for (const [link_id, group] of groups) {
    problems.push(...rowProblems(link_id, group, payload, override));
  }

  const unknown = Object.keys(payload)
    .filter((k) => !byId.has(k) && !groups.has(k) && k !== "override_reason")
    .sort();
  for (const k of unknown) problems.push({ link_id: k, message: `${k} is not a question on this form` });
  return problems;
}

/** State flags this payload raises. A critical value that is still inside the
 *  physiological range does not block; it raises a flag and the flag promotes
 *  an action elsewhere. */
export function raisedFlags(schema: Questionnaire, payload: Payload): string[] {
  const out = new Set<string>();
  // A repeating group's sub questions are answered in rows, so looking for
  // them in the payload finds nothing. Flattened with their row's value, the
  // way catalogue/validate.flags() does.
  const seen: { q: Question; v: unknown }[] = [];
  for (const q of walk(schema.questions)) {
    if (isRowGroup(q)) {
      for (const row of (Array.isArray(payload[q.link_id]) ? payload[q.link_id] : []) as unknown[]) {
        if (!row || typeof row !== "object") continue;
        for (const [sub_id, sub] of rowQuestions(q)) {
          seen.push({ q: sub, v: (row as Record<string, unknown>)[sub_id] });
        }
      }
      continue;
    }
    seen.push({ q, v: payload[q.link_id] });
  }
  for (const { q, v } of seen) {
    const phc = phcOf(q);
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
  const inside = new Set<string>();
  for (const group of rowGroups(schema).values()) {
    for (const k of rowQuestions(group).keys()) inside.add(k);
  }
  // A sub question's link_id is not a payload key, so pruning on one would
  // delete a top level answer that happens to share its name.
  const questions = walk(schema.questions)
    .filter((q) => !q.required && !inside.has(q.link_id));
  let out = payload;
  for (;;) {
    const drop = questions.filter((q) => q.link_id in out && !enabled(q, out));
    if (!drop.length) return out;
    out = { ...out };
    for (const q of drop) delete out[q.link_id];
  }
}
