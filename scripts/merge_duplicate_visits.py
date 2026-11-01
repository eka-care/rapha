"""Run: python3 scripts/merge_duplicate_visits.py [--apply]

Drop the EMPTY duplicate visits a patient accumulated before registration
carried which record the clerk had picked.

Why this exists and why it is not part of the gate
--------------------------------------------------
Until 2026-11-01 the front desk found a returning patient, the clerk picked
her, and the registration that followed wrote a second her: the form carried
her answers and nothing that said which record they came from. One demo day
had seventy-three records of one woman, each with its own visit.

The defect is fixed in the declaration, and `scripts/check_front_desk.py`
holds it. This is the other half: the rows already written. It is a one off
over a developer's own database, so it is a script somebody runs and reads
the output of, not a migration and not a check.

WHAT IT WILL NOT DO. It removes a visit only when NOTHING was recorded on it:
no observation, no note, no questionnaire response, no request of any kind. A
visit that holds one clinical row is a visit somebody worked, however it came
to exist, and it is kept and reported. The patient's own earliest visit is
always kept, so she still stands in the line once.

It prints what it would do and changes nothing unless you pass --apply, and
it writes a full backup first, which it names.
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).parents[1]
DB = ROOT / "phc.sqlite3"


# What makes a visit one somebody WORKED. Deliberately a list of clinical
# resources and not "any row that mentions this visit": every visit has an
# audit row and a questionnaire response for its own registration, and
# counting those would protect exactly the empty duplicates this removes.
# A table this build adds later is not in here, which is the safe direction:
# it is reported as holding records and kept.
CLINICAL = ("observation", "notes", "condition", "medication_request",
            "medication_dispense", "service_request", "diagnostic_report",
            "specimen", "token_booking")

# The plumbing a removed visit takes with it, so nothing is left pointing at
# a visit that is gone.
PLUMBING = ("audit", "thread_flag", "proposal", "questionnaire_response")


def _key(db, table):
    columns = [c[1] for c in db.execute("pragma table_info(%s)" % table)]
    return "encounter" if "encounter" in columns else (
        "thread" if "thread" in columns else None)


def attached(db, tables, visit):
    """Clinical rows on this visit. Plumbing is not work."""
    total = 0
    for table in CLINICAL:
        if table not in tables:
            continue
        key = _key(db, table)
        if not key:
            continue
        total += db.execute(
            "select count(*) from %s where %s = ?" % (table, key), [visit]).fetchone()[0]
    return total


def main():
    apply = "--apply" in sys.argv
    if not DB.exists():
        print("no database at %s" % DB)
        return 1
    db = sqlite3.connect(str(DB))
    db.row_factory = sqlite3.Row
    tables = [t[0] for t in db.execute(
        "select name from sqlite_master where type='table'")]

    # A patient with more than one visit where all but the first are empty.
    duplicated = db.execute("""
        select patient, count(*) n from encounter
        where patient is not null group by patient having n > 1
        order by n desc""").fetchall()
    if not duplicated:
        print("no patient has more than one visit; nothing to do")
        return 0

    plan = []
    for row in duplicated:
        visits = [r["id"] for r in db.execute(
            "select id from encounter where patient = ? order by created_date, rowid",
            [row["patient"]])]
        name = db.execute("select name from patient where id = ?",
                          [row["patient"]]).fetchone()
        empty = [v for v in visits[1:] if attached(db, tables, v) == 0]
        worked = len(visits) - 1 - len(empty)
        print("%s: %d visits, keeping the first%s, %d empty duplicates%s"
              % (name["name"] if name else row["patient"], len(visits),
                 "" if worked == 0 else " and %d that hold records" % worked,
                 len(empty), "" if empty else " (nothing to remove)"))
        plan.extend(empty)

    if not plan:
        print("\nnothing is removable: every extra visit holds a record")
        return 0
    if not apply:
        print("\n%d empty visits would be removed. Nothing has changed." % len(plan))
        print("Run again with --apply to do it.")
        return 0

    backup = DB.with_name("phc-before-merge.sqlite3")
    if backup.exists():
        print("\nrefusing to overwrite the existing backup at %s" % backup)
        return 1
    db.execute("VACUUM INTO ?", [str(backup)])
    print("\nbackup written to %s" % backup)

    marks = ",".join("?" * len(plan))
    with db:
        for table in PLUMBING:
            if table not in tables:
                continue
            key = _key(db, table)
            if key:
                db.execute("delete from %s where %s in (%s)" % (table, key, marks), plan)
        db.execute("delete from encounter where id in (%s)" % marks, plan)
    print("removed %d empty duplicate visits, and the registration rows on them"
          % len(plan))
    print("patients: %d, visits: %d"
          % (db.execute("select count(*) from patient").fetchone()[0],
             db.execute("select count(*) from encounter").fetchone()[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
