# Scribe Engine (Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record from any encounter without opening a form, transcribe, and fill whichever operation's questionnaire the station's template names, using one generic engine instead of per-form mapping code.

**Architecture:** Eka is asked for the transcript only. `api/fill.py` (pure) flattens a questionnaire and coerces values; `api/extract.py` asks Claude for `{value, confidence, evidence}` per field and drops anything whose evidence is not in the transcript. `api/scribe.py` holds the session and transcript (24h) and builds `Draft`s from those two modules. In the browser, the mic sits on the encounter composer, a `ScribeBar` records and switches templates, and the result opens in the ordinary `OperationPanel`, where every non-text value needs a tick before Commit.

**Tech Stack:** Python 3.9 + FastAPI (`api/`), anthropic SDK (already installed, `claude-opus-5`), ekacare SDK, React 19 + Vite (`web/`), node `--experimental-strip-types` checks.

**Spec:** `docs/superpowers/specs/2026-09-16-scribe-design.md` (read §3–§4 and §10 decisions 1–7).

## Global Constraints

- Transcript retention: **24 hours** from when the transcript arrives, then deleted from the session.
- Languages: `en-IN`, Hinglish, Hindi, Tamil, Telugu.
- Model: `claude-opus-5`, used only when `ANTHROPIC_API_KEY` is set. No key → no draft, transcript only. No regex fallback.
- A template **is an operation id**; the questionnaire is `op["input"]`. Only operations in the scribe instrument's `operations` list may be filled.
- Every non-text value filled by a recording (integer, decimal, quantity, date, choice, boolean) must be ticked before Commit. Text and structured keep the unconfirmed highlight only.
- `readback: required`, `commit: tap`, consent (`requires: capture.consented`) are unchanged. Nothing on the scribe path writes.
- A value with no evidence, or evidence not found in the transcript, is dropped.
- Confidence sent to the renderer is capped at `0.89`.
- Checks are assert scripts: `python3 -m api.<module>` for pure modules, `python3 -m api.tests.test_api` for routes, `cd web && npm run check` for the renderer.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `api/fill.py` | create | `flatten`, `coerce`, `enabled`, `build_draft`: pure |
| `api/extract.py` | create | `extract(fields, transcript, client=None)`: the one LLM call |
| `api/scribe.py` | modify | transcript-only Eka request, session with transcript + expiry, `refill`; delete `fill/_prop/_phrase/_dose/KNOWN` |
| `api/main.py` | modify | `GET /scribe/templates`, `POST /scribe/sessions` takes `operations` + `language`, `POST /scribe/sessions/{id}/extract` |
| `bundles/phc/bundle.yaml` | modify | `scribe:` station defaults |
| `bundles/phc/phc.inst.consult-scribe.md` | modify | operations allowlist grows |
| `kernel/declarations.py` | modify | lint `scribe:` block; drop the device rule |
| `kernel/DECLARATIONS.md` | modify | §4 rule text |
| `kernel/contracts.py` | modify | `Draft.evidence` |
| `api/tests/test_api.py` | modify | route checks |
| `web/src/scribe/session.ts` | modify | `mustTick` replaces `narrative`; types gain `evidence` |
| `web/src/scribe/client.ts` | modify | `templates`, `startSession(ops, language)`, `refill` |
| `web/src/scribe/ScribeBar.tsx` | create | record, template switch, language, open drafts |
| `web/src/scribe/Recorder.tsx` | delete | replaced by ScribeBar |
| `web/src/form/Panel.tsx` | modify | drop Recorder mount; accept `draft`; tick gate |
| `web/src/form/Form.tsx` | modify | evidence line + tick box per field |
| `web/src/screens/Encounter.tsx` | modify | mic → ScribeBar; open panels from drafts |
| `web/src/scribe/scribe.check.ts` | modify | new properties |

---

### Task 1: `api/fill.py`: flatten and coerce

**Files:**
- Create: `api/fill.py`

**Interfaces:**
- Produces:
  - `flatten(schema: dict) -> list[dict]`. Each field is `{link_id, path, text, description, type, structured_type, required, repeats, unit, options: list[str], enable_when: list}`.
  - `coerce(field: dict, value, today: date) -> (ok: bool, value)`
  - `enabled(fields: list[dict], values: dict) -> dict` (drops values for disabled fields)
  - `TICK_TYPES = ("integer", "decimal", "quantity", "date", "dateTime", "time", "choice", "boolean")`

- [ ] **Step 1: Write the module with its `demo()` asserts first, functions raising `NotImplementedError`**

```python
"""One questionnaire, any questionnaire: its fields as a flat list, and a heard
value made into a value that field can hold, or refused.

Pure. No model, no network, no clock except the `today` a caller hands in.
Run: python3 -m api.fill
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

TICK_TYPES = ("integer", "decimal", "quantity", "date", "dateTime", "time",
              "choice", "boolean")


def flatten(schema):
    raise NotImplementedError


def coerce(field, value, today):
    raise NotImplementedError


def enabled(fields, values):
    raise NotImplementedError


def demo():
    schema = {"questions": [
        {"link_id": "intro", "text": "Read this", "type": "display"},
        {"link_id": "systolic", "text": "Systolic BP", "type": "integer",
         "required": True, "styling_metadata": {"phc": {"unit": "mm[Hg]"}}},
        {"link_id": "right_eye", "text": "Right eye", "type": "group", "questions": [
            {"link_id": "re_va", "text": "Visual acuity", "type": "choice",
             "answer_option": [{"value": "6/6"}, {"value": "6/9"}, {"value": "6/60"}]}]},
        {"link_id": "pregnant", "text": "Pregnant", "type": "boolean"},
        {"link_id": "lmp", "text": "LMP", "type": "date",
         "enable_when": [{"question": "pregnant", "operator": "equals", "answer": True}]},
        {"link_id": "diagnosis", "text": "Diagnosis", "type": "structured",
         "structured_type": "condition", "repeats": True},
    ]}
    fields = flatten(schema)
    ids = [f["link_id"] for f in fields]
    assert ids == ["systolic", "re_va", "pregnant", "lmp", "diagnosis"], ids
    by = {f["link_id"]: f for f in fields}
    assert by["re_va"]["path"] == "right_eye.re_va", by["re_va"]
    assert by["re_va"]["options"] == ["6/6", "6/9", "6/60"]
    assert by["systolic"]["unit"] == "mm[Hg]"

    today = date(2026, 9, 16)
    assert coerce(by["systolic"], "140", today) == (True, 140)
    assert coerce(by["systolic"], "one forty", today) == (False, None)
    assert coerce(by["systolic"], 140.5, today) == (False, None), "an integer is whole"
    assert coerce(by["re_va"], " 6 / 9 ", today) == (True, "6/9")
    assert coerce(by["re_va"], "6/12", today) == (False, None), "off the list is refused"
    assert coerce(by["pregnant"], "yes", today) == (True, True)
    assert coerce(by["pregnant"], "maybe", today) == (False, None)
    assert coerce(by["lmp"], "2026-08-01", today) == (True, "2026-08-01")
    assert coerce(by["lmp"], "15 August", today) == (True, "2026-08-15")
    assert coerce(by["lmp"], "15 December", today) == (True, "2025-12-15"), \
        "a day and month with no year is the most recent one, never the future"
    assert coerce(by["lmp"], "yesterday", today) == (True, "2026-09-15")
    assert coerce(by["diagnosis"], [{"code": "Fever"}], today) == (True, [{"code": "Fever"}])
    assert coerce(by["diagnosis"], "Fever", today) == (False, None)

    assert enabled(fields, {"pregnant": False, "lmp": "2026-08-01"}) == {"pregnant": False}
    assert enabled(fields, {"pregnant": True, "lmp": "2026-08-01"}) == \
        {"pregnant": True, "lmp": "2026-08-01"}
    print("ok api.fill")


if __name__ == "__main__":
    demo()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m api.fill`
