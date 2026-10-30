"""Run: python3 scripts/seed_terminology.py [slug ...]

Generate a value set cache in terminology/ from a terminology server.

DESIGN TIME ONLY. This is the one script in the repository that needs a
network, and it is deliberately NOT in scripts/check.sh. Coded data plan step
2 says so in as many words: confirming a code list is design time work and it
never runs at the point of care. Everything the product does at the point of
care reads the generated file, offline, through kernel/terminology.py.

Why it exists rather than a hand written file
---------------------------------------------
`terminology/*.json` carries, per concept, where it was confirmed. A hand
transcribed file makes that claim without being able to support it: the
transcription is exactly where a wrong code enters, and a wrong code reads as
correct everywhere afterwards. Two have already been caught on this branch,
and both looked right:

- SpO2 was bound to 59408-5, oxygen saturation by pulse oximetry, which is
  what a health centre measures and is still the wrong code to store alone,
  because the FHIR oxygensat profile fixes Observation.code to 2708-6.
- blood urea was going to be bound to 11065-0, from memory, as "Urea
  [Mass/volume] in Serum or Plasma". It is not. 11065-0 is "Urea nitrogen
  [Mass/volume] in Serum or Plasma --pre dialysis", a different analyte
  reported as a different number. The right code is 3091-6, found by asking
  the server rather than by remembering.

So the display and the unit in a generated file are the SERVER'S answer, not
anybody's recollection of it, and the LOINC version they came from is written
down beside them.

The source
----------
`https://tx.fhir.org`, HL7's own public terminology server, which serves
official LOINC content and reports its version (2.83 at the time of writing).
`CodeSystem/$lookup` gives a concept's display and its properties, including
LOINC's `EXAMPLE_UCUM_UNITS`, which is how a unit gets into the file without
anybody choosing it.

What stays a human decision
---------------------------
Which concepts to seed, and why each one rather than a near neighbour. The
server answers "what is this code"; it cannot answer "is this the code a
health centre should store". That reasoning is in the SEEDS table below,
concept by concept, with its primary source cited, and it is the part to read
in review.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
OUT = ROOT / "terminology"
SERVER = "https://tx.fhir.org/r4"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"

# NEDL is the primary source for WHICH tests a primary health centre runs, and
# LOINC is the primary source for what each code means. Both are cited per
# concept. The NEDL rows are from Table 3, "List of diagnostic tests at
# Primary Health Centre (PHC)", of the National Essential Diagnostics List
# 2025, ICMR. Its `#` marker means a test may follow a hub and spoke model
# where the analyser is unavailable; the test is still a PHC test, which is
# why a marked row is seeded.
NEDL = ("ICMR National Essential Diagnostics List 2025, Table 3, "
        "List of diagnostic tests at Primary Health Centre (PHC)")

SEEDS = {
    "lab-analyte": {
        "title": "Laboratory analytes a primary health centre reports",
        "system": LOINC,
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "Concepts chosen from %s and confirmed against LOINC through "
                  "tx.fhir.org. Short on purpose: only the quantitative tests a "
                  "PHC runs itself, and only where the specimen and method are "
                  "stated clearly enough to pick a code that does not claim "
                  "something that was not measured." % NEDL,
        "concepts": {
            "718-7": {
                "why": "Haemoglobin. %s row 1, capillary blood, digital "
                       "haemoglobinometer. The unqualified blood mass per volume "
                       "concept, which capillary blood is: the arterial and "
                       "by-calculation concepts would both claim something the "
                       "haemoglobinometer did not do." % NEDL},
            "41653-7": {
                "why": "Blood glucose by glucometer. %s row 22, capillary blood, "
                       "glucometer. Specific on purpose, and the opposite call "
                       "from the leucocyte and platelet concepts below, for a "
                       "reason: a capillary glucometer reading is numerically "
                       "not a plasma glucose, so storing it as the serum or "
                       "plasma concept would be a false claim about the "
                       "specimen rather than a vaguer true one." % NEDL},
            "2345-7": {
                "why": "Glucose in serum or plasma. %s row 22 footnote, blood "
                       "glucose by semi-autoanalyser for women with gestational "
                       "diabetes, and row 23, the glucose tolerance test on "
                       "plasma. Seeded beside the glucometer concept rather "
                       "than instead of it, because a technician who ran the "
                       "analyser must be able to say so: that is what binding "
                       "the ANSWER is for." % NEDL},
            "3091-6": {
                "why": "Blood urea. %s row 30, serum, semi-autoanalyser. Urea "
                       "mass per volume and NOT urea nitrogen: an Indian report "
                       "gives urea in mg/dL while a urea nitrogen result is a "
                       "different analyte and a different number, about half of "
                       "it. 11065-0 was the code this was going to be seeded "
                       "with from memory and it is urea nitrogen, pre dialysis." % NEDL},
            "2160-0": {
                "why": "Serum creatinine. %s row 31, serum, semi-autoanalyser. "
                       "The serum or plasma concept, matching the stated "
                       "specimen, rather than the whole blood one." % NEDL},
            "26464-8": {
                "why": "Total leucocyte count. %s row 6, EDTA whole blood, "
                       "microscopy, and row 9, CBC on a 3-part analyser. Method "
                       "NEUTRAL on purpose: a health centre may count by "
                       "microscopy or by its analyser, so binding the manual "
                       "concept would make the stored code a false claim about "
                       "method whenever the analyser was used, and a consumer "
                       "looking for a leucocyte count finds the neutral one "
                       "either way." % NEDL},
            "26515-7": {
                "why": "Platelet count. %s row 8, EDTA whole blood, microscopy, "
                       "and row 9. Method neutral for the same reason as the "
                       "leucocyte count above." % NEDL},
        },
    },
}


def lookup(code, system=LOINC):
    """A concept's display, version and properties, from the server."""
    url = "%s/CodeSystem/$lookup?%s" % (SERVER, urllib.parse.urlencode(
        {"system": system, "code": code, "property": "*"}))
    request = urllib.request.Request(url, headers={"Accept": "application/fhir+json"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        blob = json.loads(answer.read().decode())
    if blob.get("resourceType") == "OperationOutcome":
        raise SystemExit("FAIL %s: %s" % (code, [i.get("diagnostics")
                                                 for i in blob.get("issue", [])]))
    out = {"properties": {}}
    for parameter in blob.get("parameter", []):
        name = parameter.get("name")
        if name in ("display", "version"):
            out[name] = parameter.get("valueString")
        elif name == "property":
            parts = {p["name"]: (p.get("valueString") or p.get("valueCode"))
                     for p in parameter.get("part", [])}
            if parts.get("code"):
                out["properties"][parts["code"]] = parts.get("value")
    if not out.get("display"):
        raise SystemExit("FAIL %s: the server returned no display" % code)
    return out


def build(slug):
    spec = SEEDS[slug]
    concepts, versions = {}, set()
    for code in sorted(spec["concepts"]):
        found = lookup(code, spec["system"])
        versions.add(found.get("version") or "?")
        unit = found["properties"].get("EXAMPLE_UCUM_UNITS")
        concept = {
            "display": found["display"],
            "verified": "confirmed against LOINC %s through tx.fhir.org"
                        % (found.get("version") or "?"),
            "why": spec["concepts"][code]["why"],
        }
        if unit:
            # LOINC's own example unit, so no unit in this file is anybody's
            # choice. kernel/terminology.py checks a reported unit against it.
            concept["unit"] = unit
            concept["unit_system"] = UCUM
            concept["unit_verified"] = (
                "LOINC EXAMPLE_UCUM_UNITS for this code, LOINC %s through "
                "tx.fhir.org" % (found.get("version") or "?"))
        concepts[code] = concept
        print("ok   %-9s %s  [%s]" % (code, found["display"], unit or "no unit"))
    blob = {
        "slug": slug,
        "title": spec["title"],
        "system": spec["system"],
        "binding": spec["binding"],
        "generated": "2026-10-31",
        "source": spec["source"],
        "verified": "confirmed against LOINC %s through tx.fhir.org"
                    % ", ".join(sorted(versions)),
        "concepts": concepts,
    }
    path = OUT / ("%s.json" % slug)
    path.write_text(json.dumps(blob, indent=2) + "\n")
    print("wrote %s, %d concepts" % (path.relative_to(ROOT), len(concepts)))


def main():
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")] or sorted(SEEDS)
    for slug in wanted:
        if slug not in SEEDS:
            raise SystemExit("no seed definition for %r; have %s"
                             % (slug, ", ".join(sorted(SEEDS))))
        build(slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
