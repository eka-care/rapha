"""Form answers from the scribe service's STRUCTURED note, with no second model.

Eka's own app does not read a consultation back out of text. It asks the
service to write the note section by section -- vitals as rows with a unit,
a medicine split into name, strength, form, dose and frequency, a follow-up
with a date -- and the doctor edits THAT. The kernel can ask the same way
(api/scribe.agent_state), and this module reads what comes back into the shape
`api/fill.py` takes, which is the shape `api/shaped.py` produces from the
markdown note. Everything downstream of an answer is therefore unchanged.

WHICH SECTION FILLS WHICH QUESTION IS DECLARED, NEVER TYPED HERE. The scribe
instrument's `reads:` block names, per operation and per question, where in the
note the answer lives. Nothing in this file names a vital, a drug or a form.

WHAT DOES NOT CHANGE, because it is what makes a draft safe to tap:

- EVIDENCE IS FOUND, NOT TRUSTED. The structured note carries no span of the
  words a value came from, and the markdown reader dropped any answer whose
  span was not really in the transcript. So the span is looked for here, in
  the transcript, by this code: a number must be a literal digit token that
  was said, a name must be a word that was said, and a value with no span is
  dropped and named by `api/fill.py` as unfilled. A model cannot invent
  evidence it never gets to write.
- A CATALOGUE CODE IT ATTACHES IS NOT READ AT ALL. The service suggests codes
  ("urine routine" came back as a urine protein dipstick). Only the words are
  taken, and `api/fill.py` resolves them against this bundle's own value sets.
- CONFIDENCE IS 0. It is "not scored": the service reports no per-value
  certainty, and `api/fill.py` caps every one below the renderer's threshold
  anyway, so every value still has to be confirmed by a person.

Run: python3 -m api.structured
"""
from __future__ import annotations

import copy
import json
import re

from api import fill

_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(.*)$")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")


def _norm(text):
    return _SPACE.sub(" ", str(text)).strip().lower()


# ------------------------------------------------------------ the stream

