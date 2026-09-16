"""A transcript and a field list in, what was said for each field out.

The one place a model reads a consultation. Three rules, all enforced after
the model answers rather than asked of it:

- a field is answered only with `evidence`, a span copied from the transcript,
  and a span that is not in the transcript drops the answer;
- a link_id the field list does not hold is dropped;
- no key means no answer. The caller shows the transcript and the keypad.

Run: python3 -m api.extract
"""
from __future__ import annotations

import json
import os
import re

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
            },
            "required": ["link_id", "value", "confidence", "evidence"],
        }}},
        "required": ["answers"],
    },
}

_SPACE = re.compile(r"\s+")


def _norm(text):
    return _SPACE.sub(" ", str(text)).strip().lower()


def extract(fields, transcript, *, client=None, model=MODEL):
    if not transcript.strip():
        return {}
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {}
        import anthropic
        client = anthropic.Anthropic()
    brief = [{k: f.get(k) for k in ("link_id", "text", "description", "type", "unit", "options")}
             for f in fields]
    message = client.messages.create(
        model=model, max_tokens=4000, system=SYSTEM, tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        messages=[{"role": "user", "content": json.dumps(
            {"fields": brief, "transcript": transcript}, ensure_ascii=False)}])

    known = {f["link_id"] for f in fields}
    heard = _norm(transcript)
    out = {}
    for block in message.content:
        if getattr(block, "type", None) != "tool_use" or block.name != TOOL["name"]:
            continue
        for a in (block.input or {}).get("answers") or []:
            link_id, evidence = a.get("link_id"), str(a.get("evidence") or "")
            if link_id not in known or link_id in out:
                continue
            if not evidence.strip() or _norm(evidence) not in heard:
                continue
            try:
                confidence = max(0.0, min(1.0, float(a.get("confidence"))))
            except (TypeError, ValueError):
                confidence = 0.0
            out[link_id] = {"value": a.get("value"), "confidence": confidence,
                            "evidence": evidence}
    return out


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

    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert extract(fields, transcript) == {}, "no key, no answer"
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved
    assert extract(fields, "", client=stub) == {}, "nothing said, nothing asked"
    print("ok api.extract")


if __name__ == "__main__":
    demo()
