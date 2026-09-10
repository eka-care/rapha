"""Lint and compile operation atoms.

The atoms are the specification. This turns them into the artifacts that run:
the guard's operation table and the MCP server's tool list. Because those are
executable, lint here is stricter than a docs linter would be. A capability
misspelt in frontmatter is not a typo, it is an operation nobody can invoke or,
worse, one anybody can.
"""
import json
import pathlib
import re
import sys

import yaml

from catalogue import validate, vocab

OPS = pathlib.Path(__file__).parent / "ops"
OUT = pathlib.Path(__file__).parent / "catalogue.json"
# The Go MCP server embeds its catalogue, and go:embed cannot reach out of
# its own package, so the compiled form is written to both places by this
# one writer. scripts/check.sh gates both against drift.
OUT_GO = pathlib.Path(__file__).parents[1] / "care_phc_mcp" / "catalogue.json"

REQUIRED = ("id", "type", "kind", "short", "title", "summary", "capability", "station",
            "instrument", "preconditions", "irreversibility", "input", "writes",
            "emits", "surfaces", "verified")


def parse(path):
    """Split an atom into (frontmatter dict, body str)."""
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: no frontmatter")
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body


def load():
    return {p: parse(p) for p in sorted(OPS.glob("*.md"))}


def lint(atoms):
    """Return a list of failure strings. Empty means the catalogue is sound."""
    bad = []
    ids = {fm.get("id") for fm, _ in atoms.values()}

    for path, (fm, body) in atoms.items():
        def fail(msg):
            bad.append(f"{path.name}: {msg}")

        for key in REQUIRED:
            if key not in fm:
                fail(f"missing required field '{key}'")
        if bad and fm.get("id") is None:
            continue

        if len(str(fm.get("short", ""))) > 14:
            fail(f"short label {fm['short']!r} is too long for an action bar")
        if fm["id"] != path.stem:
            fail(f"id '{fm['id']}' does not match filename")
        if fm["capability"] not in vocab.CAPABILITIES:
            fail(f"unknown capability '{fm['capability']}'")
        if fm["kind"] not in vocab.KINDS:
            fail(f"kind must be one of {vocab.KINDS}")
        if fm["station"] not in vocab.STATIONS:
            fail(f"unknown station '{fm['station']}'")
        if fm["instrument"] not in vocab.INSTRUMENTS:
            fail(f"unknown instrument '{fm['instrument']}'")
        if fm["irreversibility"] not in vocab.IRREVERSIBILITY:
            fail(f"irreversibility must be one of {vocab.IRREVERSIBILITY}")

        for pre in fm["preconditions"] or []:
            flag = pre[4:] if pre.startswith("not ") else pre
            if flag not in vocab.STATES:
                fail(f"precondition names unknown state '{flag}'")
        for flag in fm["emits"] or []:
            if flag not in vocab.STATES:
                fail(f"emits unknown state '{flag}'")
        for res in fm["writes"] or []:
            if res not in vocab.CARE_RESOURCES:
                fail(f"writes unknown CARE resource '{res}'")

        # v0.1 SS4: invocable identically from both surfaces, or it does not ship.
        if set(fm["surfaces"]) != {"rendered", "mcp"}:
            fail("surfaces must be exactly [rendered, mcp]")

        for section in vocab.BODY_SECTIONS:
            if f"## {section}" not in body:
                fail(f"missing body section '{section}'")

        for ref in (fm.get("related") or {}).get("operations") or []:
            if ref not in ids:
                fail(f"related operation '{ref}' does not exist")

        # The atom names a questionnaire; it must exist, be structurally sound,
        # and point back at this atom. A one-way reference drifts silently.
        try:
            schema = validate.load(fm["input"])
        except FileNotFoundError as e:
            fail(str(e))
        else:
            for q in validate.walk(schema["questions"]):
                if q["type"] not in validate.TYPES:
                    fail(f"question '{q['link_id']}' has non-CARE type '{q['type']}'")
                if q["type"] == "choice" and not (q.get("answer_option") or q.get("answer_value_set")):
                    fail(f"choice question '{q['link_id']}' has no options")
                if q["type"] == "group" and not q.get("questions"):
                    fail(f"group question '{q['link_id']}' has no sub-questions")
            back = validate._phc(schema).get("operation")
            if back != fm["id"]:
                fail(f"questionnaire '{fm['input']}' points at '{back}', not this atom")

        if "—" in body or "—" in str(fm.get("summary", "")):
            fail("em dash: the writing guide forbids it")

    return bad


def tool_name(fm):
    """MCP tool name. Writes are proposals; there is no confirm verb."""
    stem = fm["id"].rsplit(".", 1)[-1].replace("-", "_")
    return stem if fm["kind"] == "read" else f"propose_{stem}"


def compile_catalogue(atoms):
    ops = {}
    for _, (fm, body) in atoms.items():
        plain = body.split("## In plain words", 1)[1].split("##", 1)[0].strip()
        schema = validate.load(fm["input"])
        fields = [
            {"link_id": q["link_id"], "type": q["type"], "text": q["text"],
             "required": bool(q.get("required")),
             "options": [o["value"] for o in q.get("answer_option") or []] or None}
            for q in validate.walk(schema["questions"])
        ]
        ops[fm["id"]] = {
            **{k: fm[k] for k in REQUIRED if k != "verified"},
            "scope_qualifier": fm.get("scope_qualifier"),
            "verified": fm["verified"]["status"],
            "tool": tool_name(fm),
            "description": plain,
            "fields": fields,
        }
    return {
        "capabilities": sorted(vocab.CAPABILITIES),
        "bundles": vocab.BUNDLES,
        "states": sorted(vocab.STATES),
        "operations": ops,
    }


def main():
    atoms = load()
    if not atoms:
        print("FAIL no atoms found")
        return 1
    bad = lint(atoms)
    for line in bad:
        print(f"FAIL {line}")
    if bad:
        return 1
    cat = compile_catalogue(atoms)
    blob = json.dumps(cat, indent=2, sort_keys=True) + "\n"
    OUT.write_text(blob)
    OUT_GO.parent.mkdir(exist_ok=True)
    OUT_GO.write_text(blob)
    print(f"ok   {len(atoms)} atoms linted and compiled to {OUT.name}")
    for oid, op in sorted(cat["operations"].items()):
        print(f"     {op['tool']:<28} {op['capability']:<20} {op['verified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
