"""Run: python3 scripts/check_instruments.py

The instrument vocabulary is ONE list, and this is the check that it stays
one. `catalogue/vocab.py` owns it; `kernel/contracts.py` re-exports it rather
than writing it out a second time, because this file is the lower layer
(kernel imports catalogue, never the other way round).

Two fields read that one list:

  - an instrument atom's `kind:`, which may name any INSTRUMENT_KINDS entry,
    because the renderer implements a component for each.
  - an operation's `instrument:`, its default, which may name any INSTRUMENTS
    entry. That is the strict subset a pill can draw, derived from the master
    by removing NOT_AN_OPERATION_DEFAULT.

They were written out twice and drifted: `catalogue/vocab.py` carried
`palette`, left behind by the Palette-to-Khoj rename, while
`kernel/contracts.py` carried `spoken-prompt`. So an operation could never
declare the instrument that exists and could happily declare the one that
does not. scripts/check_khoj.py missed it because it hunts the capital P
`Palette` identifier and this was a lowercase string in a tuple.

Mutation: add a sixth entry to INSTRUMENT_KINDS in catalogue/vocab.py, or
define INSTRUMENT_KINDS in kernel/contracts.py again instead of importing it,
or drop a key from TAG in web/src/screens/Encounter.tsx, and this fails.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from catalogue import vocab                     # noqa: E402
from kernel import contracts as c               # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


# ---------------------------------------------------------------------------
# One definition, not two. The identity check is what makes drift impossible
# rather than merely unlikely: contracts.py cannot hold a different tuple
# without holding a different object.
# ---------------------------------------------------------------------------

contracts_src = (ROOT / "kernel" / "contracts.py").read_text()
RE_EXPORT = "from catalogue.vocab import INSTRUMENT_KINDS"
assert RE_EXPORT in contracts_src, (
    "kernel/contracts.py no longer re-exports INSTRUMENT_KINDS from "
    "catalogue/vocab.py. If it defines its own, the two can drift again."
)
assert not re.search(r"^INSTRUMENT_KINDS\s*=", contracts_src, re.M), (
    "kernel/contracts.py defines INSTRUMENT_KINDS itself; it must re-export "
    "catalogue/vocab.py's, which is the single source."
)
ok("kernel/contracts.py re-exports INSTRUMENT_KINDS rather than defining it")

assert c.INSTRUMENT_KINDS is vocab.INSTRUMENT_KINDS, (
    "kernel.contracts.INSTRUMENT_KINDS is no longer catalogue.vocab's own "
    "object: %r vs %r" % (c.INSTRUMENT_KINDS, vocab.INSTRUMENT_KINDS)
)
ok("the kernel's INSTRUMENT_KINDS is catalogue/vocab.py's own tuple")

# ---------------------------------------------------------------------------
# The subset is derived, and every exclusion names a kind that exists. An
# exclusion naming a ghost is how `palette` would come back.
# ---------------------------------------------------------------------------

assert vocab.NOT_AN_OPERATION_DEFAULT, (
    "NOT_AN_OPERATION_DEFAULT is empty. If every kind may now be an "
    "operation's default, say so here and delete this check's reason."
)
ghost_exclusions = [k for k in vocab.NOT_AN_OPERATION_DEFAULT
                    if k not in vocab.INSTRUMENT_KINDS]
assert not ghost_exclusions, (
    "NOT_AN_OPERATION_DEFAULT excludes %r, which is not an instrument kind at "
    "all" % (ghost_exclusions,)
)
ok("every NOT_AN_OPERATION_DEFAULT entry is a real instrument kind")

expected = tuple(k for k in vocab.INSTRUMENT_KINDS
                 if k not in vocab.NOT_AN_OPERATION_DEFAULT)
assert vocab.INSTRUMENTS == expected, (
    "INSTRUMENTS is not the master list minus the exclusions: %r != %r"
    % (vocab.INSTRUMENTS, expected)
)
assert vocab.INSTRUMENTS, "INSTRUMENTS is empty; no operation could declare one"
ok("INSTRUMENTS is exactly INSTRUMENT_KINDS minus NOT_AN_OPERATION_DEFAULT")

# ---------------------------------------------------------------------------
# The renderer's side. An operation's instrument is drawn as a pill tag and
# nothing else, so TAG is the list of defaults a screen can actually keep a
# promise about. `palette` sat in the vocabulary precisely because nothing
# tied the tuple to the renderer.
# ---------------------------------------------------------------------------

enc = (ROOT / "web" / "src" / "screens" / "Encounter.tsx").read_text()
block = re.search(r"const TAG: Record<string, string> = \{(.*?)\}", enc, re.S)
assert block, (
    "web/src/screens/Encounter.tsx no longer declares `const TAG: "
    "Record<string, string>`; this check cannot see what a pill can draw."
)
tag_keys = set(re.findall(r'(?:"([^"]+)"|([A-Za-z_][\w-]*))\s*:', block.group(1)))
tag_keys = {q or b for q, b in tag_keys}
assert tag_keys, "parsed no keys out of Encounter.tsx's TAG map"

assert tag_keys == set(vocab.INSTRUMENTS), (
    "TAG in web/src/screens/Encounter.tsx and INSTRUMENTS disagree. "
    "only in TAG: %r; only in INSTRUMENTS: %r"
    % (sorted(tag_keys - set(vocab.INSTRUMENTS)),
       sorted(set(vocab.INSTRUMENTS) - tag_keys))
)
ok("every instrument an operation may default to has a pill tag, and no other")

# ---------------------------------------------------------------------------
# Nothing in either list is a ghost: every kind is named by a declared atom,
# by a declared operation's default, or by the renderer's pill map. `form` has
# no instrument atom and is still real, because fourteen operations declare it.
# ---------------------------------------------------------------------------

cat = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
declared_kinds = {i.get("kind") for i in cat["instruments"].values()}
declared_defaults = {o.get("instrument") for o in cat["operations"].values()}
assert declared_kinds and declared_defaults, "catalogue.json declares neither"

stray = sorted(k for k in declared_kinds if k not in vocab.INSTRUMENT_KINDS)
assert not stray, "declared instrument kinds outside INSTRUMENT_KINDS: %r" % stray
stray = sorted(d for d in declared_defaults if d not in vocab.INSTRUMENTS)
assert not stray, "declared operation defaults outside INSTRUMENTS: %r" % stray
ok("every declared kind and every declared default is in its own list")

live = declared_kinds | declared_defaults | tag_keys
ghosts = sorted(k for k in vocab.INSTRUMENT_KINDS if k not in live)
assert not ghosts, (
    "instrument kinds nothing declares and no pill draws: %r. An entry no "
    "atom names and no renderer implements is how `palette` survived." % ghosts
)
ok("no instrument kind is a ghost: each is declared or drawn")

print("ok   instrument vocabulary: %d checks passed" % checks)
