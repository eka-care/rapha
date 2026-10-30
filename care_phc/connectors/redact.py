"""What must never reach a log, a traceback or a rendered error.

Shared by every connector, and owned by none of them. It lived in the ABDM
connector, and the scribe connector imported it from there with a comment
saying the two must not drift apart on what an Aadhaar number looks like. That
was the right instinct and the wrong direction: it made the scribe unable to
ship without the ABDM connector, which is the one thing a connector must never
do to another. The pattern is shared here instead, so neither owns it and
neither can drift.

Pure. One regular expression and one function. Its check also asserts the
property this module exists to create: no connector imports another.
Run: python3 -m care_phc.connectors.redact
"""
from __future__ import annotations

import pathlib
import re

# 12 digits, optionally spaced or hyphenated. Matched so it can be removed,
# never stored.
_AADHAAR = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")

AADHAAR_MARK = "<aadhaar-redacted>"


def aadhaar(text):
    """Remove anything Aadhaar shaped before it can reach a log or a traceback."""
    return _AADHAAR.sub(AADHAAR_MARK, str(text))


def _no_connector_imports_another():
    """A connector that imports another cannot be removed without breaking it.

    This is the check for the bug this module was made to fix: the scribe
    connector imported the ABDM connector's Aadhaar pattern, so a facility
    that wanted dictation and not ABHA could not have one without the other.

    Only import lines count. A comment naming a sibling is prose, not a
    dependency, and two of those are left in place on purpose because they say
    where a reader should look next.
    """
    root = pathlib.Path(__file__).parent
    siblings = sorted(d.name for d in root.iterdir()
                      if d.is_dir() and (d / "__init__.py").exists())
    assert len(siblings) >= 2, "nothing to keep apart: %s" % siblings
    read = 0
    for name in siblings:
        others = [o for o in siblings if o != name]
        for path in sorted((root / name).rglob("*.py")):
            for n, raw in enumerate(path.read_text().splitlines(), 1):
                line = raw.strip()
                if not (line.startswith("import ") or line.startswith("from ")):
                    continue
                read += 1
                for other in others:
                    assert "connectors.%s" % other not in line, (
                        "%s:%d imports the %s connector: %s"
                        % (path.relative_to(root.parents[1]), n, other, line))
    # Without this the loop above passes just as well on a glob that matched
    # nothing, which is what a moved directory would look like.
    assert read > 10, "no import lines were read, so nothing was checked: %d" % read
    return len(siblings), read


def demo():
    # The three spellings a gateway echoes back, all of which must go.
    for spelling in ("123456785678", "1234 5678 5678", "1234-5678-5678"):
        out = aadhaar('{"error":"bad aadhaar %s"}' % spelling)
        assert AADHAAR_MARK in out, out
        assert "5678" not in out, out
    # A number that is not twelve digits is not an Aadhaar and is left alone,
    # because a redactor that eats identifiers a person needs to read is a
    # redactor people route around.
    assert aadhaar("status 404 on session scr-1") == "status 404 on session scr-1"
    assert aadhaar("12345678") == "12345678"
    # Called on exception objects as often as on strings.
    assert AADHAAR_MARK in aadhaar(ValueError("1234 5678 5678"))
    kinds, read = _no_connector_imports_another()
    print("ok care_phc.connectors.redact: aadhaar redacted, "
          "%d connectors import none of each other over %d import lines"
          % (kinds, read))


if __name__ == "__main__":
    demo()
