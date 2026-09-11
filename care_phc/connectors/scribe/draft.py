"""What Eka returned, turned into a Draft keyed by an operation's link_ids.

Pure. No sockets, no clock, no files: it takes the decoded templates and
returns `kernel.contracts.Draft`, so the whole mapping is checkable without a
credential. `check.py` runs it against the real response recorded below.

THE SHAPES HERE WERE OBSERVED, NOT GUESSED. A 92 second test consultation was
uploaded to https://api.eka.care on 2026-09-11, twice, and came back in 25 and
52 seconds. Three templates carry everything this bundle asks for:

  clinical_notes_template  markdown, prose, sections headed `**Assessment**`
                           and separated by `---`. This is the narrative half
                           and it goes into the consult's text fields.
  eka_emr_template         JSON, `{"prescription": {"diagnosis": [...],
                           "medications": [...], "symptoms": [...],
                           "advices": [...], "followup": {...},
                           "medicalHistory": {...}}}`. This is the discrete
                           half: every value out of it is marked unconfirmed.
  transcript_template      plain text. It is asked for under that name and
                           comes back under another: `template_id` is
                           "transcript", inside `data.template_results.
                           transcript`, and never in `data.output` at all. Both
                           spellings are read. It becomes Draft.transcript,
                           which
                           is what a doctor reads the discrete values back
                           against.

Two rules this file exists to keep:

- NOTHING IS INVENTED. A field Eka did not return is absent from `values`, not
  present and empty. A partial draft the doctor finishes is the correct
  outcome; a fabricated one is a clinical error that looks like a feature.
- EVERY DISCRETE VALUE IS UNCONFIRMED. Eka returns no per field confidence
  score. What it returns is `linked.confidence: true`, a boolean about whether
  it found a code for a term, which is not a measure of whether it heard the
  term right. So discrete link_ids get NO_SCORE, and the renderer marks them
  for re-reading. Turning a boolean into a percentage and printing it next to
  a diagnosis would be a fabricated measurement in front of a clinician, which
  is worse than saying nothing.

Vitals are deliberately not mapped. `eka_emr_template` returned a temperature
and this file drops it: `phc.inst.consult-scribe` names the consult and the
prescription and not `phc.op.vitals-record`, because ambient recognition is
worst at exactly that kind of short numeric utterance. The temperature still
reaches the doctor as prose, inside the examination note, where it is read and
retyped rather than silently recorded.
"""
from __future__ import annotations

import re

from kernel.contracts import Draft

CONSULT = "phc.op.consult-document"
RX = "phc.op.rx-prescribe"

INSTRUMENT = "phc.inst.consult-scribe"

# The confidence a discrete value carries when the gateway scored nothing. The
# renderer marks anything under 0.9 for re-reading (web/src/Form.tsx SURE), so
# any value below that would do; zero is chosen because it is the only honest
# reading of "this was not scored", and because it must never be mistaken for
# a measurement Eka supplied.
NO_SCORE = 0.0

# A heading in the clinical notes markdown, either `**Assessment**` on its own
# line or `## Assessment`. The template is a markdown one by declaration
# (`type: markdown` in template_results), so both forms are worth accepting.
_HEADING = re.compile(r"^\s*(?:\*\*(?P<bold>[^*]+?)\*\*|#{1,6}\s*(?P<hash>.+?))\s*:?\s*$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")

# Which consult link_id each heading feeds. Observed headings first; the rest
# are the common synonyms a different template or speciality would produce.
SECTIONS = {
    "chief complaint": "history",
    "chief complaints": "history",
    "history of present illness": "history",
    "history": "history",
    "review of systems": "history",
    "past medical history": "history",
    "vital signs": "examination",
    "vitals": "examination",
    "physical examination": "examination",
    "examination": "examination",
    "assessment": "assessment",
    "impression": "assessment",
    "diagnosis": "assessment",
    "treatment plan": "plan",
    "plan": "plan",
    "advices": "plan",
    "advice": "plan",
    "follow-up instructions": "plan",
    "follow up instructions": "plan",
    "follow-up": "plan",
    "follow up": "plan",
    "medications": "plan",
    "prescription": "plan",
}

# Where a heading nobody mapped goes. It goes somewhere: a paragraph the doctor
# dictated and the note dropped in silence is a clinical value lost, which is
# the same reason kernel/DECLARATIONS.md refuses an unmapped required question.
# History is the narrative catch all, and the heading rides along with it so
# the doctor can see what it was.
SPILL = "history"