Expected: `NotImplementedError`

- [ ] **Step 3: Implement the three functions** (replace the stubs)

```python
def _options(q):
    return [str(o.get("value")) for o in q.get("answer_option") or [] if o.get("value") is not None]


def flatten(schema):
    out = []

    def walk(questions, prefix):
        for q in questions:
            path = prefix + [q["link_id"]]
            if q.get("type") == "group":
                walk(q.get("questions") or [], path)
                continue
            if q.get("type") == "display":
                continue
            phc = (q.get("styling_metadata") or {}).get("phc") or {}
            out.append({
                "link_id": q["link_id"], "path": ".".join(path),
                "text": q.get("text", ""), "description": q.get("description", ""),
                "type": q.get("type"), "structured_type": q.get("structured_type"),
                "required": bool(q.get("required")), "repeats": bool(q.get("repeats")),
                "unit": q.get("unit") or phc.get("unit"), "options": _options(q),
                "enable_when": q.get("enable_when") or [],
            })
            walk(q.get("questions") or [], path)

    walk(schema.get("questions") or [], [])
    return out


_SQUASH = re.compile(r"\s+")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date(value, today):
    text = str(value).strip().lower()
    if text in ("today",):
        return today
    if text in ("yesterday",):
        return today - timedelta(days=1)
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass
    # ponytail: "15 August" / "August 15" only; add weekday phrases when golden transcripts need them
    m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)|([a-z]+)\s+(\d{1,2})", text)
    if not m:
        return None
    day, month = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    month = _MONTHS.get(month[:3])
    if not month:
        return None
    try:
        found = date(today.year, month, int(day))
    except ValueError:
        return None
    return found if found <= today else found.replace(year=today.year - 1)


def coerce(field, value, today):
    kind = field["type"]
    if value is None or value == "" or value == []:
        return False, None
    try:
        if kind == "integer":
            number = float(value)
            return (True, int(number)) if number.is_integer() else (False, None)
        if kind in ("decimal", "quantity"):
            return True, float(value)
        if kind == "boolean":
            text = str(value).strip().lower()
            if text in ("true", "yes", "y", "1", "haan", "ha"):
                return True, True
            if text in ("false", "no", "n", "0", "nahi"):
                return True, False
            return False, None
        if kind in ("date", "dateTime"):
            found = _date(value, today)
            return (True, found.isoformat()) if found else (False, None)
        if kind == "choice":
            want = _SQUASH.sub("", str(value)).lower()
            for option in field["options"]:
                if option == value or _SQUASH.sub("", option).lower() == want:
                    return True, option
            return False, None
        if kind == "structured":
            ok = isinstance(value, list) and all(isinstance(v, dict) for v in value)
            return (True, value) if ok else (False, None)
        if kind in ("string", "text", "url", "time"):
            return True, str(value).strip()
    except (TypeError, ValueError):
        return False, None
    return False, None


_OPS = {
    "exists": lambda have, want: (have is not None) == bool(want),
    "equals": lambda have, want: have == want,
    "not_equals": lambda have, want: have != want,
    "greater": lambda have, want: have is not None and have > want,
    "less": lambda have, want: have is not None and have < want,
    "greater_or_equals": lambda have, want: have is not None and have >= want,
    "less_or_equals": lambda have, want: have is not None and have <= want,
}


def enabled(fields, values):
    by = {f["link_id"]: f for f in fields}
    out = dict(values)
    for link_id in list(out):
        rules = by.get(link_id, {}).get("enable_when") or []
        if rules and not all(_OPS[r["operator"]](out.get(r["question"]), r["answer"])
                             for r in rules):
            del out[link_id]
    return out
```

Note: `enable_behavior: any` is not handled (all rules must hold). None of the existing questionnaires use it; add it when one does.

- [ ] **Step 4: Run it to see it pass**

Run: `python3 -m api.fill`
Expected: `ok api.fill`

- [ ] **Step 5: Commit**

```bash
git add api/fill.py
git commit -m "Flatten any questionnaire and coerce a heard value to its field

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `api/extract.py`: the one model call

**Files:**
- Create: `api/extract.py`

**Interfaces:**
- Consumes: `flatten` field dicts from Task 1.
- Produces: `extract(fields: list[dict], transcript: str, *, client=None, model: str = "claude-opus-5") -> dict[str, dict]`, which maps `link_id` to `{"value", "confidence": float, "evidence": str}`. It returns `{}` when there is no API key and no client.

- [ ] **Step 1: Write the module with a stub client check first**

```python
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
    raise NotImplementedError


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
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m api.extract`
Expected: `NotImplementedError`

- [ ] **Step 3: Implement `extract`**

```python
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
```

- [ ] **Step 4: Run it to see it pass**

Run: `python3 -m api.extract`
Expected: `ok api.extract`

- [ ] **Step 5: Commit**

```bash
git add api/extract.py
git commit -m "Ask the model for what the transcript states, and keep only what it can quote

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `api/fill.build_draft` and the session in `api/scribe.py`

**Files:**
- Modify: `api/fill.py` (add `build_draft`)
- Modify: `api/scribe.py` (TEMPLATES, `drafts`, `begin`, `collect`, `public`, `demo`; delete `_prop`, `_phrase`, `_dose`, `KNOWN`, `fill`, `CONSULT`, `RX`)
- Modify: `kernel/contracts.py:361` (`Draft.evidence`)

**Interfaces:**
- Consumes: `flatten`, `coerce`, `enabled`, `TICK_TYPES` (Task 1); `extract` (Task 2).
- Produces:
  - `fill.build_draft(operation: str, schema: dict, answers: dict, transcript: str, *, instrument: str, today: date) -> dict | None`. The dict is `{instrument, operation, values, confidence, evidence, tick: [link_id], unfilled: [link_id], transcript}`.
  - `scribe.start(audio, *, suffix, languages: list[str]) -> txn`
  - `scribe.begin(thread, actor, txn, operations: dict[str, dict], instrument) -> session`. `operations` maps op id to `{"schema": dict}`.
  - `scribe.refill(session, operations: dict[str, dict], *, extractor=extract.extract) -> session`
  - `scribe.TRANSCRIPT_SECONDS = 24 * 3600`
  - `scribe.public(session)` adds `"transcript"` and `"operations": [op ids]`.

