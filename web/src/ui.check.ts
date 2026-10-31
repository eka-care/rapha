/** The renderer's own rules, checked without a browser.
 *
 *  Run: node --experimental-strip-types src/ui.check.ts   (from web/)
 *
 *  Three properties, and each one is a bug this branch actually shipped:
 *
 *  1. PORTABILITY. Nothing in web/src may type a station, a flag, a
 *     capability, a bundle id or a declared view's title. The same renderer
 *     draws a health centre's line and a laboratory's bench, and the only
 *     reason that keeps working is that a word on screen comes from a
 *     declaration or does not appear. This is checked against the COMPILED
 *     vocabulary, so it grows automatically when a bundle does -- the
 *     previous spelling was a hand-kept list of one bundle's words.
 *
 *  2. THE MENUS ARE NOT LISTS. `/` is thread.actions, already narrowed by the
 *     guard, and `@` is the declared roles. A literal menu would look right
 *     on the demo and offer refused actions on anything else.
 *
 *  3. ACCESSIBILITY (§68). An icon-only control with no accessible name, a
 *     positive tabIndex, or an animation that ignores prefers-reduced-motion.
 *
 *  THE HONEST LIMIT. This reads .tsx and .css as text under plain node: no
 *  DOM, no cascade, no layout. It cannot prove a contrast ratio that only
 *  exists once the cascade runs, it cannot see a rectangle, and it cannot tell
 *  a handler that runs from one that is attached and inert. Those need the
 *  browser, and the browser is where the flex-shrink bug that clipped every
 *  card was actually found -- not here.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(fileURLToPath(import.meta.url));
const ROOT = join(SRC, "..", "..");
let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };

function walk(dir: string, ext: string[]): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (name === "node_modules") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, ext));
    else if (ext.some((e) => name.endsWith(e))) out.push(p);
  }
  return out;
}
const rel = (p: string) => relative(SRC, p);
/** Prose is not code. A file that explains a rule is not a file breaking it. */
const code = (s: string) =>
  s.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");

const TSX = walk(SRC, [".tsx", ".ts"]).filter((f) => !f.endsWith(".check.ts"));

// -------------------------------------------------------------- 1. portability

const catalogue = JSON.parse(readFileSync(join(ROOT, "catalogue", "catalogue.json"), "utf8"));

/** Every word this bundle owns: its stations, flags, capabilities, role ids,
 *  operation ids and the titles its views declare. Read from the compiled
 *  catalogue, never typed here. */
function vocabulary(): { word: string; kind: string }[] {
  const out: { word: string; kind: string }[] = [];
  const add = (kind: string, words: unknown) => {
    for (const w of (words as string[]) ?? []) {
      if (typeof w === "string" && w.length > 3) out.push({ word: w, kind });
    }
  };
  add("capability", catalogue.capabilities);
  add("flag", catalogue.states);
  add("role", Object.keys(catalogue.bundles ?? {}));
  const stations = new Set<string>();
  for (const wf of Object.values(catalogue.workflows ?? {}) as { steps?: { station: string }[] }[]) {
    for (const step of wf.steps ?? []) stations.add(step.station);
  }
  add("station", [...stations]);
  add("view title", Object.values(catalogue.views ?? {}).map((v) => (v as { title: string }).title));
  // Which fields name a subject and which describe one is a view's own
  // `columns:`. A screen that types one of them has decided what a patient is
  // -- which is how the patient screen came to show age, sex and village at a
  // bundle whose subject might be a specimen.
  for (const v of Object.values(catalogue.views ?? {})) {
    add("view column", (v as { columns?: string[] }).columns);
  }
  return out;
}

/** The renderer's OWN closed vocabularies: the kernel/renderer contract, not
 *  any bundle's words. `presents: handover` and `kind: scribe` are promises a
 *  declaration makes to this renderer, so the renderer has to be able to name
 *  them -- the same way it names "queue" or "summary".
 *
 *  This is an exemption, so it is kept honest two ways. It is small and
 *  written out, and every word in it must be genuinely implemented somewhere
 *  in the renderer: an exemption for a word nothing implements is a hole
 *  somebody widened to get a bundle's word through.
 *
 *  It collides with this bundle by accident today -- "handover" is also a PHC
 *  capability -- which is exactly why the collision is resolved here and
 *  stated, rather than by quietly dropping the word from the check. The cost
 *  is real and worth naming: the renderer could now type "handover" meaning
 *  the capability and this would not catch it. */
