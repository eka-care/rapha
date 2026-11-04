/** Which instruments an operation may be captured with, and over which fields.
 *
 *  Every answer here comes from a declaration in bundles/phc/*.inst.*.md,
 *  compiled into catalogue.json. Nothing in this file names a field, an
 *  operation or a bundle: change the declaration and the buttons change.
 *
 *  It is also a second gate. kernel/declarations.py already refuses an
 *  instrument whose readback is not required or whose commit is not a tap,
 *  but the renderer is the thing that would actually put a microphone on
 *  screen, so it re-checks rather than trusting what it was handed.
 */
/** A numeric question a constrained-voice instrument may fill.
 *
 *  This and `fieldsFrom` below came from `packages/voice`, which held a number
 *  grammar that read "one forty" in the browser. The grammar is gone: every
 *  aspect of scribing goes through the medical scribe service, which answers
 *  the form's own questions, so nothing here reads words any more. What was
 *  worth keeping is this -- which questions a spoken reading may touch -- and
 *  it is renderer work, so it lives with the mounts it feeds.
 *
 *  The spoken aliases, the units and the ranges went with the grammar. The
 *  form draws units and ranges from the questionnaire itself and always did;
 *  the aliases stayed behind in `packages/voice/src/spoken.json`, whose
 *  readers are now agent/planner.py and care_phc_mcp/planner. */
export type FieldSpec = {
  linkId: string;
  type: "integer" | "decimal";
};

/** The numeric questions of the questionnaire the operation names. Only
 *  integer and decimal come back: those are the discrete values voice is
 *  allowed near, and the instrument's own `types:` narrows them further. */
export function fieldsFrom(schema: { questions: Question[] }): FieldSpec[] {
  return schema.questions
    .filter((q) => q.type === "integer" || q.type === "decimal")
    .map((q) => ({ linkId: q.link_id, type: q.type as FieldSpec["type"] }));
}
import type { Operation, Question, Questionnaire } from "../types";
import { walk } from "../validate.ts";   // the extension is for node: voice.check.ts runs this file outside vite

/** The grammars this renderer implements. A declaration naming any other one
 *  is not offered, because there is no parser behind it. */
export const IMPLEMENTED_GRAMMARS = ["number"];

type Decl = {
  id: string;
  kind: string;
  title: string;
  summary?: string;
  operations?: string[];
  fields?: string[];
  types?: string[];
  grammar?: string | null;
  readback?: string;
  commit?: string;
  fallback?: string;
  says?: string;
  spoken?: boolean;
  requires?: string | null;
};

type Common = {
  id: string; title: string; summary: string; fallback: string;
  /** The thread flag this instrument may not run without, from the
   *  declaration's own `requires:`. Undefined means no gate. The renderer used
   *  to hard-code the health centre's consent flag here, so a bundle spelling
   *  its own differently got no gate at all. */
  requires?: string;
};

export type Mount =
  | (Common & {
      kind: "constrained-voice";
      fields: FieldSpec[];
      /** link_id to the question's own text, for the readback list. */
      labels: Record<string, string>;
    })
  | (Common & { kind: "scribe"; targets: Question[] })
  | (Common & { kind: "device"; fields: string[] });

export function mountsFor(
  instruments: Record<string, unknown> | undefined,
  op: Operation,
  schema: Questionnaire,
): Mount[] {
  const questions = walk(schema.questions);
  const out: Mount[] = [];

  for (const d of Object.values(instruments ?? {}) as Decl[]) {
    if (!(d.operations ?? []).includes(op.id)) continue;
    if (d.commit !== "tap" || d.readback !== "required") continue;

    const common: Common = {
      id: d.id,
      title: d.title,
      summary: d.summary ?? "",
      fallback: d.fallback ?? "keypad",
      requires: d.requires ?? undefined,
    };
    // An empty fields list in a declaration means "every field this kind can
    // take", not "no fields": the scribe declares none and takes the prose.
    const named = new Set(d.fields ?? []);
    const types = new Set(d.types ?? []);

    if (d.kind === "constrained-voice") {
      if (!IMPLEMENTED_GRAMMARS.includes(String(d.grammar))) continue;
      const fields = fieldsFrom({ questions }).filter(
        (f) =>
          (named.size === 0 || named.has(f.linkId)) &&
          (types.size === 0 || types.has(f.type)),
      );
      if (!fields.length) continue;
      const labels: Record<string, string> = {};
      for (const q of questions) labels[q.link_id] = q.text;
      out.push({ ...common, kind: "constrained-voice", fields, labels });
    } else if (d.kind === "scribe") {
      // Narrative and structured, never a number. A scribe declaration that
      // named a number would be a declaration bug, and the filter here is what
      // stops it reaching a discrete field: no recording goes near one. A
      // structured answer (a diagnosis, a medication) is a list of words and is
      // allowed, and it lands unconfirmed in the form's own row editor like
      // every other drafted value.
      const targets = questions.filter(
        (q) =>
          (q.type === "text" || q.type === "structured") &&
          (named.size === 0 || named.has(q.link_id)),
      );
      if (!targets.length) continue;
      out.push({ ...common, kind: "scribe", targets });
    } else if (d.kind === "device") {
      // Declared, and there is no pairing code on this machine. It is drawn
      // as one honest line rather than left out, so the screen does not imply
      // the declaration is wrong.
      out.push({ ...common, kind: "device", fields: [...named] });
    }
  }
  return out;
}
