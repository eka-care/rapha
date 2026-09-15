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
import { toneOf } from "./tone.ts";

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

// -- no stylesheet spends a token :root never declares -----------------------
//
// var(--x) is invalid-at-computed-value-time when --x is undefined, which
// drops the WHOLE declaration, not just that one property -- this is what
// let a wholesale :root rewrite silently take the operation modal's panel,
// the scribe's recording banner and the kernel-reachability dot out from
// under their own rules while every existing check stayed green. Mutation-
// proof by construction: comment out any token :root declares and every one
// of its call sites fires here, across every stylesheet under web/src.
// Comments are stripped first so this docstring's own mention of "--x" (and
// theme.css's header, which lists the very names a past sweep left dangling)
// cannot trip it.
const definedTokens = new Set([...theme.matchAll(/--([\w-]+)\s*:/g)].map((m) => m[1]));
ok(definedTokens.size > 40, "found enough declared tokens for the dangling-token scan to mean something");
for (const file of [
  "web/src/theme.css", "web/src/renderer.css", "web/src/voice/voice.css",
  "web/src/scribe/scribe.css", "web/src/abha/abha.css",
]) {
  const noComments = read(file).replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of noComments.matchAll(/var\(\s*--([\w-]+)\s*\)/g)) {
    ok(definedTokens.has(m[1]),
      `${file} spends --${m[1]}, which no :root declares -- the declaration is dropped at computed-value time`);
  }
}

// -- CLAUSE ONE OF THE COLOUR LAW: "you are here" is not coloured -----------
//
// Carried over from group A (which rewrote this file before the sidebar
// block existed to check against): a nav row is never coloured for BEING
// Home or any other fixed view -- it is always that view, and a noun does
// not change shift to shift. The row that is currently SELECTED may be
// coloured, because selection moves. The old
// `.nv.on{background:var(--eka-blue-bg);color:var(--eka-blue)}` rule is the
// thing this replaces: a plain background/color fill on the bare selector is
// exactly "coloured for being here", so it must be gone, and whatever
// replaced it must carry the selected state some other way (a wash plus a
// bar, per the spec), not a --hand background fill. Checked against the
// comment-stripped stylesheet, the same way colourUsages() above does it, so
// a docstring that quotes the deleted rule for context (this file's own
// theme.css comment does exactly that) cannot trip either direction of this
// check.
const themeNoComments = theme.replace(/\/\*[\s\S]*?\*\//g, "");
const navOnRule = /(?:^|[};])\s*\.nv\.on\s*\{([^}]*)\}/.exec(themeNoComments)?.[1] ?? "";
ok(navOnRule.length > 0, "a .nv.on rule exists for the selected nav row");
ok(!/\.nv\.on\s*\{\s*background:\s*var\(--eka-blue-bg\)/.test(themeNoComments),
  "the old .nv.on{background:var(--eka-blue-bg)} rule (coloured for being current, not for being selected) is gone");
ok(!/background(?:-color)?:\s*var\(--hand\)/.test(navOnRule),
  "'you are here' is not coloured: .nv.on must not fill itself with --hand as a background");
ok(/box-shadow:[^;]*var\(--hand\)/.test(navOnRule),
  ".nv.on carries the selected row's --hand bar as a box-shadow (no layout box, no background fill)");
ok(/font-weight:\s*600/.test(navOnRule), ".nv.on carries the selected row's weight 600");

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
const lightDecls = [...rootBlock.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => ({ name: m[1], value: m[2].trim() }));
const darkTokens = new Set([...darkBlock.matchAll(/--([\w-]+):/g)].map((m) => m[1]));
// Tokens that are legitimately theme-invariant (the ease curve, the spacing
// scale, the inset/rail/stub geometry, the motion durations) are not colour
// and are excluded by name; Vernier's spec says as much in so many words:
// "every geometry and motion token is theme-invariant and is not
// redeclared". --sh-overlay/--sh-pop are colour (they carry alpha against a
// ground that flips), so they are deliberately NOT in this list and DO have
// to be redeclared below, which they are.
const INVARIANT = /^(ease|s\d+|inset-|rail-w|stub-w|dur-)/;
// A token whose own value is a literal colour (hex/rgb/hsl) can silently
// fall through to the wrong theme if [data-theme="dark"] forgets it -- that
// is the failure this check exists to catch. A token whose value is instead
// var(--other-token) cannot fall through: it has no colour of its own, it
// resolves whatever --other-token resolves to, which already carries (or is
// itself checked for) a deliberate dark value. The sweep's neutral/agency
// aliases (--surface, --gray-100, --eka-blue, ...) are exactly this shape by
// design, so they are correctly exempt, not silently exempted by name.
const isLiteralColour = (v: string) => /#[0-9a-fA-F]{3,8}\b/.test(v) || /\b(rgba?|hsla?)\(/.test(v);
const colourTokens = lightDecls.filter(({ name, value }) => !INVARIANT.test(name) && isLiteralColour(value));
ok(colourTokens.length > 15, "found enough colour tokens for the check to mean something");
for (const { name } of colourTokens) {
  ok(darkTokens.has(name), `--${name} has a deliberate dark-mode value, not a silent fall-through`);
}

// -- the colour law's arithmetic, RUN, not just read as text ----------------
//
// Every assertion above reads theme.css/renderer.css back as text, which is
// exactly why inverting or deleting toneOf's own body left this file (and
// every other .check.ts) green: toneOf lived in a .tsx, and a .check.ts may
// never import one. It now lives in ./tone.ts (a plain .ts, moved verbatim,
// re-exported from ViewRenderer.tsx so every existing import stays valid),
// so it can be imported and RUN here. A boundary table, both directions of
// the mutation proof the spec names: no declared threshold is vacuously
// monochrome (the laboratory bundle's own guarantee), and a declared one
// still colours -- so `return null` unconditionally fails the second
// assertion and `return "over"` unconditionally (ignoring decl) fails the
// first.
const longAgo = new Date(Date.now() - 6 * 3600_000).toISOString();
const soon = new Date(Date.now() + 3600_000).toISOString();
ok(toneOf(undefined, { opened_at: longAgo }) === null,
  "no declared view at all: no tone, however long the wait (the laboratory bundle's own guarantee)");
ok(toneOf({ target_minutes: null }, { opened_at: longAgo }) === null,
  "a null target_minutes is not a threshold: still no tone, however long the wait");
ok(toneOf({ target_minutes: 30 }, { opened_at: longAgo }) === "act",
  "a declared threshold still colours -- toneOf is not vacuously monochrome for every input");
ok(toneOf({ target_minutes: 30 }, { opened_at: new Date(Date.now() - 40 * 60_000).toISOString() }) === "over",
  "elapsed at 40 of a 30-minute target (before the default 60-minute escalation): over, not act");
ok(toneOf({ target_minutes: 30 }, { opened_at: new Date(Date.now() - 20 * 60_000).toISOString() }) === null,
  "elapsed at 20 of a 30-minute target: no tone yet");
ok(toneOf({ target_minutes: 30, escalate_minutes: 45 }, { opened_at: new Date(Date.now() - 50 * 60_000).toISOString() }) === "act",
  "a declared escalate_minutes overrides the 2x-target default");
ok(toneOf({ target_minutes: 30 }, { opened_at: soon }) === null,
  "a timestamp ahead of the clock (a future opened_at) is not a wait at all, not a negative one");

console.log(`ok   design: ${checks} checks`);
