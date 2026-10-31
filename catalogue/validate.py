"""Payload validation against the CARE questionnaire an operation names.

CARE validates on submit and stays the authority at commit time. This runs
earlier, because the guard has to decide before anything is proposed, and a
proposal arriving over MCP must be checkable without a round trip.

So this is deliberately thin: required answers, types, choices, and the range
rule. Everything subtler is CARE's job.

Repeating groups
----------------
A question of type `group` with `repeats: true` holds a LIST OF ROWS, and each
row is a small payload over that group's own sub questions. Every rule above
applies per row: a required sub question is required in every row, a choice is
constrained in every row, a range is checked in every row, and a key the group
did not declare is refused in every row.

This is the replacement for `type: structured`, which is the escape hatch this
product inherited from CARE and which CARE never finished: its
`questionnaire/spec.py` carries `# TODO : Add validation later` against
`structured_type`, and its response validator opens by returning early for
exactly those questions. So a structured answer was validated nowhere, by
anybody, and a diagnosis was whatever text arrived. A repeating group is
CARE's own fully validated construct and it is native to FHIR R4, so this is
not a new idea, only the one of CARE's two ideas that was finished.
"""
import json
import pathlib

SCHEMAS = pathlib.Path(__file__).parents[1] / "questionnaires"

# CARE's QuestionType enum, care/emr/resources/questionnaire/spec.py
TYPES = {"group", "boolean", "decimal", "integer", "string", "text", "display",
         "date", "dateTime", "time", "choice", "url", "quantity", "structured"}

_NUMERIC = {"integer": int, "decimal": float}


def load(schema_id):
    path = SCHEMAS / f"{schema_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no questionnaire for '{schema_id}'")
    return json.loads(path.read_text())


def _phc(node):
    return (node.get("styling_metadata") or {}).get("phc") or {}


def walk(questions):
    for q in questions:
        yield q
        yield from walk(q.get("questions") or [])


def is_row_group(q):
    """Does this question hold a list of rows?

    A `group` that repeats. Both halves matter: a group that does not repeat is
    a heading over questions answered once, and a repeating question that is
    not a group is one answer given several times, which nothing here declares.
    """
    return (q or {}).get("type") == "group" and bool((q or {}).get("repeats"))


def row_groups(schema):
    """{link_id: question} for every repeating group on this form."""
    return {q["link_id"]: q for q in walk(schema["questions"]) if is_row_group(q)}


def row_questions(group):
    """{link_id: question} for one repeating group's sub questions."""
    return {q["link_id"]: q for q in walk((group or {}).get("questions") or [])}


def row_label(group):
    """What one row of this group is called, for a sentence a clinician reads.

    Declared in styling_metadata.phc.row, and "row" when a group does not say.
    Not derived from the link_id: `medications` would give "medications", and
    "medications 2 is required" is not a sentence.
    """
    return _phc(group or {}).get("row") or "row"


def _answer_problems(q, value, where, override):
    """Type, choice and range failures for one answered value. `where` is the
    prefix that says which row it was in, and is empty at the top level."""
    link_id = where + q["link_id"]
    caster = _NUMERIC.get(q["type"])
    if caster:
        try:
            value = caster(value)
        except (TypeError, ValueError):
            return [f"{link_id} must be {q['type']}"]
    elif q["type"] == "boolean" and not isinstance(value, bool):
        return [f"{link_id} must be boolean"]
    elif q["type"] == "choice":
        allowed = {o["value"] for o in q.get("answer_option") or []}
        if allowed and value not in allowed:
            return [f"{link_id} must be one of {sorted(allowed)}"]

    # The range rule. Addendum SSA: a value outside physiological range
    # blocks the commit and requires an explicit override carrying a
    # reason. The override is recorded, not waived.
    rng = _phc(q).get("range")
    if rng and caster and not (rng["low"] <= value <= rng["high"]):
        if override:
            return []
        return [f"{link_id} is {value}, outside {rng['low']} to {rng['high']}. "
                "Enter a reason to override, or correct the value."]
    return []


