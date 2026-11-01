"""Fields from the scribe service's own structured note, with no second model.

The owner's decision of 2026-11-01: nothing but the scribe service may be
asked to read a consultation. The module that used to send the transcript to a
second provider is deleted, not merely unused, because an unused way to make
that call is a way to make it. This asks EkaScribe for a note already shaped
like the form, and reads that note with a parser.

Why this can be a parser and not a model
----------------------------------------
EkaScribe takes a template whose instructions are plain markdown and follows
them (developer.eka.care, Create Template: "Describe the exact structure,
sections and style you want in `desc`"). So the shape of the answer is ours to
choose, and we choose a markdown table with fixed columns. A table is the one
structure that service is documented as reliable at, and a table with named
columns is parseable without guessing.

THE INSTRUCTIONS ARE BUILT FROM THE DECLARATION, NEVER TYPED HERE. The field
list in the template is `api/fill.py`'s flattening of the operation's own
questionnaire. Nothing in this module names a field, a unit or an option, so a
bundle that declares a new operation gets a template for it without this file
changing. That is the kernel's own rule and it is the reason this is not just
a prompt in a string.

What does NOT change, because it is what makes a draft safe to tap
------------------------------------------------------------------
Every rule the old module enforced AFTER its model answered is enforced here
after the service answers, by the code carried over from it:

- an answer is kept only if its `heard` span is really in the transcript;
- a field the questionnaire does not declare is dropped;
- a row answer that names no row keeps its bare id and is dropped by name;
- confidence is clamped, and `api/fill.py` caps it below the renderer's SURE
  threshold, so no value drawn from a recording ever reads as confirmed.

So the tick survives the change of engine. A doctor still sees the words that
produced each number and still has to confirm it.

Run: python3 -m api.shaped
"""
from __future__ import annotations

import re

from api import fill

_SPACE = re.compile(r"\s+")


def _norm(text):
    return _SPACE.sub(" ", str(text)).strip().lower()


def _ident(field, answer):
    """The id this answer is filed under: row addressed, or the bare link_id.

    A row field whose answer names no row keeps its bare link_id and is
    therefore dropped by `api/fill.py`, which names it in `unfilled`. That is
    deliberate: the alternative is choosing a row for it, and a dose on a
    medicine nobody identified goes on whichever medicine was first. Dropped
    and named beats placed and plausible.

    Carried here verbatim from the module that used to send the transcript to
    a second provider, which this one replaces.
    """
    group = field.get("row_of")
    row = answer.get("row")
    if not group or not isinstance(row, int) or isinstance(row, bool) or row < 0:
        return field["link_id"]
    return fill.row_id(group, row, field["link_id"])

# The columns, in order. `field` and `heard` carry the two rules above; `row`
# addresses a repeating group; `sure` is the service's own reading of how
# plainly the words state the value, and is clamped on the way in.
COLUMNS = ("field", "value", "row", "heard", "sure")

HOW = """\
You are filling one clinical form from a consultation you have transcribed.

Return ONLY a markdown table and nothing else: no heading, no preamble, no
commentary after it. The table has exactly these columns, in this order:

| field | value | row | heard | sure |

One line per field the consultation actually states.

- `field` is copied exactly from the Fields list below. Never invent one.
- `value` is what was said, written in English. For a field with options,
  answer with one of its options word for word.
- `row` is for a field marked "row of <group>": the number of the row this
  answer belongs to, counting from 0 in the order the consultation names
  them. Keep one row's answers on the same number. Leave it empty for every
  other field.
- `heard` is the words from the transcript you relied on, copied exactly, in
  the language they were spoken in. An answer with nothing in `heard` is
  discarded, so never leave it empty and never paraphrase it.
- `sure` is 0 to 1: how plainly those words state this value.

Leave a field out rather than inferring, calculating or assuming it. A field
nobody mentioned has no line.

Fields
------
"""


def instructions(fields):
    """The template `desc` for this questionnaire: the rules above, then the
    declared fields. Handed to EkaScribe's Create Template, once per operation.
    """
    return HOW + "\n".join(_line(f) for f in fields) + "\n"


def _line(field):
    """One field, as the template describes it to the service."""
    bits = ["- `%s` — %s" % (field["link_id"], field.get("text") or field["link_id"])]
    if field.get("description"):
        bits.append("(%s)" % field["description"])
    bits.append("[%s]" % (field.get("type") or "string"))
    if field.get("unit"):
        bits.append("in %s" % field["unit"])
    if field.get("options"):
        bits.append("one of: %s" % "; ".join(str(o) for o in field["options"]))
    if field.get("row_of"):
        bits.append("row of %s" % field["row_of"])
    return " ".join(bits)


_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_RULE = re.compile(r"^[\s:|-]+$")


def answers(note, fields, transcript):
    """Read the service's note into the shape `api/fill.py` takes.

    The same return and the same guards as the model reader this replaces.
    A note that is prose, empty, or a table with the wrong columns
    yields nothing: the caller then shows the transcript and says nothing
    filled the form, which is the truth and is already what it does.
    """
    known = {f["link_id"]: f for f in fields}
    heard_all = _norm(transcript)
    out, columns = {}, None
    for line in str(note or "").splitlines():
        hit = _ROW.match(line)
        if not hit:
            continue
        cells = [c.strip() for c in hit.group(1).split("|")]
        if columns is None:
            # The header, wherever in the note it sits. Only a table whose
            # columns are the ones we asked for is read at all.
            if [c.strip().strip("`").lower() for c in cells] == list(COLUMNS):
                columns = list(COLUMNS)
            continue
        if _RULE.match("|".join(cells)):          # the ---|--- under the header
            continue
        cell = dict(zip(columns, cells))
        link_id = cell.get("field", "").strip().strip("`")
        if link_id not in known:
            continue
        evidence = _strip_quotes(cell.get("heard", ""))
        if not evidence or _norm(evidence) not in heard_all:
            continue
        ident = _ident(known[link_id], {"row": _row(cell.get("row"))})
        if ident in out:                          # first answer for a field wins
            continue
        value = cell.get("value", "").strip()
        if not value:
            continue
        out[ident] = {"value": value, "confidence": _sure(cell.get("sure")),
                      "evidence": evidence}
    return out


