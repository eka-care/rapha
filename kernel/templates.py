"""The doctor's templates: one operation's form, narrowed, generated not written.

What a template is
------------------
A clinician does not want the general consultation form for every patient. A
long term condition review, an antenatal visit and a follow up each ask a
different, mostly predictable subset of the same questions.

A template here is NOT a fourth kind of declaration and NOT a new
questionnaire. `bundles/<id>/bundle.yaml` already says what a template is:
"A template is an operation: its questionnaire is the form, and its mapping is
the only way anything heard reaches a row." So a template IS an operation, and
this module is what stops that meaning costing a hand written form each time.

A template declaration names one existing operation and an ordered subset of
the questions that operation's form already asks. From it this module
GENERATES the operation atom and the questionnaire, derived from the base's
own: the same questions, the same bindings, the same mapping sources, the same
capability, station, preconditions, instrument, emits and surfaces. Nothing
clinical is declared here. No condition, no medicine, no value set, no
interval, no schedule, no threshold.

Why generated and not written
-----------------------------
Three hand written questionnaires would be three more files to keep in step
with every value set, every binding and every mapping, which is the drift this
architecture exists to prevent. Generated files cannot drift: `drift()` holds
what is on disk against what the declaration produces, so a hand edit to a
generated atom fails the gate rather than surviving.

Four consequences worth stating, because each one is a property and not a
convenience:

- a template publishes into the SAME document path as its base. Its mapping
  records are the base's, so it writes the same resources, and
  `bundle.yaml documents` files a resource by type and never by operation.
- the narrative fallback is intact by construction. The note record is the
  base's `{note: [...]}` source narrowed to the questions the template asks,
  so a template that codes nothing still carries its consultation as text
  into a DocumentReference.
- the tick cannot be weakened. A template narrows the FORM, not a renderer's
  display, so a question a template does not ask is absent from its
  questionnaire and no recording can produce a value for it. There is no
  hidden field to fill untickably. `api/fill.py` is unchanged and owes a tick
  for every non text value of every row of whatever form it is handed.
- a narrowing that would record nothing is refused. A template whose narrowed
  mapping writes no row is a form that looks like a consultation and keeps no
  consultation.

What this does NOT solve
------------------------
The clinical vocabulary is three conditions and six medicines, neither list
signed off, and nothing in either is obstetric. So the narrowing a template
declares is the only thing that distinguishes one visit type from another
today, and WHICH questions each visit type should ask is a clinical and
product decision, not this module's. Every template declaration carries its
own sign off banner for the same reason `terminology/condition-code.json`
carries one.

Pure: reads files, writes the two generated files when asked, touches no
database and no network.
"""
from __future__ import annotations

import pathlib

import yaml

from catalogue import validate, vocab
from catalogue.build import parse

ROOT = pathlib.Path(__file__).parents[1]
OPS = ROOT / "catalogue" / "ops"
SCHEMAS = ROOT / "questionnaires"

# What a template declaration may say, and nothing else. `of` is the operation
# it narrows, `asks` the ordered subset of that form's questions, `require`
# the answers this visit type will not commit without, and the rest is the
# words a clinician reads.
KEYS = ("of", "short", "title", "summary", "asks", "require", "plain",
        "sign_off")
REQUIRED = ("of", "short", "title", "summary", "asks", "plain", "sign_off")

# Frontmatter a template inherits from its base, unchanged. A template may not
# widen what a person may do, where they may do it, or which surface may
# invoke it: every one of these is the base's answer.
INHERITED = ("type", "kind", "capability", "station", "instrument",
             "preconditions", "irreversibility", "writes", "emits",
             "surfaces", "verified", "scope_qualifier", "presents")

# The mapping sources that read one named answer, and the two that read a list
# of them. Narrowing a record means asking which questions it reads and
# whether the template still asks them.
ONE_LINK = ("answer", "answer_code", "answer_code_system", "answer_code_display")
LINK_LIST = ("joined", "note")

BANNER = ("GENERATED FILE. Do not edit. It is derived from the `templates` "
          "declaration in bundles/%s/bundle.yaml by kernel/templates.py, and "
          "`sh scripts/check.sh` fails on a hand edit. Change the declaration.")


def declared(manifest):
    """{template_id: declaration} this bundle.yaml declares, or {}."""
    return dict(manifest.get("templates") or {})


# --------------------------------------------------------------------------
# narrowing
# --------------------------------------------------------------------------