def sections(markdown):
    """[(heading, body)] in document order. A body before any heading is
    dropped on purpose: the templates put a heading on everything, and a bare
    preamble is more likely to be template furniture than clinical text."""
    out = []
    heading, body = None, []
    for line in (markdown or "").splitlines():
        if _RULE.match(line):
            continue
        found = _HEADING.match(line)
        if found and (found.group("bold") or found.group("hash")):
            if heading is not None:
                out.append((heading, "\n".join(body).strip()))
            heading = (found.group("bold") or found.group("hash")).strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        out.append((heading, "\n".join(body).strip()))
    return [(h, b) for h, b in out if b]


def prose(markdown):
    """The note's sections gathered under the consult's own link_ids. Each
    block keeps its heading, because "Chest: clear on auscultation" under a
    box labelled Examination reads as what was said and a naked fragment does
    not."""
    blocks = {}
    for heading, body in sections(markdown):
        link_id = SECTIONS.get(heading.lower().strip(), SPILL)
        blocks.setdefault(link_id, []).append("%s\n%s" % (heading, body))
    return {k: "\n\n".join(v) for k, v in blocks.items() if v}


def _text(value):
    return str(value).strip() if value not in (None, "") else ""


def diagnoses(emr):
    """`prescription.diagnosis` as rows for the consult's structured question.

    The atom's mapping is `code: {item: [code, text]}`, one visible field, so
    what goes in `code` is what the doctor reads back. That is the diagnosis in
    words rather than J06.9: a code nobody can read is not a readback. The ICD
    and SNOMED codes ride along under their own keys, where the form leaves
    them alone and `kernel/mapping.py` does not look, so today they are carried
    and not stored. That is a gap in `phc.op.consult-document`'s mapping and
    not something a connector may fix from here.
    """
    rows = []
    for item in (emr or {}).get("diagnosis") or []:
        name = _text(item.get("name"))
        if not name:
            continue
        linked = item.get("linked") or {}
        row = {"code": name, "text": name}
        for key in ("icd10_code", "snomedct_code"):
            if _text(linked.get(key)):
                row[key] = _text(linked.get(key))
        rows.append(row)
    return rows


def medications(emr):
    """`prescription.medications` as rows for the prescription's structured
    question. The mapping's first keys are `medication` and
    `dosage_instruction`, which are the two boxes the doctor sees.

    A dose is assembled from what was returned and nothing else. The live
    response of 2026-09-11 carried `dose.custom` ("1 tablet"),
    `frequency.custom` ("1-1-1", "SOS"), `duration.custom` ("5 Days") and
    `timing` ("after food"); `instruction` is the free text one ("For fever")
    and did not appear in that response. All five are read, in the order a
    prescription is said, because every one of them is a clinical instruction
    the doctor dictated and a dropped one is a dictated instruction lost. A
    medication with no dose at all keeps an empty dose box rather than a
    guessed one.
    """
    rows = []
    for item in (emr or {}).get("medications") or []:
        name = _text(item.get("name"))
        if not name:
            continue
        parts = [_text((item.get("dose") or {}).get("custom")),
                 _text((item.get("frequency") or {}).get("custom")),
                 _text((item.get("duration") or {}).get("custom")),
                 _text(item.get("timing")),
                 _text(item.get("instruction"))]
        rows.append({"medication": name,
                     "dosage_instruction": ", ".join(p for p in parts if p)})
    return rows


def build(operation, *, notes=None, emr=None, transcript=None,
          instrument=INSTRUMENT):
    """The Draft for one operation. Unknown operation, or nothing heard for
    it, gives a Draft with no values, which is the fail closed outcome the
    renderer draws as the form."""
    values, confidence = {}, {}
    emr = (emr or {}).get("prescription") if isinstance(emr, dict) else None

    if operation == CONSULT:
        values.update(prose(notes))
        rows = diagnoses(emr)
        if rows:
            values["diagnosis"] = rows
            confidence["diagnosis"] = NO_SCORE
    elif operation == RX:
        rows = medications(emr)
        if rows:
            values["medications"] = rows
            confidence["medications"] = NO_SCORE

    return Draft(instrument=instrument, operation=operation, values=values,
                 confidence=confidence, transcript=transcript)
