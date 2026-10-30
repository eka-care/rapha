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
    {actor: id}                who is performing this operation

`{actor: id}` is required on every record, and it is the answer to "who wrote
this row". Rows used to land with `created_by` null on every adapter, which
left the audit trail as the only record of authorship and made separation of
duties a convention about which role bundle a person logs in with.

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
from kernel import terminology

OPS = pathlib.Path(__file__).parents[1] / "catalogue" / "ops"

SOURCES = ("answer", "const", "item", "minus", "question", "joined", "note",
           "json", "actor",
           # The third binding form: the ANSWER carries the concept. One kind
           # per part of the coding, mirroring the `question:` facts, because
           # the grammar is one key and one argument and a nested selector
           # would be the first exception to that.
           "answer_code", "answer_code_system", "answer_code_display")
# Sources that do not read the payload. A record made only of these is written
# every time; a record with any other source is written only when the payload
# gave one of them a value.
PAYLOAD_FREE = ("const", "actor")
ACTOR_FACTS = ("id",)
ITEM_ONLY = ("item", "minus")
QUESTION_ONLY = ("question",)
# What `{question: X}` may ask about the question a row is being made for.
# `link_id` and `answer` are facts about the form. The five below are facts a
# question's BINDING produced, which is why this file imports
# kernel/terminology.py, and each maps to (which binding, which part of that
# binding's coding).
#
# How invariant I1 is held, in two places, because one of them cannot be
# enough:
#
#   at build time, _compile_record resolves each of these through
#   Terminology.bound(), whose only way to return anything is to have found
#   the code in the value set. A question declaring a code its value set does
#   not hold fails the build.
#
#   at write time, _value re-checks the code against the same authority before
#   it will fill a column with it. That check is not a formality: the compiled
#   mapping goes on the wire as plain JSON (web/src/structured.ts reads it, so
#   web/src/messages.check.ts json.dumps it), which means the Coding object
#   cannot travel and the facts arrive as strings. A string carries no proof,
#   so the proof is re-established where the row is made.
#
# The re-check is a dict lookup in an lru_cached local file. No socket, no
# database, nothing that can be down. CARE pays a Postgres read plus an HTTP
# round trip per bound field per write for the same guarantee, and stubs the
# whole thing out in its test suite because of it.
CODING_FACTS = {
    "code": ("code", "code"),
    "code_system": ("code", "system"),
    "code_display": ("code", "display"),
    "unit": ("unit", "code"),
    "unit_system": ("unit", "system"),
}
# Which value set each binding is closed over.
CODING_BINDING = {"code": terminology.CODE_BINDING, "unit": terminology.UNIT_BINDING}

# The answer bound family, and which part of the resolved coding each reads.
# Unlike the `question:` facts these cannot be resolved at build time: the
# concept is whichever one the technician picked, so resolution happens in
# _value at write time, through the same single constructor. The value set is
# the question's own `answer_value_set`, so one source kind serves a lab
# analyte and a unit and anything else that binds an answer later.
ANSWER_CODING_FACTS = {"answer_code": "code",
                       "answer_code_system": "system",
                       "answer_code_display": "display"}
QUESTION_FACTS = ("link_id", "answer") + tuple(CODING_FACTS)
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


def _bound_fact(fact, context, terminology_=None):
    """One fact a question's binding produced, re-checked before it is stored.

    This is the write path half of invariant I1, and the clause that makes it
    a check and not a comment is the `validate` call: a code the value set
    does not hold stops the write rather than becoming a row. A missing fact
    stops it too, because a coding column that lands null is the silent
    failure this file exists to prevent.
    """
    which, _ = CODING_FACTS[fact]
    code = context.get(which if which != "code" else "code")
    value = context.get(fact)
    where = context.get("link_id")
    if _blank(code) or _blank(value):
        raise terminology.UnboundCoding(
            "question %r has no %s binding, so {question: %s} has nothing a "
            "value set vouched for" % (where, which, fact))
    t = terminology_ or terminology.LOCAL
    if not t.validate(CODING_BINDING[which], code):
        raise terminology.UnboundCoding(
            "question %r would store %r, which value set %r does not hold"
            % (where, code, CODING_BINDING[which]))
    return value