- [ ] **Step 1: Add `Draft.evidence` in `kernel/contracts.py`**

```python
@dataclass(frozen=True)
class Draft:
    """... (keep the existing docstring) ... `evidence` is per link_id, the
    words the value was taken from, shown beside it for the readback."""
    instrument: str
    operation: str
    values: dict
    confidence: dict = field(default_factory=dict)
    transcript: Optional[str] = None
    evidence: dict = field(default_factory=dict)
```

- [ ] **Step 2: Add the failing asserts for `build_draft` to `api/fill.py` `demo()`, before the final print**

```python
    answers = {"systolic": {"value": "140", "confidence": 0.97, "evidence": "BP 140"},
               "re_va": {"value": "6/12", "confidence": 0.9, "evidence": "six by twelve"},
               "lmp": {"value": "15 August", "confidence": 0.9, "evidence": "15 August"},
               "diagnosis": {"value": [{"code": "Fever"}], "confidence": 0.8, "evidence": "fever"}}
    d = build_draft("x.op", schema, answers, "BP 140 ...", instrument="i", today=today)
    assert d["values"] == {"systolic": 140, "diagnosis": [{"code": "Fever"}]}, d
    assert d["unfilled"] == ["lmp", "re_va"], "off-list and disabled are heard but not filled"
    assert d["confidence"] == {"systolic": 0.89, "diagnosis": 0.8}, "capped under SURE"
    assert d["tick"] == ["systolic"], "numbers are ticked, structured rows are not"
    assert d["evidence"]["systolic"] == "BP 140"
    assert build_draft("x.op", schema, {}, "hello", instrument="i", today=today) is None
```

- [ ] **Step 3: Run it to see it fail**

Run: `python3 -m api.fill`
Expected: `NameError: name 'build_draft' is not defined`

- [ ] **Step 4: Implement `build_draft` in `api/fill.py`**

```python
CAP = 0.89   # under web/src/form/Form.tsx SURE, so every heard value reads as unconfirmed


def build_draft(operation, schema, answers, transcript, *, instrument, today):
    fields = flatten(schema)
    by = {f["link_id"]: f for f in fields}
    values, unfilled = {}, []
    for link_id, a in answers.items():
        ok, value = coerce(by[link_id], a["value"], today) if link_id in by else (False, None)
        if ok:
            values[link_id] = value
        else:
            unfilled.append(link_id)
    kept = enabled(fields, values)
    unfilled += [k for k in values if k not in kept]
    if not kept:
        return None
    return {"instrument": instrument, "operation": operation, "values": kept,
            "confidence": {k: min(CAP, answers[k]["confidence"]) for k in kept},
            "evidence": {k: answers[k]["evidence"] for k in kept},
            "tick": [k for k in kept if by[k]["type"] in TICK_TYPES],
            "unfilled": sorted(unfilled), "transcript": transcript}
```

- [ ] **Step 5: Run it to see it pass**

Run: `python3 -m api.fill`
Expected: `ok api.fill`

- [ ] **Step 6: Change `api/scribe.py`**

Before editing, check Eka's language codes: open `https://developer.eka.care/llms.txt`, find the EkaScribe `input_language` values, and put the exact codes in `LANGUAGES` below. If Hindi, Tamil or Telugu are spelled differently, use Eka's spelling. Keep the UI names.

Replace `TEMPLATES` and `start`'s signature:

```python
# The transcript and nothing else. Structure is ours: api/fill.py and
# api/extract.py read whatever questionnaire the template names.
TEMPLATES = [{"template_id": "transcript_template", "codification_needed": False}]

# What a person picks in the bar, to what Eka is told was spoken. Hinglish is
# two languages at once, which is how it is sent.
LANGUAGES = {"en-IN": ["en-IN"], "hinglish": ["en-IN", "hi"], "hi": ["hi"],
             "ta": ["ta"], "te": ["te"]}

TRANSCRIPT_SECONDS = 24 * 3600
```

In `start`, rename the `language="en-IN"` parameter to `languages=("en-IN",)` and pass `"input_language": list(languages)`.

Delete `_prop`, `_phrase`, `_dose`, `KNOWN`, `fill`, `drafts`, `CONSULT`, `RX`, and the `SAMPLE` EMR payload's use in `demo()`. Replace the session section with:

```python
import time
from datetime import date

from api import extract as extractor_module
from api import fill as filler


def transcript_of(status):
    text = decoded(status)
    return (text.get("transcript_template") or text.get("transcript") or "").strip()


def begin(thread, actor, txn, operations, instrument=""):
    session = {"id": "scr-" + uuid.uuid4().hex[:12], "thread": thread,
               "actor": actor, "txn": txn, "operations": operations,
               "instrument": instrument, "status": "running", "reason": "",
               "drafts": [], "transcript": "", "expires": None}
    SESSIONS[session["id"]] = session
    return session


def expire(now=None):
    """Drop every transcript past its 24 hours. Called on every session read,
    so nothing needs a timer; a kernel nobody asks keeps nothing it could have
    dropped either, because a restart empties SESSIONS."""
    now = time.time() if now is None else now
    for sid in [s for s, v in SESSIONS.items() if v["expires"] and v["expires"] <= now]:
        del SESSIONS[sid]


def refill(session, operations, *, extractor=None, today=None):
    """Build drafts for these operations from the transcript already held. The
    template switch: no re-recording, no second upload."""
    extractor = extractor or extractor_module.extract
    today = today or date.today()
    session["operations"] = operations
    session["drafts"] = []
    for op_id, spec in sorted(operations.items()):
        answers = extractor(filler.flatten(spec["schema"]), session["transcript"])
        d = filler.build_draft(op_id, spec["schema"], answers, session["transcript"],
                               instrument=session["instrument"], today=today)
        if d:
            session["drafts"].append(d)
    if session["drafts"]:
        session.update(status="ready", reason="")
    else:
        session.update(status="ready", reason="Nothing in the recording fills this form. "
                       "The transcript is below. Type the note.")
    return session


def collect(session, *, extractor=None):
    if session["status"] in ("ready", "failed", "withdrawn"):
        return session
    try:
        status = poll(session["txn"])
    except ScribeError as broke:
        session.update(status="failed", reason=str(broke))
        return session
    if running(status):
        return session
    session["transcript"] = transcript_of(status)
    if not session["transcript"]:
        said = failures(status)
        session.update(status="failed", reason="No transcript came back. %s Type the note."
                       % " ".join(said))
        return session
    session["expires"] = time.time() + TRANSCRIPT_SECONDS
    return refill(session, session["operations"], extractor=extractor)


def withdraw(session):
    session.update(status="withdrawn", drafts=[], transcript="",
                   reason="Withdrawn. Nothing from this recording was kept.")
    return session


def public(session):
    return {"session": session["id"], "status": session["status"],
            "reason": session["reason"], "drafts": session["drafts"],
            "transcript": session["transcript"],
            "operations": sorted(session["operations"])}
```

