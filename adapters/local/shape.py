"""Payload to rows. The one place adapter 0 knows what a questionnaire means.

Why it is here and not in a declaration
---------------------------------------
An operation declares `writes: [observation]`. Nothing yet declares which
answer becomes which column, so kernel/proposals.py hands the whole confirmed
payload to Store.write and says, correctly, that the mapping is the adapter's
knowledge. This is that knowledge, in one file, for one adapter. Adapter 1
will have its own and it will look different, because CARE's REST API takes
questionnaire responses and not rows.

What would replace it: a `records:` block on the operation atom in the same
query grammar the state rules use. That is a declaration change and a lint
change, so it belongs to the build agent, not to an adapter.

Honest limits
-------------
- The observation table below repeats the units that questionnaires already
  carry under styling_metadata.phc.unit. It repeats them because Store.write
  receives a payload and not the operation that produced it, so there is no
  questionnaire to read. That is a gap in the Store protocol, reported rather
  than patched around.
- A payload key nothing here recognises is dropped, not stored. Dropping a
  clinical value silently is the worst failure mode in this file, so every
  operation in the PHC bundle has a check in tests/test_store.py that the row
  it writes is not empty.
"""
from __future__ import annotations

import json

# link_id -> (category, unit). Vitals are observations; a lab value is not,
# it is a diagnostic report, because that is what the lab atom declares.
OBSERVATION_CODES = {
    "systolic": ("vital-signs", "mm[Hg]"),
    "diastolic": ("vital-signs", "mm[Hg]"),
    "pulse": ("vital-signs", "/min"),
    "spo2": ("vital-signs", "%"),
    "weight": ("vital-signs", "kg"),
    "temperature": ("vital-signs", "Cel"),
}

# Free text answers that belong in a clinical note, in the order they read.
NOTE_KEYS = ("history", "examination", "assessment", "plan", "narrative")

PATIENT_COLUMNS = ("name", "age", "sex", "phone", "village", "category", "abha_number")


def shape(resource, payload, *, thread, store):
    """The rows one resource takes from this payload. May be empty."""
    builder = BUILDERS.get(resource)
    if builder is None:
        # A resource nothing reads yet: writing an empty row would be a lie
        # about what happened, so nothing is written.
        return []
    return [row for row in builder(dict(payload or {}), thread, store) if row]


def _items(payload, key):
    """A repeating structured answer as a list of dicts. A bare string counts."""
    value = payload.get(key)
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    return [i if isinstance(i, dict) else {"code": str(i)} for i in items]


def _patient(payload, thread, store):
    fields = {k: payload[k] for k in PATIENT_COLUMNS if payload.get(k) not in (None, "")}
    if not fields:
        return []
    existing = store.select("patient", thread=thread, where={}, fields=["id"], limit=1)
    if existing:
        # Registration made the row; linking an ABHA updates it. Which one
        # this is does not need the operation's name, only the thread's state.
        return [dict(fields, id=existing[0]["id"])]
    return [fields]


def _encounter(_payload, thread, _store):
    # The encounter row is the thread and already exists; documenting against
    # it moves it out of "arrived".
    return [{"id": thread, "status": "in_progress"}]


def _observation(payload, _thread, _store):
    rows = []
    for code, (category, unit) in OBSERVATION_CODES.items():
        value = payload.get(code)
        if value in (None, ""):
            continue
        rows.append({"category": category, "code": code, "value": value, "unit": unit})
    return rows


def _notes(payload, _thread, _store):
    text = "\n\n".join("%s: %s" % (k.title(), payload[k])
                       for k in NOTE_KEYS if payload.get(k))
    return [{"text": text}] if text else []


def _condition(payload, _thread, _store):
    return [{"code": i.get("code") or i.get("text") or "",
             "verification_status": "confirmed"} for i in _items(payload, "diagnosis")]


def _service_request(payload, _thread, _store):
    return [{"code": i.get("code") or i.get("test") or "", "status": "active"}
            for i in _items(payload, "investigations")]


def _medication_request(payload, _thread, _store):
    return [{"medication": i.get("medication") or i.get("code") or "",
             "dosage_instruction": i.get("dosage_instruction") or i.get("dose") or "",
             "status": "active"} for i in _items(payload, "medications")]


def _medication_dispense(payload, _thread, _store):
    return [{"medication": i.get("medication") or i.get("code") or "",
             "quantity": str(i.get("quantity") or 1),
             "status": "completed"} for i in _items(payload, "dispenses")]


def _inventory_item(payload, _thread, _store):
    return [{"code": i.get("medication") or i.get("code") or "",
             "quantity": "-%s" % (i.get("quantity") or 1), "status": "issued"}
            for i in _items(payload, "dispenses")]


def _diagnostic_report(payload, _thread, _store):
    if not payload.get("analyte"):
        return []
    # preliminary until lab.result.validate finalises it: the lab.validated
    # flag reads status = final and must not be true the moment a result lands.
    return [{"code": payload["analyte"], "status": "preliminary",
             "conclusion": ("%s %s" % (payload.get("value"),
                                       payload.get("unit") or "")).strip()}]


def _specimen(payload, _thread, _store):
    return [{"code": payload["analyte"], "status": "available"}] \
        if payload.get("analyte") else []


def _questionnaire_response(payload, _thread, _store):
    return [{"questionnaire": payload.get("questionnaire"),
             "payload": json.dumps(payload, sort_keys=True)}]


BUILDERS = {
    "patient": _patient,
    "encounter": _encounter,
    "observation": _observation,
    "notes": _notes,
    "condition": _condition,
    "service_request": _service_request,
    "medication_request": _medication_request,
    "medication_dispense": _medication_dispense,
    "inventory_item": _inventory_item,
    "diagnostic_report": _diagnostic_report,
    "specimen": _specimen,
    "questionnaire_response": _questionnaire_response,
}