def parse_stream(lines):
    """The JSON events of a server-sent stream: every `data:` line that is one.
    A keep-alive comment, a blank line and a line that is not JSON are skipped,
    which is what makes a stream cut short a short list and not an error."""
    events = []
    for line in lines:
        line = line.strip() if isinstance(line, str) else str(line, "utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        try:
            events.append(json.loads(line[5:].strip()))
        except ValueError:
            continue
    return events


def _step(node, key):
    return node[int(key)] if isinstance(node, list) else node[key]


def _patch(doc, ops):
    """RFC 6902 add / replace / remove, the three the service sends. Anything
    else is refused: guessing at a patch would be guessing at a clinical note."""
    for op in ops:
        kind = op.get("op")
        if kind not in ("add", "replace", "remove"):
            raise ValueError("a state patch this reader does not know: %r" % kind)
        path = [p.replace("~1", "/").replace("~0", "~")
                for p in str(op.get("path", "")).split("/")[1:]]
        node = doc
        for key in path[:-1]:
            node = _step(node, key)
        last = path[-1]
        if kind == "remove":
            node.pop(int(last) if isinstance(node, list) else last)
        elif isinstance(node, list):
            if last == "-":
                node.append(op["value"])
            elif kind == "add":
                node.insert(int(last), op["value"])
            else:
                node[int(last)] = op["value"]
        else:
            node[last] = op["value"]
    return doc


def final_state(events):
    """The note as the run left it: the last snapshot, then every patch after.
    None when the run never produced a snapshot, or finished in an error."""
    state, seen = None, False
    for event in events:
        kind = event.get("type")
        if kind == "RUN_ERROR":
            return None
        if kind == "STATE_SNAPSHOT":
            state, seen = copy.deepcopy(event.get("snapshot")), True
        elif kind == "STATE_DELTA" and seen:
            state = _patch(state, event.get("delta") or [])
    return state if isinstance(state, dict) else None


# ------------------------------------------------------------ reading it

def _section(state, key):
    for s in (state or {}).get("sections") or []:
        if s.get("key") == key:
            return s.get("payload") or {}
    return None


def _pick(rule, payload):
    """The raw strings this rule takes from one section, one per row.

    A table section (`rows`) is filtered by `where` and read by `take`, or
    rendered by `format` ("{finding}: {detail}"); a list section (`items`) is
    read whole; any other section is a plain mapping read by `take`.
    """
    if payload is None:
        return []
    where = {k: _norm(v) for k, v in (rule.get("where") or {}).items()}
    if "rows" in payload:
        out = []
        for row in payload["rows"] or []:
            if any(_norm(row.get(k, "")) != v for k, v in where.items()):
                continue
            if rule.get("format"):
                try:
                    out.append(rule["format"].format(**{k: str(v) for k, v in row.items()}))
                except (KeyError, IndexError):
                    continue
            else:
                out.append(str(row.get(rule.get("take"), "") or ""))
        return out
    if "items" in payload:
        return [str(i) for i in payload["items"] or []]
    return [str(payload.get(rule.get("take"), "") or "")]


def _shape(text, rule):
    """The part of a raw string the question takes: before or after a
    separator, the leading number, or what follows it."""
    text = str(text).strip()
    if rule.get("split"):
        sep, index = rule["split"]
        parts = [p.strip() for p in text.split(sep)]
        return parts[index] if 0 <= index < len(parts) else ""
    if rule.get("part") in ("number", "unit"):
        found = _NUMBER.match(text)
        if not found:
            return ""
        return found.group(1) if rule["part"] == "number" else found.group(2).strip()
    return text


# ------------------------------------------------------------ evidence

def _sentences(transcript):
    return [s.strip() for s in _SENTENCE.split(str(transcript)) if s.strip()]


def _evidence(value, transcript, numeric):
    """The words of the transcript this value stands on, or "".

    A number: the sentence holding it as a literal digit token, so "130/85"
    is found in "Blood pressure is 130/85" and "85" is not found in "185".
    Anything else: the sentence sharing the most words of four letters or more
    with it, needing at least one. A value with no such sentence has nothing
    it can be shown beside, and is dropped.
    """
    sentences = _sentences(transcript)
    if numeric:
        # Bounded on both sides, and not by a slash either: 85 is not a number
        # that was said in "130/85", it is half of one. A value taken FROM a
        # compound (split) is searched for as the compound.
        token = re.compile(r"(?<![\d./])%s(?![\d/]|\.\d)" % re.escape(str(value).strip()))
        for s in sentences:
            if token.search(s):
                return s
        return ""
    words = {w for w in _WORD.findall(_norm(value)) if len(w) >= 4 or w.isdigit()}
    best, score = "", 0
    for s in sentences:
        have = len(words & set(_WORD.findall(_norm(s))))
        if have > score:
            best, score = s, have
    return best if score else ""


# ------------------------------------------------------------ the answers

def answers(state, reads, fields, transcript):
    """Read the structured note into the shape `api/fill.py` takes.

    `reads` is the instrument's declaration for ONE operation:
    {link_id: rule}, a rule being {section, where?, take? | format?, split? |
    part?, join?, rows?}. `rows: true` means a question inside a repeating
    group, and answers one row per row of the section. `fields` is
    `fill.flatten` of the operation's questionnaire, so a rule for a question
    it does not ask is dropped, as is one for a value with no evidence.
    """
    known = {f["link_id"]: f for f in fields}
    out = {}
    for link_id, rule in (reads or {}).items():
        field = known.get(link_id)
        if not field:
            continue
        numeric = field.get("type") in ("integer", "decimal")
        raws = _pick(rule, _section(state, rule.get("section")))
        values = [_shape(v, rule) for v in raws]
        # What is looked for in the transcript: the value, or for a part of a
        # compound ("130/85" -> 85) the compound it was cut from.
        if rule.get("part"):
            # "100 mg" is evidenced by the 100, for the dose and the unit alike:
            # a unit has no words of four letters to be found, and the number
            # is what places the sentence it was said in.
            stood = [(_NUMBER.match(r) or [None, ""])[1] for r in raws]
            numeric = True
        else:
            stood = raws if rule.get("split") else values
        if rule.get("rows"):
            group = field.get("row_of")
            if not group:
                continue
            for i, value in enumerate(values):
                _keep(out, fill.row_id(group, i, link_id), value, stood[i], transcript, numeric)
            continue
        if rule.get("join") is not None:
            value = rule["join"].join(v for v in values if v)
            seen = value
        else:
            at = next((i for i, v in enumerate(values) if v), None)
            value, seen = (values[at], stood[at]) if at is not None else ("", "")
        _keep(out, link_id, value, seen, transcript, numeric)
    return out


def _keep(out, ident, value, stood, transcript, numeric):
    value = str(value or "").strip()
    if not value or ident in out:
        return
    evidence = _evidence(stood, transcript, numeric)
    if not evidence:
        return
    out[ident] = {"value": value, "confidence": 0.0, "evidence": evidence}


# ---------------------------------------------------------------------- check

def demo():
    """Run: python3 -m api.structured   (no network, no credentials)"""
    # -- the stream ---------------------------------------------------------
    snap = {"type": "STATE_SNAPSHOT", "snapshot": {"sections": [
        {"key": "vital_signs", "payload": {"rows": []}}]}}
    add = {"type": "STATE_DELTA", "delta": [
        {"op": "add", "path": "/sections/0/payload/rows/-",
         "value": {"vital_name": "Pulse", "value": "84", "unit": "/min"}},
        {"op": "add", "path": "/sections/-",
         "value": {"key": "follow_up", "payload": {"interval": "After 1 week"}}}]}
    events = parse_stream(["event: x", ": keep-alive", "",
                           "data: " + json.dumps(snap), "data: not json",
                           "data: " + json.dumps(add)])
    assert len(events) == 2, events
    state = final_state(events)
    assert [s["key"] for s in state["sections"]] == ["vital_signs", "follow_up"], state
    assert snap["snapshot"]["sections"][0]["payload"]["rows"] == [], \
        "the snapshot the stream carried is not mutated by reading it"
    assert final_state([add]) is None, "a patch with no snapshot has nothing to patch"
    assert final_state(events + [{"type": "RUN_ERROR"}]) is None, "a failed run is no note"
    try:
        final_state([snap, {"type": "STATE_DELTA", "delta": [{"op": "move", "path": "/a"}]}])
        raise AssertionError("an unknown patch must be refused, not guessed at")
    except ValueError:
        pass

    # -- reading it into a form ------------------------------------------------
    said = ("Blood pressure is 130/85. Pulse is 84 /min. Temperature is 98.6 degrees. "
            "I am prescribing nitrofurantoin 100 mg, one capsule twice a day for 5 days. "
            "Chest is clear. Burning while passing urine for four days.")
    note = {"sections": [
        {"key": "vital_signs", "payload": {"rows": [
            {"vital_name": "Blood Pressure", "value": "130/85", "unit": "mmHg"},
            {"vital_name": "Pulse", "value": "84", "unit": "/min"},
            {"vital_name": "Temperature", "value": "98.6", "unit": "F"},
            {"vital_name": "Weight", "value": "51", "unit": "kg"}]}},
        {"key": "prescribed_medications", "payload": {"rows": [
            {"name": "Nitrofurantoin", "strength": "100 mg", "frequency": "Twice daily",
             "duration": "5 days", "medication_id": "locale-x"}]}},
        {"key": "physical_examination", "payload": {"rows": [
            {"finding": "Chest", "detail": "Clear"}, {"finding": "Abdomen", "detail": "Soft"}]}},
        {"key": "chief_complaint", "payload": {"items": ["Burning urination, 4 days"]}}]}
    fields = [
        {"link_id": "systolic", "type": "integer"}, {"link_id": "diastolic", "type": "integer"},
        {"link_id": "pulse", "type": "integer"}, {"link_id": "weight", "type": "decimal"},
        {"link_id": "examination", "type": "text"}, {"link_id": "history", "type": "text"},
        {"link_id": "drug", "type": "choice", "row_of": "medications"},
        {"link_id": "dose", "type": "decimal", "row_of": "medications"},
        {"link_id": "duration", "type": "integer", "row_of": "medications"}]
    bp = {"section": "vital_signs", "where": {"vital_name": "Blood Pressure"}, "take": "value"}
    reads = {
        "systolic": {**bp, "split": ["/", 0]}, "diastolic": {**bp, "split": ["/", 1]},
        "pulse": {"section": "vital_signs", "where": {"vital_name": "Pulse"}, "take": "value"},
        "weight": {"section": "vital_signs", "where": {"vital_name": "Weight"}, "take": "value"},
        "examination": {"section": "physical_examination", "format": "{finding}: {detail}",
                        "join": "; "},
        "history": {"section": "chief_complaint", "join": "; "},
        "drug": {"section": "prescribed_medications", "rows": True, "take": "name"},
        "dose": {"section": "prescribed_medications", "rows": True, "take": "strength",
                 "part": "number"},
        "duration": {"section": "prescribed_medications", "rows": True, "take": "duration",
                     "part": "number"}}
    got = answers(note, reads, fields, said)
    assert got["systolic"]["value"] == "130" and got["diastolic"]["value"] == "85", got
    assert got["systolic"]["evidence"] == "Blood pressure is 130/85.", got["systolic"]
    assert got["pulse"]["value"] == "84", got
    assert got["medications[0].drug"]["value"] == "Nitrofurantoin", got
    assert got["medications[0].dose"]["value"] == "100", got
    assert got["medications[0].duration"]["value"] == "5", got
    assert got["examination"]["value"] == "Chest: Clear; Abdomen: Soft", got
    assert all(a["confidence"] == 0.0 for a in got.values()), "nothing is scored"

    # THE GUARDS. Each is a reason a draft is safe to tap.
    assert "weight" not in got, \
        "a weight the service wrote and nobody said has no evidence and is dropped"
    assert "medications[0].dose" not in answers(
        {"sections": [{"key": "prescribed_medications", "payload": {"rows": [
            {"name": "Nitrofurantoin", "strength": "500 mg"}]}}]}, reads, fields, said), \
        "a dose of 500 that was never said is dropped, with the drug beside it kept"
    wrong = answers({"sections": [{"key": "vital_signs", "payload": {"rows": [
        {"vital_name": "Pulse", "value": "8", "unit": "/min"}]}}]}, reads, fields, said)
    assert "pulse" not in wrong, "8 is a digit inside 84 and 98.6, not a token that was said"
    inside = answers({"sections": [{"key": "vital_signs", "payload": {"rows": [
        {"vital_name": "Pulse", "value": "85", "unit": "/min"}]}}]}, reads, fields,
        "Blood pressure is 130/85. Pulse is 185.")
    assert "pulse" not in inside, "85 inside 130/85 and 185 is not a pulse of 85"
    assert answers(note, {"nothing_asks_this": {"section": "vital_signs", "take": "value"}},
                   fields, said) == {}, "a rule for a question the form does not ask is dropped"
    assert answers(note, {"drug": {"section": "prescribed_medications", "take": "name",
                                   "rows": True}},
                   [{"link_id": "drug", "type": "choice"}], said) == {}, \
        "a row rule on a question that is in no repeating group places nothing"
    assert answers(None, reads, fields, said) == {}, "no note is nothing, not an error"
    assert answers(note, reads, fields, "") == {}, "no transcript, no evidence, no answers"
    # the code the service attached is never an answer
    assert not any("locale" in a["value"] for a in got.values()), got

    print("ok api.structured")


if __name__ == "__main__":
    demo()
