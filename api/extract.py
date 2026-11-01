"""A transcript and a field list in, what was said for each field out.

The one place a model reads a consultation. Three rules, all enforced after
the model answers rather than asked of it:

- a field is answered only with `evidence`, a span copied from the transcript,
  and a span that is not in the transcript drops the answer;
- a link_id the field list does not hold is dropped;
- no key means no answer. The caller shows the transcript and the keypad.

A field inside a repeating group carries `row_of`, and an answer to one must
say which row it belongs to. The evidence rule is unchanged and it is now the
rule that governs a row: every value of every row needs its own span, so a row
the transcript does not support loses its answers one at a time and ends up
empty, which `api/fill.py` drops. A row is never completed from a neighbour
and never merged into one.

Run: python3 -m api.extract
"""
from __future__ import annotations

import json
import os
import re

from api import fill

MODEL = "claude-opus-5"

SYSTEM = (
    "You fill a clinical form from a transcript of what was said. The transcript "
    "may be in English, Hinglish, Hindi, Tamil or Telugu. For each field, answer "
    "only if the transcript states it. Copy the exact words you relied on into "
    "`evidence`, in the transcript's own script. If nothing states it, leave the "
    "field out. Never infer, calculate or assume. For a choice field, answer with "
    "one of its options verbatim. Write values in English, except free text fields "
    "(type text or string), which keep the spoken language. Dates as spoken. "
    "confidence is 0 to 1: how clearly the words state this value."
    " A field with a `row_of` belongs to a repeating group, where one row is "
    "one medicine or one condition: answer it once per row and set `row` to "
    "that row's number, counting from 0 in the order the transcript names "
    "them. Keep a row's answers under the same `row`. Leave out a field a row "
    "does not state rather than repeating the value from another row."
)

TOOL = {
    "name": "fill_form",
    "description": "The values the transcript states, one entry per field it answers.",
    "input_schema": {
        "type": "object",
        "properties": {"answers": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "link_id": {"type": "string"},
                "value": {},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"},
                "row": {"type": "integer", "description":
                        "which row of its repeating group this answer is in, "
                        "counting from 0. Required for a field with a row_of, "
                        "and left out for every other field."},
            },
            "required": ["link_id", "value", "confidence", "evidence"],
        }}},
        "required": ["answers"],
    },
}

_SPACE = re.compile(r"\s+")


def _norm(text):
    return _SPACE.sub(" ", str(text)).strip().lower()


class NoReader(RuntimeError):
    """Nothing read the transcript, so no field was even considered.

    This used to be an empty answer, and an empty answer is indistinguishable
    from "the doctor did not say anything that fits this form". The caller
    turned that into the sentence "Nothing in the recording fills this form",
    which told a clinician their consultation was off topic when the truth was
    that this machine has no key to read it with. They are different facts and
    they lead a person to do different things, so they are different outcomes
    now.
    """


def extract(fields, transcript, *, client=None, model=MODEL):
    if not transcript.strip():
        return {}
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise NoReader(
                "The recording was transcribed, and then nothing read it into "
                "the form: this machine has no ANTHROPIC_API_KEY. The "
                "transcript is below, and the note has to be typed.")
        import anthropic
        client = anthropic.Anthropic()
    brief = [{k: f.get(k) for k in ("link_id", "text", "description", "type",
                                    "unit", "options", "row_of")}
             for f in fields]
    message = client.messages.create(
        model=model, max_tokens=4000, system=SYSTEM, tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        messages=[{"role": "user", "content": json.dumps(
            {"fields": brief, "transcript": transcript}, ensure_ascii=False)}])

    known = {f["link_id"]: f for f in fields}
    heard = _norm(transcript)
    out = {}
    for block in message.content:
        if getattr(block, "type", None) != "tool_use" or block.name != TOOL["name"]:
            continue
        for a in (block.input or {}).get("answers") or []:
            link_id, evidence = a.get("link_id"), str(a.get("evidence") or "")
            if link_id not in known:
                continue
            ident = _ident(known[link_id], a)
            if ident in out:
                continue
            if not evidence.strip() or _norm(evidence) not in heard:
                continue
            try:
                confidence = max(0.0, min(1.0, float(a.get("confidence"))))
            except (TypeError, ValueError):
                confidence = 0.0
            out[ident] = {"value": a.get("value"), "confidence": confidence,
                          "evidence": evidence}
    return out