def _row(text):
    """The row number, or nothing. Nothing is right for a field that is not in
    a repeating group, and it is also right for a row field the service could
    not place: `_ident` then leaves it under its bare id and `api/fill.py`
    drops it by name rather than putting it on whichever row came first."""
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _sure(text):
    """0 to 1, or 0 when the service did not say. `api/fill.py` caps every one
    of these below the renderer's SURE threshold anyway, so this number decides
    how loudly a field asks to be checked, never whether it has to be."""
    try:
        return max(0.0, min(1.0, float(str(text).strip())))
    except (TypeError, ValueError):
        return 0.0


def _strip_quotes(text):
    text = str(text or "").strip()
    for pair in ('""', "''", "“”", "‘’"):
        if len(text) > 1 and text[0] == pair[0] and text[-1] == pair[1]:
            text = text[1:-1].strip()
    return text


# ---------------------------------------------------------------------- check

def demo():
    """Run: python3 -m api.shaped

    No network, no credentials, and no model of any kind: that is the point of
    the module.
    """
    fields = [
        {"link_id": "systolic", "text": "Systolic", "type": "integer", "unit": "mm[Hg]"},
        {"link_id": "pulse", "text": "Pulse", "type": "integer", "unit": "/min"},
        {"link_id": "history", "text": "History", "type": "text"},
        {"link_id": "condition", "text": "Condition", "type": "choice",
         "options": ["Hypertension", "Diabetes"], "row_of": "diagnosis"},
        {"link_id": "onset", "text": "Since", "type": "string", "row_of": "diagnosis"},
    ]

    # The instructions are the declaration, not a sentence typed in this file.
    how = instructions(fields)
    assert "`systolic`" in how and "mm[Hg]" in how, how
    assert "one of: Hypertension; Diabetes" in how, how
    assert "row of diagnosis" in how, how
    for f in fields:
        assert f["link_id"] in how, f["link_id"]
    assert "| field | value | row | heard | sure |" in how, how

    said = ("Blood pressure one thirty eight over eighty six, pulse eighty eight. "
            "Headache on waking for two weeks. Hypertension since August.")
    note = """
Here are the findings.

| field | value | row | heard | sure |
|---|---|---|---|---|
| systolic | 138 | | one thirty eight | 0.95 |
| pulse | 88 | | pulse eighty eight | 0.9 |
| history | Headache on waking for two weeks | | Headache on waking for two weeks | 0.9 |
| condition | Hypertension | 0 | Hypertension | 0.8 |
| onset | August | 0 | since August | 0.7 |
"""
    got = answers(note, fields, said)
    assert got["systolic"]["value"] == "138", got
    assert got["systolic"]["confidence"] == 0.95, got
    assert got["pulse"]["evidence"] == "pulse eighty eight", got
    assert got["diagnosis[0].condition"]["value"] == "Hypertension", got
    assert got["diagnosis[0].onset"]["value"] == "August", got

    # THE GUARDS. Each of these is the reason a draft is safe to tap, and not
    # one of them was relaxed when the engine behind the answer changed.
    assert answers("""
| field | value | row | heard | sure |
|---|---|---|---|---|
| systolic | 200 | | the patient was wheeled in | 0.99 |
""", fields, said) == {}, "a span that is not in the transcript is not evidence"

    assert answers("""
| field | value | row | heard | sure |
|---|---|---|---|---|
| weight | 61 | | eighty eight | 0.9 |
""", fields, said) == {}, "a field the questionnaire does not declare is dropped"

    assert answers("""
| field | value | row | heard | sure |
|---|---|---|---|---|
| systolic | 138 | | one thirty eight | |
""", fields, said)["systolic"]["confidence"] == 0.0, \
        "no number from the service is not high confidence"

    assert answers("""
| field | value | row | heard | sure |
|---|---|---|---|---|
| systolic | | | one thirty eight | 0.9 |
""", fields, said) == {}, "a field with no value is not an answer"

    first = answers("""
| field | value | row | heard | sure |
|---|---|---|---|---|
| pulse | 88 | | pulse eighty eight | 0.9 |
| pulse | 44 | | pulse eighty eight | 0.99 |
""", fields, said)
    assert first["pulse"]["value"] == "88", "the first answer for a field wins"

    unplaced = answers("""
| field | value | row | heard | sure |
|---|---|---|---|---|
| onset | August | | since August | 0.7 |
""", fields, said)
    assert "onset" in unplaced and "diagnosis[0].onset" not in unplaced, \
        "a row answer naming no row keeps its bare id, so fill.py drops it by name"

    # A service that ignored the instructions fills nothing, rather than
    # filling something. There is no partial credit for prose.
    assert answers("The patient has hypertension and a BP of 138/86.",
                   fields, said) == {}, "prose is not a table"
    assert answers("""
| name | reading |
|---|---|
| systolic | 138 |
""", fields, said) == {}, "a table with other columns is not this table"
    assert answers("", fields, said) == {}, "nothing is nothing"

    print("ok api.shaped")


if __name__ == "__main__":
    demo()