Replace `demo()`'s draft asserts (the ones using `drafts(...)`, `consult`, `rx`, `every`) with:

```python
    DONE = {"data": {"output": [], "template_results": {"transcript": [
        {"template_id": "transcript", "status": "success",
         "value": base64.b64encode(b"BP is 140 over 90. Fever for three days.").decode()}]}}}
    assert transcript_of(DONE) == "BP is 140 over 90. Fever for three days."

    vitals = {"questions": [{"link_id": "systolic", "text": "Systolic", "type": "integer"}]}
    consult = {"questions": [{"link_id": "history", "text": "History", "type": "text"}]}

    def fake(fields, transcript):
        ids = {f["link_id"] for f in fields}
        said = {"systolic": {"value": 140, "confidence": 0.95, "evidence": "BP is 140"},
                "history": {"value": "Fever for three days", "confidence": 0.9,
                            "evidence": "Fever for three days"}}
        return {k: v for k, v in said.items() if k in ids}

    global poll
    real_poll, poll = poll, lambda txn: DONE
    try:
        s = begin("enc-003", "user:mo", "phc-y", {"v.op": {"schema": vitals}}, instrument="i")
        collect(s, extractor=fake)
    finally:
        poll = real_poll
    assert s["status"] == "ready" and s["drafts"][0]["values"] == {"systolic": 140}, s
    assert s["drafts"][0]["tick"] == ["systolic"]
    assert s["expires"] - time.time() > 24 * 3600 - 5, "the transcript is kept a day"

    refill(s, {"c.op": {"schema": consult}}, extractor=fake)
    assert [d["operation"] for d in s["drafts"]] == ["c.op"], "the switch rebuilds from the transcript"
    assert public(s)["transcript"].startswith("BP is 140")

    expire(now=s["expires"] + 1)
    assert s["id"] not in SESSIONS, "past a day the transcript is gone"

    withdrawn = begin("enc-003", "user:mo", "phc-z", {}, instrument="i")
    withdrawn["transcript"] = "something"
    withdraw(withdrawn)
    assert public(withdrawn)["transcript"] == "", "withdrawal drops the transcript too"
```

Keep the `running`, `failures`, `decoded` asserts on `PARTIAL`/`FAILED`, the withdrawn-session asserts (update the `begin` call to `begin("enc-002", "user:demo", "phc-x", {})`), and the Leaky SDK asserts. In the SDK-leak block, `start(b"x", suffix=".m4a")` still works because `languages` has a default.

Update the final line to `print("ok api.scribe")`.

- [ ] **Step 7: Run both checks**

Run: `python3 -m api.fill && python3 -m api.extract && python3 -m api.scribe`
Expected: three `ok` lines.

- [ ] **Step 8: Commit**

```bash
git add api/fill.py api/scribe.py kernel/contracts.py
git commit -m "Build scribe drafts from the transcript and the questionnaire, not from Eka's EMR JSON

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Declarations: station defaults, allowlist, and the number rule

**Files:**
- Modify: `bundles/phc/bundle.yaml`
- Modify: `bundles/phc/phc.inst.consult-scribe.md`
- Modify: `kernel/declarations.py` (`_lint_instrument`, `lint`, `Bundle`, `load`, `compile_json`)
- Modify: `kernel/DECLARATIONS.md` §4

**Interfaces:**
- Produces:
  - `BUNDLE.scribe: dict[str, {"default": str | None, "choose": list[str]}]`, keyed by station.
  - `catalogue.json["scribe"]`, the same dict, for the renderer.

- [ ] **Step 1: Add the config to `bundles/phc/bundle.yaml`** (after `stations:`)

```yaml
# Which template a recording fills at each station. A template is an operation:
# its questionnaire is the form, and its mapping is the only way anything
# heard reaches a row. `choose` is what the bar's switcher offers; every id
# must be in the scribe instrument's operations. `default: null` means the
# person picks, which is the community worker's case: several surveys, none
# of them obviously first.
scribe:
  reception: {default: phc.op.patient-register, choose: [phc.op.patient-register]}
  nurse:     {default: phc.op.vitals-record,    choose: [phc.op.vitals-record]}
  doctor:    {default: phc.op.consult-document, choose: [phc.op.consult-document, phc.op.rx-prescribe]}
  community: {default: null,                    choose: [phc.op.household-visit]}
```

- [ ] **Step 2: Grow the allowlist in `bundles/phc/phc.inst.consult-scribe.md`**

Set `operations: [phc.op.patient-register, phc.op.vitals-record, phc.op.consult-document, phc.op.rx-prescribe, phc.op.household-visit]`, `title: Scribe`, `summary: Transcribes a recording into the station's template.` Replace the body's vitals paragraph with:

```markdown
Vitals are now on this list, which reverses the earlier rule. A number a
recording fills arrives with the words it came from beside it, and the form
will not commit until the person ticks each one (spec 2026-09-16 §10.4). The
misheard "one forty" is still the risk; the tick is where it is caught.
```

- [ ] **Step 3: Write the failing lint check**

In `kernel/tests/` find the declarations test (`ls kernel/tests`). Add, following that file's style:

```python
def test_scribe_station_config_is_linted():
    from kernel import declarations
    bundle = declarations.load("phc")
    assert bundle.scribe["nurse"]["default"] == "phc.op.vitals-record"
    manifest_bad = {"scribe": {"nurse": {"default": "phc.op.nope", "choose": []}}}
    problems = declarations._lint_scribe(manifest_bad, bundle.instruments_raw)
    assert any("phc.op.nope" in p for p in problems), problems
```

Run: `python3 -m kernel.tests.<that file>` (or the runner its docstring names)
Expected: FAIL, `Bundle has no attribute scribe`

- [ ] **Step 4: Implement in `kernel/declarations.py`**

Delete the device rule in `_lint_instrument`:

```python
        if fm["kind"] == "scribe" and ops[oid]["instrument"] == "device":
            fail(...)
```

Add:

```python
def _lint_scribe(manifest, instruments):
    """Every station default and choice is an operation a scribe may fill."""
    allowed = {oid for fm in instruments if fm.get("kind") == "scribe"
               for oid in fm.get("operations") or []}
    stations = set(manifest.get("stations") or [])
    bad = []
    for station, cfg in (manifest.get("scribe") or {}).items():
        if stations and station not in stations:
            bad.append(f"bundle.yaml scribe: '{station}' is not a station")
        choose = list(cfg.get("choose") or [])
        for oid in choose + ([cfg["default"]] if cfg.get("default") else []):
            if oid not in allowed:
                bad.append(f"bundle.yaml scribe.{station}: '{oid}' is not in a scribe "
                           "instrument's operations")
        if cfg.get("default") and cfg["default"] not in choose:
            bad.append(f"bundle.yaml scribe.{station}: default must be one of choose")
    return bad
```

Add `scribe: dict = dataclasses.field(default_factory=dict)` and `instruments_raw: list = dataclasses.field(default_factory=list)` to `Bundle`. In `load`, after `bad = lint(...) + bad_mappings`:

