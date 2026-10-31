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
SNOMED = "http://snomed.info/sct"
THO = "http://terminology.hl7.org/CodeSystem"

# The three ways a concept is confirmed, and which servers answer which. One
# resolver per kind rather than one clever one: a LOINC concept carries example
# units, a SNOMED concept carries a release version and a branch it must be
# inside, a published FHIR value set carries the whole list, and a UCUM symbol
# is a grammar expression rather than a list entry. Conflating them is how a
# unit would end up with a LOINC version written beside it.
RESOLVERS = ("loinc", "snomed", "valueset", "ucum")

# Where a medicine list may legitimately come from. Not a formulary: see the
# `source` on the medication-code seed and the sign-off it still needs.
NLEM = ("India's National List of Essential Medicines 2022, the report of the "
        "Standing National Committee on Medicines, Ministry of Health and "
        "Family Welfare, read 2026-10-31 from "
        "https://icmr.gov.in/icmrobject/custom_data/"
        "1720338777_report_nlem_2022_f_website.pdf. The report marks every "
        "medicine with its level of healthcare, P for primary, S for "
        "secondary, T for tertiary, and only P medicines are seeded.")

NRCES_EX = ("the NRCeS India FHIR R4 implementation guide's own OPConsultRecord "
            "example, Bundle-OPConsultNote-example-05, read 2026-10-31 through "
            "the abdm-docs server's get_fhir_example")

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

    # ---------------------------------------------------------------- Condition
    #
    # Three value sets, because a diagnosis is three answers: what was found,
    # whether the patient has it now, and how sure the clinician is. The second
    # and third are FHIR's own published value sets and nothing about them is
    # anybody's choice, which is why their concepts are not listed here: the
    # `valueset` resolver takes whatever the server expands, so this file
    # cannot hold a stale subset of a standard list.
    "condition-clinical-status": {
        "title": "Whether a condition is current",
        "system": "%s/condition-clinical" % THO,
        "resolve": "valueset",
        "valueset": "http://hl7.org/fhir/ValueSet/condition-clinical",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "The FHIR R4 published value set "
                  "http://hl7.org/fhir/ValueSet/condition-clinical, expanded "
                  "through tx.fhir.org. Taken whole: Condition.clinicalStatus "
                  "is required to be a code from this list, so a subset would "
                  "be this product narrowing a standard it does not own.",
    },
    "condition-verification-status": {
        "title": "How sure a condition is",
        "system": "%s/condition-ver-status" % THO,
        "resolve": "valueset",
        "valueset": "http://hl7.org/fhir/ValueSet/condition-ver-status",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "The FHIR R4 published value set "
                  "http://hl7.org/fhir/ValueSet/condition-ver-status, expanded "
                  "through tx.fhir.org. This is invariant I6's mechanism: a "
                  "denied finding is `refuted` and a scribe's guess is "
                  "`unconfirmed`, so neither is stored as a settled fact and "
                  "neither is dropped. Before this existed the consultation "
                  "atom wrote `verification_status: {const: confirmed}` on "
                  "every diagnosis, which asserted every one of them.",
    },
    "condition-code": {
        "title": "Conditions this build can code",
        "system": SNOMED,
        "resolve": "snomed",
        # Every concept is checked to be inside SNOMED's Clinical finding
        # branch, which is the whole of CARE's own diagnosis binding and the
        # plan's. A code that is a route or a product fails the seed.
        "member_of": "%s?fhir_vs=isa/404684003" % SNOMED,
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "NOT A PRIMARY HEALTH CENTRE DIAGNOSIS LIST, and must not be "
                  "read as one. These are the clinical findings that appear in "
                  "%s, which is the only source for a condition code this "
                  "build could resolve. No authoritative list of the "
                  "conditions an Indian primary health centre records was "
                  "reachable, and inventing one is forbidden: a diagnosis list "
                  "presented as a formulary decides what a clinician can say. "
                  "So the list is short on purpose and the designed fallback "
                  "stands, which is that an uncoded diagnosis is narrative "
                  "text and the note still reaches ABDM. NEEDS SIGN-OFF from a "
                  "named clinical officer, against a published list, before "
                  "this is a picker anybody uses." % NRCES_EX,
        "concepts": {
            "297142003": {
                "why": "Foot swelling. Published as a Condition in %s, where "
                       "it is the chief complaint of the visit." % NRCES_EX},
            "46635009": {
                "why": "Diabetes mellitus type 1. Published as a Condition in "
                       "%s, under Medical History with a clinical status of "
                       "recurrence." % NRCES_EX},
            "44054006": {
                "why": "Diabetes mellitus type 2. Published as a Condition in "
                       "%s, under Medical History. The display stored is the "
                       "one the server returns rather than the one the example "
                       "prints, because a display that disagrees with the "
                       "terminology is not storable here." % NRCES_EX},
        },
    },
    # ------------------------------------------------------- MedicationRequest
    #
    # A medicine is a drug, a dose, a route, a frequency and a duration, and
    # each of those is its own answer. The drug concept is deliberately the
    # SNOMED product with no strength and no form in it ("only product"),
    # because the strength IS the dose answer and the form follows the route.
    # Binding a clinical drug like "Amoxicillin 500 mg oral capsule" would say
    # the same thing twice and let the two disagree.
    "medication-code": {
        "title": "Medicines this build can code",
        "system": SNOMED,
        "member_of": "%s?fhir_vs=isa/763158003" % SNOMED,
        "resolve": "snomed",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "A STARTER SET, NOT A FORMULARY. Every medicine here is "
                  "marked P, primary level of healthcare, in %s. It is short "
                  "because the report publishes the level of care only in its "
                  "annexures of changes, so these are the primary level "
                  "medicines that document could be read to confirm, not the "
                  "whole of the primary level list. No dose limit, no "
                  "indication and no interaction is stated here and none may "
                  "be inferred from the list. NEEDS SIGN-OFF: a facility "
                  "formulary approved by a named medical officer, which is "
                  "also what the `rx.prescribe` capability's own qualifier has "
                  "been waiting for." % NLEM,
        "concepts": {
            "777067000": {
                "why": "Paracetamol. %s, Annexure 3.3, section 2.1 non-opioid "
                       "analgesics, antipyretics and nonsteroidal "
                       "anti-inflammatory medicines, level of healthcare "
                       "P,S,T. SNOMED International's preferred term is the "
                       "United States name, acetaminophen; the Indian "
                       "preferred term needs the SNOMED CT India extension, "
                       "which needs the MLDS licence this build does not "
                       "hold." % NLEM},
            "776654009": {
                "why": "Mefenamic acid. %s, Annexure 3.3, section 2.1, level "
                       "of healthcare P,S,T." % NLEM},
            "774586009": {
                "why": "Amoxicillin. %s, Annexure 3.3, section 6.2.1 "
                       "beta-lactam antibacterials, level of healthcare "
                       "P,S,T." % NLEM},
            "774448003": {
                "why": "Albendazole. %s, Annexure 3.3, section 6.1.1 "
                       "intestinal anthelminthics, level of healthcare "
                       "P,S,T." % NLEM},
            "776713006": {
                "why": "Metformin. %s, Annexure 3.3, section 18.4.1 insulins "
                       "and other antidiabetic agents, level of healthcare "
                       "P,S,T." % NLEM},
            "775195004": {
                "why": "Chlorpheniramine. %s, Annexure 3.3, level of "
                       "healthcare P,S,T. The section heading above this row "
                       "in the extracted text is not legible enough to quote, "
                       "so it is not quoted." % NLEM},
        },
    },
    "medication-route": {
        "title": "Routes of administration",
        "system": SNOMED,
        "member_of": "http://hl7.org/fhir/ValueSet/route-codes",
        "resolve": "snomed",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "Members of the FHIR R4 published value set "
                  "http://hl7.org/fhir/ValueSet/route-codes, each confirmed to "
                  "be in it through tx.fhir.org. A subset and not the whole "
                  "list, because that list runs to several hundred routes "
                  "including intrathecal and suprachoroidal ones, and a picker "
                  "offering those at a health centre is a picker nobody can "
                  "use. Choosing which routes a health centre administers by "
                  "is a product decision rather than a clinical claim: no "
                  "route here says anything about a drug, a dose or an "
                  "indication.",
        "concepts": {
            "26643006": {"why": "Oral."},
            "78421000": {"why": "Intramuscular."},
            "47625008": {"why": "Intravenous."},
            "34206005": {"why": "Subcutaneous."},
            "6064005": {"why": "Topical."},
            "37161004": {"why": "Rectal."},
            "54485002": {"why": "Ophthalmic."},
            "46713006": {"why": "Nasal."},
            "447694001": {"why": "Respiratory tract, which is what an inhaler "
                                 "and a nebuliser are."},
        },
    },
    "medication-frequency": {
        "title": "How often a medicine is taken",
        "system": SNOMED,
        "member_of": "%s?fhir_vs=isa/307438009" % SNOMED,
        "resolve": "snomed",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "Children of SNOMED CT 307438009, Frequency per day, each "
                  "confirmed to be inside it through tx.fhir.org. SNOMED "
                  "rather than FHIR's own timing abbreviations because %s "
                  "codes its dosage instruction with SNOMED, and a frequency "
                  "ABDM's own example cannot read is a frequency this product "
                  "should not emit. The parent concept itself is not seeded: "
                  "the server reports it notSelectable, and 'frequency per "
                  "day' is not a frequency. Nothing here invents a schedule: "
                  "each concept means exactly the number of times a day it "
                  "names and no more, so it carries no timing, no 'as "
                  "required' and no relation to meals." % NRCES_EX,
        "concepts": {
            "229797004": {"why": "Once a day."},
            "229799001": {"why": "Twice a day. The concept %s publishes as "
                                 "MedicationRequest.dosageInstruction."
                                 "additionalInstruction." % NRCES_EX},
            "229798009": {"why": "Three times a day."},
            "307439001": {"why": "Four times a day."},
        },
    },
    # ------------------------------------------- the two unit sets a dose needs
    #
    # Separate from ucum-units, and from each other, for one reason: a single
    # unit value set lets a prescriber give a dose in weeks. UCUM is a grammar
    # rather than a list, so a value set over it is always a chosen subset, and
    # these two are chosen by what the question is asking for.
    "dose-unit": {
        "title": "Units a dose is given in",
        "system": UCUM,
        "resolve": "ucum",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "UCUM symbols, each confirmed through tx.fhir.org "
                  "CodeSystem/$validate-code against the UCUM code system. "
                  "Deliberately separate from duration-unit: one unit value "
                  "set across both would let a dose be two weeks.",
        "concepts": {
            "mg": {"why": "Milligram, how a tablet strength is written.",
                   "display": "milligram"},
            "mL": {"why": "Millilitre, how an oral liquid is measured.",
                   "display": "millilitre"},
            "{tablet}": {
                "why": "One tablet. A UCUM annotation, which is a real UCUM "
                       "expression and not a free text escape: the braces are "
                       "the grammar's own way of carrying a unit that has no "
                       "dimension. A prescription written in tablets is how a "
                       "health centre dispenses, and refusing it would push "
                       "the count into a text box.",
                "display": "tablet"},
        },
    },
    "duration-unit": {
        "title": "Units a course length is given in",
        "system": UCUM,
        "resolve": "ucum",
        "binding": "a questionnaire question's `answer_value_set`, when the "
                   "answer carries the concept",
        "source": "UCUM symbols, each confirmed through tx.fhir.org "
                  "CodeSystem/$validate-code against the UCUM code system.",
        "concepts": {
            "d": {"why": "Day.", "display": "day"},
            "wk": {"why": "Week.", "display": "week"},
            "mo": {"why": "Month.", "display": "month"},
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


def _get(path, params):
    url = "%s/%s?%s" % (SERVER, path, urllib.parse.urlencode(params))
    request = urllib.request.Request(url, headers={"Accept": "application/fhir+json"})
    with urllib.request.urlopen(request, timeout=90) as answer:
        return json.loads(answer.read().decode())


def _parameters(blob):
    """A FHIR Parameters resource as a plain dict of the names we read."""
    out = {}
    for parameter in blob.get("parameter", []):
        name = parameter.get("name")
        for key in ("valueBoolean", "valueString", "valueUri", "valueCode"):
            if key in parameter:
                out[name] = parameter[key]
                break
    return out


def member(valueset, code, system):
    """Whether the server agrees this code is in this value set.

    The point of the exercise for a SNOMED binding. A code's display proves it
    exists; it does not prove it is the KIND of thing the question asks for,
    and the two failures look identical in a file. 26643006 is a real SNOMED
    code with a believable display and it is a route of administration, so a
    diagnosis value set holding it would read as correct. Asking the server
    whether it is inside the Clinical finding branch is what catches that, and
    it is the same filter CARE binds its own diagnosis field to.
    """
    blob = _get("ValueSet/$validate-code",
                {"url": valueset, "system": system, "code": code})
    found = _parameters(blob)
    if blob.get("resourceType") == "OperationOutcome":
        raise SystemExit("FAIL %s: %s" % (code, [i.get("diagnostics")
                                                 for i in blob.get("issue", [])]))
    return bool(found.get("result")), found


def ucum(code):
    """A UCUM symbol, confirmed against the UCUM code system.

    UCUM is a grammar rather than a code list, so there is nothing to expand
    and no display to read off: `$validate-code` answers whether the symbol
    parses, and the symbol is its own printable form. The plain words beside
    it in this file are a label for a picker and are declared in the seed,
    which is said so in the generated file rather than left to look like the
    server's answer.
    """
    blob = _get("CodeSystem/$validate-code", {"url": UCUM, "code": code})
    found = _parameters(blob)
    if not found.get("result"):
        raise SystemExit("FAIL %s is not a UCUM symbol: %s"
                         % (code, found.get("message")))
    return found.get("version") or "?"


def published(valueset):
    """Every concept of a published FHIR value set, by code, from the server.

    Recursive, because an expansion is a tree: condition-clinical nests
    `recurrence` and `relapse` under `active`, and reading only the top level
    would drop four of the seven codes while looking like it had read them all.
    """
    blob = _get("ValueSet/$expand", {"url": valueset, "count": 500})
    if blob.get("resourceType") == "OperationOutcome":
        raise SystemExit("FAIL %s: %s" % (valueset, [i.get("diagnostics")
                                                     for i in blob.get("issue", [])]))
    out = {}

    def walk(contains):
        for concept in contains:
            if concept.get("abstract") or concept.get("inactive"):
                continue
            out[concept["code"]] = {"display": concept.get("display") or "",
                                    "system": concept.get("system")}
            walk(concept.get("contains") or [])

    walk(blob.get("expansion", {}).get("contains") or [])
    if not out:
        raise SystemExit("FAIL %s expanded to nothing" % valueset)
    return out, blob.get("version") or "?"


def _write(slug, spec, concepts, verified):
    blob = {
        "slug": slug,
        "title": spec["title"],
        "system": spec["system"],
        "binding": spec["binding"],
        "generated": "2026-10-31",
        "source": spec["source"],
        "verified": verified,
        "concepts": concepts,
    }
    path = OUT / ("%s.json" % slug)
    path.write_text(json.dumps(blob, indent=2) + "\n")
    print("wrote %s, %d concepts" % (path.relative_to(ROOT), len(concepts)))


def build_loinc(slug, spec):
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
    _write(slug, spec, concepts,
           "confirmed against LOINC %s through tx.fhir.org" % ", ".join(sorted(versions)))


def build_snomed(slug, spec):
    """A SNOMED binding: every code's display from the server, and every code
    confirmed to be inside the branch the question is asking about.

    Both halves are needed and neither is enough. The display catches a code
    that means something else; the branch catches a code that means the right
    thing in the wrong dimension, which is the one that reads as correct.
    """
    inside = spec["member_of"]
    concepts, versions = {}, set()
    for code in sorted(spec["concepts"]):
        ok, found = member(inside, code, spec["system"])
        if not ok:
            raise SystemExit("FAIL %s is not in %s: %s"
                             % (code, inside, found.get("message")))
        display = found.get("display")
        if not display:
            raise SystemExit("FAIL %s: the server returned no display" % code)
        version = found.get("version") or "?"
        versions.add(version)
        concepts[code] = {
            "display": display,
            "verified": "confirmed in value set %s, SNOMED CT release %s, "
                        "through tx.fhir.org" % (inside, version),
            "why": spec["concepts"][code]["why"],
        }
        print("ok   %-14s %-46s in %s" % (code, display, inside))
    _write(slug, spec, concepts,
           "every concept confirmed to be in %s, SNOMED CT release %s, through "
           "tx.fhir.org" % (inside, ", ".join(sorted(versions))))


def build_valueset(slug, spec):
    """A published FHIR value set, taken whole.

    No `concepts` in the seed, on purpose: the list is the standard's and this
    file must not be able to hold a stale subset of it. What the seed chooses
    is which value set, and that is a binding decision rather than a clinical
    one.
    """
    if spec.get("concepts"):
        raise SystemExit("FAIL %s: a published value set is taken whole, so "
                         "the seed may not list concepts" % slug)
    found, version = published(spec["valueset"])
    concepts = {}
    for code in sorted(found):
        if found[code]["system"] != spec["system"]:
            raise SystemExit("FAIL %s: %s is from %s, not %s. One code system "
                             "per cached value set."
                             % (slug, code, found[code]["system"], spec["system"]))
        concepts[code] = {
            "display": found[code]["display"],
            "verified": "expanded from the published value set %s, version %s, "
                        "through tx.fhir.org" % (spec["valueset"], version),
            "why": "a code of the published value set %s; this product chose "
                   "the binding and not the list" % spec["valueset"],
        }
        print("ok   %-18s %s" % (code, found[code]["display"]))
    _write(slug, spec, concepts,
           "expanded whole from the published value set %s, version %s, "
           "through tx.fhir.org" % (spec["valueset"], version))


def build_ucum(slug, spec):
    concepts, versions = {}, set()
    for code in sorted(spec["concepts"]):
        version = ucum(code)
        versions.add(version)
        declared = spec["concepts"][code]
        concepts[code] = {
            # The printable symbol IS the code in UCUM, which is why
            # kernel/fhir.py fills Quantity.unit and Quantity.code from one
            # column. The words are a picker label declared in the seed, said
            # so here so that nobody reads them as the server's answer.
            "display": declared["display"],
            "display_source": "a label declared in scripts/seed_terminology.py; "
                              "UCUM publishes no display, the symbol is the code",
            "verified": "confirmed as a UCUM %s symbol through tx.fhir.org "
                        "CodeSystem/$validate-code" % version,
            "why": declared["why"],
        }
        print("ok   %-10s %s" % (code, declared["display"]))
    _write(slug, spec, concepts,
           "every symbol confirmed against UCUM %s through tx.fhir.org"
           % ", ".join(sorted(versions)))


BUILDERS = {"loinc": build_loinc, "snomed": build_snomed,
            "valueset": build_valueset, "ucum": build_ucum}


def build(slug):
    spec = SEEDS[slug]
    resolve = spec.get("resolve", "loinc")
    if resolve not in RESOLVERS:
        raise SystemExit("no resolver %r; have %s" % (resolve, ", ".join(RESOLVERS)))
    BUILDERS[resolve](slug, spec)


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
