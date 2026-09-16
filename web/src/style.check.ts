/** The colour system, made mechanical.
 *
 *  Run: node --experimental-strip-types src/style.check.ts   (from web/)
 *
 *  Three rules, and the reason each exists is a bug this repository actually
 *  shipped:
 *
 *  1. CONTAINMENT. tokens.css is the only file that may name a colour. The
 *     Vernier theme replaced the palette but not the components, so ~200 call
 *     sites went on spending names the new file no longer declared and the
 *     compatibility sweep that rescued them flattened every surface to the
 *     same two greys. If colour can only be written in one file, a palette
 *     swap is a diff in one file.
 *
 *  2. CONTRAST. The spec targets WCAG 2.2 AA (spec §68) and its own §48 light
 *     palette misses it: §62's status chips run 3.50-3.75:1 for 11px/600 text.
 *     A scribe banner shipped at 1.3:1 on this branch and nobody saw it until
 *     it was on screen. Arithmetic sees it before a person does.
 *
 *  3. COMPLETENESS. Every var() resolves. 34 tokens were deleted here once
 *     while ~240 references stayed, and the result was a modal with no panel
 *     and two severities that rendered identically.
 *
 *  WHAT THIS CANNOT DO. It reads CSS as text under plain node: no browser, no
 *  cascade, no layout. It cannot know which pair actually lands on screen, so
 *  PAIRS below is hand-maintained and each entry cites the spec section that
 *  puts that foreground on that background. A rule that paints text on a
 *  surface not listed here passes this check and can still fail a person.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(fileURLToPath(import.meta.url));
const TOKENS = join(SRC, "style", "tokens.css");
let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };

function cssFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (name === "node_modules") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...cssFiles(p));
    else if (name.endsWith(".css")) out.push(p);
  }
  return out;
}

/** Strip comments so a hex inside one is not a violation, and a token
 *  mentioned in prose is not a declaration. */
const decomment = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "");

// ---------------------------------------------------------------- 1. containment

const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color-mix)\s*\(/;

{
  const offenders: string[] = [];
  for (const file of cssFiles(SRC)) {
    if (file === TOKENS) continue;
    decomment(readFileSync(file, "utf8")).split("\n").forEach((line, i) => {
      if (COLOUR.test(line)) offenders.push(`${relative(SRC, file)}:${i + 1}: ${line.trim()}`);
    });
  }
  assert.deepEqual(offenders, [],
    "only style/tokens.css may name a colour; move these into a token:\n  " + offenders.join("\n  "));
  ok("containment: no colour literal outside style/tokens.css");
}

// ---------------------------------------------------------------- parse tokens

/** name -> value, per theme. Light is bare :root. Dark is whatever sits under
 *  [data-theme="dark"]; the prefers-color-scheme block must repeat it, which
 *  is asserted separately below rather than merged away here. */
function block(css: string, selector: string): Record<string, string> {
  const at = css.indexOf(selector);
  assert.notEqual(at, -1, `tokens.css has no ${selector} block`);
  const open = css.indexOf("{", at);
  let depth = 0, end = open;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}" && --depth === 0) { end = i; break; }
  }
  const out: Record<string, string> = {};
  for (const m of css.slice(open + 1, end).matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

const tokensRaw = decomment(readFileSync(TOKENS, "utf8"));
const light = block(tokensRaw, ":root");
const darkOnly = block(tokensRaw, '[data-theme="dark"]');
const dark = { ...light, ...darkOnly };

// ---------------------------------------------------------------- 2. contrast

function srgb(hex: string): [number, number, number] {
  const h = hex.trim().replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  assert.match(full, /^[0-9a-fA-F]{6}$/, `not a plain hex colour: ${hex}`);
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255) as [number, number, number];
}
const lum = (hex: string) =>
  srgb(hex).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    .reduce((a, c, i) => a + [0.2126, 0.7152, 0.0722][i] * c, 0);