def _record_links(record):
    """(the top level questions this mapping record reads, the list sources).

    A `per_row` record's FIELDS read the group's own sub questions and never a
    top level one, which kernel/mapping.py refuses to mix. So a per_row record
    reads exactly one top level question: the group itself.
    """
    if record.get("per_row"):
        return {record["per_row"]}, {}
    links, lists = set(), {}
    for key in ("per_item",):
        if record.get(key):
            links.add(record[key])
    for link_id in record.get("per_question") or []:
        links.add(link_id)
    for column, source in (record.get("fields") or {}).items():
        if not isinstance(source, dict) or len(source) != 1:
            continue
        (kind, arg), = source.items()
        if kind in ONE_LINK:
            links.add(arg)
        elif kind in LINK_LIST:
            lists[column] = (kind, list(arg or []))
    return links, lists


def narrow(records, asks):
    """The base's mapping records, kept for the questions this template asks.

    A record is dropped when a question it reads is not asked, because a
    column sourced from an answer the form does not collect is a column that
    can never be filled. A list source (`note`, `joined`) is narrowed instead
    of dropped, and the record goes only when the narrowing leaves it empty.
    A record made only of literals and the actor is always kept: that is the
    encounter row an operation touches.
    """
    asked = set(asks)
    kept = []
    for record in records:
        links, lists = _record_links(record)
        if links - asked:
            continue
        out = {k: v for k, v in record.items() if k != "fields"}
        fields, empty = {}, False
        for column, source in (record.get("fields") or {}).items():
            if column in lists:
                kind, named = lists[column]
                narrowed = [k for k in named if k in asked]
                if not narrowed:
                    empty = True
                    break
                fields[column] = {kind: narrowed}
            else:
                fields[column] = source
        if empty:
            continue
        out["fields"] = fields
        kept.append(out)
    return kept


def schema_id(template_id):
    """The questionnaire id a template's generated form is filed under.

    Derived from the operation id so there is no second name to keep in step:
    `phc.op.ncd-review` asks `phc.schema.ncd-review-v1`.
    """
    prefix, _, stem = template_id.partition(".op.")
    return "%s.schema.%s-v1" % (prefix, stem)


def questionnaire(template_id, decl, base_schema):
    """The generated questionnaire: the base's own questions, narrowed."""
    by = {q["link_id"]: q for q in base_schema.get("questions") or []}
    require = set(decl.get("require") or [])
    questions = []
    for link_id in decl["asks"]:
        q = dict(by[link_id])
        if link_id in require:
            q["required"] = True
        questions.append(q)
    phc = dict(validate._phc(base_schema))
    phc["operation"] = template_id
    return {
        "version": base_schema.get("version", "1.0"),
        "slug": schema_id(template_id).replace(".schema.", "-").replace(".", "-"),
        "title": decl["title"],
        "status": base_schema.get("status", "active"),
        "subject_type": base_schema.get("subject_type"),
        "styling_metadata": {"phc": phc},
        "questions": questions,
    }


def _body(template_id, decl, base_id, bundle_id):
    """The five sections an operation atom's body must carry.

    The clinician facing paragraph is the declaration's own `plain`, because
    words a clinician reads are the facility's and not a generator's. The
    other four say what this template shares with its base, which is
    everything, and that is the honest answer rather than four paragraphs
    restating the base's.
    """
    return """
## In plain words

%s

%s

## Before you start

The same as %s, which this template narrows: nothing about who may do this,
where, or what must already be true is changed by asking fewer questions.

## What happens

Exactly what %s does. The form is narrower, the mapping is the base's own
narrowed to the questions this form asks, and the record published is the
same kind of record filed under the same heading.

## How you know it worked

The note is on the thread under this template's own title, and an answer this
form did not ask is absent rather than empty.

## When it goes wrong

- **A question you needed is not on this form.** Use %s, which asks all of
  them. Narrowing is a declaration in bundles/%s/bundle.yaml and not a code
  change.
- **The finding you want to record cannot be coded.** It belongs in the
  narrative, which still reaches the published document as text. That is the
  designed fallback and not a workaround.
""" % (decl["plain"].strip(), decl["sign_off"].strip(), base_id, base_id,
       base_id, bundle_id)


