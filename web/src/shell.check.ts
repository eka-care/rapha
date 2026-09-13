/** The shell: nav built from declarations, Home first, no New chat / Search
 *  left in the sidebar, and "Lines" is the atom's word, never the renderer's.
 *
 *  Run: node --experimental-strip-types src/shell.check.ts   (from web/)
 *
 *  Mutation this catches: hard-coding `title: "Lines"` (or any other queue
 *  title) into Shell.tsx instead of reading `v.title` off the declaration
 *  would still draw the right word on screen, and no DOM check run under
 *  plain node would tell the difference. Reading it back out of
 *  catalogue.json, and asserting the renderer source contains the *word*
 *  "Lines" nowhere at all, catches that: a renderer that never types the
 *  word cannot be the one that put it on screen.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (p: string) => readFileSync(root + p, "utf8");

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

// -- the atom, not the renderer, owns the word ------------------------------
const cat = JSON.parse(read("catalogue/catalogue.json"));
assert.equal(cat.views["phc.view.station-queue"].title, "Lines", "FAIL the compiled title is the atom's own word");
checks++;
// The laboratory keeps its own word: retitling the health centre's queue must
// not have touched the other bundle's atom.
const labAtom = read("bundles/lab/lab.view.worklist.md");
ok(/title:\s*Worklist by status/.test(labAtom), "the laboratory's own view keeps its own title");

const shell = read("web/src/Shell.tsx");
const stripped = shell.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
ok(!/Lines/.test(stripped), "Shell.tsx's live code contains the word \"Lines\" nowhere");
ok(/v\.title\s*\?\?\s*title\(v\.id\)/.test(shell), "nav draws each entry's own declared title, not a lookup keyed on id");
ok(!/New chat/.test(shell), "New chat has left the sidebar");
ok(!/>Search</.test(shell) && !/["']Search["']/.test(stripped), "the sidebar draws no Search entry of its own; Khoj is search");

// Every tracked, non-check web/src source file (Khoj.tsx included, since it
// is where Search now actually lives) gets the same word check, so the
// title cannot have been moved sideways into a different renderer.
const tracked = execFileSync("git", ["ls-files", "web/src"], { cwd: root, encoding: "utf8" })
  .split("\n")
  .filter((f) => /\.(tsx?|css)$/.test(f) && !f.endsWith(".check.ts"));
ok(tracked.length > 5, "the check actually found renderer files to read");
for (const f of tracked) {
  const src = read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  ok(!/\bLines\b/.test(src), `${f} does not hard-code the queue's title`);
}

// -- Home is first and default ----------------------------------------------
const main = read("web/src/main.tsx");
const parseFn = main.slice(main.indexOf("function parse("), main.indexOf("\n}\n", main.indexOf("function parse(")));
ok(/if \(!head \|\| head === "home"\) return \{ kind: "home"/.test(parseFn), "an empty route, and #/home, both resolve to home");
// In the sidebar's own JSX, the Home button is the nav's first element: it is
// written before `nav.map(...)`, not after, so a bundle with views cannot
// push it down the list.
const sbHomeAt = shell.indexOf('onGo("#/home")');
const sbNavMapAt = shell.indexOf("nav.map(");
ok(sbHomeAt > 0 && sbNavMapAt > sbHomeAt, "Home is written before the declared views, so it renders first");

console.log(`ok   shell: ${checks} checks`);
