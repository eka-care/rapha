"""A module's live code, with the comments, the docstrings and the self-test
stripped off.

Shared by scripts/check_vitals.py and scripts/check_rx.py, which both assert
the same rule from different directions: no engine module types a clinical
word. It lives in its own file because importing it from another check would
RUN that check, and a rule asserted twice by accident is a rule asserted
nowhere on purpose.
"""
from __future__ import annotations


def engine_code(path):
    """A module's live code: no comments, no docstrings, no self-test.

    Three exemptions, each for the reason scripts/check_khoj.py exempts
    itself. A comment or a docstring explaining a rule has to be able to name
    what breaking it would look like, which is why `if code == "..."` appears
    in kernel/fhir.py's docstring as the thing it must never contain. And a
    `demo()` has to name a concrete code and a concrete unit or it is not a
    test of anything.

    Comments and docstrings are removed with tokenize rather than by scanning
    for a `#`, so a `#` inside a string cannot blank out the rest of a live
    line. A docstring is a STRING token standing alone as a statement, which
    is the one shape a comment-like string takes. The self-test is everything
    from `def demo(`, and the marker is asserted by the caller so that
    renaming demo() cannot quietly exempt a module.
    """
    import io
    import tokenize

    text = path.read_text()
    marker = "\ndef demo("
    live = text.split(marker)[0] if marker in text else text
    # A string that STARTS a statement is a docstring; one that follows an
    # operator or a name is a value. So `previous` tracks every token,
    # trivia included, which is the whole distinction.
    STATEMENT_START = (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
                       tokenize.DEDENT, tokenize.ENCODING)
    out, previous = [], tokenize.NEWLINE
    for tok in tokenize.generate_tokens(io.StringIO(live).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and previous in STATEMENT_START:
            previous = tok.type
            continue                      # a docstring, not a value
        previous = tok.type
        out.append(tok.string)
    return "\n".join(out)