def atom(template_id, decl, base_fm, base_records, bundle_id):
    """The generated operation atom, as (frontmatter dict, body str)."""
    fm = {k: base_fm.get(k) for k in INHERITED if k in base_fm}
    records = narrow(base_records, decl["asks"])
    fm["id"] = template_id
    fm["short"] = decl["short"]
    fm["title"] = decl["title"]
    fm["summary"] = decl["summary"].strip()
    fm["input"] = schema_id(template_id)
    fm["writes"] = [r["resource"] for r in records]
    fm["mapping"] = {"records": records}
    fm["related"] = {"operations": [decl["of"]], "concepts": []}
    return fm, _body(template_id, decl, decl["of"], bundle_id)


_ORDER = ("id", "type", "kind", "short", "title", "summary", "capability",
          "scope_qualifier", "presents", "station", "instrument",
          "preconditions", "irreversibility", "input", "writes", "mapping",
          "emits", "surfaces", "verified", "related")


def _dump(fm, bundle_id):
    ordered = {k: fm[k] for k in _ORDER if k in fm}
    ordered.update({k: v for k, v in fm.items() if k not in ordered})
    text = yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False,
                          width=100, allow_unicode=True)
    return "---\n# %s\n%s---\n" % (BANNER % bundle_id, text)


def generate(manifest, ops_dir=OPS, schemas_dir=SCHEMAS):
    """{path: text} every file this bundle's template declarations produce.

    Both generated files for each template: the questionnaire and the atom.
    The caller writes them (scripts/build_templates.py) or compares them
    (drift, called from the lint).
    """
    import json

    bundle_id = manifest.get("id", "?")
    out = {}
    for template_id, decl in sorted(declared(manifest).items()):
        base_path = pathlib.Path(ops_dir) / ("%s.md" % decl["of"])
        base_fm, _ = parse(base_path)
        base_schema = validate.load(base_fm["input"])
        records = list((base_fm.get("mapping") or {}).get("records") or [])
        schema = questionnaire(template_id, decl, base_schema)
        out[pathlib.Path(schemas_dir) / ("%s.json" % schema_id(template_id))] = \
            json.dumps(schema, indent=2) + "\n"
        fm, body = atom(template_id, decl, base_fm, records, bundle_id)
        out[pathlib.Path(ops_dir) / ("%s.md" % template_id)] = _dump(fm, bundle_id) + body
    return out


def drift(manifest, ops_dir=OPS, schemas_dir=SCHEMAS):
    """Failures where a generated file on disk is not what the declaration says.

    This is what makes "generated, so it cannot drift" true rather than
    hopeful. A hand edit to a generated atom, a stale file left behind by a
    declaration that changed, and a missing file are the same failure here.
    """
    bad = []
    for path, want in generate(manifest, ops_dir, schemas_dir).items():
        if not path.exists():
            bad.append("%s is declared as a template and not generated. Run "
                       "python3 scripts/build_templates.py" % path.name)
        elif path.read_text() != want:
            bad.append("%s does not match the `templates` declaration it is "
                       "generated from. Do not edit it; change the "
                       "declaration and run python3 "
                       "scripts/build_templates.py" % path.name)
    return bad


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------

def _bound_slugs(questions):
    """Every value set an asked question, or one of its sub questions, binds
    its answer to."""
    from kernel import terminology
    out = set()
    for q in validate.walk(questions):
        slug = terminology.answer_binding(q)
        if slug:
            out.add(slug)
    return out


