/** The colour law's enforcement mechanism, and what survives of task 7's
 *  visual-system checks now that the accent/tier system it checked is gone.
 *
 *  Run: node --experimental-strip-types src/design.check.ts   (from web/)
 *
 *  Same technique as shell.check.ts and tasklist.check.ts: read the CSS and
 *  the renderer sources back as text and assert against them, because a
 *  `.check.ts` may never import a `.tsx` or load a browser.
 *
 *  CLAUSE TWO OF THE COLOUR LAW, MADE MECHANICAL: no CSS rule may use
 *  var(--over) or var(--act) unless EVERY selector in its list contains
 *  [data-over] or [data-act]. Those attributes are set in exactly one place
 *  in the renderer (ViewRenderer.tsx, a later group), from a declared
 *  threshold; deleting the declared field makes the attribute never set and
 *  the colour must vanish everywhere. This replaces task 7's ACCENT_ALLOW
 *  machinery, which matched a selector against the START of a comma list
 *  (`/^\.b-warn/`) rather than every entry in it -- a rule quietly edited to
 *  `.b-warn,.nv.on{...}` rode the allow-listed selector's permission in on
 *  the same block. Checking every comma-separated selector individually is
 *  what closes that hole; it is also why this check needs no allow-list at
 *  all: a selector either carries the gating attribute or it does not.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const theme = read("web/src/theme.css");
const renderer = read("web/src/renderer.css");

// -- the colour gate: every --over/--act usage, gated on every selector ----
//
// A "usage" is a declaration block whose body mentions var(--over) or
// var(--act). `\b` after the token name is what stops a future --overflow or
// --active token from being mistaken for a hit; there is no such token today,
// but the boundary costs nothing and removes the question later.
function colourUsages(rawCss: string): { selector: string; body: string }[] {
  const css = rawCss.replace(/\/\*[\s\S]*?\*\//g, "");
  const withoutDecls = css
    .replace(/:root\{[\s\S]*?\n\}/, "")
    .replace(/\[data-theme="dark"\]\{[\s\S]*?\n\}/, "");
  const usages: { selector: string; body: string }[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(withoutDecls))) {
    if (!/--over\b/.test(m[2]) && !/--act\b/.test(m[2])) continue;
    usages.push({ selector: m[1].trim().replace(/\s+/g, " "), body: m[2] });
  }
  return usages;
}

const gated = [...colourUsages(theme), ...colourUsages(renderer)];
ok(gated.length >= 1, "the colour gate is actually exercised somewhere (the check is not vacuous)");
for (const { selector, body } of gated) {
  const parts = selector.split(",").map((s) => s.trim());
  const allGated = parts.every((p) => p.includes("[data-over]") || p.includes("[data-act]"));
  ok(allGated,
    `"${selector}" uses --over/--act ("${body.trim()}") but not every selector in its ` +
    `comma list carries [data-over] or [data-act] -- one bare selector is enough to leak colour`);
}

// -- Khoj takes the centre of the header bar, by layout, not by a margin ---
const topbarRule = /\.topbar\{[^}]*\}/.exec(theme)?.[0] ?? "";
ok(/grid-template-columns:\s*1fr auto 1fr/.test(topbarRule),
  "the topbar is a three-column grid with equal side columns, so the middle column is genuinely centred");
ok(/\.khoj-trigger\{[^}]*justify-self:center/.test(theme), "Khoj's own trigger is placed in the centred column");
// The old trick: an empty `<div className="ml-auto" />` spacer pushed a
// search button to one side by consuming the other side's space. If that
// comes back, Khoj is "centred" only by coincidence of its neighbours'
// widths, not by the bar's own layout.
const main = read("web/src/main.tsx");
const topbarJsx = main.slice(main.indexOf('<div className="topbar">'), main.indexOf('<div className="topbar">') + 1200);
ok(!/ml-auto/.test(topbarJsx), "no ml-auto spacer sits in the topbar faking a centred layout");
ok(/khoj-trigger/.test(topbarJsx), "the topbar actually renders the centred Khoj trigger");

// -- there is no display face: the largest number on the page is a mono
// numeral rule, not a headline ----------------------------------------------
//
// task 7's version of this compared .greet against a metric's own number;
// .greet is gone (Vernier's rule is "no display face at all", not "a smaller
// one"), so this compares every font-size rule in the stylesheet against
// itself and asserts the winner is a tabular mono numeral, not prose.
function fontSizeRules(rawCss: string): { size: number; rule: string }[] {
  const css = rawCss.replace(/\/\*[\s\S]*?\*\//g, "");
  const out: { size: number; rule: string }[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css))) {
    const sizeMatch = /font-size:\s*(\d+(?:\.\d+)?)px/.exec(m[2]) ??
      /font:[^;]*?(?:^|\s)(\d+(?:\.\d+)?)px\//.exec(m[2]);
    if (!sizeMatch) continue;
    out.push({ size: parseFloat(sizeMatch[1]), rule: `${m[1].trim()}{${m[2].trim()}}` });
  }
  return out;
}
const sized = [...fontSizeRules(theme), ...fontSizeRules(renderer)];
ok(sized.length > 10, "found enough font-size rules for the check to mean something");
const maxSize = Math.max(...sized.map((r) => r.size));
const atMax = sized.filter((r) => r.size === maxSize);
for (const { rule } of atMax) {
  ok(/mono/i.test(rule), `the largest font-size in the stylesheet (${maxSize}px, "${rule}") is not a mono numeral rule`);
}
ok(!/\.greet\s*\{/.test(theme) && !/\.greet\s*\{/.test(renderer), "no .greet rule exists: a greeting is not the largest thing on the page any more");
// No uppercase above 11px: checked per rule block that declares both
// properties itself, the same text-only reach every other check here has.
for (const { rule } of sized) {
  if (!/text-transform:\s*uppercase/.test(rule)) continue;
  const size = parseFloat(/font-size:\s*(\d+(?:\.\d+)?)px/.exec(rule)![1]);
  ok(size <= 11, `"${rule}" sets text-transform:uppercase above the 11px floor`);
}

// -- "Use demo data" is gone, root and branch -------------------------------
// Checked against the working tree, not the git index: a deletion not yet
// staged still appears in `git ls-files`, but the file itself is gone.
//
// One assertion over the concatenation of every tracked renderer file, not
// one assertion per file: repeating the same string-absence check file by
// file inflates the count (it grows by two every time anyone adds an
// unrelated file) without adding rigour — a file that never mentioned demo
// data was never going to fail on its own. Concatenating first means a hit
// anywhere still fails the build, and says which file in its own message.
ok(!existsSync(root + "web/src/mock.ts"), "web/src/mock.ts no longer exists");
const tracked = execFileSync("git", ["ls-files", "web/src"], { cwd: root, encoding: "utf8" })
  .split("\n")
  .filter((f) => /\.(tsx?|css)$/.test(f) && !f.endsWith(".check.ts") && existsSync(root + f));
ok(tracked.length > 5, "the check actually found renderer files to read");
const bodies = tracked.map((f) => ({ f, src: read(f) }));
const demoHit = bodies.find(({ src }) => /Use demo data/.test(src));
ok(!demoHit, demoHit ? `${demoHit.f} still contains "Use demo data"` : "");
const mockHit = bodies.find(({ src }) => /\bmockApi\b/.test(src));
ok(!mockHit, mockHit ? `${mockHit.f} still references mockApi` : "");

// -- dark mode is deliberate: every light-mode token this file defines has a
// dark-mode override, not a silent fall-through to the light value ---------
const rootBlock = /:root\{([\s\S]*?)\n\}/.exec(theme)![1];
const darkBlock = /\[data-theme="dark"\]\{([\s\S]*?)\n\}/.exec(theme)![1];
const lightTokens = [...rootBlock.matchAll(/--([\w-]+):/g)].map((m) => m[1]);
const darkTokens = new Set([...darkBlock.matchAll(/--([\w-]+):/g)].map((m) => m[1]));
// Tokens that are legitimately theme-invariant (the ease curve, the spacing
// scale, the inset/rail/stub geometry, the motion durations) are not colour
// and are excluded by name; Vernier's spec says as much in so many words:
// "every geometry and motion token is theme-invariant and is not
// redeclared". --sh-overlay/--sh-pop are colour (they carry alpha against a
// ground that flips), so they are deliberately NOT in this list and DO have
// to be redeclared below, which they are.
const INVARIANT = /^(ease|s\d+|inset-|rail-w|stub-w|dur-)/;
const colourTokens = lightTokens.filter((t) => !INVARIANT.test(t));
ok(colourTokens.length > 15, "found enough colour tokens for the check to mean something");
for (const t of colourTokens) {
  ok(darkTokens.has(t), `--${t} has a deliberate dark-mode value, not a silent fall-through`);
}

console.log(`ok   design: ${checks} checks`);