def _value(source, payload, context, actor=None):
    (kind, arg), = source.items()
    if kind == "const":
        return arg
    if kind == "actor":
        return actor
    if kind == "answer":
        return payload.get(arg)
    if kind in ANSWER_CODING_FACTS:
        question = (context.get("questions") or {}).get(arg)
        if question is None:
            raise terminology.UnboundCoding(
                "{%s: %s} has no question to read a binding from; lint should "
                "have refused it" % (kind, arg))
        answer = payload.get(arg)
        if _blank(answer):
            # Unreachable from _row, which refuses the whole record first.
            # Kept as the same fail closed shape _bound_fact has rather than
            # returning None: a code column that lands null is the silent
            # failure this file exists to prevent, and the two coding families
            # must not disagree about that.
            raise terminology.UnboundCoding(
                "question %r was not answered, so {%s: %s} has no concept to "
                "store" % (arg, kind, arg))
        coding = terminology.answer_coding(question, answer)
        return getattr(coding, ANSWER_CODING_FACTS[kind])
    if kind == "item":
        return _first(context, arg)
    if kind == "minus":
        value = _first(context, arg)
        return None if _blank(value) else "-%s" % value
    if kind == "question":
        if arg in CODING_FACTS:
            return _bound_fact(arg, context)
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


def _row(record, payload, context, actor=None):
    """One row, or None when this record has nothing to say about this payload.

    A record that codes a column from an answer writes NOTHING when that
    answer is absent. Not a style choice: without it a laboratory result whose
    analyte was left blank became an observation carrying a value and a unit
    and no code, which is a clinical number with nothing saying what it
    measured. Found by mutation. The validator refuses that payload upstream
    because the analyte is required, so this is the second line, and it is the
    line that also makes an OPTIONAL coded answer safe: no concept means no
    row rather than an uncoded one.
    """
    for source in record["fields"].values():
        if not isinstance(source, dict) or len(source) != 1:
            continue
        (kind, arg), = source.items()
        if kind in ANSWER_CODING_FACTS and _blank(payload.get(arg)):
            return None
    row, derived, any_derived_source = {}, False, False
    for column, source in record["fields"].items():
        from_payload = not set(source) & set(PAYLOAD_FREE)
        any_derived_source = any_derived_source or from_payload
        value = _value(source, payload, context, actor)
        if _blank(value):
            continue
        row[column] = value
        derived = derived or from_payload
    if any_derived_source and not derived:
        return None
    return row


def records(op, payload, actor=None):
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
        # The bound questions this record's answer coding sources need, so
        # _value never opens a questionnaire. Compiled in, and JSON able,
        # because the compiled mapping travels to the renderer.
        bound = record.get("questions") or {}
        for context in contexts:
            if bound:
                context = dict(context, questions=bound)
            row = _row(record, payload, context, actor)
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
        elif arg in CODING_FACTS:
            # One branch for all five, because they are one rule: a column
            # that reads a binding needs the question to have that binding,
            # or it lands null. The wording differs because the two bindings
            # are declared differently, not because the rule does.
            which, _ = CODING_FACTS[arg]
            for link_id in record.get("per_question") or []:
                if _declares(questions.get(link_id), which):
                    continue
                fail("%s: question '%s' %s, so {question: %s} has nothing %s"
                     % (where, link_id,
                        "declares no unit" if which == "unit" else "binds no code",
                        arg,
                        "to read" if which == "unit"
                        else "a value set vouched for"))
        return set()
    if kind == "answer":
        if arg not in questions:
            fail("%s: '%s' is not a question on this form" % (where, arg))
        return {arg}
    if kind in ANSWER_CODING_FACTS:
        if arg not in questions:
            fail("%s: '%s' is not a question on this form" % (where, arg))
        elif not terminology.answer_binding(questions[arg]):
            # The failure this exists for: a column that would hold a code,
            # filled from an answer nothing checks. That is the defect the
            # analyte column had, where whatever the technician typed became
            # the report's code.
            fail("%s: question '%s' declares no %s, so {%s: %s} would store a "
                 "code no value set vouched for"
                 % (where, arg, terminology.ANSWER_VALUE_SET, kind, arg))
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
    if kind == "actor":
        if arg not in ACTOR_FACTS:
            fail("%s: actor takes one of %s" % (where, ", ".join(ACTOR_FACTS)))
        return set()
    return set()                       # const, item, minus: no link_id


