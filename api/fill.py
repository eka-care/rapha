"""One questionnaire, any questionnaire: its fields as a flat list, and a heard
value made into a value that field can hold, or refused.

Pure. No model, no network, no clock except the `today` a caller hands in.
Run: python3 -m api.fill
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

TICK_TYPES = ("integer", "decimal", "quantity", "date", "dateTime", "time",
              "choice", "boolean")


def _options(q):
    return [str(o.get("value")) for o in q.get("answer_option") or [] if o.get("value") is not None]


def flatten(schema):
    out = []

    def walk(questions, prefix):
        for q in questions:
            path = prefix + [q["link_id"]]
            if q.get("type") == "group":
                walk(q.get("questions") or [], path)
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
                "enable_when": q.get("enable_when") or [],
            })
            walk(q.get("questions") or [], path)

    walk(schema.get("questions") or [], [])
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
            for option in field["options"]:
                if option == value or _SQUASH.sub("", option).lower() == want:
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
        {"link_id": "diagnosis", "text": "Diagnosis", "type": "structured",
         "structured_type": "condition", "repeats": True},
    ]}
    fields = flatten(schema)
    ids = [f["link_id"] for f in fields]
    assert ids == ["systolic", "re_va", "pregnant", "lmp", "diagnosis"], ids
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
    assert coerce(by["diagnosis"], [{"code": "Fever"}], today) == (True, [{"code": "Fever"}])
    assert coerce(by["diagnosis"], "Fever", today) == (False, None)

    assert enabled(fields, {"pregnant": False, "lmp": "2026-08-01"}) == {"pregnant": False}
    assert enabled(fields, {"pregnant": True, "lmp": "2026-08-01"}) == \
        {"pregnant": True, "lmp": "2026-08-01"}
    print("ok api.fill")


if __name__ == "__main__":
    demo()