```python
    raw_instruments = [fm for fm, _ in decls.values() if fm.get("type") == "instrument"]
    bad += _lint_scribe(manifest, raw_instruments)
```

and pass `scribe=dict(manifest.get("scribe") or {}), instruments_raw=raw_instruments` into `Bundle(...)`. In `compile_json`, add `"scribe": bundle.scribe` to the returned dict.

- [ ] **Step 5: Update `kernel/DECLARATIONS.md` §4**

Replace the bullet "A `scribe` instrument may not list an operation whose default `instrument` is `device`..." with:

```markdown
- A `scribe` instrument may list any operation. Every non-text value it fills
  (integer, decimal, quantity, date, choice, boolean) is shown with the words
  it came from, and the renderer will not commit until each one is ticked.
  Station defaults live in `bundle.yaml` under `scribe:` and must name
  operations a scribe instrument lists.
```

- [ ] **Step 6: Compile and run**

Run: `python3 -m catalogue.build && python3 -m kernel.declarations && python3 -m kernel.tests.<that file>`
Expected: no `FAIL` lines; test passes; `grep -c '"scribe"' catalogue/catalogue.json` ≥ 1.

- [ ] **Step 7: Commit**

```bash
git add bundles/phc kernel catalogue/catalogue.json care_phc_mcp/catalogue.json
git commit -m "Declare each station's scribe template and let a scribe fill numbers behind a tick

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Routes

**Files:**
- Modify: `api/main.py:563-689`
- Modify: `api/tests/test_api.py` (scribe section, from line 367)

**Interfaces:**
- Consumes: `BUNDLE.scribe` (Task 4), `scribe.begin/collect/refill/public/LANGUAGES/expire` (Task 3).
- Produces (all under the existing router prefix the web client uses, `/api/v1/phc`; the tests use `/api`):
  - `GET /scribe/templates?station=<s>` returns `{"default": op_id | null, "choose": [{"operation", "title"}], "languages": [...]}`, filtered to operations the caller holds the capability for.
  - `POST /scribe/sessions?thread=<t>&operations=<a,b>&language=<code>`, where the body is audio. It refuses with 403 without consent (unchanged), with 403 for an operation not allowed for this caller, 400 for more than 2 operations or an unknown language, and 503 for an Eka failure.
  - `POST /scribe/sessions/{id}/extract` with JSON body `{"operations": [...]}` returns the session. It is 409 unless status is `ready`, and applies the same operation checks.

- [ ] **Step 1: Write the failing route tests** (append to the scribe section of `api/tests/test_api.py`; reuse `fake_scribe`, `AUDIO`, and the consent setup the existing consent-granted test uses. Read that test first and copy how it raises `capture.consented` on a thread.)

```python
TRANSCRIPT = {"data": {"output": [], "template_results": {"transcript": [
    {"template_id": "transcript", "status": "success",
     "value": base64.b64encode(b"BP is 140 over 90").decode()}]}}}


def fake_extract(fields, transcript):
    ids = {f["link_id"] for f in fields}
    return {"systolic": {"value": 140, "confidence": 0.95, "evidence": "BP is 140"}} \
        if "systolic" in ids else {}


def test_templates_are_the_stations_and_the_callers():
    body = client.get("/api/scribe/templates?station=doctor&role=mo").json()
    assert body["default"] == "phc.op.consult-document"
    assert [c["operation"] for c in body["choose"]] == \
        ["phc.op.consult-document", "phc.op.rx-prescribe"]
    assert "hi" in body["languages"] and "ta" in body["languages"]
    nurse_as_pharmacist = client.get("/api/scribe/templates?station=nurse&role=pharmacist").json()
    assert nurse_as_pharmacist["choose"] == [], "no capability, no template"


def test_a_recording_fills_the_named_template_and_switches_without_rerecording():
    reset()
    fake = fake_scribe(TRANSCRIPT)
    scribe.extractor_module.extract = fake_extract   # restored below
    try:
        thread = consented_thread()                  # the helper the consent test uses
        started = client.post(
            f"/api/scribe/sessions?thread={thread}&operations=phc.op.vitals-record"
            "&language=hinglish&role=nurse",
            content=AUDIO, headers={"Content-Type": "audio/webm"}).json()
        ready = client.get(f"/api/scribe/sessions/{started['session']}?role=nurse").json()
        assert ready["status"] == "ready", ready
        assert ready["drafts"][0]["values"] == {"systolic": 140}
        assert ready["drafts"][0]["tick"] == ["systolic"]
        assert fake.v2rx.uploads[0]["bytes"] == AUDIO

        switched = client.post(f"/api/scribe/sessions/{started['session']}/extract?role=mo",
                               json={"operations": ["phc.op.consult-document"]}).json()
        assert switched["operations"] == ["phc.op.consult-document"]
        assert len(fake.v2rx.uploads) == 1, "switching never uploads again"

        refused = client.post(
            f"/api/scribe/sessions?thread={thread}&operations=phc.op.lab-order&role=mo",
            content=AUDIO, headers={"Content-Type": "audio/webm"})
        assert refused.status_code == 403, "not on the scribe's list"
        too_many = client.post(
            f"/api/scribe/sessions?thread={thread}&role=mo&operations="
            "phc.op.consult-document,phc.op.rx-prescribe,phc.op.vitals-record",
            content=AUDIO, headers={"Content-Type": "audio/webm"})
        assert too_many.status_code == 400
    finally:
        import importlib
        importlib.reload(scribe.extractor_module)
```

If there is no `consented_thread()` helper, write one at the top of this block from the steps the existing consent-granted test performs, and make that test use it too. Add `import base64` at the top if missing.

- [ ] **Step 2: Run to see failures**

Run: `python3 -m api.tests.test_api`
Expected: failures on the new tests (404 for `/scribe/templates`, and so on).

- [ ] **Step 3: Implement in `api/main.py`**

Replace `scribe_targets` with:

```python
def scribe_allowed(user):
    """{operation_id: {"schema": questionnaire}} a recording may fill for this caller:
    on a scribe instrument's list, and within the caller's capabilities."""
    caps = set(user["capabilities"])
    out, instrument = {}, ""
    for decl in BUNDLE.instruments.values():
        if decl.kind != "scribe" or decl.commit != "tap" or decl.readback != "required":
            continue
        instrument = instrument or decl.id
        for op_id in decl.operations:
            op = BUNDLE.operations.get(op_id)
            if op and op["capability"] in caps:
                out[op_id] = {"schema": validate.load(op["input"])}
    return out, instrument


def scribe_pick(user, names):
    allowed, instrument = scribe_allowed(user)
    wanted = [n for n in (names or []) if n]
    if not wanted or len(wanted) > 2:
        raise HTTPException(400, "Name one or two templates to fill.")
    missing = [n for n in wanted if n not in allowed]
    if missing:
        raise HTTPException(403, "A recording may not fill %s for you. Type the note."
                            % ", ".join(missing))
    return {n: allowed[n] for n in wanted}, instrument


