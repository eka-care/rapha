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
import { fieldsFrom, type FieldSpec } from "../../../packages/voice/src/index.ts";
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
  | (Common & { kind: "device"; fields: string[] })
  | (Common & { kind: "spoken-prompt"; says: string; spoken: boolean; fields: string[] });

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
    } else if (d.kind === "spoken-prompt") {
      // A prompt with no sentence and no fields on this form is not a prompt
      // this operation owns: skip it rather than draw an empty box.
      if (!d.says) continue;
      const fields = questions.filter((q) => named.has(q.link_id)).map((q) => q.link_id);
      if (!fields.length) continue;
      out.push({ ...common, kind: "spoken-prompt", says: d.says, spoken: !!d.spoken, fields });
    }
  }
  return out;
}