def _unit(question):
    return ((question or {}).get("styling_metadata") or {}).get("phc", {}).get("unit")


def _declares(question, which):
    """Does this question bind a coding of this kind at all?

    A question's own concept is declared as a bare `code`; its unit is read
    from styling_metadata.phc.unit, where it already lives next to the range
    that validates it. Neither is moved and neither is duplicated: see
    kernel/terminology.question_codings.
    """
    if which == "unit":
        return bool(_unit(question))
    return bool((question or {}).get("code"))


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
    # Every row says who wrote it. Not a style rule: a row with no author is
    # why "the same person must not verify their own result" could be declared
    # nowhere and enforced nowhere.
    if not any(isinstance(s, dict) and "actor" in s for s in fields.values()):
        fail("%s: no author. Give one column {actor: id}" % where)
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
    try:
        return [_compile_record(r, questions) for r in declared], []
    except terminology.UnboundCoding as exc:
        # A declared code outside its value set is a build failure, reported
        # like every other lint line rather than raised as a traceback: the
        # person who mistyped a LOINC code should read it next to whatever
        # else is wrong with the atom.
        return [], ["%s" % exc]


def _compile_record(record, questions, terminology_=None):
    """One compiled record.

    Compiling resolves two things so that evaluation never opens a file: the
    per_question facts, and the bound codings. The codings are resolved HERE,
    at build time, once per question per build, and not once per write: the
    local cache is the authority and it does not change between builds, so a
    per write lookup would buy nothing and put a file read on the hot path.
    CARE pays a database read plus an HTTP round trip per bound field per
    write; this pays none. kernel/terminology.py says more about why.
    """
    return {
        "resource": record["resource"],
        "per_item": record.get("per_item"),
        "per_question": [_compile_question(questions[link_id], terminology_)
                         for link_id in record.get("per_question") or []] or None,
        "questions": _compile_bound(record, questions),
        "fields": dict(record["fields"]),
    }


def _compile_bound(record, questions):
    """The questions this record's answer coding sources resolve against.

    Only the two fields a resolution needs, so the compiled mapping stays
    small and plain JSON: the link_id, and the value set the answer is drawn
    from. The answer itself is not here, because it is not known until
    somebody answers, which is the whole difference between this binding form
    and the other two.
    """
    out = {}
    for source in (record.get("fields") or {}).values():
        if not isinstance(source, dict) or len(source) != 1:
            continue
        (kind, arg), = source.items()
        if kind not in ANSWER_CODING_FACTS or arg not in questions:
            continue
        out[arg] = {"link_id": arg,
                    terminology.ANSWER_VALUE_SET:
                        terminology.answer_binding(questions[arg])}
    return out


def _compile_question(question, terminology_=None):
    """One per_question context: plain JSON, every coding fact resolved.

    Plain JSON because this travels. The compiled mapping is served on
    /operations and read by web/src/structured.ts, so a Coding object here
    would be a 500 on the thread panel and a failed renderer check. The
    objects do their work in question_codings() and then only their facts
    survive, which is why _bound_fact re-checks one before storing it.
    """
    codings = terminology.question_codings(question, terminology_)
    out = {"link_id": question["link_id"]}
    for fact, (which, attr) in CODING_FACTS.items():
        coding = codings.get(which)
        out[fact] = getattr(coding, attr) if coding is not None else None
    return out


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
