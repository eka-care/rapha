"""One questionnaire, any questionnaire: its fields as a flat list, and a heard
value made into a value that field can hold, or refused.

Repeating groups, and why the tick gets harder here
---------------------------------------------------
A repeating group's answer is a list of rows, so a recording that fills one is
filling several values per row and several rows per question. Two rules hold
that together and both are refusals:

  an answer is addressed to one row, by number, as `medications[1].dose`. A
  row field answered with no row number is DROPPED. It is never folded into
  the first row, because a dose that belongs to a medicine nobody identified
  is a dose on the wrong medicine.

  every filled non text value of every row is owed its own tick, under its own
  row addressed id. One tick per question would mean confirming the first
  medicine and committing four more unread.

Pure. No model, no network, no clock except the `today` a caller hands in.
The one thing it reads is the local terminology cache, which is an offline
file, so that a choice bound to a value set has options to match a heard word
against. Run: python3 -m api.fill
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from catalogue import validate
from kernel import terminology

TICK_TYPES = ("integer", "decimal", "quantity", "date", "dateTime", "time",
              "choice", "boolean")

# How an answer names the row it belongs to. One shape, used by the extractor
# that produces an answer, the draft that carries it, the tick that is owed for
# it and the renderer that resolves it against the payload.
ROW_ID = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]\.([A-Za-z_][A-Za-z0-9_]*)$")


def row_id(group, index, link_id):
    return "%s[%d].%s" % (group, index, link_id)


def split_id(ident):
    """(group, index, link_id) for a row addressed id, (None, None, id) else."""
    found = ROW_ID.match(str(ident))
    if not found:
        return None, None, str(ident)
    return found.group(1), int(found.group(2)), found.group(3)


def _options(q):
    """The values this choice may take.

    Two sources, and a bound one wins, because it is the authority: a question
    with an `answer_value_set` takes the codes that value set holds, and one
    with `answer_option` takes the values the form declares.

    A bound choice used to come back with NO options, and that was not
    cosmetic. `coerce` matches a heard word against this list, so an empty list
    refused every heard value: a recording could not fill a bound choice at
    all. The laboratory result's analyte has been in that state since the day
    it was bound, and nothing said so because no scribe instrument is declared
    for that operation. A diagnosis and a prescription are on a scribe
    instrument, so the same hole would have been a doctor dictating a medicine
    into a field that silently refused it.
    """
    slug = terminology.answer_binding(q)
    if slug:
        return sorted(terminology.LOCAL.concepts(slug))
    return [str(o.get("value")) for o in q.get("answer_option") or [] if o.get("value") is not None]


def _labels(q):
    """code -> display for a bound choice, so a heard phrase can find its code.

    Nobody says "two two nine seven nine nine zero zero one"; they say "twice a
    day". The display is the terminology's own, never a caller's, which is the
    same rule `Coding.display` is held to.
    """
    slug = terminology.answer_binding(q)
    if not slug:
        return {}
    return {code: (concept.get("display") or "")
            for code, concept in terminology.LOCAL.concepts(slug).items()}


def flatten(schema):
    """Every answerable question, with the repeating group each one is inside.

    A repeating group is not itself answerable, so it is not in the list; its
    sub questions are, each carrying `row_of`, the group they belong to. That
    is what keeps this list flat while the payload is not: one entry per
    question to ask about, and the row addressing lives on the answers.
    """
    out = []

    def walk(questions, prefix, row_of):
        for q in questions:
            path = prefix + [q["link_id"]]
            if q.get("type") == "group":
                walk(q.get("questions") or [], path,
                     q["link_id"] if validate.is_row_group(q) else row_of)
                continue
            if q.get("type") == "display":
                continue
            phc = (q.get("styling_metadata") or {}).get("phc") or {}
            out.append({
                "link_id": q["link_id"], "path": ".".join(path),
                "text": q.get("text", ""), "description": q.get("description", ""),
                "type": q.get("type"), "structured_type": q.get("structured_type"),
                "required": bool(q.get("required")), "repeats": bool(q.get("repeats")),
                "unit": q.get("unit") or phc.get("unit"), "options": _options(q),
                "labels": _labels(q), "row_of": row_of,
                "enable_when": q.get("enable_when") or [],
            })
            walk(q.get("questions") or [], path, row_of)

    walk(schema.get("questions") or [], [], None)
    return out


_SQUASH = re.compile(r"\s+")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date(value, today):
    text = str(value).strip().lower()
    if text in ("today",):
        return today
    if text in ("yesterday",):
        return today - timedelta(days=1)
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass
    # ponytail: "15 August" / "August 15" only; add weekday phrases when golden transcripts need them
    m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)|([a-z]+)\s+(\d{1,2})", text)
    if not m:
        return None
    day, month = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    month = _MONTHS.get(month[:3])
    if not month:
        return None
    try:
        found = date(today.year, month, int(day))
    except ValueError:
        return None
    return found if found <= today else found.replace(year=today.year - 1)


def coerce(field, value, today):
    kind = field["type"]
    if value is None or value == "" or value == []:
        return False, None
    try:
        if kind == "integer":
            number = float(value)
            return (True, int(number)) if number.is_integer() else (False, None)
        if kind in ("decimal", "quantity"):
            return True, float(value)
        if kind == "boolean":
            text = str(value).strip().lower()
            if text in ("true", "yes", "y", "1", "haan", "ha"):
                return True, True
            if text in ("false", "no", "n", "0", "nahi"):
                return True, False
            return False, None
        if kind in ("date", "dateTime"):
            found = _date(value, today)
            return (True, found.isoformat()) if found else (False, None)
        if kind == "choice":
            want = _SQUASH.sub("", str(value)).lower()
            labels = field.get("labels") or {}
            for option in field["options"]:
                if option == value or _SQUASH.sub("", option).lower() == want:
                    return True, option
            # A bound choice's answer is a code and nobody speaks a code. The
            # value stored is still the code: the display is how it was found,
            # never what is kept, so a value set that renames a concept cannot
            # rewrite what was recorded.
            for option, display in labels.items():
                if display and _SQUASH.sub("", display).lower() == want:
                    return True, option
            return False, None
        if kind == "structured":
            ok = isinstance(value, list) and all(isinstance(v, dict) for v in value)
            return (True, value) if ok else (False, None)
        if kind in ("string", "text", "url", "time"):
            return True, str(value).strip()
    except (TypeError, ValueError):
        return False, None
    return False, None


_OPS = {
    "exists": lambda have, want: (have is not None) == bool(want),
    "equals": lambda have, want: have == want,
    "not_equals": lambda have, want: have != want,
    "greater": lambda have, want: have is not None and have > want,
    "less": lambda have, want: have is not None and have < want,
    "greater_or_equals": lambda have, want: have is not None and have >= want,
    "less_or_equals": lambda have, want: have is not None and have <= want,
}


def enabled(fields, values):
    by = {f["link_id"]: f for f in fields}
    out = dict(values)
    for link_id in list(out):
        rules = by.get(link_id, {}).get("enable_when") or []
        if rules and not all(_OPS[r["operator"]](out.get(r["question"]), r["answer"])
                             for r in rules):
            del out[link_id]
    return out


CAP = 0.89   # under web/src/form/Form.tsx SURE, so every heard value reads as unconfirmed


def build_draft(operation, schema, answers, transcript, *, instrument, today):
    """One draft from a set of heard answers, or None when nothing coerced.

    `answers` is keyed by field id: a link_id for a top level question, and
    `group[index].link_id` for a question inside a repeating group. The index
    is the extractor's own numbering and is only used for grouping; the rows
    that survive are renumbered from zero so that the draft's ids address the
    payload it carries, with no gaps a renderer would have to guess about.
    """
    fields = flatten(schema)
    by = {f["link_id"]: f for f in fields}
    flat, rows, unfilled = {}, {}, []
    heard = {}
    for ident, a in answers.items():
        group, index, link_id = split_id(ident)
        field = by.get(link_id)
        ok, value = coerce(field, a["value"], today) if field else (False, None)
        if ok and (field.get("row_of") or None) != group:
            # Either a row field answered with no row, or a field answered
            # into a group it is not in. Both are dropped. The first is the
            # one that matters: folding it into row zero would put a dose on
            # whichever medicine happened to be first.
            ok = False
        if not ok:
            unfilled.append(ident)
            continue
        heard[ident] = a
        if group is None:
            flat[link_id] = value
        else:
            rows.setdefault(group, {}).setdefault(index, {})[link_id] = value

    kept = enabled(fields, flat)
    unfilled += [k for k in flat if k not in kept]
    values = dict(kept)
    # Renumbered in the extractor's own row order, which is the order the
    # transcript named them in.
    renumbered = {}
    for group in sorted(rows):
        made = []
        for index in sorted(rows[group]):
            for link_id in rows[group][index]:
                renumbered[row_id(group, index, link_id)] = \
                    row_id(group, len(made), link_id)
            made.append(rows[group][index])
        values[group] = made

    # The id each surviving answer arrived under, so its confidence and the
    # words it came from follow it through the renumbering.
    was = {new_id: old_id for old_id, new_id in renumbered.items()}
    ids = list(kept) + list(was)
    if not ids:
        return None

    return {"instrument": instrument, "operation": operation, "values": values,
            "confidence": {i: min(CAP, heard[was.get(i, i)]["confidence"]) for i in ids},
            "evidence": {i: heard[was.get(i, i)]["evidence"] for i in ids},
            # Every filled non text value, each under its own id, so a row's
            # third field is owed a tick of its own rather than riding on the
            # question's.
            "tick": [i for i in ids if by[split_id(i)[2]]["type"] in TICK_TYPES],
            "unfilled": sorted(unfilled), "transcript": transcript}


def demo():
    schema = {"questions": [
        {"link_id": "intro", "text": "Read this", "type": "display"},
        {"link_id": "systolic", "text": "Systolic BP", "type": "integer",
         "required": True, "styling_metadata": {"phc": {"unit": "mm[Hg]"}}},
        {"link_id": "right_eye", "text": "Right eye", "type": "group", "questions": [
            {"link_id": "re_va", "text": "Visual acuity", "type": "choice",
             "answer_option": [{"value": "6/6"}, {"value": "6/9"}, {"value": "6/60"}]}]},
        {"link_id": "pregnant", "text": "Pregnant", "type": "boolean"},
        {"link_id": "lmp", "text": "LMP", "type": "date",
         "enable_when": [{"question": "pregnant", "operator": "equals", "answer": True}]},
        {"link_id": "diagnosis", "text": "Diagnosis", "type": "group",
         "repeats": True, "questions": [
             {"link_id": "condition", "text": "Condition", "type": "choice",
              "answer_value_set": "condition-code", "required": True},
             {"link_id": "onset", "text": "Since", "type": "date"}]},
    ]}
    fields = flatten(schema)
    ids = [f["link_id"] for f in fields]
    assert ids == ["systolic", "re_va", "pregnant", "lmp", "condition", "onset"], ids
    by_all = {f["link_id"]: f for f in fields}
    assert by_all["condition"]["row_of"] == "diagnosis", by_all["condition"]
    assert by_all["condition"]["path"] == "diagnosis.condition"
    assert by_all["systolic"]["row_of"] is None
    # The hole a bound choice had: options, so a heard word has something to
    # match against, and labels, so the word can be the display.
    assert "44054006" in by_all["condition"]["options"], by_all["condition"]
    assert by_all["condition"]["labels"]["44054006"] == "Type 2 diabetes mellitus"
    by = {f["link_id"]: f for f in fields}
    assert by["re_va"]["path"] == "right_eye.re_va", by["re_va"]
    assert by["re_va"]["options"] == ["6/6", "6/9", "6/60"]
    assert by["systolic"]["unit"] == "mm[Hg]"

    today = date(2026, 9, 16)
    assert coerce(by["systolic"], "140", today) == (True, 140)
    assert coerce(by["systolic"], "one forty", today) == (False, None)
    assert coerce(by["systolic"], 140.5, today) == (False, None), "an integer is whole"
    assert coerce(by["re_va"], " 6 / 9 ", today) == (True, "6/9")
    assert coerce(by["re_va"], "6/12", today) == (False, None), "off the list is refused"
    assert coerce(by["pregnant"], "yes", today) == (True, True)
    assert coerce(by["pregnant"], "maybe", today) == (False, None)
    assert coerce(by["lmp"], "2026-08-01", today) == (True, "2026-08-01")
    assert coerce(by["lmp"], "15 August", today) == (True, "2026-08-15")
    assert coerce(by["lmp"], "15 December", today) == (True, "2025-12-15"), \
        "a day and month with no year is the most recent one, never the future"
    assert coerce(by["lmp"], "yesterday", today) == (True, "2026-09-15")
    assert coerce(by_all["condition"], "44054006", today) == (True, "44054006")
    assert coerce(by_all["condition"], "Type 2 diabetes mellitus", today) == \
        (True, "44054006"), "a spoken display finds its code, and the code is kept"
    assert coerce(by_all["condition"], "type 2  DIABETES mellitus", today) == \
        (True, "44054006")
    assert coerce(by_all["condition"], "Dengue", today) == (False, None), \
        "a condition this build cannot code is refused, never stored as text"

    assert split_id("medications[2].dose") == ("medications", 2, "dose")
    assert split_id("systolic") == (None, None, "systolic")
    assert row_id("medications", 1, "dose") == "medications[1].dose"

    assert enabled(fields, {"pregnant": False, "lmp": "2026-08-01"}) == {"pregnant": False}
    assert enabled(fields, {"pregnant": True, "lmp": "2026-08-01"}) == \
        {"pregnant": True, "lmp": "2026-08-01"}

    answers = {"systolic": {"value": "140", "confidence": 0.97, "evidence": "BP 140"},
               "re_va": {"value": "6/12", "confidence": 0.9, "evidence": "six by twelve"},
               "lmp": {"value": "15 August", "confidence": 0.9, "evidence": "15 August"},
               "diagnosis[0].condition": {"value": "Type 2 diabetes mellitus",
                                          "confidence": 0.8, "evidence": "sugar"},
               "diagnosis[0].onset": {"value": "15 August", "confidence": 0.7,
                                      "evidence": "since August"},
               # A second row, numbered 4 by the extractor. It is kept, and it
               # is renumbered to 1 so the draft's ids address its own payload.
               "diagnosis[4].condition": {"value": "Foot swelling",
                                          "confidence": 0.6, "evidence": "swollen foot"},
               # A row field with no row. Dropped, never folded into row zero.
               "condition": {"value": "Foot swelling", "confidence": 0.9,
                             "evidence": "swollen foot"},
               # A row field addressed into a group it is not in.
               "systolic": {"value": "140", "confidence": 0.97, "evidence": "BP 140"}}
    d = build_draft("x.op", schema, answers, "BP 140 ...", instrument="i", today=today)
    assert d["values"] == {"systolic": 140, "diagnosis": [
        {"condition": "44054006", "onset": "2026-08-15"},
        {"condition": "297142003"}]}, d
    assert d["unfilled"] == ["condition", "lmp", "re_va"], \
        "off-list, disabled and row-less are heard but not filled"
    assert d["confidence"] == {"systolic": 0.89, "diagnosis[0].condition": 0.8,
                               "diagnosis[0].onset": 0.7,
                               "diagnosis[1].condition": 0.6}, "capped under SURE"
    assert sorted(d["tick"]) == ["diagnosis[0].condition", "diagnosis[0].onset",
                                 "diagnosis[1].condition", "systolic"], \
        "every non text value of every row is owed its own tick"
    assert d["evidence"]["diagnosis[1].condition"] == "swollen foot", \
        "the words follow the answer through the renumbering"
    assert d["evidence"]["systolic"] == "BP 140"
    assert build_draft("x.op", schema, {}, "hello", instrument="i", today=today) is None
    only_rows = build_draft("x.op", schema, {
        "diagnosis[0].condition": {"value": "44054006", "confidence": 1.0,
                                   "evidence": "sugar"}},
        "sugar", instrument="i", today=today)
    assert only_rows["values"] == {"diagnosis": [{"condition": "44054006"}]}, only_rows
    print("ok api.fill")


if __name__ == "__main__":
    demo()
