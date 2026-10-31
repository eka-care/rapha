/** The installable app, made mechanical.
 *
 *  Run: node --experimental-strip-types src/pwa.check.ts   (from web/)
 *
 *  One rule matters more than the rest and it is the reason this file exists.
 *
 *  A service worker is the only part of this product that can answer a
 *  clinical question without the kernel being asked. Everything else in the
 *  architecture funnels through the guard; a cache sits in front of it and
 *  answers from yesterday. So the line is absolute: the worker may cache the
 *  DECLARATIONS, which are compiled artifacts identical for every caller, and
 *  it may cache the application's own files. It may not cache one byte about
 *  a patient.
 *
 *  That line is a comment in sw.js and comments do not fail builds. Here the
 *  worker's own path patterns are lifted out and run against real paths from
 *  this product's route table, so a fourth pattern added in a hurry that
 *  happens to match a thread is a failing check rather than a stale vital
 *  sign on a screen in a clinic.
 *
 *  WHAT THIS CANNOT DO. It reads two files as text under plain node: no
 *  browser, no service worker runtime, no install. It cannot prove the worker
 *  registers, activates, or serves anything. It proves what the worker says
 *  it will match, and that the manifest names files that exist.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(fileURLToPath(import.meta.url));
const PUBLIC = join(SRC, "..", "public");
let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };

// ---------------------------------------------------------------- the manifest

const manifest = JSON.parse(readFileSync(join(PUBLIC, "manifest.webmanifest"), "utf8"));

{
  for (const key of ["name", "short_name", "start_url", "scope", "display",
                     "background_color", "theme_color", "icons"]) {
    assert.ok(manifest[key], `manifest has no ${key}`);
  }
  assert.equal(manifest.display, "standalone",
    "display must be standalone: a browser-tab app is not installed, it is bookmarked");
  ok("manifest: every field an install prompt needs is present");
}

{
  // Chrome will not offer to install without a 192 and a 512. Android crops a
  // maskable icon to a shape of its own choosing, so one of each purpose is
  // the minimum that survives both a launcher and a splash screen.
  const have = (size: string, purpose: string) =>
    manifest.icons.some((i: { sizes: string; purpose?: string }) =>
      i.sizes === size && (i.purpose ?? "any").split(/\s+/).includes(purpose));
  for (const size of ["192x192", "512x512"]) {
    assert.ok(have(size, "any"), `no ${size} icon with purpose any`);
    assert.ok(have(size, "maskable"), `no ${size} icon with purpose maskable`);
  }
  ok("manifest: 192 and 512, each in both purposes");
}

{
  const missing = manifest.icons
    .map((i: { src: string }) => i.src)
    .filter((src: string) => !existsSync(join(PUBLIC, src.replace(/^\//, ""))));
  assert.deepEqual(missing, [],
    "manifest names an icon that is not on disk, so the install prompt never " +
    "appears and nothing says why: " + missing.join(", "));
  ok(`manifest: all ${manifest.icons.length} icons exist on disk`);
}

// ---------------------------------------------------------------- the worker

const sw = readFileSync(join(PUBLIC, "sw.js"), "utf8");

/** The worker's own DECLARATION array, lifted out and made live. If the array
 *  is renamed or restructured this throws rather than silently checking
 *  nothing, which is the failure mode of every regex-scraping check. */
const PATTERNS: RegExp[] = (() => {
  const at = sw.indexOf("const DECLARATION = [");
  assert.notEqual(at, -1,
    "sw.js has no `const DECLARATION = [` — if the worker's cache rules moved, " +
    "move this check with them rather than deleting it");
  const body = sw.slice(at, sw.indexOf("];", at));
  // One pattern a line, read between the first slash and the last. Scraping
  // the whole block with one regex instead looks tidier and silently drops
  // any pattern containing a character class, because the `/` inside `[^/]+`
  // ends the match early. That is how a check comes to be testing three of
  // four rules while reporting four.
  const found = body.split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("/") && /\/[a-z]*,$/.test(line))
    .map((line) => new RegExp(line.slice(1, line.lastIndexOf("/"))));
  assert.ok(found.length > 0, "the DECLARATION array parsed to no patterns at all");
  return found;
})();

const P = "/api/v1/phc";

/** Real paths this product serves. The second column is whether the worker is
 *  allowed to keep a copy. Anything about a person is false. */
const PATHS: [string, boolean][] = [
  [`${P}/catalogue`, true],
  [`${P}/catalogue/`, true],
  [`${P}/questionnaires/`, true],
  [`${P}/questionnaires/phc-register-v1`, true],
  [`${P}/valuesets/condition-code`, true],
  [`${P}/valuesets/ucum-units`, true],
  // and everything that is a person
  [`${P}/queue`, false],
  [`${P}/views/today`, false],
  [`${P}/threads/enc-003`, false],
  [`${P}/subjects/pat-001`, false],
  [`${P}/patients/search?q=kamala`, false],
  [`${P}/patients/pending`, false],
  [`${P}/whoami`, false],
  [`${P}/facility`, false],
  [`${P}/roles`, false],
  [`${P}/proposals/abc123def456`, false],
  [`${P}/khoj`, false],
  // near misses, which is where a hurried fourth pattern does its damage
  [`${P}/threads/valuesets`, false],
  [`${P}/threads/enc-003/questionnaires`, false],
  [`${P}/valuesets/condition-code/threads/enc-003`, false],
];

{
  const wrong: string[] = [];
  for (const [path, cacheable] of PATHS) {
    const matched = PATTERNS.some((re) => re.test(path.split("?")[0]));
    if (matched !== cacheable) {
      wrong.push(`${path} ${matched ? "IS" : "is NOT"} cached, and should ${cacheable ? "be" : "not be"}`);
    }
  }
  assert.deepEqual(wrong, [],
    "the service worker caches the wrong thing. A cached clinical read is a " +
    "stale queue, a seen patient shown as waiting, or a vital sign from " +
    "yesterday:\n  " + wrong.join("\n  "));
  ok(`worker: ${PATHS.length} real paths cached or not, exactly as declared`);
}

{
  // Anchoring is what stops `/threads/valuesets` matching, and an unanchored
  // pattern passes the table above only until somebody adds the path that
  // catches it. Assert the property rather than the examples.
  const loose = PATTERNS.filter((re) => !re.source.endsWith("$"));
  assert.deepEqual(loose.map(String), [],
    "a declaration pattern is not anchored at the end, so it matches any path " +
    "that merely begins with a declaration's: " + loose.map(String).join(", "));
  ok("worker: every declaration pattern is anchored");
}

{
  // A worker that caches a write has replayed a clinical action the person can
  // no longer see. The guard is the only thing allowed to decide a write
  // happens, and it is not in this file.
  assert.match(sw, /request\.method\s*!==\s*"GET"/,
    "sw.js does not bail out on a non-GET: a cached or replayed write is the " +
    "'reported as sent when it was not' failure the outbox exists to prevent");
  ok("worker: nothing but GET is touched");
}

console.log(`\n${checks} checks passed`);
