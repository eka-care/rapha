"""Which answer becomes which column. Declared on the operation, not guessed.

Why this exists
---------------
An operation atom says `writes: [observation]`. Until now nothing said that
`systolic` becomes the `code` column of an observation row whose `unit` is the
one the questionnaire already carries, so kernel/proposals.py handed the whole
payload to every resource and adapters/local/shape.py re-derived what a blood
pressure is. Adapter 1 would have re-derived it again, differently, and the two
would have drifted with nothing to catch it. That is a correctness problem: a
column nobody mapped is a clinical value silently dropped.

Why it lives on the operation atom
----------------------------------
The mapping is a fact about one operation, not about a questionnaire and not
about an adapter:

- It must be checked against `writes`, which is on the operation. A mapping
  naming a resource the operation does not write is the exact drift this is
  meant to make impossible, and only the atom holds both halves.
- The same questionnaire answer goes to different places in different
  operations. `abha_number` is a patient column when linking and would be a
  consent field somewhere else. Putting the mapping on the questionnaire would
  force one questionnaire per destination.
- Adapters must not own it, or every adapter owns a different copy. That is
  the bug being fixed.

So it is one new frontmatter key, `mapping`, beside `input` and `writes`, in
the same file, linted by the same build. It is not compiled into
catalogue.json: nothing outside the kernel writes rows, and the Go server
proposes only. Add it to the compiled artifact when an out of process consumer
needs it.

The grammar
-----------
    mapping:
      ignored: [<link_id>, ...]        # answers deliberately not stored
      records:
        - resource: <one of writes>
          per_item: <link_id>          # a repeating structured answer, one row per item
          per_question: [<link_id>]    # one row per answered question
          fields:
            <column>: <source>

A source is a single key dict, one of:

    {answer: <link_id>}        the payload's answer
    {const: <literal>}         a literal
    {item: <key> | [<key>]}    the current item's value, first non empty
    {minus: <key> | [<key>]}   the same, negated, for a stock decrement
    {question: link_id | answer | unit}   about the current question
    {joined: [<link_id>]}      non empty answers joined with a space
    {note: [<link_id>]}        non empty answers as labelled paragraphs
    {json: payload}            the whole payload as sorted JSON

`{question: unit}` is the point of the exercise: the unit comes from
`styling_metadata.phc.unit` on the question, so it is written once, next to the
range that validates it, and no adapter repeats it.

When a record is written
------------------------
A record whose fields are all `const` is written every time (the encounter row
a consultation touches). A record with any answer derived field is written only
when at least one of them produced a value, so an unanswered question is no
row rather than an empty row.

Honest limits
-------------
- A structured answer (`medications`, `dispenses`) has no sub schema in the
  questionnaire, so lint cannot check the keys `{item: ...}` names. The
  fallback list in the atom is the whole of what is accepted, which is at
  least now written down instead of hidden in an adapter.
- Column names are not linted here. The kernel must not know an adapter's
  schema. adapters/local/tests/test_store.py lints them against its own
  tables, and adapters/local/store.py raises on a column it does not have
  rather than dropping it.
- No default values. shape.py used to turn a dispense with no quantity into a
  quantity of 1; a silently invented stock decrement is worse than a null.

Pure: parses files, touches no database and no network. Python 3.9.
"""
from __future__ import annotations

import json
import pathlib
import re

from catalogue import validate
from catalogue.build import parse

OPS = pathlib.Path(__file__).parents[1] / "catalogue" / "ops"

SOURCES = ("answer", "const", "item", "minus", "question", "joined", "note", "json")
ITEM_ONLY = ("item", "minus")
QUESTION_ONLY = ("question",)
QUESTION_FACTS = ("link_id", "answer", "unit")
LINK_LISTS = ("joined", "note")
RECORD_KEYS = ("resource", "per_item", "per_question", "fields")
MAPPING_KEYS = ("records", "ignored")
_COLUMN = re.compile(r"^[a-z_][a-z0-9_]*$")


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------

def _blank(value):
    return value is None or value == "" or value == [] or value == {}


def items(payload, link_id):
    """A repeating structured answer as a list of dicts. A bare string counts
    as {"code": <it>}, because that is what a renderer sends for a free text
    line and dropping it would lose the order."""
    value = payload.get(link_id)
    if _blank(value):
        return []
    listed = value if isinstance(value, list) else [value]
    return [i if isinstance(i, dict) else {"code": str(i)} for i in listed]


