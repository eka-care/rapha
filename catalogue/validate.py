"""Payload validation against the CARE questionnaire an operation names.

CARE validates on submit and stays the authority at commit time. This runs
earlier, because the guard has to decide before anything is proposed, and a
proposal arriving over MCP must be checkable without a round trip.

So this is deliberately thin: required answers, types, choices, and the range
rule. Everything subtler is CARE's job.
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


def make_validator(schema):
    """Return a callable(op, payload) -> list of problems, for guard.evaluate."""
    questions = {q["link_id"]: q for q in walk(schema["questions"])}

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

            value = payload[link_id]
            caster = _NUMERIC.get(q["type"])
            if caster:
                try:
                    value = caster(value)
                except (TypeError, ValueError):
                    problems.append(f"{link_id} must be {q['type']}")
                    continue
            elif q["type"] == "boolean" and not isinstance(value, bool):
                problems.append(f"{link_id} must be boolean")
                continue
            elif q["type"] == "choice":
                allowed = {o["value"] for o in q.get("answer_option") or []}
                if allowed and value not in allowed:
                    problems.append(f"{link_id} must be one of {sorted(allowed)}")
                    continue

            # The range rule. Addendum SSA: a value outside physiological range
            # blocks the commit and requires an explicit override carrying a
            # reason. The override is recorded, not waived.
            rng = _phc(q).get("range")
            if rng and caster and not (rng["low"] <= value <= rng["high"]):
                if override:
                    continue
                problems.append(
                    f"{link_id} is {value}, outside {rng['low']} to {rng['high']}. "
                    "Enter a reason to override, or correct the value.")

        unknown = set(payload) - set(questions) - {"override_reason"}
        problems.extend(f"{k} is not a question on this form" for k in sorted(unknown))
        return problems

    return validate


def flags(schema, payload):
    """State flags this payload raises. Critical values promote an action."""
    raised = set()
    for q in walk(schema["questions"]):
        phc, value = _phc(q), payload.get(q["link_id"])
        crit, flag = phc.get("critical"), phc.get("flags")
        if not (crit and flag) or value in (None, ""):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not (crit["low"] <= value <= crit["high"]):
            raised.add(flag)
    return raised
