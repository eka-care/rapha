"""Generate the dev harness's fixtures from the real derivation rules.

The frontend must never reimplement visible() or actions(). Two copies of the
ordering rules drift, and the copy that drifts is the one a pharmacist sees.
So the UI renders whatever the backend hands it, and for the harness, which has
no backend, we precompute exactly what the backend would say. This file is the
only place the two are joined, and it is generated.

Run: python3 scripts/gen-fixtures.py
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

from care_phc.thread import Snapshot, actions, derive, station  # noqa: E402
from catalogue import vocab  # noqa: E402

CAT = json.loads((pathlib.Path(__file__).parents[1] / "catalogue" / "catalogue.json").read_text())
OUT = pathlib.Path(__file__).parents[1] / "care_phc_fe" / "src" / "fixtures.json"

PATIENTS = [
    {"name": "Lakshmi Devi", "age": 52, "sex": "F", "village": "Yadiki",
     "note": "Hypertension, 4 years", "snapshot": {"patient_exists": True}},
    {"name": "Lakshmamma G", "age": 61, "sex": "F", "village": "Tadipatri",
     "note": "Osteoarthritis. Shares a household phone",
     "team": [["SM", "Suneetha M", "Vitals"]],
     "audit": [["09:12", "phc.op.patient-register", "Lalitha G"],
               ["09:31", "phc.op.vitals-record", "Suneetha M"]],
     "snapshot": {"patient_exists": True, "vitals_observations": 4,
                  "stored": ["vitals.flagged"]}},
    {"name": "Lakshman Rao", "age": 38, "sex": "M", "village": "Yadiki",
     "note": "Type 2 diabetes. Sulfa allergy",
     "team": [["SM", "Suneetha M", "Vitals"], ["AR", "Dr Anitha R", "Treating doctor"]],
     "audit": [["08:54", "phc.op.patient-register", "Lalitha G"],
               ["08:58", "phc.op.abha-link", "Lalitha G"],
               ["09:20", "phc.op.vitals-record", "Suneetha M"],
               ["09:41", "phc.op.consult-document", "Dr Anitha R"],
               ["09:46", "phc.op.rx-prescribe", "Dr Anitha R"]],
     "snapshot": {"patient_exists": True, "abha_number": "54-9911-2233-0001",
                  "vitals_observations": 4, "consult_notes": 1,
                  "active_medication_requests": 2, "prescribed_lines": 2}},
    {"name": "Sarojamma K", "age": 29, "sex": "F", "village": "Peddavadugur",
     "note": "Pregnancy, 26 weeks. Anaemia",
     "team": [["SM", "Suneetha M", "Vitals"], ["AR", "Dr Anitha R", "Treating doctor"],
              ["KP", "Kiran Kumar P", "Lab"]],
     "audit": [["09:02", "phc.op.patient-register", "Lalitha G"],
               ["09:25", "phc.op.vitals-record", "Suneetha M"],
               ["09:50", "phc.op.consult-document", "Dr Anitha R"],
               ["09:52", "phc.op.lab-order", "Dr Anitha R"]],
     "snapshot": {"patient_exists": True, "abha_number": "21-7788-1122-9090",
                  "vitals_observations": 4, "consult_notes": 1,
                  "service_requests": 1}},
    {"name": "Ramesh Naidu", "age": 44, "sex": "M", "village": "Yadiki",
     "note": "Pulmonary TB, month 3 of 6",
     "snapshot": {"patient_exists": True, "abha_number": "33-4455-6677-8899",
                  "vitals_observations": 4, "consult_notes": 1,
                  "active_medication_requests": 1, "prescribed_lines": 3,
                  "dispensed_lines": 3}},
]

KEEP = ("id", "tool", "short", "title", "summary", "station", "capability", "instrument",
        "irreversibility", "verified", "preconditions", "kind")

# Verbatim from the prototype. These are the standing constraint for each cadre,
# shown on the patient screen rather than buried in documentation nobody opens.
NUDGES = {
    "frontdesk": "Search is the default surface. ABHA creation is irreversible, "
                 "so the confirm is explicit and un-prefilled, never automatic.",
    "nurse": "Vitals are discrete values. Unedited speech recognition shows about "
             "7.4% error, deletions and substitutions dominating. Form or device, "
             "never ambient scribe.",
    "mo": "Read scope is the widest of any cadre; write is confined to "
          "documentation, prescription, orders and referral. No master access.",
    "lab": "Manual entry uses per-analyte range validation. Out of range blocks "
           "the commit and requires an override with a reason.",
    "lab_incharge": "Releasing a result is a separate capability from entering "
                    "one, and the person who entered it does not hold it.",
    "pharmacist": "Dispense stays blocked until a prescription is confirmed. The "
                  "precondition lives in the operation catalogue, not the UI.",
    "asha": "Narrative goes to scribe; assessment items go to a form. Scoring is "
            "computed by rule, never model generated.",
    "anm": "Narrative goes to scribe; assessment items go to a form. Scoring is "
           "computed by rule, never model generated.",
    "cho": "Prescribing here is bounded by an approved formulary and protocol "
           "set. That bound is declared and is not yet enforced.",
}

# The agent explains the ordering. It does not decide it, per addendum D.2.
AGENT = {
    "reception": "Patient opened. Nothing recorded for this visit yet.",
    "nurse": "Registered and in the queue. Vitals are the next thing.",
    "doctor": "Vitals are in. Documentation is unblocked.",
    "lab": "An investigation is on the lab worklist. Until a result exists, the "
           "lab station stays blocked for this patient.",
    "pharmacy": "Prescription confirmed. Pharmacy is unblocked.",
    None: "Nothing outstanding. The thread stays open as this patient's record.",
}


def main():
    out = {"bundles": {}, "capabilities": sorted(vocab.CAPABILITIES), "patients": []}
    for bundle, caps in vocab.BUNDLES.items():
        out["bundles"][bundle] = sorted(caps)

    for p in PATIENTS:
        snap = dict(p["snapshot"])
        snap["stored"] = frozenset(snap.get("stored", ()))
        flags = derive(Snapshot(**snap))
        entry = {k: p[k] for k in ("name", "age", "sex", "village", "note")}
        entry["flags"] = sorted(flags)
        entry["station"] = station(flags)
        entry["team"] = p.get("team", [])
        entry["audit"] = p.get("audit", [])
        entry["agent"] = AGENT[entry["station"]]
        entry["nudges"] = NUDGES
        entry["actions"] = {
            bundle: [{k: op[k] for k in KEEP}
                     for op in actions(CAT, flags, set(caps))]
            for bundle, caps in vocab.BUNDLES.items()
        }
        out["patients"].append(entry)

    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"ok   {len(PATIENTS)} patients x {len(vocab.BUNDLES)} bundles -> {OUT.name}")
    for p in out["patients"]:
        mo = [a["title"] for a in p["actions"]["mo"]]
        ph = [a["title"] for a in p["actions"]["pharmacist"]]
        print(f"     {p['name']:<16} at {str(p['station']):<10} "
              f"MO:{len(mo)} pharmacist:{len(ph)} {'<- dispense live' if ph else ''}")


if __name__ == "__main__":
    main()