@router.get("/scribe/templates")
def scribe_templates(request: Request, station: str = ""):
    user = caller(request)
    allowed, _ = scribe_allowed(user)
    cfg = BUNDLE.scribe.get(station) or {}
    choose = [o for o in cfg.get("choose") or [] if o in allowed]
    default = cfg.get("default") if cfg.get("default") in choose else None
    return {"default": default,
            "choose": [{"operation": o, "title": BUNDLE.operations[o]["title"]} for o in choose],
            "languages": list(scribe.LANGUAGES)}
```

In `scribe_start`, add `operations: str = "", language: str = "en-IN"` parameters. Replace the `targets` block with:

```python
    if language not in scribe.LANGUAGES:
        raise HTTPException(400, "Unknown language %r." % language)
    picked, instrument = scribe_pick(user, operations.split(","))
```

pass `languages=scribe.LANGUAGES[language]` to `scribe.start`, and call `scribe.begin(thread_id, user["id"], txn, picked, instrument=instrument)`.

In `scribe_or_404`, call `scribe.expire()` first.

Add:

```python
@router.post("/scribe/sessions/{session_id}/extract")
async def scribe_extract(session_id: str, request: Request):
    """The template switch. Rebuilds drafts from the transcript this kernel
    already holds; nothing is uploaded and nothing is recorded again."""
    user = caller(request)
    session = scribe_or_404(session_id)
    if session["status"] != "ready":
        raise HTTPException(409, "There is no transcript to fill from yet.")
    body = await request.json()
    picked, _ = scribe_pick(user, body.get("operations") or [])
    return scribe.public(await run_in_threadpool(scribe.refill, session, picked))
```

- [ ] **Step 4: Run to see them pass**

Run: `python3 -m api.tests.test_api`
Expected: all pass, including the pre-existing consent and withdrawal tests. If a pre-existing scribe test asserts the old EMR-derived values, change it to the transcript-derived shape and state why in the commit body.

- [ ] **Step 5: Commit**

```bash
git add api/main.py api/tests/test_api.py
git commit -m "Route a recording to named templates, and refill another template from the held transcript

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Renderer, pure half: `session.ts` and `client.ts`

**Files:**
- Modify: `web/src/scribe/session.ts`
- Modify: `web/src/scribe/client.ts`
- Modify: `web/src/scribe/scribe.check.ts`

**Interfaces:**
- Produces:
  - `ScribeDraft` gains `evidence: Record<string,string>`, `tick: string[]`, `unfilled: string[]`
  - `ScribeSession` gains `transcript: string`, `operations: string[]`
  - `apply(draft, payload): Applied`, which drops the `allowed` parameter. `narrative()` is deleted.
  - `mustTick(draft: ScribeDraft | null, ticked: Set<string>, payload: Payload): string[]` lists link_ids still needing a tick, skipping any the person has since edited away from the drafted value
  - `lastTemplate(role: string, station: string): string | null` and `rememberTemplate(role, station, op)` (localStorage, try/catch)
  - client: `templates(station)`, `startSession(thread, audio, operations: string[], language: string)`, `refill(id, operations)`

- [ ] **Step 1: Rewrite property 1 in `scribe.check.ts`** (replace the "A recording never fills a number" block; keep properties 2–4)

```ts
// 1. A number a recording filled cannot be committed until it is ticked, and
//    editing it to something else makes it the person's number, not a heard one.
{
  const draft = {
    instrument: "i", operation: "phc.op.vitals-record",
    values: { systolic: 140, history: "fever" },
    confidence: { systolic: 0.89, history: 0.89 },
    evidence: { systolic: "BP is 140", history: "fever" },
    tick: ["systolic"], unfilled: [], transcript: "BP is 140, fever",
  };
  assert.deepEqual(mustTick(draft, new Set(), { systolic: 140 }), ["systolic"]);
  assert.deepEqual(mustTick(draft, new Set(["systolic"]), { systolic: 140 }), []);
  assert.deepEqual(mustTick(draft, new Set(), { systolic: 120 }), [],
    "typed over, so it is no longer a heard value");
  assert.deepEqual(mustTick(null, new Set(), {}), []);
  const applied = apply(draft, {});
  assert.deepEqual(applied.fill, { systolic: 140, history: "fever" });
  checks += 5;
}
// Nothing in the renderer still refuses numbers by type.
assert.ok(!read("web/src/scribe/session.ts").includes("export function narrative"));
checks += 1;
```

Update the import line to `import { apply, draftFor, elsewhere, mustTick, pickMime, preview, reasonFor, sentence, type ScribeSession } from "./session.ts";`

- [ ] **Step 2: Run to see it fail**

Run: `cd web && node --experimental-strip-types src/scribe/scribe.check.ts`
Expected: FAIL, `mustTick` is not exported

- [ ] **Step 3: Implement in `session.ts`**

Add fields to the types:

```ts
export type ScribeDraft = {
  instrument: string;
  operation: string;
  values: Record<string, unknown>;
  confidence: Record<string, number>;
  /** The words each value was taken from, shown beside the field. */
  evidence: Record<string, string>;
  /** Non-text values: each needs a person's tick before Commit. */
  tick: string[];
  /** Heard, but not a value this form can hold. Named, never guessed into a field. */
  unfilled: string[];
  transcript: string;
};

export type ScribeSession = {
  session: string;
  status: ScribeStatus;
  reason: string;
  drafts: ScribeDraft[];
  transcript: string;
  operations: string[];
};
```

Delete `narrative`. Change `apply`:

```ts
export function apply(draft: ScribeDraft | null, payload: Payload): Applied {
  const out: Applied = { fill: {}, held: [], refused: [] };
  for (const [link_id, value] of Object.entries(draft?.values ?? {})) {
    if (typed(payload[link_id])) out.held.push({ link_id, value });
    else out.fill[link_id] = value;
  }
  return out;
}

export function mustTick(draft: ScribeDraft | null, ticked: Set<string>, payload: Payload): string[] {
  return (draft?.tick ?? []).filter(
    (id) => !ticked.has(id) && JSON.stringify(payload[id]) === JSON.stringify(draft!.values[id]),
  );
}

const KEY = (role: string, station: string) => `scribe.template.${role}.${station}`;

export function lastTemplate(role: string, station: string): string | null {
  try { return localStorage.getItem(KEY(role, station)); } catch { return null; }
}

export function rememberTemplate(role: string, station: string, op: string) {
  try { localStorage.setItem(KEY(role, station), op); } catch { /* private mode */ }
}
```

Keep `refused` on `Applied` for type compatibility; it is now always empty.

- [ ] **Step 4: Implement in `client.ts`**