def _rows(link_id, group, payload, override):
    """Every failure in one repeating group's answer.

    The whole point of the repeating group: each row is validated, so there is
    no answer on this form that nothing checks. A row is refused for its own
    reasons and the row number is in every sentence, because "medications is
    invalid" does not tell a prescriber which line to fix.
    """
    subs = row_questions(group)
    label = row_label(group)
    value = payload.get(link_id)
    if value in (None, "", []):
        return [f"{link_id} is required"] if group.get("required") else []
    if not isinstance(value, list):
        return [f"{link_id} is a list of rows, one per {label}"]
    problems = []
    for index, row in enumerate(value):
        where = f"{link_id}[{index}]."
        if not isinstance(row, dict):
            problems.append(f"{link_id}[{index}] is not a {label}: a {label} is "
                            f"a set of answers, not a single value")
            continue
        for sub_id, q in subs.items():
            answered = sub_id in row and row[sub_id] not in (None, "")
            if q.get("required") and not answered:
                problems.append(f"{where}{sub_id} is required")
                continue
            if not answered:
                continue
            problems += _answer_problems(q, row[sub_id], where, override)
        for extra in sorted(set(row) - set(subs)):
            problems.append(f"{where}{extra} is not a question on this {label}")
    return problems


def make_validator(schema):
    """Return a callable(op, payload) -> list of problems, for guard.evaluate."""
    groups = row_groups(schema)
    inside = set()
    for group in groups.values():
        inside |= set(row_questions(group))
    # A repeating group's sub questions are answered inside its rows and never
    # at the top level, so they are not top level questions. That also makes a
    # sub question's link_id arriving at the top level an unknown key, which is
    # what it is: a renderer sending `condition` beside `diagnosis` has lost
    # the row it belonged to.
    questions = {q["link_id"]: q for q in walk(schema["questions"])
                 if q["link_id"] not in inside and q["link_id"] not in groups}

    def validate(op, payload):
        problems = []
        override = str(payload.get("override_reason") or "").strip()

        for link_id, q in questions.items():
            answered = link_id in payload and payload[link_id] not in (None, "")
            if q.get("required") and not answered:
                problems.append(f"{link_id} is required")
                continue
            if not answered:
                continue
            problems += _answer_problems(q, payload[link_id], "", override)

        for link_id, group in groups.items():
            problems += _rows(link_id, group, payload, override)

        unknown = set(payload) - set(questions) - set(groups) - {"override_reason"}
        problems.extend(f"{k} is not a question on this form" for k in sorted(unknown))
        return problems

    return validate


def flags(schema, payload):
    """State flags this payload raises. Critical values promote an action, and
    a question that declares `flags` with no `critical` band raises its flag
    when the answer is yes.

    The second form is what a consent is. A consent has no physiological range
    to be outside of, so requiring `critical` here is what left
    capture.consented declared, gated on, and raised by nothing. Deliberately
    strict: only a real boolean true raises, so a missing answer and a string
    fail closed to no flag.
    """
    raised = set()
    # A repeating group's sub questions are answered in rows, so looking for
    # them in the payload finds nothing. Flattened here with their row's value
    # rather than passed over: a sub question that declares a flag and raises
    # it nowhere is the hole `capture.consented` already had once.
    seen = []
    for q in walk(schema["questions"]):
        if is_row_group(q):
            for row in payload.get(q["link_id"]) or []:
                if isinstance(row, dict):
                    seen += [(sub, row.get(sub_id))
                             for sub_id, sub in row_questions(q).items()]
            continue
        seen.append((q, payload.get(q["link_id"])))
    for q, value in seen:
        phc = _phc(q)
        crit, flag = phc.get("critical"), phc.get("flags")
        if not flag or value in (None, ""):
            continue
        if not crit:
            if value is True:
                raised.add(flag)
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not (crit["low"] <= value <= crit["high"]):
            raised.add(flag)
    return raised