def _ident(field, answer):
    """The id this answer is filed under: row addressed, or the bare link_id.

    A row field whose answer names no row keeps its bare link_id and is
    therefore dropped by `api/fill.py`, which names it in `unfilled`. That is
    deliberate: the alternative is choosing a row for it, and a dose on a
    medicine nobody identified goes on whichever medicine was first. Dropped
    and named beats placed and plausible.
    """
    group = field.get("row_of")
    row = answer.get("row")
    if not group or not isinstance(row, int) or isinstance(row, bool) or row < 0:
        return field["link_id"]
    return fill.row_id(group, row, field["link_id"])


def demo():
    class Block:
        def __init__(self, data):
            self.type, self.name, self.input = "tool_use", "fill_form", data

    class Stub:
        def __init__(self, answers):
            self.answers, self.asked = answers, None
            self.messages = self

        def create(self, **kw):
            self.asked = kw
            return type("M", (), {"content": [Block({"answers": self.answers})]})()

    fields = [{"link_id": "systolic", "text": "Systolic BP", "type": "integer",
               "unit": "mm[Hg]", "options": [], "required": True},
              {"link_id": "history", "text": "History", "type": "text",
               "unit": None, "options": [], "required": False}]
    transcript = "BP is 140 over 90. Bukhaar teen din se hai."
    stub = Stub([
        {"link_id": "systolic", "value": 140, "confidence": 0.97, "evidence": "BP is 140"},
        {"link_id": "history", "value": "Bukhaar teen din se", "confidence": 0.8,
         "evidence": "bukhaar  teen din se"},
        {"link_id": "pulse", "value": 80, "confidence": 0.9, "evidence": "BP is 140"},
        {"link_id": "history", "value": "invented", "confidence": 0.9,
         "evidence": "the patient said nothing like this"},
    ])
    got = extract(fields, transcript, client=stub)
    assert set(got) == {"systolic", "history"}, got
    assert got["systolic"] == {"value": 140, "confidence": 0.97, "evidence": "BP is 140"}
    assert got["history"]["value"] == "Bukhaar teen din se", \
        "evidence matches ignoring case and spacing, and a later bad answer does not replace it"
    assert stub.asked["model"] == MODEL
    assert "140 over 90" in stub.asked["messages"][0]["content"]

    # A repeating group. Two rows, each answer carrying its own span, and the
    # three refusals: a row answer whose span is not in the transcript, a
    # second answer for a row and field already filled, and a row field with
    # no row at all.
    rx = [{"link_id": "drug", "text": "Medicine", "type": "choice",
           "unit": None, "options": ["777067000", "774586009"],
           "row_of": "medications", "required": True},
          {"link_id": "dose", "text": "Dose", "type": "decimal", "unit": None,
           "options": [], "row_of": "medications", "required": True}]
    said = "Paracetamol 650 twice a day, and amoxicillin 500 three times."
    stub = Stub([
        {"link_id": "drug", "value": "777067000", "row": 0, "confidence": 0.9,
         "evidence": "Paracetamol"},
        {"link_id": "dose", "value": 650, "row": 0, "confidence": 0.9,
         "evidence": "650"},
        {"link_id": "drug", "value": "774586009", "row": 1, "confidence": 0.9,
         "evidence": "amoxicillin"},
        {"link_id": "dose", "value": 500, "row": 1, "confidence": 0.9,
         "evidence": "500"},
        {"link_id": "dose", "value": 250, "row": 2, "confidence": 0.9,
         "evidence": "metronidazole 250 at night"},
        {"link_id": "dose", "value": 999, "row": 0, "confidence": 0.9,
         "evidence": "650"},
        {"link_id": "dose", "value": 325, "confidence": 0.9, "evidence": "500"},
    ])
    got = extract(rx, said, client=stub)
    assert set(got) == {"medications[0].drug", "medications[0].dose",
                        "medications[1].drug", "medications[1].dose",
                        "dose"}, got
    assert got["medications[0].dose"]["value"] == 650, \
        "a second answer for a row and field already filled does not replace it"
    assert "medications[2].dose" not in got, \
        "a row answer with no span in the transcript is dropped, not kept empty"
    assert got["dose"]["value"] == 325, \
        "a row field with no row keeps its bare id, so the draft drops it by name"
    assert "row_of" in stub.asked["messages"][0]["content"], \
        "the model is told which fields are rows"

    # No key is a REFUSAL, not an empty answer. The empty answer is what made
    # a machine with no key tell a doctor their consultation did not fit the
    # form, which is the kind of wrong that a person acts on.
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        try:
            extract(fields, transcript)
        except NoReader as broke:
            assert "ANTHROPIC_API_KEY" in str(broke), str(broke)
        else:
            raise AssertionError("no key must refuse, not answer nothing")
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved
    assert extract(fields, "", client=stub) == {}, "nothing said, nothing asked"
    print("ok api.extract")


if __name__ == "__main__":
    demo()
