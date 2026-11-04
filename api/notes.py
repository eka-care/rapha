"""The notes a visit has had written, kept beside the visit.

A recording is written up in one of Eka's templates -- the default prescription
note, say -- and the note has to outlive the recording and the person who made
it. The nurse records the vitals and the doctor records the consultation, and
what the next person opens is ONE note with both of them in it, each under
their own name. That is a different life from a scribe session, which is in
memory for a day and is deliberately lost with a restart: a transcript is
somebody's consultation and costs the record nothing to lose, but a note a
colleague is going to read next is a thing a clinician said, and it stays.

WORDS, NOT A RECORD. Nothing here is a row of the patient's record, nothing
reads it back into a form, and no value in a note reaches one without a person
typing it. It is a text a template wrote, kept for people to read.

It is its own table in the same database file, opened on its own connection
and not through the shared store: the Go engine does not serve the scribe, so
it has no business with this table and never touches it. Being in that file is
what keeps it under the same ignore rules, backups and access as the records
it sits beside -- a note is as sensitive as they are, and a second file beside
the database is one more place for a patient's words to be left lying around.
"""
import os
import sqlite3
import time
import uuid

_COLUMNS = ("id TEXT PRIMARY KEY, thread TEXT NOT NULL, template TEXT NOT NULL, "
            "title TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, "
            "session TEXT NOT NULL, text TEXT NOT NULL, UNIQUE (session, template)")


def _db(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS scribe_note (%s)" % _COLUMNS)
    return db


def keep(path, *, thread, template, title, actor, session, text, at=None):
    """Add one section to this visit's note in this template.

    Idempotent on (session, template): a poll and a webhook both collect the
    same recording, and the second must not write the second copy.
    Returns True when this call is the one that kept it.
    """
    text = (text or "").strip()
    if not text:
        return False
    at = at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db = _db(path)
    try:
        with db:
            cur = db.execute(
                "INSERT OR IGNORE INTO scribe_note (id, thread, template, title, actor, at, "
                "session, text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("nt-" + uuid.uuid4().hex[:12], thread, template, title, actor, at,
                 session, text))
        return cur.rowcount == 1
    finally:
        db.close()


def for_thread(path, thread):
    """[{template, title, sections: [{id, actor, at, text}]}], templates in the
    order they were first written and sections oldest first, so a note reads
    as the visit did: the nurse, then the doctor."""
    db = _db(path)
    try:
        rows = db.execute(
            "SELECT id, template, title, actor, at, text FROM scribe_note "
            "WHERE thread = ? ORDER BY at, rowid", (thread,)).fetchall()
    finally:
        db.close()
    out = {}
    for nid, template, title, actor, at, text in rows:
        slot = out.setdefault(template, {"template": template, "title": title, "sections": []})
        slot["sections"].append({"id": nid, "actor": actor, "at": at, "text": text})
    return list(out.values())