```ts
export type Templates = {
  default: string | null;
  choose: { operation: string; title: string }[];
  languages: string[];
};

export async function templates(station: string): Promise<Templates> {
  const res = await fetch(`${API_BASE}${ROUTE.replace("/sessions", "/templates")}?station=${encodeURIComponent(station)}`,
                          { headers: { "X-PHC-Role": currentRole() } });
  if (!res.ok) throw new ApiError(`The kernel answered ${res.status}.`, "Type the note.", res.status);
  return res.json();
}

export const startSession = (thread: string, audio: Blob, operations: string[], language: string) =>
  ask(`${ROUTE}?thread=${encodeURIComponent(thread)}&operations=${encodeURIComponent(operations.join(","))}` +
      `&language=${encodeURIComponent(language)}`,
      { method: "POST", body: audio, headers: { "Content-Type": audio.type || "audio/webm" } });

export const refill = (id: string, operations: string[]) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}/extract`,
      { method: "POST", body: JSON.stringify({ operations }), headers: { "Content-Type": "application/json" } });
```

- [ ] **Step 5: Run to see it pass**

Run: `cd web && node --experimental-strip-types src/scribe/scribe.check.ts`
Expected: the check's ok line. (`tsc` will fail until Task 7 removes `Recorder.tsx`'s use of `narrative`; that is expected here.)

- [ ] **Step 6: Commit**

```bash
git add web/src/scribe/session.ts web/src/scribe/client.ts web/src/scribe/scribe.check.ts
git commit -m "Replace the renderer's no-numbers rule with a tick per heard value

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Renderer, screens: ScribeBar, panel tick gate, mic without a form

**Files:**
- Create: `web/src/scribe/ScribeBar.tsx`
- Delete: `web/src/scribe/Recorder.tsx`
- Modify: `web/src/form/Panel.tsx` (remove the Recorder import and mount at lines ~285–305; add `draft` prop and tick gate)
- Modify: `web/src/form/Form.tsx` (evidence + tick per field)
- Modify: `web/src/screens/Encounter.tsx:59,136-160`
- Modify: `web/src/scribe/scribe.css`

**Interfaces:**
- Consumes: Task 6 exports; `OperationPanel` props; `cat.instruments`, `thread.flags`, `thread.station`. Check the `Thread` type in `web/src/types.ts` for the station field name, and use what is there.
- Produces:
  - `<ScribeBar thread station flags requires onDrafts(session) onClose />`
  - `OperationPanel` prop `draft?: ScribeDraft`
  - `Form` props `evidence?: Record<string,string>`, `ticks?: {need: string[]; ticked: Set<string>; onTick(id: string): void}`

- [ ] **Step 1: Add the failing source checks to `scribe.check.ts`** (these read source text, like property 3 already does)

```ts
// 5. The mic does not open a form, and the panel refuses Commit while a heard number is unticked.
{
  const enc = read("web/src/screens/Encounter.tsx");
  assert.ok(!enc.includes("Dictation is not offered at this step"), "the mic no longer needs a scribe operation");
  assert.ok(enc.includes("<ScribeBar"), "the encounter owns the recording bar");
  const panel = read("web/src/form/Panel.tsx");
  assert.ok(!panel.includes("<Recorder"), "the form no longer starts recordings");
  assert.ok(/disabled=\{[^}]*unticked\.length/.test(panel), "Commit waits on the ticks");
  assert.throws(() => read("web/src/scribe/Recorder.tsx"));
  checks += 5;
}
```

Run: `cd web && node --experimental-strip-types src/scribe/scribe.check.ts`
Expected: FAIL on the first of these asserts.

- [ ] **Step 2: Create `web/src/scribe/ScribeBar.tsx`**

Move the recording machinery from `Recorder.tsx` (the `rec/chunks/keep/timers/alive` refs, `halt`, the unmount effect, `pickMime`, `reasonFor`, the elapsed-seconds timer, the poll loop at `POLL_MS`) into this component unchanged, and delete `Recorder.tsx`. Change what it does around the recording:

```tsx
import { useEffect, useRef, useState } from "react";
import { currentRole } from "../api";
import { dropSession, pollSession, refill, startSession, templates, type Templates } from "./client";
import { lastTemplate, pickMime, reasonFor, rememberTemplate, sentence, type ScribeSession } from "./session";
import "./scribe.css";

const POLL_MS = 3000;
const LANGUAGE_NAMES: Record<string, string> = {
  "en-IN": "English", hinglish: "Hinglish", hi: "हिन्दी", ta: "தமிழ்", te: "తెలుగు",
};

type Phase = "idle" | "recording" | "uploading" | "waiting" | "ready" | "failed" | "withdrawn";

export function ScribeBar({ thread, station, onDrafts, onClose }: {
  thread: string;
  station: string;
  /** Called with every ready session, including after a template switch. */
  onDrafts: (s: ScribeSession) => void;
  onClose: () => void;
}) {
  const [menu, setMenu] = useState<Templates | null>(null);
  const [template, setTemplate] = useState<string>("");
  const [language, setLanguage] = useState("en-IN");
  const [phase, setPhase] = useState<Phase>("idle");
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [note, setNote] = useState("");
  // ... refs and halt() moved from Recorder.tsx ...

  useEffect(() => {
    templates(station).then((t) => {
      setMenu(t);
      const remembered = lastTemplate(currentRole(), station);
      const pick = t.choose.find((c) => c.operation === remembered)?.operation ?? t.default ?? "";
      setTemplate(pick);
      if (pick) void begin(pick);   // recording starts on the click that opened the bar
    }).catch((e) => { setPhase("failed"); setNote(String(e.message ?? e)); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station]);

  const choose = async (op: string) => {
    setTemplate(op);
    rememberTemplate(currentRole(), station, op);
    if (phase === "idle") return void begin(op);
    if (session && phase === "ready") {
      const next = await refill(session.session, [op]);
      setSession(next);
      onDrafts(next);
    }
  };

  // begin(op): getUserMedia + MediaRecorder exactly as Recorder.tsx's start did.
  // stop(): build the blob, then
  //   const s = await startSession(thread, blob, [template], language);
  //   setPhase("waiting"); poll until s.status !== "running";
  //   on "ready": setSession(s); setPhase("ready"); onDrafts(s);
  //   on "failed": setPhase("failed"); setNote(s.reason);
  // withdraw(): halt(); if (session) await dropSession(session.session); setPhase("withdrawn").

  return (
    <div className="scribe-bar" role="status" aria-live="polite">
      <span className={`scribe-dot ${phase === "recording" ? "on" : ""}`} aria-hidden />
      <span className="scribe-phase">{/* "Recording 0:42" | "Transcribing" | "Ready" | note */}</span>
      <select aria-label="Template" value={template} onChange={(e) => void choose(e.target.value)}
              disabled={!menu || phase === "uploading" || phase === "waiting"}>
        {!template && <option value="">Choose a template</option>}
        {menu?.choose.map((c) => <option key={c.operation} value={c.operation}>{c.title}</option>)}
      </select>
      <select aria-label="Language" value={language} onChange={(e) => setLanguage(e.target.value)}
              disabled={phase !== "idle" && phase !== "recording"}>
        {(menu?.languages ?? ["en-IN"]).map((l) => <option key={l} value={l}>{LANGUAGE_NAMES[l] ?? l}</option>)}
      </select>
      {phase === "recording" && <button className="cq" onClick={stop}>Stop</button>}
      {(phase === "recording" || phase === "waiting") && <button className="cq" onClick={withdraw}>Discard</button>}
      {phase === "ready" && session && session.drafts.length === 0 && (
        <details><summary>Nothing to fill. Transcript</summary><p>{session.transcript}</p></details>
      )}
      {sentence(phase === "waiting" ? "running" : phase, note) && <span className="f-hint">{sentence(phase === "waiting" ? "running" : phase, note)}</span>}
      <button className="cq" onClick={() => { halt(); onClose(); }} aria-label="Close scribe">×</button>
    </div>
  );
}
```