def _first(context, keys):
    for key in ([keys] if isinstance(keys, str) else keys):
        if not _blank(context.get(key)):
            return context[key]
    return None


def _value(source, payload, context):
    (kind, arg), = source.items()
    if kind == "const":
        return arg
    if kind == "answer":
        return payload.get(arg)
    if kind == "item":
        return _first(context, arg)
    if kind == "minus":
        value = _first(context, arg)
        return None if _blank(value) else "-%s" % value
    if kind == "question":
        return context.get(arg)
    if kind == "joined":
        return " ".join(str(payload[k]) for k in arg
                        if not _blank(payload.get(k))) or None
    if kind == "note":
        return "\n\n".join("%s: %s" % (k.title(), payload[k]) for k in arg
                           if not _blank(payload.get(k))) or None
    if kind == "json":
        return json.dumps(payload, sort_keys=True)
    raise ValueError("unknown mapping source %r; lint should have refused it" % kind)


def _row(record, payload, context):
    """One row, or None when this record has nothing to say about this payload."""
    row, derived, any_derived_source = {}, False, False
    for column, source in record["fields"].items():
        any_derived_source = any_derived_source or "const" not in source
        value = _value(source, payload, context)
        if _blank(value):
            continue
        row[column] = value
        derived = derived or "const" not in source
    if any_derived_source and not derived:
        return None
    return row


def records(op, payload):
    """The rows this payload becomes, as [(resource, row)] in declared order.

    `op` is a compiled operation carrying "mapping"; kernel/declarations.py
    attaches it. An operation with no mapping writes nothing, which lint
    already refuses for a write operation.
    """
    payload = dict(payload or {})
    out = []
    for record in op.get("mapping") or []:
        if record.get("per_item"):
            contexts = items(payload, record["per_item"])
        elif record.get("per_question"):
            contexts = [dict(q, answer=payload.get(q["link_id"]))
                        for q in record["per_question"]
                        if not _blank(payload.get(q["link_id"]))]
        else:
            contexts = [{}]
        for context in contexts:
            row = _row(record, payload, context)
            if row is not None:
                out.append((record["resource"], row))
    return out


# --------------------------------------------------------------------------
# lint and compile
# --------------------------------------------------------------------------

def _lint_source(source, where, record, questions, fail):
    """Check one source dict. Returns the link_ids it consumes."""
    if not isinstance(source, dict) or len(source) != 1:
        fail("%s: a source is one of %s" % (where, ", ".join(SOURCES)))
        return set()
    (kind, arg), = source.items()
    if kind not in SOURCES:
        fail("%s: unknown source '%s'" % (where, kind))
        return set()
    if kind in ITEM_ONLY and not record.get("per_item"):
        fail("%s: '%s' reads the current item, so the record needs per_item" % (where, kind))
        return set()
    if kind in QUESTION_ONLY and not record.get("per_question"):
        fail("%s: 'question' reads the current question, so the record needs "
             "per_question" % where)
        return set()

    if kind == "question":
        if arg not in QUESTION_FACTS:
            fail("%s: question takes one of %s" % (where, ", ".join(QUESTION_FACTS)))
        elif arg == "unit":
            for link_id in record.get("per_question") or []:
                if not _unit(questions.get(link_id)):
                    fail("%s: question '%s' declares no unit, so {question: unit} "
                         "has nothing to read" % (where, link_id))
        return set()
    if kind == "answer":
        if arg not in questions:
            fail("%s: '%s' is not a question on this form" % (where, arg))
        return {arg}
    if kind in LINK_LISTS:
        if not isinstance(arg, list) or not arg:
            fail("%s: %s takes a non empty list of link_ids" % (where, kind))
            return set()
        for link_id in arg:
            if link_id not in questions:
                fail("%s: '%s' is not a question on this form" % (where, link_id))
        return set(arg)
    if kind == "json":
        if arg != "payload":
            fail("%s: json takes 'payload' and nothing else" % where)
        return set(questions)          # the blob keeps every answer
    return set()                       # const, item, minus: no link_id


def _unit(question):
    return ((question or {}).get("styling_metadata") or {}).get("phc", {}).get("unit")


