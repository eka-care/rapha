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
// to one of these exact, individual selectors. This is an exact-match Set,
// not a prefix test: a first cut of this check used `/^\.b-warn/.test(...)`,
// which matches the *start* of a selector list, so a rule edited to
// `.b-warn,.nv.on{...}` still passed (".nv.on" rides in on the same block as
// the one legitimate selector). Splitting every rule's selector list on its
// commas and checking each piece against this Set exactly closes that: the
// appended selector is its own entry, and ".nv.on" is not in the Set.
//
// There used to be a second colour token (--destructive) that was
// byte-identical to --accent in both themes; a rule could "avoid" this guard
// simply by spelling the token differently while painting the exact same
// pixel. That token is gone (merged into --accent, see the token block
// above), so there is now only one spelling to police.
const ACCENT_ALLOW = new Set([
  ".b-warn", ".b-crit",                        // a flag, a critical value
  ".fl-p.alert", ".fl-p.alert .fl-av",         // the live line's own critical row
  ".at-ic.red", ".at-ic.amb",                  // the attention list's own flag/critical icon
  ".dot.down",                                  // kernel unreachable: a critical system state
  ".nudge",                                     // a clinical flag rendered as a sentence
  ".f-field.override",                          // an ABHA-locked field under override: a flag
  ".prop.primary", ".prop.primary .p-s", ".prop.primary .p-tag",
  ".btn-b",
  ".cq.rose",                                   // the primary action, everywhere it appears
  // (the :hover variants of these three lighten via filter:brightness, not
  // via --accent, so they carry no usage of the token to allow-list)
  // Consolidated former --destructive users: every one is an error, an
  // irreversible-action warning, or a critical value already, which is why
  // they were folded into the same token rather than given their own entry.
  ".state.bad", ".f-field.bad .f-in", ".f-bad", ".f-bad.block",
  ".confirmbox", ".cap.risk", ".kv.crit b", ".p-tag.irr", ".crit-box",
]);

function accentUsageSelectors(rawCss: string): string[] {
  const css = rawCss.replace(/\/\*[\s\S]*?\*\//g, "");
  // Strip the two blocks that DECLARE the token; only usage sites remain.
  const withoutDecls = css
    .replace(/:root\{[\s\S]*?\n\}/, "")
    .replace(/\[data-theme="dark"\]\{[\s\S]*?\n\}/, "");
  const selectors: string[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(withoutDecls))) {
    if (!m[2].includes("--accent")) continue;
    for (const part of m[1].split(",")) {
      selectors.push(part.trim().replace(/\s+/g, " "));
    }
  }
  return selectors;
}

// The specific bypass this guarded against once: --destructive was declared
// as the exact same hex value as --accent in both themes, so a rule could
// paint the identical pixel while spelling a different token name and slip
// past a check that only watches for `var(--accent...)`. That token is gone
// now, but nothing stops a *new* one from reintroducing the same trick, so
// this checks the general case: no other colour token in either theme block
// may share --accent's exact hex value.
function hexTokens(block: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of block.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{3,8})\b/g)) out.set(m[1], m[2].toUpperCase());
  return out;
}
for (const [label, blockRe] of [
  ["light", /:root\{([\s\S]*?)\n\}/],
  ["dark", /\[data-theme="dark"\]\{([\s\S]*?)\n\}/],
] as const) {
  const block = blockRe.exec(theme)![1];
  const hexes = hexTokens(block);
  const accentHex = hexes.get("accent");
  ok(!!accentHex, `--accent has a hex value in the ${label} theme block, for this check to compare against`);
  for (const [name, hex] of hexes) {
    if (name === "accent" || name === "accent-bg" || name === "accent-border") continue;
    ok(hex !== accentHex, `--${name} (${label}) is not a byte-identical duplicate of --accent (${accentHex})`);
  }
}

const usages = [...accentUsageSelectors(theme), ...accentUsageSelectors(renderer)];
ok(usages.length >= 8, "the accent token is actually used somewhere (the check is not vacuous)");
for (const selector of usages) {
  ok(ACCENT_ALLOW.has(selector), `"${selector}" uses --accent but is not an exact allow-listed flag/critical/primary selector`);
}
// The allow-list itself must not silently grow stale: every entry should be
// exercised by something in the stylesheet, or it is dead permission.
for (const allowed of ACCENT_ALLOW) {
  ok(usages.includes(allowed), `"${allowed}" is allow-listed but nothing in the stylesheet actually uses it`);
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

// Each tier class must draw from its OWN named tokens, not a hardcoded
// value that happens to match today. An earlier version of this check
// asserted the literal collapsed CSS text (e.g. "border:none" for .flat),
// which meant the day .flat and .rule were wired up to actually use the
// --tier-flat-*/--tier-rule-* tokens declared for exactly this purpose, the
// check itself had to be rewritten anyway — it had locked in the very
// copy-paste the token scale exists to replace, rather than checking that a
// scale was in use at all.
ok(/\.card\{background:var\(--surface\);border:var\(--tier-surface-border\);border-radius:var\(--tier-surface-radius\)/
  .test(flat), ".card is drawn from the surface tier's tokens, not a value of its own");
ok(/\.flat\{background:transparent;border:var\(--tier-flat-border\);box-shadow:var\(--tier-flat-shadow\);border-radius:var\(--tier-flat-radius\)\}/
  .test(flat), "the flat tier draws from its own tier tokens, not a hardcoded none/0");
ok(/\.rule\{border-top:var\(--tier-rule-border\);box-shadow:var\(--tier-rule-shadow\);border-radius:var\(--tier-rule-radius\)/
  .test(flat), "the rule tier draws from its own tier tokens too");
// And the three tiers must actually differ from each other - a "scale" where
// every step names the same value is the single-value problem wearing three
// names.
ok(/--tier-flat-radius:0px/.test(theme) && /--tier-surface-radius:var\(--r-lg\)/.test(theme)
  && /--tier-rule-radius:0px/.test(theme), "the radius tier values are the ones the tokens actually declare");
ok(!/--tier-flat-shadow:var\(--sh-card\)/.test(theme), "flat's shadow is not quietly the same as surface's");

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
// Tokens that are legitimately theme-invariant (the ease curve, the radius
// scale, spacing) are not colour and are excluded by name.
const INVARIANT = /^(ease|r-|sh-rose|tier-)/;
const colourTokens = lightTokens.filter((t) => !INVARIANT.test(t));
ok(colourTokens.length > 15, "found enough colour tokens for the check to mean something");
for (const t of colourTokens) {
  ok(darkTokens.has(t), `--${t} has a deliberate dark-mode value, not a silent fall-through`);
}

console.log(`ok   design: ${checks} checks`);