const IMPLEMENTED = [
  "event", "artifact", "handover", "task", "comment",          // THREAD_OBJECTS
  "scribe", "device", "constrained-voice", "spoken-prompt",    // INSTRUMENT_KINDS
  "queue", "summary", "dashboard", "tasklist",                 // view kinds
  // loops.SortKey. The list screen's three sorts are the renderer's own, and
  // "name" collides with this bundle's first declared queue column by
  // accident, the same way "handover" collides with a capability. The LABEL on
  // that sort is `decl.columns[0]`, never this word, which is what makes the
  // collision harmless; the cost is that the renderer could now type "name"
  // meaning the column and this would not catch it.
  "recent", "name", "station",
];

{
  const all = TSX.map((f) => readFileSync(f, "utf8")).join("\n");
  const dead = IMPLEMENTED.filter((w) => !new RegExp(`["'\`]${w}["'\`]`).test(all));
  assert.deepEqual(dead, [],
    "an exemption for a word the renderer does not implement is a hole: " + dead.join(", "));
  ok(`vocabulary: all ${IMPLEMENTED.length} exempted words are really implemented`);
}

{
  const vocab = vocabulary().filter((v) => !IMPLEMENTED.includes(v.word));
  assert.ok(vocab.length >= 20, `the vocabulary check has something to check: ${vocab.length}`);
  const offenders: string[] = [];
  for (const file of TSX) {
    // The declarations glob and the types mirror are allowed to name shapes;
    // neither renders. abha/ is the one accepted exception in this renderer:
    // ABHA is a national identifier, not a facility's concept.
    if (/\/(types|declarations)\.ts$/.test(file) || /\/abha\//.test(file)) continue;
    const body = code(readFileSync(file, "utf8"));
    for (const { word, kind } of vocab) {
      // Only a quoted literal counts. A variable that happens to be spelled
      // like a station is not this renderer typing one.
      const quoted = new RegExp(`["'\`]${word.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")}["'\`]`);
      if (quoted.test(body)) offenders.push(`${rel(file)}: ${kind} "${word}"`);
    }
  }
  assert.deepEqual(offenders, [],
    "the renderer types a word only a declaration may put on screen:\n  " + offenders.join("\n  "));
  ok(`portability: no renderer file types any of this bundle's ${vocab.length} declared words`);
}

// ------------------------------------------- 1b. the kernel serves the words

/** A screen may not be a second place where clinical truth lives, and the
 *  longest running breach of that was the forms: `declarations.ts` compiled
 *  questionnaires/*.json and terminology/*.json into the browser bundle with a
 *  Vite glob, so what a form ASKED a clinician was the one thing on a screen
 *  the kernel did not serve, and no facility could change a question without
 *  rebuilding the browser. GET /questionnaires/ and GET /valuesets/{slug}
 *  serve them now. These are the assertions that stop a glob coming back. */
{
  const reading: string[] = [];
  for (const file of TSX) {
    const body = code(readFileSync(file, "utf8"));
    // A glob at all. There is no legitimate one left in this renderer: every
    // declaration arrives over the API, and the one that did not was this.
    if (/import\.meta\.glob/.test(body)) reading.push(`${rel(file)}: import.meta.glob`);
    // Or a FILE under either declaration directory. The route literal
    // "/questionnaires/" in api.ts names the same word and is the opposite of
    // the thing being refused, so what counts is a literal that reaches for a
    // file: one ending .json, or a glob pattern.
    for (const dir of ["questionnaires", "terminology"]) {
      const path = new RegExp(`["'\`][^"'\`]*${dir}/[^"'\`]*(\\.json|\\*)`);
      if (path.test(body)) reading.push(`${rel(file)}: reads a file under ${dir}/`);
    }
  }
  assert.deepEqual(reading, [],
    "a renderer file reads a declaration off disk instead of from the kernel:\n  "
    + reading.join("\n  "));
  ok("live: no renderer file reads a questionnaire or a value set off disk");

  const decl = code(readFileSync(join(SRC, "declarations.ts"), "utf8"));
  assert.match(decl, /source\.questionnaires\(\)/, "the forms come from the route");
  assert.match(decl, /source\.valueset\(slug\)/, "and a bound choice from the value set route");
  const client = code(readFileSync(join(SRC, "api.ts"), "utf8"));
  assert.match(client, /"\/questionnaires\/"/, "api.ts calls GET /questionnaires/");
  assert.match(client, /\/valuesets\//, "api.ts calls GET /valuesets/{slug}");
  // And the app waits for them, rather than drawing a form with no questions
  // in it and filling them in later.
  const app = code(readFileSync(join(SRC, "app", "App.tsx"), "utf8"));
  assert.match(app, /loadDeclarations\(api\)/, "App loads the declarations");
  assert.match(app, /decls\.loading/, "and does not draw a screen until they are there");
  ok("live: the forms and the bound choices are fetched before the first screen draws");
}

// ------------------------------------ 1c. a screen decides nothing the kernel does

/** Three places a screen had taken a decision back off the kernel. Each one
 *  shipped, and each one is a different shape of the same mistake. */
{
  // The role editor. `inert()` decided whether a grant does anything from the
  // workflow alone, so a centre with a plugin off still offered the switch and
  // the guard refused every use of it. Contradiction 25.
  const grants = code(readFileSync(join(SRC, "grants.ts"), "utf8"));
  assert.match(grants, /export function inert\(cap: string, cat: Catalogue, facility: Withheld\)/,
    "inert() is told what the facility withholds; it may not guess");
  assert.match(grants, /export function inertReason\(cap: string, cat: Catalogue, facility: Withheld\)/,
    "and so is the sentence that explains it");
  assert.match(grants, /if \(facility\.withheld\[cap\]\) return true/,
    "a withheld capability is dead, whatever the workflow draws");
  const settings = code(readFileSync(join(SRC, "screens", "Settings.tsx"), "utf8"));
  assert.match(settings, /inert\(cap, cat, facility\)/, "the editor passes it through");
  assert.match(settings, /facility\.withheld\[cap\]/,
    "and refuses a withheld capability even when no operation names it");
  // No default: a facility argument that may be omitted is the old behaviour
  // with a longer signature, and it is the centre that withholds something
  // that would get it wrong.
  assert.ok(!/facility: Withheld = /.test(grants),
    "the withheld map has no default; 'nothing is withheld' must never be assumed");

  // The patient screen. It chose three subject fields to show, which made it a
  // second opinion about what a subject is; messages.header() already reads
  // the queue view's own `columns:`.
  const patient = code(readFileSync(join(SRC, "screens", "Patient.tsx"), "utf8"));
  assert.match(patient, /header\(/, "the patient header is the declared rule, not a field list");
  // The precise property: no screen reads a subject by a field name it typed.
  // Not a count of literals -- the three tabs on this screen are the
  // renderer's own and have nothing to do with a subject -- but any named
  // read of the subject at all. `Object.entries(view.subject)` is fine: it
  // shows whatever the kernel sent, in the kernel's order.
  const named = TSX.filter((f) => /\/screens\//.test(f))
    // `.id` is exempt, and only `.id`: it is the Store protocol's own primary
    // key on every resource (kernel/contracts.py), not a word any bundle
    // chose, and the thread screen needs it to link to the spine.
    .filter((f) => /subject(\.(?!id\b)\w+|\[\s*["'`])/.test(code(readFileSync(f, "utf8"))))
    .map(rel);
  assert.deepEqual(named, [],
    "a screen reads a subject by a field name it typed: " + named.join(", "));

  // A summary section's rows. The renderer led with whichever of six field
  // names it had typed out, so reordering the declaration changed nothing.
  const view = code(readFileSync(join(SRC, "view", "View.tsx"), "utf8"));
  assert.match(view, /describe\(r, section\.fields\)/,
    "a row leads with the field the section declared first");
  assert.match(view, /for \(const k of fields \?\? \[\]\)/,
    "in the declared order, and from no other list");
  ok("live: the role editor, the patient header and a summary row all read the kernel's decision");
}

// ------------------------------------------------------------ 2. the menus

{
  const menu = code(readFileSync(join(SRC, "thread", "Menu.tsx"), "utf8"));
  assert.match(menu, /export function slashItems\(actions: Operation\[\]/,
    "/ is built from the operations handed in, which are thread.actions");
  assert.match(menu, /export function atItems\(roles: string\[\]/,
    "@ is built from the roles handed in, which are the bundle's own");
  // A hard-coded array of menu entries is the failure this exists to catch.
  assert.ok(!/\[\s*["'][^"']{4,}["']\s*,\s*["']/.test(menu),
    "no literal list of menu entries");

  const composer = code(readFileSync(join(SRC, "thread", "Composer.tsx"), "utf8"));
  assert.match(composer, /slashItems\(actions, query\)/, "the / menu reads the actions prop");
  assert.match(composer, /atItems\(roles, query\)/, "the @ menu reads the roles prop");
  // The trigger must not fire mid-word, or an address opens a menu.
  assert.match(composer, /\/\(\^\|\\s\)\(\[\/@\]\)/,
    "a menu opens only at the start of a word");
  assert.ok(!/\.slice\(0,\s*\d+\)/.test(composer),
    "the menu is not silently truncated; it scrolls and filters instead");
  ok("menus: / and @ are sourced from declarations, never written down");

  const encounter = code(readFileSync(join(SRC, "screens", "Encounter.tsx"), "utf8"));
  assert.match(encounter, /weigh\(thread\.actions, thread\.closes\)/,
    "§33's ordering is the declared rule in loops.ts, not a sort in the screen");
  assert.ok(!/\.sort\(/.test(encounter), "the screen does not re-rank the actions");
  assert.match(encounter, /const QUICK = 6;/, "§33 caps the quick action row at six");
  assert.match(encounter, /ranked\.length > QUICK/,
    "and says how many more are behind / rather than dropping them silently");
  ok("quick actions: capped at six, ordered by the declared rule, remainder named");
}

// --------------------------------------------------------- 3. accessibility

{
  const problems: string[] = [];
  for (const file of TSX.filter((f) => f.endsWith(".tsx"))) {
    const body = readFileSync(file, "utf8");
    body.split("\n").forEach((line, i) => {
      if (/tabIndex=\{[1-9]/.test(line)) {
        problems.push(`${rel(file)}:${i + 1}: a positive tabIndex reorders the whole page`);
      }
    });
    // A button whose only child is an <Icon> needs a name of its own.
    for (const m of body.matchAll(/<button\b([^>]*)>\s*(<Icon[^>]*\/>)\s*<\/button>/g)) {
      if (!/aria-label=/.test(m[1])) {
        problems.push(`${rel(file)}: an icon-only button with no aria-label`);
      }
    }
  }
  assert.deepEqual(problems, [], problems.join("\n  "));
  ok("a11y: no positive tabIndex, and every icon-only button has a name");

  // §69: every animation must have a reduced-motion escape. An animation
  // nobody can turn off is a vestibular hazard, not a flourish.
  const css = walk(SRC, [".css"]);
  const animated: string[] = [];
  for (const file of css) {
    const body = readFileSync(file, "utf8");
    const names = [...body.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]);
    if (!names.length) continue;
    const guarded = /prefers-reduced-motion/.test(body)
      || readFileSync(join(SRC, "style", "base.css"), "utf8").includes("prefers-reduced-motion");
    if (!guarded) animated.push(`${rel(file)}: ${names.join(", ")}`);
  }
  assert.deepEqual(animated, [],
    "an animation with no prefers-reduced-motion escape:\n  " + animated.join("\n  "));
  ok("a11y: every animation is reachable by prefers-reduced-motion");

  const base = readFileSync(join(SRC, "style", "base.css"), "utf8");
  assert.match(base, /:focus-visible\s*\{[^}]*outline:/,
    "§68: focus is visible, and not removed anywhere");
  // A file may drop the default outline ONLY if it puts one back for
  // :focus-visible, which is the state that needs it. This used to be a list
  // of filenames, which is an exemption that grows rather than a rule: the
  // prototype's `outline:none` was ported into two new stylesheets and the
  // allowlist would simply have been extended to cover them.
  const removed = css.filter((f) => {
    const body = readFileSync(f, "utf8")
      .split("\n").filter((l) => !/^\s*(\/\*|\*)/.test(l)).join("\n");
    const strips = /outline:\s*(none|0)\b/.test(body.replace(/:focus-visible[^}]*\}/g, ""));
    if (!strips) return false;
    const restores = /:focus-visible[^{]*\{[^}]*outline:\s*(?!none|0)/.test(body);
    return !restores;
  }).map(rel);
  assert.deepEqual(removed, [],
    "a stylesheet drops the focus outline and never puts one back for " +
    ":focus-visible: " + removed.join(", "));
  ok("a11y: focus is visible and no stylesheet takes it away");
}

console.log(`\n${checks} checks passed`);