function ratio(fg: string, bg: string) {
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/** Each entry: [foreground token, background token, minimum, why].
 *  4.5 is AA for text under 18pt. 3.0 is AA for borders, focus rings and
 *  other non-text (WCAG 2.2 SC 1.4.11). */
const PAIRS: [string, string, number, string][] = [
  // body and metadata on each of the three grounds a surface can be (§48)
  ["--color-text-primary",   "--color-bg-surface",   4.5, "§55 message body"],
  ["--color-text-primary",   "--color-bg-canvas",    4.5, "§51 body"],
  ["--color-text-primary",   "--color-bg-subtle",    4.5, "§53 sidebar nav"],
  ["--color-text-primary",   "--color-bg-selected",  4.5, "§53 nav active"],
  ["--color-text-primary",   "--color-bg-rail",      4.5, "sidebar ground"],
  ["--color-text-secondary", "--color-bg-rail",      4.5, "sidebar nav item"],
  ["--color-text-tertiary",  "--color-bg-rail",      4.5, "sidebar section label"],
  ["--color-eyebrow",        "--color-bg-surface",   4.5, "card eyebrow, 10px"],
  ["--color-eyebrow",        "--color-tint-warm",    4.5, "hero eyebrow on its tint"],
  ["--color-text-secondary", "--color-bg-surface",   4.5, "§55 message body"],
  ["--color-text-secondary", "--color-bg-canvas",    4.5, "§53 nav item"],
  ["--color-text-secondary", "--color-bg-subtle",    4.5, "§53 nav item"],
  ["--color-text-secondary", "--color-bg-hover",     4.5, "§53 nav hover"],
  ["--color-text-tertiary",  "--color-bg-surface",   4.5, "§55 message-meta, 12px"],
  ["--color-text-tertiary",  "--color-bg-canvas",    4.5, "§58 composer placeholder"],
  ["--color-text-tertiary",  "--color-bg-subtle",    4.5, "§56 object header, 11px"],
  // §62 status chips: 11px/600 text on its OWN soft ground, the tightest case
  ["--color-success",        "--color-success-soft", 4.5, "§62 success chip"],
  ["--color-warning",        "--color-warning-soft", 4.5, "§62 warning chip"],
  ["--color-critical",       "--color-critical-soft",4.5, "§62 critical chip"],
  ["--color-agent",          "--color-agent-soft",   4.5, "§62 agent chip"],
  ["--color-abdm",           "--color-abdm-soft",    4.5, "§27 ABHA event"],
  // the same inks on ordinary ground (§59 recording label, §21 agent line)
  ["--color-critical",       "--color-bg-surface",   4.5, "§59 recording label"],
  ["--color-agent",          "--color-bg-surface",   4.5, "§21 agent attribution"],
  ["--color-success",        "--color-bg-surface",   4.5, "§27 confirmed"],
  ["--color-warning",        "--color-bg-surface",   4.5, "§33 attention"],
  ["--color-abdm",           "--color-bg-surface",   4.5, "§38 ABHA linked"],
  // non-text: borders and the focus ring (§51, §47)
  ["--color-border-control", "--color-bg-surface",   3.0, "§58 composer boundary (SC 1.4.11)"],
  ["--color-border-control", "--color-bg-canvas",    3.0, "§58 composer boundary (SC 1.4.11)"],
  ["--color-border-control", "--color-bg-subtle",    3.0, "§53 sidebar controls"],
  ["--color-agent",          "--color-bg-canvas",    3.0, "§51 :focus-visible ring"],
  ["--color-agent",          "--color-bg-surface",   3.0, "§51 :focus-visible ring"],
];

{
  let tightest = { at: Infinity, what: "" };
  for (const [theme, tokens] of [["light", light], ["dark", dark]] as const) {
    for (const [fg, bg, min, why] of PAIRS) {
      assert.ok(tokens[fg], `${theme}: ${fg} is not declared (${why})`);
      assert.ok(tokens[bg], `${theme}: ${bg} is not declared (${why})`);
      const r = ratio(tokens[fg], tokens[bg]);
      assert.ok(r >= min,
        `${theme}: ${fg} on ${bg} is ${r.toFixed(2)}:1, needs ${min}:1 — ${why}`);
      const slack = r / min;
      if (slack < tightest.at) tightest = { at: slack, what: `${theme} ${fg} on ${bg} = ${r.toFixed(2)}:1 (needs ${min})` };
    }
  }
  ok(`contrast: ${PAIRS.length} pairs x 2 themes clear WCAG 2.2 AA`);
  console.log("     tightest: " + tightest.what);
}

{
  // A dark value declared only under [data-theme="dark"] leaves the system
  // default ("no attribute stamped, browser set to dark") on the light
  // palette. The media block must carry the same names.
  const media = tokensRaw.slice(tokensRaw.indexOf("prefers-color-scheme: dark"));
  assert.notEqual(media, "", "tokens.css has no prefers-color-scheme block");
  const missing = Object.keys(darkOnly).filter((n) => !media.includes(n + ":"));
  assert.deepEqual(missing, [],
    "declared under [data-theme=dark] but not in the prefers-color-scheme block, " +
    "so a viewer on system-dark sees the light value: " + missing.join(", "));
  ok("dark: every dark token is also in the prefers-color-scheme block");
}

// ---------------------------------------------------------------- 3. completeness

{
  const declared = new Set(Object.keys(light));
  for (const n of Object.keys(dark)) declared.add(n);
  const dangling: string[] = [];
  for (const file of cssFiles(SRC)) {
    decomment(readFileSync(file, "utf8")).split("\n").forEach((line, i) => {
      for (const m of line.matchAll(/var\((--[a-z0-9-]+)/g)) {
        if (!declared.has(m[1])) dangling.push(`${relative(SRC, file)}:${i + 1}: ${m[1]}`);
      }
    });
  }
  assert.deepEqual(dangling, [],
    "var() naming a token tokens.css does not declare; a browser drops the " +
    "whole declaration and the rule renders unstyled:\n  " + dangling.join("\n  "));
  ok("completeness: every var() resolves to a declared token");
}

console.log(`\n${checks} checks passed`);
