"""Run: python3 scripts/check_khoj.py

Khoj replaced the Palette component and the /agent/say route. This is the
check that the rename actually happened everywhere it had to, and stayed
that way: no tracked source file still carries the `Palette` identifier, and
no tracked source file still makes a live call to the deprecated
`/agent/say` path, outside the one place backward compatibility requires it
(api/main.py's alias route, which delegates to khoj() and changes nothing
about what it does).

Markdown is exempt. Prose that records what a build used to be called, or
that explains the deprecated alias, is history and documentation, not a
live reference; kernel/ARCHITECTURE.md and web/RESTORATION.md both do this
on purpose and neither should have to be rewritten every time a name moves.

Mutation: rename Khoj back to Palette in web/src/Khoj.tsx, or point
web/src/ask.ts at /agent/say again, and this fails.
"""
from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).parents[1]
checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def tracked_source_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True)
    for rel in out.stdout.splitlines():
        if rel.endswith(".md"):
            continue  # docs and history, not live code
        yield rel


# Files allowed to still make a live call to the deprecated path: its own
# alias route, api/main.py's `say()`, which delegates to `khoj()` and has no
# logic of its own; the test that proves that alias still answers; and this
# file. Everywhere else, a comment is allowed to talk about /agent/say (that
# is history, same as a .md file), but code is not: see the comment-strip
# below, the same technique web/src/messages.check.ts uses for the same
# reason.
ALLOWED_SAY_CODE = {"api/main.py", "api/tests/test_api.py", "scripts/check_khoj.py"}


def code_only(text: str) -> str:
    return "\n".join(
        line for line in text.split("\n")
        if not line.strip().startswith(("#", "//", "*", "/*"))
    )


bad = []
for rel in tracked_source_files():
    path = ROOT / rel
    try:
        text = path.read_text()
    except (UnicodeDecodeError, OSError):
        continue
    if "Palette" in code_only(text):
        bad.append(f"{rel}: the 'Palette' identifier survives the Khoj rename")
    if rel not in ALLOWED_SAY_CODE and "agent/say" in code_only(text):
        bad.append(f"{rel}: names the deprecated /agent/say path outside its alias")

assert not bad, "\n".join(bad)
ok("no tracked source file outside docs still carries the 'Palette' identifier")
ok("no tracked source file calls /agent/say outside its deprecated alias in api/main.py")

print("ok   khoj rename: %d checks passed" % checks)
