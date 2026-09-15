/** Vernier step 13: the closed spacing scale, the five-value type scale, and
 *  the handful of geometric rules a text parser can actually stand behind.
 *
 *  Run: node --experimental-strip-types src/layout.check.ts   (from web/)
 *
 *  THE HONEST LIMIT, STATED FIRST. Most of the spec's thirteen "Measurable
 *  assertions" are rectangles: a rail row's left edge, a plate's width, the
 *  44px header height surviving the handle's removal, the topbar and the
 *  page agreeing at five viewports, zero dead pixels between plates. Group B
 *  found `.sb`'s border-right eating 1px of the rail-body's own box, and it
 *  was invisible to source inspection -- only live DOM measurement caught it.
 *  This file runs under plain node: no DOM, no layout engine, no browser. It
 *  cannot open a page and read a rect. So it does not pretend to. Every
 *  geometric assertion below is either left uncovered (named in this file's
 *  own header and in the group report) or reduced to a CSS-declaration proxy
 *  that is labelled as a proxy at the point it is made -- never silently
 *  presented as the real thing. A check that looks like it covers geometry
 *  but does not is worse than an honest gap; that is the failure this file is
 *  written not to repeat.
 *
 *  WHAT THIS FILE CANNOT COVER, AND WHY (see also the group report):
 *    - rail row rect.left === 8, plate x === 304 / width === 1336, the
 *      topbar/.wrap left edge agreeing at five viewports, zero dead pixels
 *      between plates, the collapsed rail's computed width. All rectangles;
 *      none exist until a browser lays the page out.
 *    - "removing the handle changes the header's height by 0px", "the main
 *      column's width takes exactly two distinct values across 20 frames".
 *      Both are live-DOM measurements of a mutation over time; this file
 *      checks the CSS declarations that are SUPPOSED to make them true
 *      (assertions 5 and 7 below) and says so at the point it does.
 *    - the reorder gesture, the act budget's rendered DOM count, and the
 *      colour gate itself are covered elsewhere (home.check.ts,
 *      design.check.ts) and are not duplicated here.
 *
 *  SCOPE OF THE FILES THIS CHECK ENFORCES THE SCALE AGAINST, AND WHY.
 *  theme.css carries the whole prototype's CSS in one file. Steps 1-3, 4-6,
 *  7 and 8-10 rewrote its token blocks, its base/page grid, its sidebar
 *  block and its Home bands (resume/scale/stack/plate/stub) -- INCLUDED
 *  below by the file's own `/* ---------- name ---------- * /` section
 *  markers ("base", "sidebar", "main", "home"). Nobody, across any of the
 *  four groups, was ever assigned the cards/chat/queue/records/sheet/
 *  composer/spotlight/modal sections: every prior group's own commit says so
 *  in as many words ("Scope, per this group's brief: theme.css and
 *  index.html only... cards, chat, queue, spotlight, modal... untouched"),
 *  and the file's own header comment names the same list. Those sections
 *  render five screens this spec never asked anyone to rebuild (Thread, the
 *  Roles and Operation modals, the summary Sheet, the old Khoj results
 *  list); closing the scale there means redesigning those screens, which is
 *  not what "write the checks" means. They are EXCLUDED below, by name, not
 *  by a silent regex miss -- and so are voice.css, scribe.css and abha.css,
 *  which predate Vernier entirely and were never touched by any of its
 *  commits (confirmed against `git log` for this report). renderer.css is
 *  fully in scope: group C's own commit says it swept every dangling token
 *  there, and this file's own scan (see the group report) finds zero
 *  violations in it.
 *  Every .tsx's INLINE styles, by contrast, are checked with NO file
 *  exclusion at all: there were only a couple of dozen `style={{...}}`
 *  blocks in the entire renderer, small enough to fix outright rather than
 *  carve an exception for (Khoj.tsx's own padding:'38px 22px' -> '40px 20px'
 *  is the spec's own example of exactly this).
 *
 *  WHAT "SPACING" MEANS HERE, AND THE ONE PLACE THE SPEC CONTRADICTS ITSELF.
 *  The spec's own shipped code needs numbers outside the 14-value set for
 *  properties the "Spacing scale" section's prose also names: --rail-w is
 *  264px, the rail's own popover is width:248px (spec: "Menu width:248px"),
 *  and the plate header is height:44px (spec: "VERTICAL RHYTHM... 44 plate
 *  header" -- a sixth height nowhere in the 14-value list). A closed-set
 *  check applied to width/height literally would fail the spec's own
 *  required numbers, not just this codebase's debt. So this file enforces
 *  the closed set on the properties that actually carry RHYTHM -- padding,
 *  margin, gap, and the position offsets (inset/top/right/bottom) used for
 *  hit-area and badge-offset tricks -- and leaves width/height alone. Font
 *  size and line-height are checked separately, against their own five-value
 *  and divisible-by-4 rules, never folded into the spacing set.
 *  Within padding/margin/gap specifically, 1 and 2 are dropped from the
 *  legal set: "1 and 2 permitted only in a border, a ring or a bar" and this
 *  codebase draws borders, rings and bars with border-width, outline and
 *  height, never with a padding or a margin or a gap of 1px or 2px -- so for
 *  THESE properties the tightened set is {0,4,8,12,16,20,24,32,40,48,60,64}.
 *  For inset/top/right/bottom, 1 and 2 stay legal: the rail's own CSS-drawn
 *  chevron is "drawn from a border and a bar, both legal at 2px" by the
 *  file's own comment, positioned with top/bottom:-2px.
 *  Media-query breakpoints (900, 1100) are excluded on purpose, not by
 *  accident: they are widths of the VIEWPORT, not spacing on an element, and
 *  this file's declaration parser never treats an `@media(...)` condition as
 *  a property in the first place, so they never reach the scan.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

// -- gather the in-scope CSS text -------------------------------------------
const themeCss = read("web/src/theme.css");
const rendererCss = read("web/src/renderer.css");

function themeSections(css: string): Record<string, string> {
  const marker = /\/\*\s*-{4,}\s*(.+?)\s*-{4,}\s*\*\//g;
  const starts: { name: string; matchStart: number; contentStart: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = marker.exec(css))) starts.push({ name: m[1].trim(), matchStart: m.index, contentStart: m.index + m[0].length });
  const out: Record<string, string> = { preamble: css.slice(0, starts.length ? starts[0].matchStart : css.length) };
  for (let i = 0; i < starts.length; i++) {
    const end = i + 1 < starts.length ? starts[i + 1].matchStart : css.length;
    out[starts[i].name] = css.slice(starts[i].contentStart, end);
  }
  return out;
}
const sections = themeSections(themeCss);
const INCLUDED = ["preamble", "base", "sidebar", "main", "home"];
const EXCLUDED = ["cards", "chat view", "queue", "the right rail's records", "summary sheet", "composer", "spotlight", "modal"];
for (const name of [...INCLUDED.filter((n) => n !== "preamble"), ...EXCLUDED]) {
  ok(name in sections, `theme.css still has its own "${name}" section marker (the scope list above names it by hand)`);
}
const inScopeThemeCss = INCLUDED.map((n) => sections[n] ?? "").join("\n");
ok(inScopeThemeCss.length > 500, "the in-scope slice of theme.css is not accidentally empty");
const outOfScopeThemeCss = EXCLUDED.map((n) => sections[n] ?? "").join("\n");
ok(outOfScopeThemeCss.length > 500, "the excluded slice of theme.css is not accidentally empty (there is real, named debt sitting there)");

const cssScope = inScopeThemeCss + "\n" + rendererCss;

// -- gather every .tsx, and every className token in it ---------------------
function allTsx(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(root + dir, { withFileTypes: true })) {
    if (e.isDirectory()) out.push(...allTsx(`${dir}/${e.name}`));
    else if (e.name.endsWith(".tsx")) out.push(`${dir}/${e.name}`);
  }
  return out;
}
const tsxFiles = allTsx("web/src");
ok(tsxFiles.length >= 15, `found enough .tsx files to mean something (${tsxFiles.length})`);
const tsxSources = tsxFiles.map((f) => ({ f, src: read(f) }));

// -- declaration parsing: selector{ decl; decl; decl } with no nesting ------
// The last declaration in a block is not required to end in `;`, which a
// naive `prop:value;` regex misses -- .tb-sub{...;margin-top:1px} (no
// trailing semicolon) is exactly the kind of rule that regex would silently
// skip. Splitting the block body on `;` catches it.
function declarations(css: string): { selector: string; prop: string; value: string }[] {
  const noComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const out: { selector: string; prop: string; value: string }[] = [];
  const blockRe = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = blockRe.exec(noComments))) {
    const selector = m[1].trim();
    for (const decl of m[2].split(";")) {
      const i = decl.indexOf(":");
      if (i < 0) continue;
      out.push({ selector, prop: decl.slice(0, i).trim().toLowerCase(), value: decl.slice(i + 1).trim() });
    }
  }
  return out;
}

const SPACING_PROPS = new Set([
  "padding", "padding-inline", "padding-block", "padding-top", "padding-bottom",
  "padding-left", "padding-right", "padding-inline-start", "padding-inline-end",
  "margin", "margin-inline", "margin-block", "margin-top", "margin-bottom",
  "margin-left", "margin-right", "margin-inline-start", "margin-inline-end",
  "gap", "column-gap", "row-gap",
]);
const INSET_PROPS = new Set(["inset", "top", "left", "right", "bottom"]);
const SPACING_LEGAL = new Set([0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 60, 64]);
const INSET_LEGAL = new Set([0, 1, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 60, 64]);
const FONT_SIZES = new Set([11, 13, 15, 20, 32]);

function pxNumbers(value: string): number[] {
  return [...value.matchAll(/(-?\d+(?:\.\d+)?)px/g)].map((m) => parseFloat(m[1]));
}

// -- assertion 10 (part 1): the closed spacing scale, in CSS ---------------
let cssSpacingChecked = 0;
for (const { selector, prop, value } of declarations(cssScope)) {
  const legal = SPACING_PROPS.has(prop) ? SPACING_LEGAL : INSET_PROPS.has(prop) ? INSET_LEGAL : null;
  if (!legal) continue;
  for (const n of pxNumbers(value)) {
    cssSpacingChecked++;
    ok(Number.isInteger(n) && legal.has(Math.abs(n)),
      `"${selector}" sets ${prop}:${value.trim()} -- ${n}px is not in the closed spacing scale`);
  }
}
ok(cssSpacingChecked > 30, `the spacing scan actually found declarations to check (${cssSpacingChecked})`);

// -- assertion 10 (part 2): the same scale, in every .tsx's inline styles --
// No file is excluded here (unlike the CSS scan above): there are only a
// couple of dozen `style={{...}}` blocks in the whole renderer, few enough
// to fix outright. flex/width/height/minWidth/maxWidth are deliberately not
// scanned, for the same reason theme.css's own --rail-w:264 and .plate-h's
// height:44 are not: they are not spacing rhythm.
const STYLE_SPACING_KEYS: Record<string, "spacing" | "inset"> = {
  padding: "spacing", paddingtop: "spacing", paddingbottom: "spacing", paddingleft: "spacing",
  paddingright: "spacing", paddinginline: "spacing", paddingblock: "spacing",
  margin: "spacing", margintop: "spacing", marginbottom: "spacing", marginleft: "spacing",
  marginright: "spacing", margininline: "spacing", marginblock: "spacing",
  gap: "spacing", columngap: "spacing", rowgap: "spacing",
  inset: "inset", top: "inset", left: "inset", right: "inset", bottom: "inset",
};
let tsxSpacingChecked = 0;
for (const { f, src } of tsxSources) {
  for (const m of src.matchAll(/style=\{\{([^}]*)\}\}/g)) {
    for (const part of m[1].split(",")) {
      const c = part.indexOf(":");
      if (c < 0) continue;
      const key = part.slice(0, c).replace(/[^a-zA-Z]/g, "").toLowerCase();
      const kind = STYLE_SPACING_KEYS[key];
      if (!kind) continue;
      const val = part.slice(c + 1);
      const legal = kind === "spacing" ? SPACING_LEGAL : INSET_LEGAL;
      for (const n of pxNumbers(val) as number[]) {
        tsxSpacingChecked++;
        ok(Number.isInteger(n) && legal.has(Math.abs(n)), `${f}: ${key} has ${n} in [${val.trim()}] -- not in the closed spacing scale`);
      }
      // A bare number (`gap: 9`, no unit) is still a px value in React's
      // inline-style convention for these properties.
      const bare = val.trim();
      if (/^-?\d+(\.\d+)?$/.test(bare)) {
        tsxSpacingChecked++;
        const n = parseFloat(bare);
        ok(Number.isInteger(n) && legal.has(Math.abs(n)), `${f}: ${key}: ${bare} (bare number) -- not in the closed spacing scale`);
      }
    }
  }
}
ok(tsxSpacingChecked > 15, `the inline-style scan actually found spacing values to check (${tsxSpacingChecked})`);

// -- assertion 10 (part 3): the five-value type scale, and line-height ------
let fontSizesChecked = 0;
for (const { selector, prop, value } of declarations(cssScope)) {
  if (prop === "font-size") {
    const n = parseFloat(value);
    if (!Number.isNaN(n)) { fontSizesChecked++; ok(FONT_SIZES.has(n), `"${selector}" sets font-size:${value.trim()} -- not one of the five legal sizes`); }
  }
  if (prop === "font") {
    const m = /(\d+(?:\.\d+)?)px\s*\/\s*(\d+(?:\.\d+)?)px/.exec(value);
    if (m) {
      fontSizesChecked++;
      const fs = parseFloat(m[1]); const lh = parseFloat(m[2]);
      ok(FONT_SIZES.has(fs), `"${selector}" sets font:...${fs}px/${lh}px... -- ${fs}px is not one of the five legal sizes`);
      ok(lh % 4 === 0, `"${selector}" sets font:...${fs}px/${lh}px... -- line-height ${lh}px is not divisible by 4`);
    }
  }
  if (prop === "line-height" && /px$/.test(value.trim())) {
    const n = parseFloat(value);
    fontSizesChecked++;
    ok(n % 4 === 0, `"${selector}" sets line-height:${value.trim()} -- not divisible by 4`);
  }
}
for (const { f, src } of tsxSources) {
  for (const m of src.matchAll(/style=\{\{([^}]*)\}\}/g)) {
    for (const part of m[1].split(",")) {
      const c = part.indexOf(":");
      if (c < 0) continue;
      const key = part.slice(0, c).replace(/[^a-zA-Z]/g, "").toLowerCase();
      if (key !== "fontsize") continue;
      const n = parseFloat(part.slice(c + 1));
      if (Number.isNaN(n)) continue;
      fontSizesChecked++;
      ok(FONT_SIZES.has(n), `${f}: fontSize: ${part.slice(c + 1).trim()} -- not one of the five legal sizes`);
    }
  }
}
ok(fontSizesChecked > 20, `the font-size scan actually found rules to check (${fontSizesChecked})`);

// -- margin-left/margin-inline-start:auto, banned outright ------------------
// In the in-scope CSS (the rail/page/plate system) and renderer.css: the
// property itself must never be set to auto. Elsewhere in theme.css (the
// excluded chat/queue/records sections' .msg.right, .p-tag, .qc-tok, .rec-n)
// and in voice.css/scribe.css, the SAME idiom survives as pre-Vernier flex
// alignment unrelated to RULE B's actual concern (the rail's trailing chrome
// reaching its own spine) -- named here, not silently passed over, and left
// alone for the same reason the rest of those sections are.
for (const { selector, prop, value } of declarations(cssScope)) {
  if (prop !== "margin-left" && prop !== "margin-inline-start") continue;
  ok(!/^auto$/.test(value.trim()), `"${selector}" sets ${prop}:auto -- RULE B bans this outright`);
}
ok(/margin-left:auto/.test(themeCss), "sanity: margin-left:auto still exists somewhere in theme.css's excluded legacy sections (the check above is not vacuous)");

for (const { f, src } of tsxSources) {
  ok(!/marginLeft:\s*["']auto["']/.test(src), `${f}: marginLeft:"auto" -- RULE B bans this outright`);
  ok(!/marginInlineStart:\s*["']auto["']/.test(src), `${f}: marginInlineStart:"auto" -- RULE B bans this outright`);
}

// -- shared class-token extraction, from a real parse of the attribute value,
// not a `[^}]*` scan that stops at the first `}` a template's own ${...}
// contains (that bug would truncate `${STYLE[style] ?? "b-mute"}` before its
// closing brace and silently drop the fallback). Used below both by the
// .ml-auto check and by the class census. --------------------------------
//
// A className built from a template literal is walked, not grepped: its
// static text is a token run same as a plain string; each ${...} is resolved
// as far as it honestly can be --
//   - a ternary/nullish branch that is itself a string literal (the common
//     case throughout this renderer: `active ? " on" : ""`),
//   - a nested template literal (recursed, so `${size ? `${size}` : ""}`
//     walks into the inner `${size}` the same way as the outer one), and
//   - what is left after both of those is a bare identifier the census
//     cannot evaluate by itself. If it is one, this asks what TYPE it was
//     declared with in the SAME file: a parameter typed as a union of string
//     literals (icons.tsx's `size?: "sm" | "lg"`) names every value it can
//     ever hold. That is a rule about the language the class was built with,
//     not a memory of which class icons.tsx happens to interpolate today --
//     the honest alternative to hard-coding "sm"/"lg" into a list.
function splitTemplate(content: string): { statics: string[]; subs: string[] } {
  const statics: string[] = [];
  const subs: string[] = [];
  let i = 0, last = 0;
  while (i < content.length) {
    if (content[i] === "$" && content[i + 1] === "{") {
      statics.push(content.slice(last, i));
      let depth = 1, j = i + 2;
      while (j < content.length && depth > 0) {
        if (content[j] === "{") depth++;
        else if (content[j] === "}") depth--;
        j++;
      }
      subs.push(content.slice(i + 2, j - 1));
      i = j; last = j;
    } else i++;
  }
  statics.push(content.slice(last));
  return { statics, subs };
}
function unionLiteralsFor(fileSrc: string, ident: string): string[] {
  const m = new RegExp(`\\b${ident}\\??:\\s*((?:"[^"]*"|'[^']*')(?:\\s*\\|\\s*(?:"[^"]*"|'[^']*'))*)`).exec(fileSrc);
  return m ? [...m[1].matchAll(/"([^"]*)"|'([^']*)'/g)].map((mm) => mm[1] ?? mm[2] ?? "") : [];
}
function literalsFromTemplate(content: string, fileSrc: string): string[] {
  const { statics, subs } = splitTemplate(content);
  const out: string[] = [...statics];
  for (const sub of subs) {
    for (const m of sub.matchAll(/[?:]\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g)) out.push(m[1].slice(1, -1));
    for (const m of sub.matchAll(/`([^`]*)`/g)) out.push(...literalsFromTemplate(m[1], fileSrc));
    const bare = sub.trim();
    if (/^[A-Za-z_$][\w$]*$/.test(bare)) out.push(...unionLiteralsFor(fileSrc, bare));
  }
  return out;
}
// className="literal" is a complete, static class list. className={EXPR} is
// found with a balanced-brace walk (the bug above, avoided); EXPR is then
// either one whole template literal (walked per literalsFromTemplate) or a
// bare ternary between complete strings (`inline ? "mod inline" : "mod"`,
// OperationPanel.tsx and abha/Journey.tsx's only shape), where every quoted
// branch is simply a full className value.
function classTokens(src: string): Set<string> {
  const tokens = new Set<string>();
  const add = (text: string) => { for (const tok of text.split(/\s+/)) if (tok) tokens.add(tok); };
  for (const m of src.matchAll(/className="([^"]*)"/g)) add(m[1]);
  for (const m of src.matchAll(/className=\{/g)) {
    let depth = 1, j = m.index! + m[0].length;
    while (j < src.length && depth > 0) {
      if (src[j] === "{") depth++;
      else if (src[j] === "}") depth--;
      j++;
    }
    const expr = src.slice(m.index! + m[0].length, j - 1);
    if (expr.startsWith("`") && expr.endsWith("`")) {
      for (const lit of literalsFromTemplate(expr.slice(1, -1), src)) add(lit);
    } else {
      for (const t of expr.matchAll(/"([^"]*)"|'([^']*)'/g)) add(t[1] ?? t[2] ?? "");
    }
  }
  return tokens;
}
const tsxClassTokens = tsxSources.map(({ f, src }) => ({ f, tokens: classTokens(src) }));
ok(!/\.ml-auto\s*\{/.test(themeCss), "the .ml-auto utility class has no definition left in theme.css");
for (const { f, tokens } of tsxClassTokens) ok(!tokens.has("ml-auto"), `${f} still uses className="...ml-auto..."`);

// -- assertion 12: THE CLASS CENSUS --------------------------------------
// Replaces DEAD_CLASSES, a literal array of 21 remembered names: it caught
// exactly what someone remembered to list, and every class deleted after it
// was last edited was invisible to it -- which is how this branch shipped
// two redesigns that deleted real chrome while the gate stayed green. A
// census asks a RULE instead of consulting a memory: every className token a
// .tsx/.ts (a .check.ts excepted, see below) grants has a rule in some .css
// under web/src, and every class a selector in some .css names is granted by
// something in web/src. Both directions, no exclusion list, because a class
// exists or it does not -- unlike the spacing scale there is no legacy-debt
// argument for narrowing this one.
//
// SOURCE SCOPE: every .tsx/.ts under web/src except a .check.ts. A .check.ts
// is read here as TEXT (this file reads OperationPanel.tsx as a string
// elsewhere in the repo the same way), so a class name appearing only inside
// one -- a selector under test, not a class this renderer ever grants an
// element -- must not count as a call site. voice.check.ts's own `.sm`/`.on`
// -style assertions-by-name would otherwise launder a real orphan through
// the test that is supposed to catch it.
function allSource(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(root + dir, { withFileTypes: true })) {
    if (e.isDirectory()) out.push(...allSource(`${dir}/${e.name}`));
    else if (/\.tsx?$/.test(e.name) && !e.name.endsWith(".check.ts")) out.push(`${dir}/${e.name}`);
  }
  return out;
}
const censusSources = allSource("web/src").map((f) => ({ f, tokens: classTokens(read(f)) }));
ok(censusSources.length >= 15, `the census actually found source files to scan (${censusSources.length})`);
const usedNames = new Map<string, string[]>(); // class -> files that grant it
for (const { f, tokens } of censusSources) for (const t of tokens) usedNames.set(t, [...(usedNames.get(t) ?? []), f]);

// CSS SCOPE: every .css under web/src, no exclusion (unlike cssScope above).
// A selector list is walked with real brace-matching, not the flat
// `([^{}]+)\{([^{}]*)\}` scan `declarations()` uses above -- that one mis-
// parses `@media(...){ :root{...} }`, fine for a props-only scan but wrong
// for reading the SELECTOR of a nested rule. @-rules (`@media`, `@keyframes`)
// are recursed into rather than read as selectors; their own preludes name
// no class. Each comma-branch of a selector list is one independent "rule
// occurrence" (renderer.css's `.plate .mgrid,\n.plate .tasklist { ... }` is
// two, not one), because each names a different, independently reachable
// class chain.
function ruleSelectors(css: string): string[] {
  const noComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const out: string[] = [];
  (function walk(s: string) {
    let depth = 0, start = 0;
    for (let j = 0; j < s.length; j++) {
      if (s[j] !== "{" || depth !== 0) { if (s[j] === "{") depth++; else if (s[j] === "}") depth--; continue; }
      const prelude = s.slice(start, j).trim();
      let d = 1, k = j + 1;
      while (k < s.length && d > 0) {
        if (s[k] === "{") d++;
        else if (s[k] === "}") d--;
        k++;
      }
      const inner = s.slice(j + 1, k - 1);
      if (prelude.startsWith("@")) walk(inner);
      else if (prelude) out.push(prelude);
      start = k; j = k - 1;
    }
  })(noComments);
  return out;
}
const classesIn = (selector: string) => [...selector.matchAll(/\.([A-Za-z_-][\w-]*)/g)].map((m) => m[1]);
function findCssFiles(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(root + dir, { withFileTypes: true })) {
    if (e.isDirectory()) out.push(...findCssFiles(`${dir}/${e.name}`));
    else if (e.name.endsWith(".css")) out.push(`${dir}/${e.name}`);
  }
  return out;
}
type Rule = { file: string; selector: string; classes: string[] };
const rules: Rule[] = [];
for (const f of findCssFiles("web/src")) {
  for (const prelude of ruleSelectors(read(f))) {
    for (const sel of prelude.split(",").map((s) => s.trim()).filter(Boolean)) {
      const classes = classesIn(sel);
      if (classes.length) rules.push({ file: f, selector: sel, classes });
    }
  }
}
ok(rules.length > 100, `the census actually found CSS class rules to check (${rules.length})`);
const declaredNames = new Set<string>();
for (const r of rules) for (const c of r.classes) declaredNames.add(c);

// DIRECTION 1: every used class has a rule somewhere. THIRD-PARTY EXCEPTION,
// named rather than remembered: the ABHA SDK paints its own DOM node (the
// mount div Journey.tsx hands it, styled from its own vendor stylesheet, see
// abha/abha.css's header comment) and grants classes this repo never writes
// down in either direction -- so it never reaches usedNames or declaredNames
// at all, and needs no exemption here. Nothing else in this renderer paints
// a class it did not itself declare, so no other exemption exists.
for (const [name, files] of usedNames) {
  ok(declaredNames.has(name), `className "${name}" (used in ${files.join(", ")}) has no rule in any .css under web/src`);
}

// DIRECTION 2: every declared class has a call site.
for (const r of rules) {
  const missing = r.classes.filter((c) => !usedNames.has(c));
  ok(missing.length === 0, `${r.file}: "${r.selector}" has no call site (never granted: ${missing.join(", ")})`);
}

// -- assertion 9 (RULE B), as a real proxy: the three inset owners and their
// row-level family -----------------------------------------------------
// RULE B names three owners (the rail body, the page, the plate) and, for
// the plate, its own row family shares the SAME token across every row type
// (header, body row, the six-row cap's "+N more", the standalone queue row
// and its action line) -- theme.css's own comment says as much: "--inset-
// plate 20px -- every row inside a plate, header rows included". This is
// NOT a claim that every selector anywhere may never declare padding (a
// button or a badge legitimately owns its own): it is the named list of
// selectors whose job IS to reach the spine, checked against the actual
// measured defects (.card-h{padding:12px 14px}, the five sidebar insets).
// .plate-h is the one deliberate exception, and the spec names it by hand:
// its padding-inline-START is not the row inset at all, it is clearance for
// the absolutely-positioned drag handle (60px = --inset-plate + the handle's
// own 28px + the gap before the title), so only its END -- the side that
// actually has to agree with every other row's right edge -- is required to
// be the token. Carved out by name, not by loosening the rule for everyone.
const INSET_OWNERS: { selector: string; token: string; only?: string }[] = [
  { selector: ".rail-body", token: "--inset-rail" },
  { selector: ".topbar", token: "--inset-content" },
  { selector: ".view", token: "--inset-content" },
  { selector: ".plate-h", token: "--inset-plate", only: "padding-inline-end" },
  { selector: ".plate-row", token: "--inset-plate" },
  { selector: ".plate-more", token: "--inset-plate" },
  { selector: ".plate-empty", token: "--inset-plate" },
  { selector: ".qrow", token: "--inset-plate" },
  { selector: ".qact", token: "--inset-plate" },
];
const HORIZONTAL_PADDING = new Set(["padding", "padding-inline", "padding-left", "padding-right",
  "padding-inline-start", "padding-inline-end"]);
const allDecls = declarations(themeCss + "\n" + rendererCss);
let insetOwnersChecked = 0;
for (const { selector, token, only } of INSET_OWNERS) {
  const rows = allDecls.filter((d) => d.selector.split(",").map((s) => s.trim()).includes(selector) &&
    HORIZONTAL_PADDING.has(d.prop) && (!only || d.prop === only));
  ok(rows.length > 0, `"${selector}" declares${only ? ` a ${only}` : " a horizontal padding"} somewhere (the check is not vacuous for this selector)`);
  for (const { prop, value } of rows) {
    insetOwnersChecked++;
    const v = value.trim();
    ok(v === "0" || v.includes(`var(${token})`), `"${selector}" sets ${prop}:${v} -- must be 0 or var(${token}), never a padding it declares itself`);
  }
}
ok(insetOwnersChecked >= INSET_OWNERS.length, `every named inset owner was actually checked (${insetOwnersChecked})`);

// -- assertion 5, as a proxy: the handle has no layout box ------------------
// A real DOM measurement ("removing the handle changes the header's height
// by 0px") needs a browser. What a text check CAN prove is the CSS
// declaration that is SUPPOSED to make that true: the handle is
// position:absolute (removed from flow, so it cannot contribute to its
// parent's height by construction), and the header's own height is the
// literal 44 the vertical-rhythm section names -- reserved by the header's
// OWN padding-inline-start, not by the handle's box.
const plateHandleRule = /\.plate-handle\{([^}]*)\}/.exec(themeCss)?.[1] ?? "";
ok(/position:\s*absolute/.test(plateHandleRule), ".plate-handle is position:absolute (no layout box to inflate the header)");
const plateHRule = /\.plate-h\{([^}]*)\}/.exec(themeCss)?.[1] ?? "";
ok(/height:\s*44px/.test(plateHRule), ".plate-h's own height is the literal 44px the vertical-rhythm section names");
ok(/padding-inline-start/.test(plateHRule), ".plate-h reserves the handle's clearance with its own padding, not the handle's box");

// -- assertion 11, as a proxy: nothing reflows on collapse ------------------
// "sample the main column's width across 20 frames" needs a browser. What
// this file can prove is the CSS declaration a browser would be reading:
// .sb sets no transition on width at all (transition:none, not merely a 0s
// duration that a later rule could override), and .nv's hover has no
// transition either -- so there is nothing FOR a browser to sample a
// mid-transition frame from.
const sbRule = /(?<![\w-])\.sb\{([^}]*)\}/.exec(themeCss)?.[1] ?? "";
ok(/transition:\s*none/.test(sbRule), ".sb sets transition:none -- there is no width animation for a frame to be sampled mid-flight");
const nvRule = /(?<![\w-])\.nv\{([^}]*)\}/.exec(themeCss)?.[1] ?? "";
ok(/transition:\s*none/.test(nvRule), ".nv sets transition:none -- hover has no transition duration to disagree with 0ms");

// -- the signature: the token stub actually holds eight mono glyphs --------
//
// "The stub never wraps" needs a browser and a loaded font to measure for
// real (a .check.ts may not load either). What this file CAN prove is the
// arithmetic the spec's own sizing claims: --stub-w minus the stub's own
// padding-right is the content box a glyph run has to fit in, and eight
// glyphs of the SHIPPED mono face (measured live against both bundles:
// 8.2159px/glyph at 13px, i.e. 0.632em, not the ~0.6em generic-mono advance
// the spec assumed) must fit inside it. This is the exact defect the
// laboratory bundle's "25-0417" exposed (a 44px, then a 64px/13px stub, both
// measurably wrapped to two lines) and 0.632 is a NAMED constant carrying
// that live measurement, not a guess. Checked for both .stub and .rail-stub,
// since the signature runs down every list in the product.
const STUB_GLYPH_ADVANCE_EM = 0.632; // measured: 8.2159px / 13px, "Atkinson Hyperlegible Mono" 500
const rootVars = /:root\{([\s\S]*?)\n\}/.exec(themeCss)![1];
const stubW = parseFloat(/--stub-w:\s*(\d+(?:\.\d+)?)px/.exec(rootVars)?.[1] ?? "NaN");
ok(Number.isFinite(stubW), "--stub-w is declared as a px value in :root");
for (const sel of [".stub", ".rail-stub"]) {
  const rule = new RegExp(`(?<![\\w-])${sel.replace(".", "\\.")}\\{([^}]*)\\}`).exec(themeCss)?.[1] ?? "";
  ok(rule.length > 0, `"${sel}" has a rule in theme.css`);
  const padMatch = /padding-right:\s*(\d+(?:\.\d+)?)px/.exec(rule);
  ok(padMatch, `"${sel}" declares its own padding-right in px (content box is border-box, so this eats into --stub-w)`);
  const padRight = parseFloat(padMatch?.[1] ?? "NaN");
  const fontMatch = /font:\s*\d+\s+(\d+(?:\.\d+)?)px\/(\d+(?:\.\d+)?)px/.exec(rule);
  ok(fontMatch, `"${sel}" declares its font-size via the font shorthand`);
  const fontSize = parseFloat(fontMatch?.[1] ?? "NaN");
  const contentBox = stubW - padRight;
  const glyphRun = 8 * fontSize * STUB_GLYPH_ADVANCE_EM;
  ok(contentBox >= glyphRun,
    `"${sel}": --stub-w(${stubW}) - padding-right(${padRight}) = ${contentBox}px must hold eight glyphs at ${fontSize}px ` +
    `(${glyphRun.toFixed(2)}px at the shipped face's measured 0.632em advance) -- it wraps otherwise, silently, on any ` +
    `identifier eight glyphs long (the laboratory bundle's own "25-0417" is seven)`);
  ok(/white-space:\s*nowrap/.test(rule),
    `"${sel}" sets white-space:nowrap, so an identifier that still overflows does so visibly, not as a silent second line`);
}

console.log(`ok   layout: ${checks} checks`);