def lint(manifest, ops, decls, ops_dir=OPS):
    """Return a list of failure strings. Empty means the templates are sound.

    `ops` is the compiled operations from catalogue.json, `decls` the bundle
    directory's {id: (frontmatter, body)} so a template can be held against
    the scribe instrument and the workflow that have to offer it.

    What this refuses, each one a template that would look right and be
    wrong:

    - a template naming a question the base form does not ask. The narrowing
      is a list of link_ids and a typo in it is a question silently missing
      from a clinician's form.
    - a binding to a value set this facility cannot check offline. Inherited
      from the base, so it can only break when the base's binding does, and
      a bound choice with no cached value set draws an empty dropdown rather
      than failing.
    - a template claiming a station or a capability that is not declared: one
      the bundle does not load, one no scribe instrument may fill, or one the
      workflow does not offer at its own station. All three are a template
      that exists and can never be reached.
    - a narrowing that records nothing, a narrowing of a narrowing, a
      duplicate, a missing word a clinician reads, an unknown key, and a
      generated file that has been edited by hand.

    What it deliberately does NOT refuse
    ------------------------------------
    A required answer that goes nowhere. kernel/mapping.py already refuses an
    operation with a required question that no record stores and that nobody
    declared they were dropping, and it runs over a generated atom and its
    generated form exactly as over a hand written one. A second copy of that
    rule here would be a rule asserted twice, which is a rule nobody
    maintains, and it could not be made to fail: narrowing removes a question
    rather than orphaning one. `scripts/check_templates.py` proves the
    existing rule reaches a template instead.
    """
    from kernel import terminology

    bad = []
    templates = declared(manifest)
    if not templates:
        return bad
    loaded = list(manifest.get("operations") or [])
    scribe_ops = {oid for fm, _ in decls.values() if fm.get("type") == "instrument"
                  and fm.get("kind") == "scribe" for oid in fm.get("operations") or []}
    step_ops = {}
    for fm, _ in decls.values():
        if fm.get("type") != "workflow":
            continue
        for step in fm.get("steps") or []:
            step_ops.setdefault(step.get("station"), set()).update(
                step.get("operations") or [])

    for template_id, decl in sorted(templates.items()):
        where = "bundle.yaml templates.%s" % template_id
        if not isinstance(decl, dict):
            bad.append("%s: not a declaration" % where)
            continue
        for key in sorted(set(decl) - set(KEYS)):
            bad.append("%s: unknown key '%s'" % (where, key))
        missing = [k for k in REQUIRED if not decl.get(k)]
        if missing:
            bad.append("%s: missing %s" % (where, ", ".join(missing)))
            continue

        base_id = decl["of"]
        if base_id in templates:
            bad.append("%s: narrows '%s', which is itself a template. A "
                       "template narrows an operation, and a narrowing of a "
                       "narrowing has two declarations to keep in step"
                       % (where, base_id))
            continue
        if base_id not in ops:
            bad.append("%s: narrows '%s', which is not in the catalogue"
                       % (where, base_id))
            continue
        if base_id not in loaded:
            bad.append("%s: narrows '%s', which this bundle does not load"
                       % (where, base_id))
            continue
        if template_id not in loaded:
            bad.append("%s: is not in bundle.yaml operations, so it is "
                       "generated and never loaded" % where)

        base_path = pathlib.Path(ops_dir) / ("%s.md" % base_id)
        base_fm, _ = parse(base_path)
        if base_fm.get("kind") != "write":
            bad.append("%s: narrows '%s', which writes nothing, so there is "
                       "no mapping to narrow" % (where, base_id))
            continue
        try:
            base_schema = validate.load(base_fm["input"])
        except FileNotFoundError as exc:
            bad.append("%s: %s" % (where, exc))
            continue

        by = {q["link_id"]: q for q in base_schema.get("questions") or []}
        asks = list(decl.get("asks") or [])
        for link_id in sorted(set(asks)):
            if asks.count(link_id) > 1:
                bad.append("%s: asks '%s' twice" % (where, link_id))
        for link_id in asks:
            if link_id not in by:
                bad.append("%s: asks '%s', which %s does not ask. A template "
                           "narrows the base form and cannot add to it"
                           % (where, link_id, base_fm["input"]))
        for link_id in decl.get("require") or []:
            if link_id not in asks:
                bad.append("%s: requires '%s', which it does not ask"
                           % (where, link_id))

        asked = [by[k] for k in asks if k in by]
        for slug in sorted(_bound_slugs(asked)):
            try:
                terminology.LOCAL.concepts(slug)
            except terminology.UnboundCoding as exc:
                bad.append("%s: a question it asks binds its answer to value "
                           "set '%s': %s" % (where, slug, exc))

        records = narrow(list((base_fm.get("mapping") or {}).get("records") or []),
                         [k for k in asks if k in by])
        if not records:
            bad.append("%s: its narrowing leaves no mapping record, so the "
                       "form records nothing it is answered with" % where)
        station = base_fm.get("station")
        if template_id not in scribe_ops:
            bad.append("%s: no scribe instrument lists it, so a recording may "
                       "never fill it and the template is unreachable" % where)
        if template_id not in step_ops.get(station, set()):
            bad.append("%s: the workflow does not offer it at '%s', the "
                       "station it inherits, so nobody is ever shown it"
                       % (where, station))

    # Only once the declarations themselves are sound. A declaration naming a
    # question that does not exist cannot be generated at all, and the line
    # above already says why in the words a reader needs.
    if not bad:
        bad += drift(manifest, ops_dir)
    return bad
