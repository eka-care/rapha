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
     "snapshot": {"patient_exists": True, "vitals_observations": 4,
                  "stored": ["vitals.flagged"]}},
    {"name": "Lakshman Rao", "age": 38, "sex": "M", "village": "Yadiki",
     "note": "Type 2 diabetes. Sulfa allergy",
     "snapshot": {"patient_exists": True, "abha_number": "54-9911-2233-0001",
                  "vitals_observations": 4, "consult_notes": 1,
                  "active_medication_requests": 2, "prescribed_lines": 2}},
    {"name": "Sarojamma K", "age": 29, "sex": "F", "village": "Peddavadugur",
     "note": "Pregnancy, 26 weeks. Anaemia",
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

KEEP = ("id", "tool", "title", "summary", "station", "capability", "instrument",
        "irreversibility", "verified", "preconditions", "kind")


def main():
    out = {"bundles": {}, "patients": []}
    for bundle, caps in vocab.BUNDLES.items():
        out["bundles"][bundle] = sorted(caps)

    for p in PATIENTS:
        snap = dict(p["snapshot"])
        snap["stored"] = frozenset(snap.get("stored", ()))
        flags = derive(Snapshot(**snap))
        entry = {k: p[k] for k in ("name", "age", "sex", "village", "note")}
        entry["flags"] = sorted(flags)
        entry["station"] = station(flags)
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
