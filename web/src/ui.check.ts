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
 *  4. THE QUEUE ROW, which is the front desk's one screen and the one most
 *     likely to be read on a phone at arm's length. Six properties, each of
 *     them a decision the owner took in
 *     docs/reference/front-desk/queue-labels.html and none of them something
 *     a later edit should be able to undo quietly.
 *
 *  THE HONEST LIMIT. This reads .tsx and .css as text under plain node: no
 *  DOM, no cascade, no layout. It cannot prove a contrast ratio that only
 *  exists once the cascade runs, it cannot see a rectangle, and it cannot tell
 *  a handler that runs from one that is attached and inert. Those need the
 *  browser, and the browser is where the flex-shrink bug that clipped every
 *  card was actually found -- not here.
 */
import assert from "node:assert/strict";
import { WROTE } from "./types.ts";
import type { CalendarRow } from "./types.ts";
import { dateOf, dayLabel, dayOn, dayOf, emptyLine, EVERYONE, forRole, inPiles, roleChips, scaleOf, withView, atOf, stack, pageBy, cardHash, owedLine } from "./view/day.ts";
import { span, cells } from "./view/cells.ts";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
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
  // What a capability and a role are CALLED. The same rule as a view's title
  // just below: the bundle chose the word, so a screen may print it and may
  // never type it. Without this, declaring the words would have handed the
  // renderer sixteen new strings it could hard-code and nothing would notice.
  add("capability title", Object.values(catalogue.vocabulary?.capability_titles ?? {}));
  add("role title", Object.values(catalogue.vocabulary?.role_titles ?? {}));
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
    // How a row got into a queue, and what the chip for it is called. Both
    // are a view's own, and both are exactly the kind of word a screen is
    // tempted to type: the mark is a stored value and the label is a word a
    // person reads, so a renderer that spells either one has stopped drawing
    // what the declaration says and started knowing what a poster is.
    const prov = (v as { provenance?: { mark?: string; label?: string } }).provenance;
    if (prov) add("provenance", [prov.mark, prov.label].filter(Boolean) as string[]);
  }
  // What a declared answer is CALLED. A programme's display is the bundle's
  // word for one of its own codes, so a screen may no more type "the
  // antenatal one is called this" than it may name a station. Read off the
  // questionnaires the kernel serves, because catalogue.json compiles an
  // option's VALUE and drops its display.
  for (const file of walk(join(ROOT, "questionnaires"), [".json"])) {
    const form = JSON.parse(readFileSync(file, "utf8"));
    const questions: { answer_option?: { display?: string }[] }[] = [];
    const descend = (list: unknown) => {
      for (const q of (list as { questions?: unknown }[]) ?? []) {
        questions.push(q as { answer_option?: { display?: string }[] });
        descend((q as { questions?: unknown }).questions);
      }
    };
    descend(form.questions);
    for (const q of questions) {
      add("answer display", (q.answer_option ?? []).map((o) => o.display).filter(Boolean) as string[]);
    }
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
  "scribe", "device", "constrained-voice",                     // INSTRUMENT_KINDS
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
    //
    // words.ts is the third, and it is a SPELLING table rather than a
    // vocabulary. Its list decides that "asha" is set ASHA and "ncd" is set
    // NCD -- how the letters are drawn, never which words appear. Delete a
    // role from the bundle and nothing on any screen changes; the entry just
    // stops being reached. The rule this check protects is that the renderer
    // must not DECIDE what is shown, and a casing table decides nothing.
    if (/\/(types|declarations|words)\.ts$/.test(file) || /\/abha\//.test(file)) continue;
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

  // The role editor again, and the other half of the same rule. `inert()` is
  // about whether a switch does anything; this is about what it is CALLED. A
  // capability and a role each declare their own `title:`, and the editor
  // reads it first, before the derivations it used to rely on entirely. Four
  // capabilities had nothing to print but their identifier and two had five
  // screen names joined with a dot, and the fix for both was a declaration.
  assert.match(settings, /cat\.vocabulary\?\.capability_titles\?\.\[cap\]/,
    "a switch is named by the capability's own declared title, first of all");
  assert.match(settings, /cat\.vocabulary\?\.role_titles\?\.\[role\]/,
    "and a role in the picker by the role's own");
  // And the words really are declared, for every one of them, so no row in
  // that panel and no option in that picker falls through to a machine
  // identifier. This reads the compiled catalogue and not the screen: a
  // renderer that prefers a declaration is only half the promise, and the
  // other half is that the declaration is there.
  const titled = catalogue.vocabulary?.capability_titles ?? {};
  const roleWords = catalogue.vocabulary?.role_titles ?? {};
  const nameless = [
    ...((catalogue.vocabulary?.capabilities ?? []) as string[])
      .filter((cap) => !titled[cap]).map((cap) => `capability ${cap}`),
    ...Object.keys((catalogue.vocabulary?.roles ?? {}) as Record<string, string[]>)
      .filter((role) => !roleWords[role]).map((role) => `role ${role}`),
  ];
  assert.deepEqual(nameless, [],
    "this bundle declares no word for: " + nameless.join(", "));
  ok(`roles: the editor reads declared titles, and all ${
    Object.keys(titled).length} capabilities and ${
    Object.keys(roleWords).length} roles have one`);

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

// ------------------------------------------------ her year, in the shared grid

{
  const patient = code(readFileSync(join(SRC, "screens", "Patient.tsx"), "utf8"));
  const arc = code(readFileSync(join(SRC, "thread", "Arc.tsx"), "utf8"));
  // Her grid is the shared one, fed by HER episodes: never a centre-wide read.
  assert.match(patient, /from "\.\.\/view\/Grid"/, "her record draws the shared grid");
  assert.match(patient, /ownRows\(/, "her rows are made from her own episodes");
  assert.ok(!/api\.view\(|\{ from, to \}/.test(patient),
    "her record asked the centre for a range: it must read her own episodes");
  assert.match(patient, /Nothing is booked for her/, "no episodes at all is said in a sentence");
  assert.match(patient, /atOf\(/, "a card's date in the address opens her grid anchored there");
  // `own` (no names on chips) belongs to her page alone.
  const cal = code(readFileSync(join(SRC, "view", "Calendar.tsx"), "utf8"));
  assert.ok(!/\bown\b/.test(cal), "the facility page must never pass `own`: it would strip names from the centre's chips");
  // The month strips are gone; the plain list of visits is not.
  assert.ok(!/arc-scale|arc-months|Months\b/.test(arc), "the month strips are still drawn");
  assert.match(arc, /arc-list/, "the plain list of visits must stay");
  assert.ok(!existsSync(join(SRC, "thread", "arc-scale.ts")) && !existsSync(join(SRC, "thread", "arc-scale.check.ts")),
    "the old month-strip files are back");
  ok("her record: the shared grid from her own episodes, a sentence when empty, the plain list kept");
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
  assert.match(composer, /slashItems\(actions, query, verbs\)/,
    "the / menu reads the actions prop");
  // The screen's own verbs are the one category this layer may name, and they
  // are built in a module of their own so what the menu offers can be checked
  // without a browser. A verb typed into the component instead would be a
  // list nothing tests and nothing can turn off.
  assert.ok(!/label: ["'`]/.test(composer) && !/label: ["'`]/.test(menu),
    "a menu entry is written into the component rather than built in commands.ts");
  const verbs = code(readFileSync(join(SRC, "thread", "commands.ts"), "utf8"));
  for (const forbidden of [/station/i, /capability/i, /\bflag\b/i, /phc\./]) {
    assert.ok(!forbidden.test(verbs.replace(/^import .*$/gm, "")),
      `the screen's own verbs name something declared: ${forbidden}`);
  }
  assert.match(code(readFileSync(join(SRC, "screens", "Encounter.tsx"), "utf8")),
    /record: consented \? /,
    "the microphone is offered on the / menu whether or not it could start, " +
    "which is the one thing that menu has never done");
  assert.match(composer, /atItems\(roles, query\)/, "the @ menu reads the roles prop");
  // The trigger must not fire mid-word, or an address opens a menu.
  assert.match(composer, /\/\(\^\|\\s\)\(\[\/@\]\)/,
    "a menu opens only at the start of a word");
  assert.ok(!/\.slice\(0,\s*\d+\)/.test(composer),
    "the menu is not silently truncated; it scrolls and filters instead");
  ok("menus: / and @ are sourced from declarations, never written down");

  // ------------------------------------- paper this centre did not write
  //
  // The Background tab holds whatever the bundle declared as
  // `presents: artifact`. That word is in catalogue/vocab.THREAD_OBJECTS, a
  // closed list this renderer implements, so naming it is the renderer
  // naming its own vocabulary -- not a bundle's. Everything else about the
  // tab, including which operation fills it and what its questions are
  // called, has to come from the declarations, and these are the lines that
  // make it so rather than leave it to habit.
  const bg = code(readFileSync(join(SRC, "thread", "Background.tsx"), "utf8"));
  const enc = code(readFileSync(join(SRC, "screens", "Encounter.tsx"), "utf8"));
  assert.match(enc, /presents === "artifact"/,
    "the Background tab's contents are picked some way other than by the "
    + "word the atom declares");
  assert.match(enc, /ranked\.filter\(\(op\) => op\.presents === "artifact"\)/,
    "the way to copy paper in is not read off thread.actions, so it is "
    + "offered to somebody the guard would refuse");
  for (const forbidden of [/station/i, /capability/i, /\bflag[^s]/i, /phc\./,
                           /link_id === /, /["'`]body["'`]/, /["'`]source["'`]/]) {
    assert.ok(!forbidden.test(bg.replace(/^import .*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "")),
      `the Background tab names something declared: ${forbidden}`);
  }
  // Long answers are told apart by LENGTH, never by what the bundle called
  // the question: this renderer cannot know a field is a letter, and a
  // facility that renames it must not lose the formatting.
  assert.match(bg, /v\.value\.length > LONG/,
    "a pasted document is recognised by a field name rather than its size");
  ok("background: the tab is filled by the declared `presents` word, and "
     + "names no field, operation or capability of any bundle");

  const encounter = code(readFileSync(join(SRC, "screens", "Encounter.tsx"), "utf8"));
  assert.match(encounter, /weigh\(thread\.actions, thread\.closes\)/,
    "§33's ordering is the declared rule in loops.ts, not a sort in the screen");
  assert.ok(!/\.sort\(/.test(encounter), "the screen does not re-rank the actions");
  // §33 caps the row; it does not set the number, and this used to pin the
  // literal six. Six equal buttons is a menu, and `weigh()` has already said
  // which ONE of them closes this station, so the row draws that one. What
  // the cap is for is that the rest are never dropped in silence, and that
  // is what is asserted: a number, and the remainder named beside it.
  const quick = /const QUICK = (\d+);/.exec(encounter);
  assert.ok(quick && Number(quick[1]) >= 1 && Number(quick[1]) <= 6,
    "§33 caps the quick action row between one and six");
  assert.match(encounter, /ranked\.length > QUICK/,
    "and says how many more are behind / rather than dropping them silently");
  ok("quick actions: %s offered, ordered by the declared rule, remainder named"
     .replace("%s", quick![1]));
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

// ------------------------------------------------------------ 4. the queue row

/** Split a stylesheet into { selector, body } pairs, media queries flattened.
 *  Crude on purpose: it reads text under plain node and knows nothing about
 *  the cascade, so it can only say what a rule WRITES, never what wins. */
function rules(css: string): { selector: string; body: string }[] {
  const flat = decomment(css).replace(/@media[^{]*\{/g, "").replace(/@keyframes[^{]*\{/g, "");
  return [...flat.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .map((m) => ({ selector: m[1].trim(), body: m[2] }));
}
const decomment = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "");

{
  const queueCss = readFileSync(join(SRC, "style", "queue.css"), "utf8");
  const view = code(readFileSync(join(SRC, "view", "View.tsx"), "utf8"));
  const list = code(readFileSync(join(SRC, "screens", "ListScreen.tsx"), "utf8"));
  // THE NARROWING CONTROL MOVED, so these assertions follow it. It was a
  // strip of chips above the list and a second menu in the panel beside it,
  // over the same rows; it is one control now, in the panel, built in
  // loops.narrowings and drawn by Sidebar.tsx. The list screen obeys it.
  const sideCss = readFileSync(join(SRC, "style", "shell.css"), "utf8");
  const side = code(readFileSync(join(SRC, "app", "Sidebar.tsx"), "utf8"));
  const loops = code(readFileSync(join(SRC, "loops.ts"), "utf8"));
  const sdk = code(readFileSync(join(SRC, "abha", "sdk.ts"), "utf8"));
  const lotus = readFileSync(join(SRC, "abha", "Lotus.tsx"), "utf8");

  // -- the lotus ------------------------------------------------------------
  //
  // ABHA is the one concept this renderer may name without a declaration, and
  // abha/sdk.ts records why. The word itself therefore lives there and
  // nowhere else: the row asks whether the kernel sent that flag, it does not
  // spell it. If a bundle ever renames the state the lotus would simply stop
  // appearing, which is why the state is checked against the compiled
  // workflows rather than taken on trust.
  assert.match(sdk, /export const ABHA_LINKED = "abha\.linked";/,
    "the declared state the lotus reads is named once, in the exempt file");
  assert.match(view, /\(r\.flags \?\? \[\]\)\.includes\(ABHA_LINKED\)/,
    "the lotus is drawn from the flags the kernel sent, not from a subject field");
  const declaresLinked = Object.values(catalogue.workflows ?? {})
    .some((wf) => Object.keys((wf as { states?: object }).states ?? {})
      .includes("abha.linked"));
  assert.ok(declaresLinked,
    "no workflow declares the state the lotus reads, so the lotus can never draw");
  assert.match(lotus, /role="img"/, "the lotus is a graphic, and says so");
  assert.match(lotus, /aria-label="[^"]{8,}"/, "§68: the lotus carries an accessible name");
  assert.match(lotus, /<title>[^<]{8,}<\/title>/, "and a title, for a tooltip and for older readers");
  // The emblem is the one mark that does not take the interface's ink: a
  // national lotus drawn in the accent is a different lotus. So the rule is
  // not currentColor any more, it is that every colour on it still comes
  // from a token, which is what keeps style/tokens.css the only file in
  // web/src that names a colour.
  const fills = [...lotus.matchAll(/(?:fill|stroke)="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(fills.length >= 6, "the lotus lost its artwork: " + fills.length + " fills");
  const typed = fills.filter((f) => !/^var\(--[a-z-]+\)$/.test(f));
  assert.deepEqual(typed, [],
    "a colour on the lotus is typed into the component rather than taken "
    + "from a token: " + typed.join(", "));
  ok("queue: the lotus reads a declared state, is named, and takes its colour from a token");

  // -- colour means clinical risk, and nothing else -------------------------
  //
  // The anti-goal in the spec is "colour that does not mean anything". A
  // programme is not a risk and a station is not a risk, so exactly one tone
  // may be red. Which tone that is, is written once in loops.ts, and the
  // stylesheet may not paint the critical ink on anything that is not it.
  assert.match(loops, /export const RISK_TONE = "crit";/, "one tone means clinical risk");
  assert.match(view, /row\.badges\[f\] === RISK_TONE/, "a row's label asks the declared tone");
  assert.match(loops, /decl\?\.badges\?\.\[flag\] === RISK_TONE/,
    "and so does the narrowing the control offers for it");
  const coloured = [...rules(queueCss), ...rules(sideCss)]
    .filter((r) => /--color-critical/.test(r.body))
    .filter((r) => !/\brisk\b/.test(r.selector))
    .map((r) => r.selector);
  assert.deepEqual(coloured, [],
    "the queue or the panel beside it paints clinical red on something that "
    + "is not the risk tone: " + coloured.join(", "));
  // The stylesheet half of that rule is only half. `risk` is a class, and a
  // row can hand it to anything: painting the PROGRAMME pill red passes every
  // assertion above, because the only rule that mentions the critical ink is
  // still `.qr-pg.risk` and the pill is now wearing it. That mutation was run
  // against this repository and nothing moved.
  //
  // So: no className on this screen may contain the word outright. The one
  // legitimate use is a conditional on the DECLARED tone, and stripping the
  // interpolations leaves it with nothing to find.
  const sprayed = [...view.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)]
    .map((m) => (m[1] ?? m[2]).replace(/\$\{[^}]*\}/g, ""))
    .filter((c) => /\brisk\b/.test(c));
  assert.deepEqual(sprayed, [],
    "something on a queue row is given the risk class outright rather than " +
    "from the tone the view declared, so red has stopped meaning one thing: "
    + sprayed.join(", "));
  ok("queue: only the declared risk tone carries colour; every other label is ink");

  // -- a guess never looks like a decision ---------------------------------
  //
  // The workflow says how each of its states is decided. `{stored: true}` is
  // somebody's tick; everything else the kernel worked out of the records.
  // Dashed is the second kind. This is the property most easily lost, because
  // dropping it makes the screen look tidier, not broken.
  assert.match(loops, /"stored" in how/, "derived means: the workflow did not say somebody stored it");
  assert.match(view, /der: derived\.has\(f\)/, "and a row's label asks that, per flag");
  const dashed = rules(queueCss).filter((r) => /\bder\b/.test(r.selector));
  assert.ok(dashed.some((r) => /border-style:\s*dashed/.test(r.body)),
    "a derived label is drawn dashed");
  assert.ok(rules(queueCss).some((r) => /\.qr-pg\.risk/.test(r.selector)
    && /border-style:\s*solid/.test(r.body)),
    "and risk puts the solid edge back, so a dashed red pill is impossible");
  ok("queue: a label the kernel worked out is dashed, a person's decision is not");

  // -- a phone -------------------------------------------------------------
  //
  // Most stations will not have a laptop. Three things follow, and all three
  // were wrong before this slice: nine chips wrapped into a four-line block
  // that pushed the queue off a 375px screen, a chip was 30px tall against
  // the 44px target, and the row was a 268px card so a phone got one.
  const base = (selector: string) =>
    rules(queueCss).find((r) => r.selector === selector)?.body ?? "";
  // The strip of chips is gone, and with it the four-line block that pushed
  // the queue off a 375px screen: every narrowing is one menu now, and what
  // a menu owes a phone is that it scrolls rather than running off the
  // bottom of the screen with its last options unreachable.
  const sideBase = (selector: string) =>
    rules(sideCss).find((r) => r.selector === selector)?.body ?? "";
  const menu = sideBase(".sb-filter-menu");
  assert.match(menu, /max-height:\s*\d+px/, "the narrowing menu has no ceiling, so a day with "
    + "four programmes and three flags runs off the bottom of a phone");
  assert.match(menu, /overflow-y:\s*auto/, "and what is past that ceiling cannot be reached");
  const dead = [...rules(queueCss), ...rules(sideCss)]
    .filter((r) => /\.qtab/.test(r.selector)).map((r) => r.selector);
  assert.deepEqual(dead, [],
    "the chip strip's stylesheet is still here after the control moved, so a "
    + "second filter bar is one className away: " + dead.join(", "));
  assert.ok(!/qtab/.test(list) && !/qtab/.test(side),
    "a screen still draws the chip strip the narrowing control replaced");
  for (const [selector, floor] of [[".qr", 44]] as const) {
    const px = /min-height:\s*(\d+)px/.exec(base(selector));
    assert.ok(px, `${selector} declares no min-height, so its tap target is whatever text it holds`);
    assert.ok(Number(px![1]) >= floor,
      `${selector} is ${px![1]}px tall; a tap target is at least ${floor}px`);
  }
  // The ground a row paints under its own quietest ink. --color-bg-hover,
  // which this rule used first, runs 4.47:1 under --color-text-tertiary:
  // under AA, and nothing on screen says so. style.check.ts clears
  // --color-bg-subtle for all three inks, so that is the one the row may use.
  assert.match(base(".qr:hover"), /background:\s*var\(--color-bg-subtle\)/,
    "the row's hover ground must be one the contrast table has cleared for tertiary text");
  // Nothing on this row may be hover-only. A phone has no hover, so a count
  // or a label behind one is simply absent.
  const hoverOnly = rules(queueCss)
    .filter((r) => /:hover/.test(r.selector))
    .filter((r) => /(^|;)\s*(display|visibility|opacity|content)\s*:/.test(r.body))
    .map((r) => r.selector);
  assert.deepEqual(hoverOnly, [],
    "a queue rule reveals or hides something on hover, which a phone cannot do: "
    + hoverOnly.join(", "));
  // And the three things that may never be dropped at any width.
  const hidden = rules(queueCss)
    .filter((r) => /\.qr-tk|\.qr-nm|\.qr-pg\.risk/.test(r.selector))
    .filter((r) => /display:\s*none|visibility:\s*hidden/.test(r.body))
    .map((r) => r.selector);
  assert.deepEqual(hidden, [],
    "the number, the name or the risk label is hidden at some width: " + hidden.join(", "));
  // The table runs the full width of the page on purpose: its columns carry the
  // measure, so a name and its own labels stay in one row without a width cap.
  assert.ok(!/\.qlist\s*\{[^}]*max-width:\s*\d+px/.test(queueCss),
    ".qlist is capped at a pixel width again, so the table stops short of the page");
  // Every target in the narrowing menu is a tap target too, and these are
  // in the OTHER stylesheet, so they are measured against the same floor.
  for (const selector of [".sb-filter-go", ".sb-filter-item", ".sb-filter-x"]) {
    const px = /min-height:\s*(\d+)px/.exec(sideBase(selector));
    assert.ok(px, `${selector} declares no min-height, so its tap target is whatever text it holds`);
    assert.ok(Number(px![1]) >= 44,
      `${selector} is ${px![1]}px tall; a tap target is at least 44px`);
  }
  ok("queue: the narrowing menu scrolls instead of overflowing a phone, every "
     + "target is 44px, nothing hides on hover, and the row keeps a measure");

  // -- the programme ------------------------------------------------------
  //
  // The mockup draws the patient's programme as a monochrome pill and gives
  // it a filter chip. Which column that is, is the VIEW's own answer: it
  // declares `labels:` beside `columns:`, and the renderer draws exactly
  // those and asks nothing.
  //
  // This was briefly inferred instead, from whether the question collecting
  // the answer was an optional closed choice. It picked the right column in
  // this bundle and would have picked a second one the moment another was
  // declared. The guess is gone and so is the check that exercised it: a
  // check for a rule nothing uses reads like cover.
  assert.match(loops, /\(decl\?\.labels \?\? \[\]\)\.filter\(\(label\) => columns\.includes\(label\)\)/,
    "the labels are the view's own, intersected with the columns it carries, " +
    "and not worked out from anything");
  assert.ok(!/required|answer_option|answer_value_set/.test(loops),
    "loops.ts is still asking a questionnaire what a column means; the view says it now");
  assert.match(view, /labelColumns\(decl\)/,
    "the row asks the view, rather than deciding for itself which column is a label");
  assert.match(loops, /filterOptions\(decl, rows, labelColumns\(decl\)\)/,
    "the narrowings are built without asking the view which columns are labels");
  assert.match(side, /narrowings\(/,
    "the panel beside the line draws its own idea of what can be narrowed by, "
    + "rather than the one list every surface reads");

  // The declaration this bundle actually ships has to survive the trip: a
  // label naming a column the view does not carry is refused by the
  // declaration lint, so what reaches a screen is a real subset.
  const queueDecl = (catalogue.views ?? {})["phc.view.station-queue"] as
    { columns?: string[]; labels?: string[] };
  assert.ok((queueDecl?.labels ?? []).length > 0,
    "this bundle's queue declares no labels at all, so the programme the view " +
    "was changed to carry never reaches a screen");
  const stray = (queueDecl.labels ?? []).filter((l) => !(queueDecl.columns ?? []).includes(l));
  assert.deepEqual(stray, [],
    "a declared label names a column this view does not carry, so the row " +
    "would draw a pill off a field no row has: " + stray.join(", "));

  // A word must not appear on the row twice: once as a pill and again in the
  // line underneath. That is the bug the detail line had the moment the sixth
  // column landed.
  assert.match(view, /!labelCols\.includes\(k\)/,
    "a label column is kept out of the detail line, or the row says the same word twice");

  // And the pill carries no colour. Red means a clinician should look sooner;
  // a programme is not a risk.
  // In the menu, a programme and a station are rows under their own heading
  // and nothing paints them: only the row the view's own badge calls risk
  // may carry a tone, which the `coloured` assertion above already holds for
  // both stylesheets. What is checked here is that the headings exist, so a
  // station, a programme and a flag are not one undifferentiated run.
  assert.match(side, /\{g\.title\}/, "the narrowing menu draws no headings, so where "
    + "somebody is standing, what programme they are on and what is wrong with "
    + "them are one list of fifteen rows");
  assert.match(loops, /title: "Where they are"/, "the groups are not named in one place");
  assert.ok(rules(sideCss).some((r) => r.selector === ".sb-filter-h"),
    ".sb-filter-h is unstyled, so a heading is indistinguishable from an option");
  ok("queue: the pills are the columns the view declared as labels, monochrome, once per row");

  // -- the counts ----------------------------------------------------------
  //
  // "Counts always visible, computed from the rows actually loaded." Both
  // halves: the number is rendered unconditionally, and it is counted off the
  // rows in hand rather than read from the groups the kernel happened to send
  // for a different grouping.
  assert.match(side, /<span className="sb-filter-c">\{i\.n\}<\/span>/,
    "the count is rendered, never conditional on a state or a hover");
  assert.match(loops, /n: rows\.filter\(\(r\) => r\.flags\.includes\(flag\)\)\.length/,
    "a flag narrowing counts the rows actually loaded");
  assert.match(loops, /n: rows\.filter\(\(r\) => r\.station === station\)\.length/,
    "and so does a station narrowing");
  assert.match(loops, /n: rows\.filter\(\(r\) => String\(r\.subject\?\.\[column\] \?\? ""\) === value\)\.length/,
    "and so does a programme narrowing, off the rows in hand and not off a kernel grouping");
  assert.ok(!/result\.groups/.test(loops),
    "the narrowings read the kernel's groups, which are one grouping and not these");
  // ONE LIST, ONE SET OF CONTROLS. The Lines table is the whole list: it owns its
  // tabs, search, filter menu and column sorts, and the shell draws no second
  // panel of the same names beside it. The panel remains only on a visit.
  assert.ok(!/filter: Filter;/.test(list),
    "the list screen is being handed a narrowing by the shell again, which "
    + "is how a second control over the same question comes back");
  assert.match(side, /if \(route\.startsWith\("views\/"\)\) return null;/,
    "a queue view draws a second panel beside its own list");
  assert.match(list, /narrowings\(/,
    "the list builds its filter menu from the one list of narrowings");
  assert.match(list, /!\(i\.filter && "station" in i\.filter\)/,
    "the stations are offered both as tabs and in the menu");
  // A list that is showing part of the day says so on the list: the tab that is
  // on, the filter button naming what it is filtered by, and a way to clear it.
  assert.match(list, /chosen \? chosen\.label : "Filters"/,
    "a filtered list does not name its filter on the button");
  assert.match(list, /onClick=\{\(\) => set\(\{ q: "", extra: null, tab: ALL \}\)\}/,
    "a narrowed list has no way to clear it");
  ok("queue: one list with its own controls, every option counted off the rows in hand, "
     + "and a narrowed list says so");

  // -- and the screen is actually asking -----------------------------------
  //
  // loops.carriedInto is run against its own cases elsewhere. A correct rule
  // nothing calls is the same bug one indirection further away, so: the
  // encounter has to KEEP what a commit handed up, and every way of opening a
  // panel has to go through the rule. Two call sites, and a second one added
  // later without the seed would silently cost a patient an OTP again.
  const enc = code(readFileSync(join(SRC, "screens", "Encounter.tsx"), "utf8"));
  assert.match(enc, /onDone=\{\(got\) => \{\s*if \(got && !form\.amending\) setCarried\(\{ thread: thread\.id, payload: got \}\)/,
    "the encounter drops what the panel handed up, so the identifier a journey " +
    "produced is lost and the next panel asks for a second one time password");
  assert.match(enc, /carriedInto\(carried, thread\.id, walk\(questionnaire\(op\.input\)\?\.questions \?\? \[\]\)\)/,
    "the encounter decides for itself what to carry instead of asking the rule");
  // `op[,}]` was the first spelling of this and it counted NOTHING in the one
  // case that matters: `setModal({ op })` puts a space between the name and
  // the brace, so the unseeded call the check exists to find was the one
  // shape it could not see, and the mutation that removed a seed passed. Any
  // word boundary after `op` now, and the two counts are compared rather than
  // either being trusted alone.
  // `setModal` was the name while the form covered the screen. It opens in
  // place now, under the line that asked for it, and the state it sets is
  // `form` -- but the rule this counts is unchanged and has to stay
  // countable: a NEW form is seeded, and only a correction is not, because a
  // correction arrives holding the answers it is correcting -- and neither is
  // a PROPOSAL under review, which arrives holding the agent's.
  const opens = [...enc.matchAll(/setForm\(\{\s*op\b/g)].length;
  const seeded = [...enc.matchAll(/setForm\(\{ op, seed: carry\(op\) \}\)|setForm\(\{ op, start: [^}]*amending: true \}\)|setForm\(\{ op: operationFor\([^}]*proposal: m\.proposal \}\)/g)].length;
  // ONE CALL SITE SINCE 2026-11-02, the stronger version of the same rule:
  // `openPanel` is now the only thing that opens one, so a screen added
  // later cannot forget the seed without deleting the helper. The two counts
  // are still compared, because a pattern that silently finds nothing passes
  // every assertion under it.
  assert.ok(opens >= 1,
    `this check found ${opens} ways to open a panel and there is at least one; ` +
    "it is matching the wrong shape and would pass whatever the screen did");
  assert.equal(seeded, opens,
    `${opens - seeded} of ${opens} ways to open a panel do not carry what an ` +
    "earlier commit learned, so which one costs an extra one time password " +
    "depends on which button was pressed");
  ok("thread: what a commit learned reaches the next panel that asks for it, by every route");
}


// ----------------------------------------- 5. the structure of a page (§68)
//
// Four defects found in the running DOM, each of them a WCAG 2.2 failure and
// each of them invisible to every check that existed:
//
//   no <main> on any screen (SC 1.3.1, 2.4.1), no h1 outside the home screen
//   so the outline began at the role editor's h3 (SC 1.3.1), no live region
//   anywhere at all (SC 4.1.3), and one document title for every screen
//   (SC 2.4.2).
//
// These are checked as PROPERTIES of the files rather than as a list of
// strings, because the four of them are each one line and each one line is
// exactly the kind of thing a later edit removes without noticing.

{
  const app = code(readFileSync(join(SRC, "app", "App.tsx"), "utf8"));
  const topbar = code(readFileSync(join(SRC, "app", "Topbar.tsx"), "utf8"));
  const parts = code(readFileSync(join(SRC, "parts.tsx"), "utf8"));

  // -- the landmark and the way past the rail -------------------------------
  assert.match(app, /<main id="workspace"[^>]*className=/,
    "SC 1.3.1: the workspace is not a <main>, so there is no landmark to jump to");
  assert.match(app, /<\/main>/, "the main landmark is never closed");
  assert.match(app, /document\.getElementById\("workspace"\)\?\.focus\(\)/,
    "SC 2.4.1: nothing moves the keyboard past the rail, which repeats on every screen");
  // An anchor would be read by the router as a route: this app's address bar
  // IS its navigation, so #workspace would navigate instead of skipping.
  assert.ok(!/className="skiplink"[^>]*href=/.test(app),
    "the skip control is an anchor, and its fragment is a route in this app");
  ok("a11y: the workspace is a landmark, and the keyboard can reach it past the rail");

  // -- one h1, and it says which screen this is -----------------------------
  assert.match(topbar, /<h1 className="tb-title"/,
    "SC 1.3.1: the screen's name is not the page's heading, so there is no h1");
  const h1s = TSX.filter((f) => f.endsWith(".tsx"))
    .filter((f) => /<h1\b/.test(code(readFileSync(f, "utf8"))))
    .map(rel);
  // THREE FILES, NEVER ONE PAGE. The sign-in screen is what App renders
  // INSTEAD of the shell when there is no Eka session -- it returns before
  // the rail, the top bar and the workspace exist -- so it cannot meet
  // either of the others. The visit screen names the patient, and the top
  // bar names the screen; a visit draws no top bar, so those two cannot
  // meet either. Both exclusions are asserted below rather than trusted.
  // The list is exact so a FOURTH cannot arrive quietly.
  assert.deepEqual(h1s, ["app/Topbar.tsx", "auth/SignIn.tsx", "screens/Encounter.tsx"],
    "the page has more than one top-level heading, or none: " + h1s.join(", "));
  const appSrc = code(readFileSync(join(SRC, "app", "App.tsx"), "utf8"));
  // The visit's heading and the shell's cannot both be on screen. The bar IS
  // drawn inside a visit now, as a breadcrumb (Lines > the patient), and in
  // that form it carries no heading: the patient's name stays the page's one
  // h1. Without this, a bar that kept its title on a visit gives every visit
  // two h1s and nothing says so -- which is why the list above is exact.
  assert.match(appSrc, /<Topbar[\s\S]{0,200}?crumb=\{crumb\}/,
    "the bar is drawn on a visit without the breadcrumb that replaces its title");
  const topbarSrc = code(readFileSync(join(SRC, "app", "Topbar.tsx"), "utf8"));
  assert.match(topbarSrc, /crumb \? \([\s\S]*?<nav[\s\S]*?\) : \([\s\S]*?<h1/,
    "with a breadcrumb the bar must not also draw its page title as a heading");
  assert.ok(!/<Topbar[\s\S]{0,600}?onAssist=\{route\.kind === "thread"/.test(appSrc),
    "the bar still tests for a visit inside itself, which means it is still "
    + "drawn there");
  // And the one control that bar carried into a visit has somewhere to be.
  //
  // IT IS `@rapha` NOW, not a button. This asserted `onAsk && (`, a control
  // the composer drew to open the question box; the thing that replaced it
  // is typing the assistant's name at the start of a line, which the
  // composer routes through `onAskRapha` instead of saying it to the
  // thread. The property the rule protects is unchanged and is not about
  // either name: the top bar is not drawn inside a visit, so if the
  // composer cannot reach the assistant then inside a visit nothing can.
  //
  // Checked in two places rather than one, because the old check watched a
  // prop that could exist while being wired to nothing. The composer must
  // send to the assistant on that path, and the shell must connect that
  // prop to the thing that opens it.
  const composer = code(readFileSync(join(SRC, "thread", "Composer.tsx"), "utf8"));
  assert.match(composer, /onAskRapha!?\(/,
    "the composer no longer reaches the assistant, so inside a visit -- "
    + "where the top bar is not drawn -- there is no way left to ask");
  assert.match(appSrc, /onAskRapha=\{/,
    "the shell does not wire the composer's question to anything, so the "
    + "composer can ask and nothing opens");
  assert.match(appSrc, /if \(session !== true\) \{[\s\S]{0,400}?<SignIn/,
    "the sign-in screen must REPLACE the shell, not sit inside it: two h1s "
    + "on one page is what this allows and it is only safe because it returns");
  ok("a11y: every screen has exactly one h1, and the sign-in screen replaces "
     + "the shell rather than joining it");

  // -- a nav row this seat may not open is absent, not broken ---------------
  //
  // The kernel refuses a view whose declared capability the caller does not
  // hold. So offering every declared view in the rail gives a front desk
  // clerk a row for this centre's numbers that answers 403 when pressed. The
  // rail must compare the two facts /facility already sent it.
  assert.match(appSrc, /!v\.capability \|\| held\.has\(v\.capability\)/,
    "the rail offers every declared view, including ones the caller's role "
    + "cannot open: that row answers 403 and reads as a broken product");
  assert.match(appSrc, /facility\.data\?\.user\.capabilities/,
    "the held set is built from something other than the caller's own "
    + "capabilities, so the comparison is against a list this file invented");
  // And it compares, rather than naming. A capability id typed into the
  // renderer is the rule ui.check exists to hold, and the whole point of
  // this filter is that a bundle may move a view behind another capability
  // with no edit to any screen.
  const frontdesk = (catalogue.bundles?.frontdesk ?? []) as string[];
  assert.ok(frontdesk.length > 0, "the bundle declares no front desk role");
  for (const cap of frontdesk) {
    assert.ok(!appSrc.includes(`"${cap}"`),
      `App.tsx names the capability ${cap}, which the renderer may never do`);
  }
  ok("nav: a view the caller's role cannot open is absent from the rail, and "
     + "the rail names no capability to work that out");

  // -- a place you stand, versus a thing that wants you ---------------------
  //
  // The declared tasklist had a nav row of its own, carrying a count that
  // barely moved across a shift. Nobody navigates to "things that need me",
  // so it is the bell in the top right now. Both halves are asserted: it is
  // out of the rail, and it is in the bell, off the view's own declared
  // kind rather than off an id this renderer may not know.
  const rail = code(readFileSync(join(SRC, "app", "Rail.tsx"), "utf8"));
  assert.match(rail, /views\.filter\(\(v\) => v\.kind !== "tasklist"\)/,
    "a tasklist is still offered as a place in the rail, beside the line and "
    + "the register, which is not what it is");
  assert.match(appSrc, /l\.decl\.kind === "tasklist"/,
    "nothing feeds the bell, so what the tasklist declares reaches no screen");
  const bellSrc = code(readFileSync(join(SRC, "app", "Bell.tsx"), "utf8"));
  // The row's sentence and the button's word are both declarations'. A task
  // title typed here would be this bundle's laboratory in the renderer.
  assert.match(bellSrc, /op\.short \?\? op\.title/,
    "the quick action's word is not the operation's own, so the bell names "
    + "an action this renderer decided to call something");
  assert.match(bellSrc, /rows\.reduce\(\(n, r\) => n \+ r\.count, 0\)/,
    "the badge counts rows rather than things waiting, so two people waiting "
    + "on one kind of result reads as one");
  for (const forbidden of [/phc\./, /\blab\b/i, /station/i, /capability/i]) {
    assert.ok(!forbidden.test(bellSrc.replace(/^import .*$/gm, "")),
      `Bell.tsx names ${forbidden}, which belongs to the bundle and not to a screen`);
  }
  // Closed by Escape and by clicking away, not only by the button that
  // opened it: a corner panel with one way out gets navigated away from.
  assert.match(bellSrc, /e\.key === "Escape"/, "the bell panel cannot be dismissed by keyboard");
  assert.match(bellSrc, /wrap\.current\?\.contains/, "the bell panel does not close when you click away");
  // And the register's glyph stopped arguing with its own label.
  assert.ok(!/icon: "folder"/.test(rail),
    "the patient register still wears a folder, over a screen that lists people");
  ok("nav: a tasklist is the bell and not a place, its words are the "
     + "declaration's, and the register is not a folder");

  // -- two columns of one screen start at the same height -------------------
  //
  // The panel beside a visit carried its own "Hide" pill, in a row of its
  // own above its first card. That row pushed every card in that column 56px
  // below the card it sat beside: two columns of one screen, starting at
  // different heights, which is what the owner reported. A control that
  // opens and closes a column does not belong inside the column.
  const tabsSrc = code(readFileSync(join(SRC, "thread", "Tabs.tsx"), "utf8"));
  const encSrc = code(readFileSync(join(SRC, "screens", "Encounter.tsx"), "utf8"));
  assert.match(tabsSrc, /trailing\?: React\.ReactNode/,
    "the tab row cannot carry the panel's switch, so that switch is back "
    + "inside the column it controls");
  assert.match(encSrc, /className=\{`vtabs-fold/,
    "the panel's switch is not in the visit's tab row");
  assert.ok(!/rail-top|rail-fold/.test(encSrc),
    "the panel still draws its own fold row above its first card, which is "
    + "what pushed that column below the one beside it");
  const chatCss = readFileSync(join(SRC, "style", "chat.css"), "utf8");
  const partsCss = readFileSync(join(SRC, "style", "parts.css"), "utf8");
  const orphan = [...rules(chatCss), ...rules(partsCss)]
    .filter((r) => /\.rail-top|\.rail-fold|\.rail-open/.test(r.selector))
    .map((r) => r.selector);
  assert.deepEqual(orphan, [],
    "the old fold row's stylesheet outlived the row: " + orphan.join(", "));
  // The grid is what actually holds the alignment, so it is asserted too: a
  // column that starts its children at `start` keeps both tops level.
  assert.match(chatCss, /\.chatgrid \{[^}]*align-items:\s*start/,
    "the visit's two columns no longer start at the same height");
  ok("visit: the panel's switch is in the row that spans the screen, and "
     + "both columns start level");

  // -- the second panel is the person's own width ---------------------------
  //
  // A centre working off the line all day wants that column wide; one
  // reading long notes wants it out of the way. The rule and its limits are
  // pure and checked in app/width.check.ts; what is checked here is that the
  // screen actually goes through them, and that the divider is reachable
  // without a mouse.
  const grip = code(readFileSync(join(SRC, "app", "Grip.tsx"), "utf8"));
  const shellCssSrc = readFileSync(join(SRC, "style", "shell.css"), "utf8");
  assert.match(grip, /role="separator"/,
    "the divider is a div with a drag handler, so a keyboard cannot reach it");
  assert.match(grip, /aria-valuenow=\{width\}/,
    "the divider announces no width, so its position is a fact only a "
    + "sighted person has");
  assert.match(grip, /setPointerCapture/,
    "the drag is not captured, so moving faster than a re-render drops it "
    + "halfway and the column stops under the cursor");
  assert.match(grip, /nudge\(width, e\.key\)/,
    "the divider's keyboard behaviour is written in the component rather "
    + "than in the rule that is checked");
  assert.match(appSrc, /clampWidth\(px\)/,
    "the shell sets the width without the clamp, so a drag can produce a "
    + "column too narrow to grab again -- and that width is what gets saved");
  assert.match(shellCssSrc, /width: var\(--panel-w/,
    "the column's width is still fixed in the stylesheet, so nothing a "
    + "person drags can change it");
  ok("shell: the second panel's width is the person's, clamped to a column "
     + "that can still be grabbed, and the divider works without a mouse");

  // -- no form without a microphone ----------------------------------------
  //
  // THE RULE, in the owner's words: Rapha is a scribe-first platform and no
  // form can exist without scribe. A form that can only be typed into is the
  // product admitting its own claim is decoration. So dictation is mounted
  // on the one component every form in this product goes through, and this
  // asserts that it is still mounted there -- a screen that forgot would be
  // a screen you have to type into, with nothing on it to say so.
  const panel = code(readFileSync(join(SRC, "form", "Panel.tsx"), "utf8"));
  assert.match(panel, /useDictation\(\{ thread, operation: op\.id/,
    "the form panel no longer mounts dictation, so there are forms in this "
    + "product that can only be typed into");
  assert.match(panel, /<DictateBar/,
    "dictation runs with nothing on screen to say the microphone is open");
  assert.match(panel, /dictation\.supported && \(/,
    "the shortcut is advertised on a browser that cannot record, so the key "
    + "is offered to somebody for whom it does nothing");
  // The key is read, never spelled. A shortcut typed into a component is a
  // shortcut that cannot be changed, and there is no rupee key on a plain
  // US or UK keyboard -- which would be the whole feature gone, silently.
  const dict = code(readFileSync(join(SRC, "scribe", "dictate.ts"), "utf8"));
  const bar = code(readFileSync(join(SRC, "scribe", "DictateBar.tsx"), "utf8"));
  const hook = code(readFileSync(join(SRC, "scribe", "useDictation.ts"), "utf8"));
  for (const [file, src] of [["Panel.tsx", panel], ["DictateBar.tsx", bar],
                             ["useDictation.ts", hook]] as const) {
    assert.ok(!src.includes("\u20B9"),
      `${file} spells the dictation key, so a person whose keyboard has no `
      + "rupee sign cannot reach dictation at all");
  }
  assert.match(dict, /export const DEFAULT_KEY = "\u20B9";/,
    "the default key is declared somewhere other than the one file that owns it");
  assert.match(hook, /dictateKey\(\)/, "the hook does not read the configured key");
  // Where the words go is decided at keydown, not when they come back. A
  // person may have clicked elsewhere while speaking, and a sentence about
  // a patient's chest in whatever field they moved to is worse than none.
  assert.match(hook, /const target = isTarget\(document\.activeElement\)/,
    "the target is read when the transcript arrives rather than when the "
    + "person started speaking, so the words can land in the wrong field");
  // Assigning .value on a controlled input leaves React unaware, and the
  // next render puts the old value back -- the words appear and vanish a
  // frame later. Verified in the browser; held here.
  assert.match(hook, /getOwnPropertyDescriptor\(proto, "value"\)\?\.set/,
    "the dictated words are written straight onto .value, which React "
    + "overwrites on its next render");
  assert.match(hook, /new Event\("input", \{ bubbles: true \}\)/,
    "nothing tells React the field changed, so the form's own state never "
    + "learns what was said");
  ok("forms: every form mounts dictation, the key is a setting rather than "
     + "a constant, the words go where the cursor was, and React hears them");

  // -- the live region is in the document BEFORE it has anything to say -----
  //
  // This is the half of SC 4.1.3 that is easy to get wrong: a region that
  // appears carrying its message arrives after the assistive technology
  // stopped watching, so the message is never read.
  assert.match(parts, /export function Announcer\(\)/, "there is no live region to announce into");
  const slots = [...parts.matchAll(/role="status" aria-live="polite"/g)].length;
  assert.equal(slots, 2,
    `the announcer has ${slots} regions and needs two: a live region whose text ` +
    "did not change is not read again, so saying the same thing twice is silent");
  assert.match(app, /\n\s*<Announcer \/>/,
    "the live region is not mounted unconditionally, so it is not there when it is needed");
  assert.ok(!/\{[^}]*&&\s*<Announcer/.test(app),
    "the live region is behind a condition, which is the defect SC 4.1.3 names");

  // And the four asynchronous things this product does each say something.
  // Not a list of sentences -- those are the callers' words -- but that each
  // of the four call sites is still wired to the one region.
  const says: [string, string, RegExp][] = [
    ["form/Panel.tsx", "a write landing", /say\(`Saved: \$\{op\.title\}\.`\)/],
    ["app/App.tsx", "the agent answering", /say\(answer\.said\)/],
    ["app/App.tsx", "a list coming back changed", /say\(n === 1 \? "1 patient is here\." :/],
    ["screens/Desk.tsx", "a search answering", /say\(n === 1 \? "1 match\." :/],
  ];
  for (const [file, what, re] of says) {
    assert.match(code(readFileSync(join(SRC, file), "utf8")), re,
      `SC 4.1.3: ${what} is silent again, in ${file}`);
  }
  ok("a11y: one live region, mounted before it is needed, and the four silent things speak");

  // -- the tab says which screen it is --------------------------------------
  assert.match(parts, /document\.title = title/, "SC 2.4.2: nothing sets the document title");
  assert.match(app, /<PageTitle title=\{[^}]*bundle\.title[^}]*\}/,
    "the tab is not named after this screen and this facility, so every tab reads alike");
  ok("a11y: the tab carries the screen's name and the facility's");
}

// ------------------------------------------ 6. the loading state (§73)
//
// Before this, one screen in the app drew anything at all while it read: the
// rest showed a blank panel, which on a clinic's connection is
// indistinguishable from empty and from broken. A skeleton fixes that only if
// it has the shape of what is coming, does not flash, and is not read out as
// content.

{
  const parts = readFileSync(join(SRC, "parts.tsx"), "utf8");
  const cards = readFileSync(join(SRC, "style", "cards.css"), "utf8");

  // -- it does not flash ----------------------------------------------------
  const settle = /export const SETTLE = (\d+);/.exec(code(parts));
  assert.ok(settle, "the skeleton has no delay, so a fast answer flashes one");
  assert.ok(Number(settle![1]) >= 150,
    `a ${settle![1]}ms delay still flashes: a skeleton seen for an instant is worse than the blank`);
  assert.match(code(parts), /\{settled && <div aria-hidden="true">/,
    "the bones are drawn before the delay has passed, or are not hidden from assistive technology");

  // -- it is decoration, and the region around it is the content ------------
  assert.match(code(parts), /<div className="loading" role="status" aria-busy="true">/,
    "the loading region does not announce itself, so the skeleton is all there is");
  assert.match(code(parts), /<span className="u-sr">Loading \{what\}<\/span>/,
    "the region says nothing about WHAT is loading");

  // -- it is one primitive, not four ---------------------------------------
  const bones = TSX.filter((f) => f.endsWith(".tsx") && !f.endsWith("parts.tsx"))
    .filter((f) => /className="sk[ "]/.test(code(readFileSync(f, "utf8"))))
    .map(rel);
  assert.deepEqual(bones, [],
    "a screen draws its own skeleton bar instead of asking parts.tsx: " + bones.join(", "));

  // -- and it has the shape of what is coming -------------------------------
  //
  // The whole point. A queue is rows, a thread is messages, a panel is
  // blocks; one shape for all three is a grey rectangle that says "wait".
  const shapes: [string, RegExp][] = [
    ["app/App.tsx", /<Loading what="this list" shape="rows"/],
    ["app/App.tsx", /<Loading what="this encounter" shape="messages"/],
    ["app/App.tsx", /<Loading what="the workspace" shape="blocks"/],
    ["screens/Today.tsx", /<Loading what="the facility" shape="blocks"/],
    ["screens/Patient.tsx", /<Loading what="this patient" shape="blocks"/],
    ["screens/Desk.tsx", /<Loading what="who this might be" shape="rows"/],
  ];
  for (const [file, re] of shapes) {
    assert.match(code(readFileSync(join(SRC, file), "utf8")), re,
      `the skeleton in ${file} is not the shape of what that screen is waiting for`);
  }

  // -- a file that knows it is loading has to draw it -----------------------
  const blank = TSX.filter((f) => f.endsWith(".tsx") && !f.endsWith("parts.tsx"))
    .filter((f) => {
      const body = code(readFileSync(f, "utf8"));
      return /\bloading\b/i.test(body) && !/<Loading\b/.test(body);
    }).map(rel);
  assert.deepEqual(blank, [],
    "a screen reads a loading state and draws nothing for it: " + blank.join(", "));

  // -- less motion gets a flat tint, not a frozen frame ---------------------
  //
  // base.css shortens every animation under prefers-reduced-motion, which
  // leaves this one stopped on whichever keyframe it reached -- possibly a
  // half-faded bar that reads as disabled. The escape is written for the
  // primitive itself.
  const quiet = rules(cards).filter((r) => r.selector === ".sk" && /animation:\s*none/.test(r.body));
  assert.equal(quiet.length, 1,
    "the skeleton's shimmer has no reduced-motion escape of its own, so less " +
    "motion freezes it mid-fade instead of flattening it");
  assert.match(decomment(cards), /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.sk\s*\{/,
    "the escape is not inside a prefers-reduced-motion query");
  ok("loading: one delayed, hidden, shaped skeleton per screen, flat under less motion");
}

// --------------------------------- 7. colour still means one thing (§6.2)
//
// The queue's own rule is checked above, against queue.css. The home screen's
// line draws the same people and was never checked, and it had collected a
// tone class nothing rendered -- which is how a stylesheet starts meaning
// something the screen does not.

{
  const homeCss = readFileSync(join(SRC, "style", "home.css"), "utf8");
  const today = code(readFileSync(join(SRC, "screens", "Today.tsx"), "utf8"));
  const agent = code(readFileSync(join(SRC, "agent.ts"), "utf8"));

  const red = rules(homeCss)
    .filter((r) => /--color-critical/.test(r.body))
    .filter((r) => !/\balert\b/.test(r.selector))
    .map((r) => r.selector);
  assert.deepEqual(red, [],
    "the home screen paints clinical red on something that is not the declared " +
    "risk tone: " + red.join(", "));
  assert.match(agent, /const called = new Set\(Object\.entries\(badges\)\.filter\(\(\[, s\]\) => s === "crit"\)/,
    "the alert on the line is decided by something other than the declared tone");

  // Every tone a stylesheet offers has to be one a screen actually hands out.
  // `.at-ic.red` was styled here and rendered nowhere, which is a colour
  // waiting for somebody to reach for it.
  const tones = [...new Set(rules(homeCss)
    .flatMap((r) => [...r.selector.matchAll(/\.at-ic\.([\w-]+)/g)].map((m) => m[1])))];
  const orphans = tones.filter((t) => !new RegExp(`\\b${t}\\b`).test(today));
  assert.deepEqual(orphans, [],
    "a tone is styled on the attention icon that no screen ever gives it: " + orphans.join(", "));

  // SC 1.4.1. A person flagged on the line wore the critical tone and nothing
  // else, so the state was carried by colour alone.
  assert.match(today, /\{p\.alert && \(/, "the flagged person has no second carrier");
  assert.match(today, /<Icon name="alert"[^>]*\/>\s*<span className="u-sr">\{p\.alerts/,
    "SC 1.4.1: the flag on the line is a colour and nothing else, so it is " +
    "not there for anybody who cannot see that red");
  ok("a11y: on the line, clinical red is the declared tone and never the only carrier");

  // -- the panel that covers the screen says it covers the screen -----------
  const panel = code(readFileSync(join(SRC, "form", "Panel.tsx"), "utf8"));
  assert.match(panel, /role=\{inline \? undefined : "dialog"\}/,
    "the operation panel is a modal with nothing saying so");
  assert.match(panel, /aria-label=\{inline \? undefined : op\.title\}/,
    "and it is unnamed, so a screen reader is told a dialog opened and not which");
  // A callback ref, because voice.check.ts asserts this file holds no effect
  // and no timer: the only thing that may reach a write in the panel is a tap
  // or the Enter key, and landing the focus must not weaken that.
  assert.match(panel, /landed\.current = true;[\s\S]{0,160}?el\.focus\(\);/,
    "opening the panel leaves the keyboard behind the scrim, where Escape does nothing");
  // And it has to come back. A modal that takes the focus and does not return
  // it leaves the keyboard on a node React has removed, and the next Tab
  // starts again at the top of the document, which is worse than never having
  // moved it.
  assert.match(panel, /opener\.current = document\.activeElement/,
    "the panel does not remember what had the keyboard before it covered the screen");
  assert.match(panel, /opener\.current\?\.focus\(\)/,
    "the panel never hands the keyboard back to whatever opened it");
  // Tab out of a modal and you are in the page behind the scrim, where
  // everything is still focusable and none of it is visible.
  for (const [file, src] of [["form/Panel.tsx", panel],
                             ["app/Khoj.tsx", readFileSync(join(SRC, "app", "Khoj.tsx"), "utf8")]] as const) {
    assert.match(src, /trapTab\(/, `${file} covers the screen and lets Tab walk out behind it`);
  }
  assert.match(readFileSync(join(SRC, "app", "Khoj.tsx"), "utf8"),
    /opener\.current\?\.focus\(\)/,
    "the command bar never hands the keyboard back to whatever opened it");
  ok("a11y: the operation panel is a named dialog and the keyboard arrives in it");
}


/* ---- a liveness flag must be switched ON, not only off ------------------
 *
 * THIS KEPT SOMEBODY OUT OF THEIR OWN APP FOR AN AFTERNOON. SignIn held an
 * `alive` ref so a reply arriving after the screen had gone was ignored, and
 * the effect that managed it was a cleanup and nothing else:
 *
 *     useEffect(() => () => { alive.current = false; }, []);
 *
 * React's StrictMode mounts a component, runs the cleanup, and mounts it
 * again. With no setup body, the second mount left the flag false for the
 * rest of the session, so every `if (!alive.current) return;` below it was
 * dead code. The Eka session arrived and was thrown away, and the line that
 * would have said so was behind the same guard. It fails only in
 * development, which is the half of the day a person is looking at it.
 *
 * The rule is the shape, not the name: an effect whose entire body is a
 * cleanup setting some ref to false is refused. Setting it true on the way
 * in costs one line and survives being mounted twice.
 */
{
  const bad: string[] = [];
  for (const file of TSX) {
    const src = readFileSync(file, "utf8");
    const m = src.match(/useEffect\(\(\) => \(\) => \{?[^}]*?\.current = false;?\s*\}?,\s*\[\]\)/);
    if (m) bad.push(`${relative(SRC, file)}: ${m[0].replace(/\s+/g, " ").slice(0, 90)}`);
  }
  assert.deepEqual(bad, [],
    "an effect that is only a cleanup leaves its flag false after StrictMode "
    + "mounts the component a second time, and every guard on that flag is "
    + "then dead: set it true in the setup too. " + bad.join(" | "));
  ok("no effect sets a liveness flag false without setting it true on the way in");
}


// THE NUDGES ARE THE BUNDLE'S WORDS, NOT THIS RENDERER'S. The sentences the
// scribe screen shows somebody who has just pressed record are declared in
// bundle.yaml under `scribe.<station>.nudges`, so a centre can change them.
// One typed into a component would be a sentence no centre could edit and
// the screen would then disagree with the facility it claims to describe --
// which is the same rule that keeps stations, flags and columns out of here.
{
  const says: string[] = [];
  for (const cfg of Object.values(catalogue.scribe ?? {}) as { nudges?: { say: string }[] }[]) {
    for (const n of cfg.nudges ?? []) says.push(n.say);
  }
  assert.ok(says.length > 0, "the bundle declares no scribe nudges at all");
  const typed: string[] = [];
  for (const file of TSX) {
    const src = readFileSync(file, "utf8");
    for (const say of says) if (src.includes(say)) typed.push(`${relative(SRC, file)}: ${say}`);
  }
  assert.deepEqual(typed, [], "a nudge is typed into the renderer; it belongs in bundle.yaml");
  ok(`${says.length} scribe nudges come from the bundle, none typed into a component`);
}

// ONE LIST OF THE OUTCOMES THAT MEAN SOMETHING WAS WRITTEN, held against
// the kernel's. It was three regular expressions here and two tuples there,
// and the day "amended" was added four of them went on showing the value
// from before the correction. A screen that disagrees with the record about
// a patient's pulse is the worst drift there is, so it is one list now and
// this is what keeps it one.
{
  const vocab = readFileSync(join(ROOT, "catalogue", "vocab.py"), "utf8");
  const declared = /^WROTE = \(([^)]*)\)/m.exec(vocab);
  assert.ok(declared, "catalogue/vocab.py no longer declares WROTE");
  const kernel = [...declared![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...WROTE], kernel,
    "web/src/types.ts WROTE and catalogue/vocab.py WROTE disagree about what " +
    "counts as written");

  const stale: string[] = [];
  for (const file of TSX) {
    const src = readFileSync(file, "utf8");
    if (/committed\|confirmed\|allowed/.test(src)) stale.push(relative(SRC, file));
  }
  assert.deepEqual(stale, [],
    "an outcome list is spelled out again instead of calling wrote()");
  ok(`${kernel.length} written outcomes, one list, shared with the kernel`);
}

// ------------------------------------------------------------ the day screen

{
  const row = (contact: string, state: string, owner: string, due = "2026-11-04") =>
    ({ contact, title: contact, state, owner, due, closes: due, done_at: "", subject: "p1", subject_row: {} }) as unknown as CalendarRow;
  const rows = [row("a", "done", "r.anm"), row("b", "due", "r.mo"), row("c", "missed", "r.anm"), row("d", "due", "r.anm")];

  // Rows group late, then owed, then done, in that order.
  assert.deepEqual(inPiles(rows).map((p) => [p.pile, p.rows.map((r) => r.contact)]),
    [["late", ["c"]], ["owed", ["b", "d"]], ["done", ["a"]]]);
  assert.deepEqual(inPiles([row("x", "done", "r.anm")]).map((p) => p.pile), ["done"],
    "an empty pile is not drawn");

  // THE PILES PARTITION THE ROWS: a state nobody expected still appears, once.
  const odd = [...rows, row("e", "paused", "r.mo"), row("f", "paused", "r.anm"), row("g", "zzz", "r.anm")];
  const all = inPiles(odd);
  assert.equal(all.reduce((n, p) => n + p.rows.length, 0), odd.length, "a row vanished from the day");
  assert.deepEqual(all.map((p) => p.pile).slice(-2), ["paused", "zzz"], "unexpected states come last, named by themselves");
  assert.equal(inPiles(rows).reduce((n, p) => n + p.rows.length, 0), rows.length);
  // Emptiness is read from what the piles hold: a role whose rows are all
  // unexpected is not an empty day.
  assert.ok(inPiles(forRole([row("u", "upcoming", "r.x")], "r.x")).length > 0);
  // THE HEADING IS TRUE OF THE DAY SHOWN: "Owed today" only on today.
  assert.equal(inPiles(rows).find((p) => p.pile === "owed")?.label, "Today");
  assert.equal(inPiles(rows, false).find((p) => p.pile === "owed")?.label, "Due",
    "a day that is not today must not say 'today'");
  assert.deepEqual(inPiles(rows, false).map((p) => p.label), ["Late", "Due", "Done"]);
  // Chips are ordered by what is displayed, not by id.
  assert.deepEqual(roleChips(rows, "", (r) => (r === "r.anm" ? "Zed" : "Alpha")).roles, ["r.mo", "r.anm"]);

  // A row's owner is the role the kernel sent; the chips are those roles and
  // nothing else, so no worker name can appear.
  const { roles, initial } = roleChips(rows, "r.anm");
  assert.deepEqual(roles, ["r.anm", "r.mo"]);
  // The chip the screen opens on is the caller's own role, and everyone when
  // the caller owns nothing in this answer.
  assert.equal(initial, "r.anm");
  assert.equal(roleChips(rows, "r.other").initial, EVERYONE);
  assert.deepEqual(forRole(rows, "r.mo").map((r) => r.contact), ["b"]);
  assert.equal(forRole(rows, EVERYONE).length, 4);

  // An empty day says so, and a filtered-empty day says it was the filter.
  assert.equal(emptyLine(0, 0), "No visits this day.");
  assert.equal(emptyLine(4, 0), "No visits for you. Choose everyone to see the rest.");
  assert.equal(emptyLine(4, 2), null);

  // A date is read by position: no time zone can move it.
  assert.deepEqual(dayOf("2026-11-04"), { day: "4", month: "Nov" });

  // The screen names no state, flag, station or operation of its own. The
  // portability scan above already covers every file; this holds both day
  // files (Calendar.tsx and day.ts) to a narrower rule: none of them reads an
  // operation, station, flag or reports_as field.
  const screen = code(readFileSync(join(SRC, "view", "Calendar.tsx"), "utf8"));
  const logic = code(readFileSync(join(SRC, "view", "day.ts"), "utf8"));
  for (const [name, src] of [["Calendar.tsx", screen], ["day.ts", logic]]) {
    assert.ok(!/\.operation\b|\.station\b|\.flags\b|\.reports_as\b/.test(src),
      `${name} reads a field it should not know`);
  }
  assert.ok(!/\btitle\(|\bhuman\(/.test(screen), "the day screen cases a role id instead of reading its declared title");
  assert.match(screen, /role_titles/, "a role is named by the catalogue's role_titles");
  assert.ok(!/from "\.\/View"/.test(screen), "the day screen imports View, which imports it");
  assert.match(screen, /from "\.\.\/thread\/Arc"/, "tones and marks come from Arc, not a second copy");
  assert.ok(!/\b(TONE|MARK)\s*[:=]/.test(screen), "the day screen redefines the arc's tones");
  ok("the day screen: late, owed, done; the caller's role first; an empty day says so");
}

// ------------------------------------------------------ the home page's card

{
  // Today and tomorrow are named; the rest by weekday, read without a time zone.
  assert.equal(dayLabel("2026-11-04", "2026-11-04"), "Today");
  assert.equal(dayLabel("2026-11-05", "2026-11-04"), "Tomorrow");
  assert.equal(dayLabel("2026-11-06", "2026-11-04"), "Fri 6 Nov");
  assert.equal(dateOf("2026-11-04T11:52:10Z"), "2026-11-04");
  assert.equal(dateOf("garbage"), "");
  // The date a link carries is read only when it is a whole date.
  assert.equal(dayOn("#/views/x?on=2026-11-06"), "2026-11-06");
  assert.equal(dayOn("#/views/x?on=soon"), "");
  assert.equal(dayOn("#/views/x"), "");

  const today = code(readFileSync(join(SRC, "screens", "Today.tsx"), "utf8"));
  assert.match(today, /decl\.kind === "calendar"/, "the card is found by the declared kind of view");
  assert.ok(!/cardDays\(|wantsNextMonth\(|comingUp\(/.test(today), "the count-based card is gone");

  const cal2 = code(readFileSync(join(SRC, "view", "Calendar.tsx"), "utf8"));
  assert.match(cal2, /fetched\.data\.on === other/, "an answer is used only for the day it was asked for");
  assert.ok(!/waiting \? \[\]/.test(cal2));
  const cal = code(readFileSync(join(SRC, "view", "Calendar.tsx"), "utf8"));
  assert.match(cal, /dayOn\(/, "the day screen opens on the date a link carries");
  ok("the day helpers: labels, dates in a link, and the card is found by the declared kind of view");
}

// ------------------------------------------------------- the calendar page

{
  // The scale and the anchor date both live in the address.
  assert.equal(scaleOf("#/views/calendar?scale=week"), "week");
  assert.equal(scaleOf("#/views/calendar?on=2026-11-04&scale=year"), "year");
  assert.equal(scaleOf("#/views/calendar"), "month", "no scale in the address is the month");
  assert.equal(scaleOf("#/views/calendar?scale=decade"), "month", "an unknown scale is not trusted");
  assert.equal(withView("#/views/calendar", { on: "2026-11-09", scale: "week" }), "#/views/calendar?on=2026-11-09&scale=week");
  assert.equal(withView("#/views/calendar?on=2026-11-04&scale=week", { scale: "year" }), "#/views/calendar?on=2026-11-04&scale=year",
    "changing the scale keeps the date");
  assert.equal(withView("#/views/calendar?on=2026-11-04&scale=week", { on: "" }), "#/views/calendar?scale=week",
    "an empty date leaves the address without one");
  assert.equal(dayOn(withView("#/views/calendar", { on: "2026-11-09" })), "2026-11-09", "?on= still reads");
  // The grid's date is read from the address, separately from the day list's.
  assert.equal(atOf("#/views/phc.view.calendar?scale=month&at=2026-02-15"), "2026-02-15");
  assert.equal(atOf("#/views/phc.view.calendar?on=2026-11-04"), "", "the day list's date is not the grid's");
  assert.equal(withView("#/v?scale=week&at=2026-02-15", { at: "2026-03-01" }), "#/v?at=2026-03-01&scale=week");
  // Switching scale asks for the new span, never the old one.
  assert.notDeepEqual(span("month", "2026-11-04"), span("week", "2026-11-04"));
  assert.deepEqual(span("year", "2026-11-04"), { from: "2026-01-01", to: "2026-12-31" });

  const page = code(readFileSync(join(SRC, "view", "Calendar.tsx"), "utf8"));
  assert.match(page, /from "\.\/Grid"/, "the grid is imported as ./Grid");
  assert.match(page, /from "\.\/cells"/, "the pure logic is imported as ./cells");
  assert.match(page, /span\(scale, /, "the range asked for follows the scale");
  assert.match(page, /atOf\(hash\)/, "the grid opens on the date the address carries");
  assert.match(page, /addEventListener\("hashchange"/, "going back re-reads the address");
  assert.match(page, /api\.view\(result\.view, undefined, other\b/, "the day list asks for its own day");
  assert.ok(!/api\.view\([^)]*anchor/.test(page.replace(/\{ from, to \}/g, "")), "paging the grid does not move the day list");
  assert.match(page, /goTo\(\{ at: step\(/, "paging moves the grid's date only");
  const gridSrc = code(readFileSync(join(SRC, "view", "Grid.tsx"), "utf8"));
  assert.ok(gridSrc.indexOf("gr-chip-who") < gridSrc.indexOf("gr-chip-t\""), "a chip leads with the person");
  assert.match(page, /scaleOf\(/, "the scale is read from the address");
  assert.match(page, /withView\(/, "the scale and date are written to the address");
  assert.match(page, /forRole\(gridRows|forRole\(.*grid/s, "the role chips filter the grid too");
  assert.match(page, /<Grid\b/, "the grid is drawn");
  assert.match(page, /\{empty && /, "an empty day still shows its sentence beside a drawn grid");
  assert.ok(!/\.cell\b[^;]*\.due|\.due\b[^;]*\.cell\b/.test(page), "rows are placed by cell, never by due");
  assert.ok(!/\.operation\b|\.station\b|\.flags\b|\.reports_as\b/.test(page), "the page reads a field it should not know");
  const apiSrc = code(readFileSync(join(SRC, "api.ts"), "utf8"));
  assert.match(apiSrc, /from=|`from=/, "the api can ask for a range");
  // A range answer's rows are placed by the cell they carry.
  const r = { contact: "c", title: "c", state: "missed", owner: "r", due: "2026-09-09", cell: "2026-11-04", subject: "p", subject_row: {} } as unknown as CalendarRow;
  assert.equal(cells("month", "2026-11-04", [r], 3, "2026-11-04").find((c) => c.key === "2026-11-04")?.rows.length, 1);
  ok("the calendar page: scale and date in the address, the new span on a switch, chips filter the grid, an empty day still speaks");
}

// ------------------------------------------------------- the card stack

{
  const row = (o: Record<string, unknown>) => ({ contact: "c", title: "Visit", state: "upcoming", owner: "nurse", due: "2026-11-10", cell: "2026-11-10", subject: "p1", subject_row: {}, ...o }) as unknown as CalendarRow;
  const NOW = "2026-11-04";
  const late = row({ contact: "a", state: "missed", due: "2026-09-09", cell: NOW });
  const today = row({ contact: "b", state: "due", due: NOW, cell: NOW });
  const soon = row({ contact: "c", due: "2026-11-06" });
  const later = row({ contact: "d", due: "2027-01-02", owner: "doctor" });
  const gone = row({ contact: "e", state: "done", due: "2026-10-01" });

  // Late contacts lead, then the soonest owed, whatever order the kernel sent.
  assert.deepEqual(stack([later, soon, today, late], NOW, "").map((r) => r.contact), ["a", "b", "c", "d"]);
  assert.deepEqual(stack([soon, late, row({ contact: "z", state: "missed", due: "2026-08-01" })], NOW, "").map((r) => r.contact), ["z", "a", "c"],
    "the longest-late leads the late ones");
  // One card per contact: a woman owed two appears twice.
  assert.equal(stack([late, today], NOW, "").filter((r) => r.subject === "p1").length, 2);
  // Work already done is not coming up.
  assert.ok(!stack([gone, soon], NOW, "").some((r) => r.contact === "e"));
  // The stack opens on the viewer's role, and on everyone's when they own nothing.
  assert.deepEqual(stack([later, soon, late], NOW, "doctor").map((r) => r.contact), ["d"]);
  assert.deepEqual(stack([later, soon, late], NOW, "pharmacist").map((r) => r.contact), ["a", "c", "d"], "owning nothing falls back to everyone");
  assert.deepEqual(stack([], NOW, "nurse"), []);
  // The input is not reordered in place.
  const input = [later, late]; stack(input, NOW, ""); assert.equal(input[0], later);

  // The arrows page to later cards and cannot page past the end.
  assert.equal(pageBy(0, 1, 2), 1);
  assert.equal(pageBy(1, 1, 2), 1, "no paging past the last card");
  assert.equal(pageBy(0, -1, 2), 0, "no paging before the first");
  assert.equal(pageBy(5, 0, 0), 0, "an empty stack has only a first");
  assert.equal(pageBy(9, 0, 3), 2, "a stale position is pulled back inside the stack");

  // A card opens the calendar on the date the visit is owed.
  assert.equal(cardHash(late), "/patients/p1?at=2026-09-09", "her own page, carrying the date");
  assert.equal(atOf("#" + cardHash(soon)), "2026-11-06", "the date is in the shape the calendar reads");
  assert.ok(!/\/views\//.test(cardHash(soon)), "not the facility's calendar");
  assert.equal(cardHash(row({ subject: "a b/c" })), "/patients/a%20b%2Fc?at=2026-11-10", "an id is encoded");
  // When it is owed, in words.
  assert.equal(owedLine(late, NOW), "Late since Wed 9 Sep");
  assert.equal(owedLine(today, NOW), "Due today");
  assert.equal(owedLine(soon, NOW), "Due Fri 6 Nov");
  assert.equal(owedLine(row({ due: "2026-11-05" }), NOW), "Due tomorrow");

  const src = code(readFileSync(join(SRC, "view", "Cards.tsx"), "utf8"));
  const home = code(readFileSync(join(SRC, "screens", "Today.tsx"), "utf8"));
  // Name, which contact, when, and the role that owns it.
  assert.match(src, /nameOf\(/, "a card carries her name");
  assert.match(src, /\.title/, "a card says which contact it is");
  assert.match(src, /owedLine\(/, "a card says when it is owed");
  assert.match(src, /roleName\(/, "a card names the owning role");
  assert.match(src, /roleName\(r\.owner\)/, "a card names the owning role");
  assert.ok(!/\.owner\b/.test(src.replace(/roleName\(r\.owner\)/g, "").replace(/r\.owner &&/g, "")) && !/assignee|worker|staff/i.test(src),
    "a card names a role, never a person; the only other use of owner is whether there is one");
  // A register field she does not carry is omitted, not drawn as a blank label.
  assert.match(src, /meta && /, "the register line only draws when there is something in it");
  assert.ok(!/weeks|gestation|pregnan/i.test(src), "no dating is derived on the card");
  // Paging: the arrows are disabled at the ends and the page goes through pageBy.
  assert.match(src, /pageBy\(/, "paging goes through the pure function");
  assert.match(src, /disabled=\{/, "an arrow at the end of the stack is disabled");
  assert.match(src, /aria-label="(Earlier|Previous)/, "the arrows are named");
  assert.match(src, /aria-label="Later/, "the arrows are named");
  // Each card is as wide as its words need: a grid of cards, never one stretched
  // across the page, and no card hidden behind another.
  const css = readFileSync(join(SRC, "style", "cards-stack.css"), "utf8");
  assert.match(css, /\.stk-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill/, "the cards sit in a grid of fixed-width columns");
  assert.ok(!/--depth|\.stk-behind|\.stk-deck/.test(css), "no card is tucked behind another");
  assert.match(readFileSync(join(SRC, "main.tsx"), "utf8"), /cards-stack\.css/, "the stylesheet is loaded");
  // The home page: the stack replaces the day counts, and opens her calendar.
  assert.match(home, /stack\(/, "the home page builds the stack through day.ts");
  assert.match(home, /<Cards\b/, "the home page draws the cards");
  assert.match(home, /cardHash\(r\)/, "a card goes to her page through day.ts");
  assert.ok(!/views\/\$\{cal\.decl\.id\}/.test(home), "a card does not open the facility view");
  assert.match(home, /currentRole\(\)/, "the stack opens on the viewer's own role");
  assert.ok(!/Next visits<\/div>[\s\S]*contacts? owed/.test(home) && !/contacts owed/.test(home), "the count table is gone");
  // The renderer never names a station, flag, capability, operation or column.
  // Today.tsx also draws the line of patients, which reads stations on purpose;
  // the stack's own parts are the read of the visits and the card that draws them.
  // A marker that is not found must fail, never slice from -1 and guard air.
  const between = (text: string, from: string, to: string) => {
    const a = text.indexOf(from), b = text.indexOf(to, a + 1);
    assert.ok(a >= 0 && b > a, `the scan's markers moved: "${from}" ... "${to}"`);
    return text.slice(a, b);
  };
  const stackPart = between(home, "const calId", "if (loading") + between(home, "{cal && (", '<div className="hgrid">');
  assert.ok(stackPart.length > 400, "the scan found the stack's parts of Today.tsx");
  const dayLogic = code(readFileSync(join(SRC, "view", "day.ts"), "utf8"));
  for (const [name, text] of [["Cards.tsx", src], ["the stack's part of Today.tsx", stackPart], ["day.ts", dayLogic]] as const) {
    assert.ok(!/\.(flags|operation|reports_as|authority)\b/.test(text) && !/\.station\b/.test(text),
      `${name} reads a field it should not know`);
  }
  // A failed read of the visits is said, never swallowed into a quiet card.
  assert.match(home, /setOwed\("failed"\)/, "a failed read of the visits is recorded, not swallowed");
  assert.ok(!/(,|\.catch\()\s*(\(\s*\w*\s*\)|\w+|function\s*\(\s*\w*\s*\))\s*(=>\s*)?\{\s*\}\s*\)/.test(home),
    "an empty handler (arrow with or without a parameter, or function) hides a failed read");
  assert.match(home, /Could not load visits/, "the failure is shown");
  // The stack opens on the viewer's role and says what else exists.
  assert.match(home, /more for others/, "the stack says how much belongs to others");
  // A viewer who owns nothing while others are owed: told so, shown the others' cards, never "nobody".
  const stk = between(home, "const all =", "if (loading");
  assert.match(stk, /noneMine = all\.length > 0 && mine\.length === 0/, "owning nothing while others are owed is its own case");
  assert.match(stk, /everyone \|\| noneMine \? all/, "that viewer is shown the others' cards");
  assert.match(home, /No visits for you\. Showing \$\{others\} for others/, "and told how many");
  assert.match(home, /cards\.length === 0 \? \(\s*owed && <div[^>]*>No visits coming up/, '"no visits" is only for an empty stack');
  const endOfBranch = home.indexOf("</>\n          )}"), control = home.indexOf('className="stk-more"');
  assert.ok(endOfBranch >= 0 && control > endOfBranch, "the control sits after, so outside, the empty-or-cards branch");
  assert.match(home, /!noneMine && others > 0/, "and is hidden for a viewer who already sees everything");
  // The role filter the home page uses agrees with the one stack() applies.
  const mixed = [later, soon, late, today];
  assert.deepEqual(forRole(stack(mixed, NOW, ""), "nurse").map((r) => r.contact), stack(mixed, NOW, "nurse").map((r) => r.contact),
    "forRole over the whole stack is the role's stack, in the same order");
  assert.deepEqual(stack([soon, later], NOW, "pharmacist").map((r) => r.contact), ["c", "d"], "owning nothing shows everyone's, never none");
  assert.match(home, /setEveryone\(/, "and offers a way to see it");
  assert.ok(!/split\(" · "\)/.test(home), "a value containing the separator is not cut: facts are taken before they are joined");
  assert.ok(!/as unknown as QueueRow/.test(home.split("<Cards")[1] ?? ""), "no cast to get a subject through the types");
  assert.ok(!/Open her/.test(src), "the button does not assume the subject's sex");
  // Nothing derived is kept.
  assert.ok(!/useMemo|localStorage|sessionStorage|new Map\(/.test(src), "no cache of derived rows");
  ok("the visit cards: late first, one per contact, role first, paged without overshoot, opens her calendar on the due date");
}

console.log(`\n${checks} checks passed`);
