/** The keyboard contract for a form-instrument operation.
 *
 *  Run: node --experimental-strip-types src/keys.check.ts   (from web/)
 *
 *  Asserted against the source rather than a rendered DOM, because the thing
 *  that breaks is someone adding a control without a tabIndex, or wiring a
 *  handler that does nothing, not a runtime bug. No mic, no browser, no
 *  server. Where a plain regex would pass on a handler that exists but is
 *  empty, these checks pull out the actual block between the matched braces
 *  and assert on what is inside it, so a handler that is attached but inert
 *  fails here.
 *
 *  What this file CANNOT prove, because it never runs the component:
 *   - that onKeyDown actually fires when a key is pressed in a browser
 *   - that e.preventDefault() truly suppresses the browser's own Enter/Escape
 *     behaviour (e.g. a textarea's newline, or a <select> reacting to Enter)
 *   - that focus lands where autoFocus claims once instruments, the ABHA
 *     journey and conditional renders are all in play at once
 *   - keyboard behaviour of third-party mounts (VoiceCapture, Recorder,
 *     Journey) this file does not read
 *  The manual walk-through (Step 6 of the brief) is what closes that gap.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

/** Slice out the `{ ... }` block that opens at the first `{` at-or-after
 *  `from`, by counting braces. Lets a check inspect what a handler actually
 *  does instead of just noticing its name went by. */
function block(src: string, from: number): string {
  const start = src.indexOf("{", from);
  assert.ok(start >= 0, "no block to extract");
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error("unbalanced braces");
}

const panel = read("src/OperationPanel.tsx");

const onKeyDownAt = panel.indexOf("onKeyDown={");
ok(onKeyDownAt >= 0, "the panel handles keys at all");
const handler = onKeyDownAt >= 0 ? block(panel, onKeyDownAt) : "";

// Escape: handled, and the handler body actually calls the panel's real
// cancel prop (onCancel) rather than merely mentioning the key.
const escapeAt = handler.indexOf('key === "Escape"');
ok(escapeAt >= 0, "Escape is handled");
ok(escapeAt >= 0 && /onCancel/.test(handler.slice(escapeAt, escapeAt + 120)),
  "Escape calls the panel's own cancel handler, not a no-op");

// Enter: handled, gated on the real busy flag, and wired to the real commit
// function (send). A handler that checks e.key and does nothing else would
// fail these because the condition and the call are inspected together, not
// matched independently.
const enterIfMatch = handler.match(/if\s*\(e\.key === "Enter"([^)]*)\)\s*\{([^}]*)\}/);
ok(enterIfMatch, "Enter is handled");
const enterCond = enterIfMatch?.[1] ?? "";
const enterBody = enterIfMatch?.[2] ?? "";
ok(/!busy/.test(enterCond), "Enter is refused while a commit is already in flight");
ok(/send\s*\(/.test(enterBody), "Enter calls the panel's own commit function");

// Enter inside a textarea is a newline, not a commit. Committing a
// consultation note because someone pressed return mid-sentence is the bug
// this exists to stop. The brief's own check (`/textarea/i.test(panel)`)
// would pass even if the textarea guard were computed and never used, so this
// instead finds the variable the tagName check assigns and confirms the
// Enter condition actually negates that same variable.
const textareaGuard = handler.match(/const (\w+)\s*=\s*\(e\.target as HTMLElement\)\??\.tagName\??\.toLowerCase\(\)\s*===\s*"textarea"/);
ok(textareaGuard, "the panel checks the event target's tag name for a textarea");
const guardVar = textareaGuard?.[1];
ok(!!guardVar && new RegExp(`!${guardVar}\\b`).test(enterCond),
  "Enter is not a commit inside a textarea (the Enter condition negates the textarea check)");

const form = read("src/Form.tsx");
ok(!/tabIndex={-1}/.test(form), "no field is removed from the tab order");

// autoFocus: present, and not hardcoded true on every widget (which would
// render once per question and focus-steal onto the last one mounted, not
// the first). It must instead be driven by a value that is computed.
ok(/autoFocus/.test(form), "the first field takes focus without a click");
ok(!/autoFocus=\{true\}/.test(form), "autoFocus is not hardcoded true on every field");

// The "first" slot must be decided after a question is known to actually
// render (past the group/display/disabled-and-unanswered skips), not by the
// question's raw index in the schema array — otherwise a leading group or a
// switched-off question would steal focus from the field a clerk can see.
// Provable from source: the mutable flag that decides "first" must be
// declared outside the per-question render function, and read only after
// that function's own skip checks (its `return null` lines).
const fieldFnAt = form.indexOf("const field = (q: Question) => {");
ok(fieldFnAt >= 0, "there is a single per-question render function to check order against");
const fieldBody = fieldFnAt >= 0 ? block(form, fieldFnAt) : "";
const lastSkipReturn = fieldBody.lastIndexOf("return null;");
const flagDecl = form.slice(0, fieldFnAt).match(/let (\w+) = false;/);
ok(!!flagDecl, "the first-field flag lives outside the per-question function, so it persists across questions");
const flagVar = flagDecl?.[1];
const flagUseAt = flagVar ? fieldBody.indexOf(flagVar) : -1;
ok(flagUseAt >= 0 && lastSkipReturn >= 0 && flagUseAt > lastSkipReturn,
  "the first-field flag is read after the skip checks, so a hidden question cannot claim the focus");

console.log(`ok   ${checks} keyboard checks`);
