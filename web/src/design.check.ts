/** Task 7's visual system: one accent that only ever means "needs you", a
 *  three-step radius/border/shadow scale instead of one value everywhere,
 *  Khoj centred in the header by layout rather than by a margin, and the
 *  "Use demo data" control gone for good.
 *
 *  Run: node --experimental-strip-types src/design.check.ts   (from web/)
 *
 *  Same technique as shell.check.ts and tasklist.check.ts: read the CSS and
 *  the renderer sources back as text and assert against them, because a
 *  `.check.ts` may never import a `.tsx` or load a browser. What this catches
 *  that eyeballing a screenshot would not: a future rule quietly reaching for
 *  `--accent` to make something look nice (a hover state, a chip, a label)
 *  rather than to mean "needs you", which is exactly the drift that put five
 *  unrelated colours on the old Home page in the first place.
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

// -- one accent, scoped to flag / critical / primary, nowhere else ---------
//
// Every rule block that USES the token (`var(--accent...)`) rather than just
// declaring it (`--accent:` inside :root or [data-theme="dark"]) must belong
// to one of those three categories. The category names below are the actual
// selectors this codebase uses for a flag, a critical, or a primary action;
// a new one is added here deliberately, not inferred, so this stays a review
// gate rather than a rubber stamp.
const ACCENT_ALLOW = [
  /^\.b-warn/, /^\.b-crit/,             // a flag, a critical value
  /^\.fl-p\.alert/,                      // the live line's own critical row
  /^\.at-ic\.red/, /^\.at-ic\.amb/,      // the attention list's own flag/critical icon
  /^\.dot\.down/,                        // kernel unreachable: a critical system state
  /^\.nudge/,                            // a clinical flag rendered as a sentence
  /^\.f-field\.override/,                // an ABHA-locked field under override: a flag
  /^\.prop\.primary/, /^\.btn-b/, /^\.cq\.rose/, // the primary action, everywhere it appears
];

function accentUsageBlocks(rawCss: string): { selector: string; body: string }[] {
  const css = rawCss.replace(/\/\*[\s\S]*?\*\//g, "");
  // Strip the two blocks that DECLARE the token; only usage sites remain.
  const withoutDecls = css
    .replace(/:root\{[\s\S]*?\n\}/, "")
    .replace(/\[data-theme="dark"\]\{[\s\S]*?\n\}/, "");
  const blocks: { selector: string; body: string }[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(withoutDecls))) {
    if (m[2].includes("--accent")) blocks.push({ selector: m[1].trim(), body: m[2] });
  }
  return blocks;
}

const usages = [...accentUsageBlocks(theme), ...accentUsageBlocks(renderer)];
ok(usages.length >= 8, "the accent token is actually used somewhere (the check is not vacuous)");
for (const { selector } of usages) {
  const allowed = ACCENT_ALLOW.some((re) => re.test(selector));
  ok(allowed, `"${selector}" uses --accent but is not a declared flag/critical/primary selector`);
}

// -- three-step scale: radius, border and shadow are named tiers, not one
// hardcoded value copy-pasted onto every box -------------------------------
ok(/--tier-flat-radius/.test(theme) && /--tier-surface-radius/.test(theme) && /--tier-rule-radius/.test(theme),
  "three named radius tiers exist (flat, surface, rule)");
ok(/--tier-flat-shadow/.test(theme) && /--tier-surface-shadow/.test(theme) && /--tier-rule-shadow/.test(theme),
  "three named shadow tiers exist");
ok(/--tier-flat-border/.test(theme) && /--tier-surface-border/.test(theme) && /--tier-rule-border/.test(theme),
  "three named border tiers exist");
// Every rule below is matched against the CSS with ALL whitespace removed
// (including the spaces inside a value, e.g. "1px solid var(--border)"
// becomes "1pxsolidvar(--border)"), so the expected strings here must be
// written the same collapsed way.
const flat = theme.replace(/\s+/g, "");

// The default card is drawn from the surface tier, not a value of its own.
ok(/\.card\{background:var\(--surface\);border:var\(--tier-surface-border\);border-radius:var\(--tier-surface-radius\)/
  .test(flat), ".card is drawn from the surface tier's tokens");

// -- not every card is a card: the live line is flat, Recent is a rule -----
ok(/\.flat\{background:transparent;border:none;box-shadow:none;border-radius:0\}/.test(flat),
  "the flat tier has no box at all: no border, no shadow, no radius");
ok(/\.rule\{border-top:1pxsolidvar\(--border\);padding-top:10px\}/.test(flat),
  "the rule tier is a divider, not a surface");

// -- numbers are the largest thing after the greeting -----------------------
const numAfter = (label: string, re: RegExp): number => {
  const m = re.exec(theme) ?? re.exec(renderer);
  assert.ok(m, `could not find a font-size rule for ${label}`);
  return parseFloat(m![1]);
};
const greetSize = numAfter("the greeting", /\.greet\{font-size:(\d+(?:\.\d+)?)px/);
const metricSize = numAfter("a metric's number", /\.m-val\s*\{\s*font-size:(\d+(?:\.\d+)?)px/);
const taskSize = numAfter("a task's count", /\.task-n\s*\{\s*font-size:(\d+(?:\.\d+)?)px/);
const cardTitleSize = numAfter("a card title", /\.card-t\{font-size:(\d+(?:\.\d+)?)px/);
ok(greetSize > metricSize && greetSize > taskSize, "the greeting is larger than any number on the page");
ok(metricSize > cardTitleSize && taskSize > cardTitleSize, "a number is larger than a card title");

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

// -- "Use demo data" is gone, root and branch -------------------------------
// Checked against the working tree, not the git index: a deletion not yet
// staged still appears in `git ls-files`, but the file itself is gone.
ok(!existsSync(root + "web/src/mock.ts"), "web/src/mock.ts no longer exists");
const tracked = execFileSync("git", ["ls-files", "web/src"], { cwd: root, encoding: "utf8" })
  .split("\n")
  .filter((f) => /\.(tsx?|css)$/.test(f) && !f.endsWith(".check.ts") && existsSync(root + f));
ok(tracked.length > 5, "the check actually found renderer files to read");
for (const f of tracked) {
  const src = read(f);
  ok(!/Use demo data/.test(src), `${f} contains no "Use demo data" string`);
  ok(!/\bmockApi\b/.test(src), `${f} does not reference mockApi`);
}

// -- dark mode is deliberate: every light-mode token this file defines has a
// dark-mode override, not a silent fall-through to the light value ---------
const rootBlock = /:root\{([\s\S]*?)\n\}/.exec(theme)![1];
const darkBlock = /\[data-theme="dark"\]\{([\s\S]*?)\n\}/.exec(theme)![1];
const lightTokens = [...rootBlock.matchAll(/--([\w-]+):/g)].map((m) => m[1]);
const darkTokens = new Set([...darkBlock.matchAll(/--([\w-]+):/g)].map((m) => m[1]));
// Tokens that are legitimately theme-invariant (the ease curve, the radius
// scale, spacing) are not colour and are excluded by name.
const INVARIANT = /^(ease|r-|sh-rose|tier-)/;
const colourTokens = lightTokens.filter((t) => !INVARIANT.test(t));
ok(colourTokens.length > 15, "found enough colour tokens for the check to mean something");
for (const t of colourTokens) {
  ok(darkTokens.has(t), `--${t} has a deliberate dark-mode value, not a silent fall-through`);
}

console.log(`ok   design: ${checks} checks`);