The three commented lines (`begin`, `stop`, `withdraw`) are the bodies moved from `Recorder.tsx`, changed only as written. Write them out in full in the file. With `default: null` (community), no template is picked, so `begin` does not run until one is chosen. That is the "person picks" rule.

- [ ] **Step 3: Wire `Encounter.tsx`**

Replace `const [dictating, setDictating] = useState<Operation | null>(null);` and `scribeOp` with:

```tsx
const [scribing, setScribing] = useState(false);
const [drafts, setDrafts] = useState<ScribeDraft[]>([]);
const consentFlag = Object.values(cat.instruments ?? {})
  .map((i) => i as { kind?: string; requires?: string })
  .find((i) => i.kind === "scribe")?.requires;
const consented = !consentFlag || (thread.flags ?? []).includes(consentFlag);
```

Replace the `{dictating && (...)}` block with:

```tsx
{scribing && (
  <ScribeBar thread={thread.id} station={thread.station ?? ""}
             onDrafts={(s) => setDrafts(s.drafts)}
             onClose={() => { setScribing(false); setDrafts([]); }} />
)}
{drafts.map((d) => {
  const op = cat.operations[d.operation];
  return op ? (
    <div key={d.operation} style={{ padding: "0 15px 12px", maxHeight: "42vh", overflowY: "auto", flexShrink: 0 }}>
      <OperationPanel op={op} thread={thread.id} client={client} draft={d}
        instruments={cat.instruments} flags={thread.flags} inline
        onDone={() => { setDrafts((all) => all.filter((x) => x.operation !== d.operation)); onChanged(); }}
        onCancel={() => setDrafts((all) => all.filter((x) => x.operation !== d.operation))} />
    </div>
  ) : null;
})}
```

Composer props become:

```tsx
onStartScribe={() => setScribing(true)}
micReason={consented ? undefined : "Capture consent is not recorded on this visit"}
```

- [ ] **Step 4: Tick gate in `Panel.tsx`**

Delete the `Recorder` import and the `mounts.filter((m) => m.kind === "scribe")...` block. Add the prop `draft?: ScribeDraft` and:

```tsx
const [payload, setPayload] = useState<Payload>({ ...(proposal?.payload ?? draft?.values ?? seed ?? {}) });
const [ticked, setTicked] = useState<Set<string>>(new Set());
const unticked = mustTick(draft ?? null, ticked, payload);
```

Seed `heard` with `draft?.confidence ?? {}`. Pass to `<Form>`:

```tsx
evidence={draft?.evidence}
ticks={{ need: unticked, ticked, onTick: (id) => setTicked((s) => new Set(s).add(id)) }}
```

Change the Commit button's `disabled` to `disabled={busy || unticked.length > 0 || (stage === "confirm" && !confirmed)}`. Just above the footer, add:

```tsx
{unticked.length > 0 && <div className="f-hint unsure">Tick each heard value to commit ({unticked.length} left).</div>}
{draft && draft.unfilled.length > 0 && (
  <div className="f-hint">Heard but not filled: {draft.unfilled.map((id) => labelled(schema, id)).join(", ")}</div>
)}
```

Check `labelled`'s real signature in `Form.tsx` before using it. If it differs, use the `walk(schema.questions)` lookup the panel already does for `missing`.

- [ ] **Step 5: Evidence and tick in `Form.tsx`**

Add `evidence` and `ticks` to the props type. In the per-question render, next to the existing `unsure` hint at line ~248, add:

```tsx
{evidence?.[q.link_id] && <div className="f-hint heard">“{evidence[q.link_id]}”</div>}
{ticks?.need.includes(q.link_id) && (
  <label className="f-check">
    <input type="checkbox" checked={false} onChange={() => ticks.onTick(q.link_id)} />
    <span>Checked against what was said</span>
  </label>
)}
```

Add `.f-hint.heard { font-style: italic; }` to `scribe.css`.

- [ ] **Step 6: Run all renderer checks and the type build**

Run: `cd web && npm run check && npx tsc -b`
Expected: every check prints ok; tsc has no errors. Fix any remaining imports of `Recorder`, `narrative` or `liveSession` that tsc reports.

- [ ] **Step 7: Commit**

```bash
git add -A web/src
git commit -m "Record from the encounter bar, open drafts in the panel, and hold Commit until heard numbers are ticked

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Verify in the running app

**Files:** none unless a defect is found.

- [ ] **Step 1: Rebuild declarations and restart the API** so it loads Task 4's bundle config

Run: `python3 -m catalogue.build && python3 -m kernel.declarations`, then restart `sh api/run.sh`. The web dev server on :5173 is already running; reload the tab.

- [ ] **Step 2: Drive it in the Browser pane**

1. Open the doctor-station thread (`enc-003`). If it lacks `capture.consented`, record consent through the consent operation first.
2. Check the mic is enabled with no form open. Click it: the ScribeBar appears with "Consultation" selected, and no panel opens.
3. Switch the role to nurse on `enc-002` and check the bar defaults to vitals.
4. Switch to the community station: no template is selected and recording does not start until one is chosen.
5. Without an Eka key, stopping must show the service's refusal sentence and no form. With keys, speak "BP 140 over 90, pulse 88". The vitals panel opens with `systolic` 140, its quoted evidence, a tick box, and Commit disabled until both are ticked.
6. Switch the template to Consultation after a ready session and check the drafts replace without a new upload (network pane: one POST to `/scribe/sessions`, one to `/extract`).

- [ ] **Step 3: Screenshot the ready vitals panel with the tick gate** and share it.

- [ ] **Step 4: Run every check once more**

Run: `python3 -m api.fill && python3 -m api.extract && python3 -m api.scribe && python3 -m api.tests.test_api && (cd web && npm run check)`
Expected: all ok.

---

## Known ceilings (deliberate, not gaps)

- Sessions and transcripts live in process memory. A restart loses them, which costs one re-recording (same as today).
- `enable_behavior: any` is not evaluated; no current questionnaire uses it.
- Relative dates handle `today`, `yesterday`, and a day plus month name. Weekday phrases wait for golden transcripts that need them.
- Template memory is per browser and role, until the kernel has user accounts.
- Registration by voice needs consent recorded first. `capture.consented` still gates every recording, including at reception.
- Golden-transcript precision and recall measurement (spec §7) needs a live key and real recordings in the five languages. It belongs with Plan 2, when the specialty templates exist to measure.