def _lint_record(record, index, writes, questions, fail):
    where = "record %d" % index
    if not isinstance(record, dict):
        fail("%s: not a mapping" % where)
        return set()
    for key in set(record) - set(RECORD_KEYS):
        fail("%s: unknown key '%s'" % (where, key))
    resource = record.get("resource")
    if resource not in writes:
        fail("%s: writes '%s', which the operation does not declare in writes"
             % (where, resource))
    where = "record %d (%s)" % (index, resource)

    if record.get("per_item") and record.get("per_question"):
        fail("%s: per_item and per_question are alternatives, not both" % where)
    used = set()
    if record.get("per_item"):
        link_id = record["per_item"]
        if link_id not in questions:
            fail("%s: per_item '%s' is not a question on this form" % (where, link_id))
        elif questions[link_id]["type"] != "structured":
            fail("%s: per_item '%s' is type '%s', not structured, so it holds no "
                 "items" % (where, link_id, questions[link_id]["type"]))
        used.add(link_id)
    for link_id in record.get("per_question") or []:
        if link_id not in questions:
            fail("%s: per_question '%s' is not a question on this form" % (where, link_id))
        used.add(link_id)
    if "per_question" in record and not record.get("per_question"):
        fail("%s: per_question takes a non empty list of link_ids" % where)

    fields = record.get("fields")
    if not isinstance(fields, dict) or not fields:
        fail("%s: needs a non empty fields map" % where)
        return used
    for column, source in fields.items():
        if not _COLUMN.match(str(column)):
            fail("%s: '%s' is not a column name" % (where, column))
        used |= _lint_source(source, "%s field '%s'" % (where, column),
                             record, questions, fail)
    return used


def compile_records(fm, schema):
    """(compiled records, failures) for one operation atom.

    Compiling resolves `per_question` from a list of link_ids into the facts a
    row needs about each question, so evaluation never opens a questionnaire.
    """
    failures = []

    def fail(msg):
        failures.append(msg)

    questions = {q["link_id"]: q for q in validate.walk(schema["questions"])}
    writes = list(fm.get("writes") or [])
    block = fm.get("mapping")
    if block is None:
        fail("no mapping: a write operation must say which answer becomes "
             "which column")
        return [], failures
    if not isinstance(block, dict):
        fail("mapping must be a map with 'records' and optionally 'ignored'")
        return [], failures
    for key in set(block) - set(MAPPING_KEYS):
        fail("mapping: unknown key '%s'" % key)

    declared = block.get("records")
    if not isinstance(declared, list) or not declared:
        fail("mapping: records must be a non empty list")
        return [], failures

    used = set()
    for index, record in enumerate(declared):
        used |= _lint_record(record, index, writes, questions, fail)

    covered = {r.get("resource") for r in declared if isinstance(r, dict)}
    for resource in sorted(set(writes) - covered):
        fail("writes '%s' but no record maps anything into it" % resource)

    ignored = block.get("ignored") or []
    if not isinstance(ignored, list):
        fail("mapping: ignored must be a list of link_ids")
        ignored = []
    for link_id in ignored:
        if link_id not in questions:
            fail("ignored: '%s' is not a question on this form" % link_id)
        if link_id in used:
            fail("ignored: '%s' is also mapped; it is one or the other" % link_id)

    # The failure this catches is the quiet one: a required answer that no
    # record stores and nobody declared they were dropping.
    for link_id, question in questions.items():
        if question.get("required") and link_id not in used and link_id not in ignored:
            fail("'%s' is required and goes nowhere: map it, or list it under "
                 "mapping.ignored" % link_id)

    if failures:
        return [], failures
    return [_compile_record(r, questions) for r in declared], []


def _compile_record(record, questions):
    return {
        "resource": record["resource"],
        "per_item": record.get("per_item"),
        "per_question": [{"link_id": link_id, "unit": _unit(questions[link_id])}
                         for link_id in record.get("per_question") or []] or None,
        "fields": dict(record["fields"]),
    }


def load(ops_dir=OPS):
    """({op_id: compiled records}, [failures]) for every operation atom.

    Read operations are skipped: they write nothing, so they map nothing.
    """
    mappings, failures = {}, []
    for path in sorted(pathlib.Path(ops_dir).glob("*.md")):
        fm, _ = parse(path)
        op_id = fm.get("id") or path.stem
        if fm.get("kind") != "write":
            continue
        try:
            schema = validate.load(fm["input"])
        except (KeyError, FileNotFoundError) as exc:
            failures.append("%s: %s" % (op_id, exc))
            continue
        compiled, bad = compile_records(fm, schema)
        mappings[op_id] = compiled
        failures += ["%s: %s" % (op_id, line) for line in bad]
    return mappings, failures
