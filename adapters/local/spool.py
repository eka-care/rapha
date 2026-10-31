"""kernel.contracts.Spool over a SQLite file, and a directory of recordings.

Its own file and its own database, beside the Store adapter rather than inside
it. Three reasons, in increasing order of how much they matter:

- A recording is a blob and `Store.write` takes a mapping.
- An outbox row is not clinical state, so it would need a CARE resource name
  for a thing no CARE resource corresponds to.
- An outbox must survive the system of record being unreachable, which is the
  whole point of having one. Keeping it inside somebody else's record makes it
  empty exactly when it is needed. The second adapter this repository had was
  a REST client over CARE; an outbox behind that protocol would have gone when
  it did.

The one subtle method is `claim`, and the subtlety is durability rather than
locking. `UPDATE ... WHERE state = 'ready'` is a single statement and the
connection is in autocommit, so the move from ready to sending is on disk
before the method returns. That is what makes "a crash between taking an item
and sending it loses nothing" true: the row is `sending` and nothing can
mistake it for untried work. With WAL and the default synchronous=NORMAL a
committed transaction survives a process crash, which is the failure this
guards against; it is a power cut that needs synchronous=FULL, and that is a
deployment's decision about its own hardware rather than this file's.

`rowcount` on that UPDATE is also the compare-and-set: two pumps racing for one
item both run the statement, and exactly one of them changes a row. The loser
gets None and moves on. scripts/check_queues.py runs four threads at one item
and asserts one claim.

Run: python3 -m adapters.local.spool
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid

from kernel.contracts import QUEUE_KINDS, QUEUE_STATES, QueueItem

# The row, in order. The dataclass is the authority on what a queued item is,
# so this is asserted against its fields rather than maintained beside them:
# a field added there and forgotten here is a column that silently never
# persists, which is the worst kind of bug this file could have.
COLUMNS = ("id", "kind", "key", "thread", "operation", "capability",
           "facility", "created_at", "actor", "blob", "state", "attempts",
           "last_error", "claimed_at", "sent_at", "receipt")

# `key` and `state` are not SQL keywords in SQLite but `key` reads badly
# unquoted, and every identifier here is quoted for the same reason the Store
# adapter validates its own: a column name that reaches SQL unchecked is one
# edit away from being a caller's string.
TABLE = "outbox"

INTS = ("attempts",)


class SqliteSpool:
    """kernel.contracts.Spool over a SQLite file. ":memory:" for a test."""

    def __init__(self, path: str = ":memory:"):
        # The same trick the Store adapter uses and for the same reason: a
        # plain ":memory:" database is private to one connection, so a second
        # thread would open an empty one and a race check would pass for the
        # wrong reason.
        self._uri = path == ":memory:"
        self.path = ("file:spool-%s?mode=memory&cache=shared" % uuid.uuid4().hex
                     if self._uri else path)
        self._local = threading.local()
        self._keepalive = self.db
        cols = ", ".join(
            '"%s" %s%s' % (c, "INTEGER" if c in INTS else "TEXT",
                           " PRIMARY KEY" if c == "id" else "")
            for c in COLUMNS)
        self.db.execute('CREATE TABLE IF NOT EXISTS "%s" (%s)' % (TABLE, cols))
        # Every read is by state, and a clinic's outbox after a bad week is the
        # one table here that grows without being cleared.
        self.db.execute('CREATE INDEX IF NOT EXISTS outbox_state '
                        'ON "%s" (state, created_at)' % TABLE)

    @property
    def db(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, uri=self._uri, timeout=30)
            conn.row_factory = sqlite3.Row
            # Autocommit. Every method here is one statement, and one
            # statement committing by itself is exactly the durability
            # `claim` needs: there is no multi row invariant to hold open a
            # transaction for.
            conn.isolation_level = None
            if not self._uri:
                conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    # ----------------------------------------------------------------- reads

    def get(self, item_id):
        row = self.db.execute('SELECT * FROM "%s" WHERE id = ?' % TABLE,
                              [item_id]).fetchone()
        return _item(row) if row else None

    def items(self, *, state=None, kind=None, limit=500):
        sql, params = [], []
        if state is not None:
            _one_of(state, QUEUE_STATES, "state")
            sql.append("state = ?")
            params.append(state)
        if kind is not None:
            _one_of(kind, QUEUE_KINDS, "kind")
            sql.append("kind = ?")
            params.append(kind)
        clause = " AND ".join(sql) or "1=1"
        rows = self.db.execute(
            'SELECT * FROM "%s" WHERE %s ORDER BY created_at, id LIMIT ?'
            % (TABLE, clause), params + [int(limit)]).fetchall()
        return [_item(r) for r in rows]

    # ---------------------------------------------------------------- writes

    def put(self, item):
        _one_of(item.kind, QUEUE_KINDS, "kind")
        _one_of(item.state, QUEUE_STATES, "state")
        self.db.execute(
            'INSERT OR REPLACE INTO "%s" (%s) VALUES (%s)'
            % (TABLE, ", ".join('"%s"' % c for c in COLUMNS),
               ", ".join("?" * len(COLUMNS))),
            [_value(item, c) for c in COLUMNS])

    def claim(self, item_id, *, at):
        """ready -> sending and one more attempt, atomically and durably.

        One statement, so it either happened or it did not, and it is on disk
        when this returns. `rowcount` is the compare-and-set: the pump that
        changed a row owns the item and every other one is told None.
        """
        changed = self.db.execute(
            'UPDATE "%s" SET state = ?, attempts = attempts + 1, '
            'claimed_at = ? WHERE id = ? AND state = ?' % TABLE,
            ["sending", at, item_id, "ready"]).rowcount
        if not changed:
            return None
        return self.get(item_id)

    def settle(self, item_id, *, state, at, receipt="", error=""):
        """End an attempt. `sent_at` is set only by reaching `sent`, so a row
        carrying one is a row something acknowledged; an item that goes back
        to `ready` keeps the previous reason until the next attempt replaces
        it, which is what lets `status()` say why the last one failed."""
        _one_of(state, QUEUE_STATES, "state")
        self.db.execute(
            'UPDATE "%s" SET state = ?, last_error = ?, receipt = ?, '
            'sent_at = CASE WHEN ? = \'sent\' THEN ? ELSE sent_at END '
            'WHERE id = ?' % TABLE,
            [state, str(error or ""), str(receipt or ""), state, at, item_id])

    # ------------------------------------------------------- the bytes
    # Not part of the protocol. The kernel is handed paths and a `delete`
    # callable and never opens a directory itself, so these two are this
    # adapter's own and a spool over object storage would replace them without
    # the kernel noticing.

    def keep(self, item_id, audio, *, root):
        """Write one recording where it waits, owner readable only.

        The filename is the item's opaque id and nothing else. A name carrying
        a patient, a thread or a time of day would put identifiable
        information in a directory listing, which is the one place in this
        design where a file name is as readable as a log line.
        """
        os.makedirs(root, mode=0o700, exist_ok=True)
        path = os.path.join(root, "%s.bin" % item_id)
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle, "wb") as out:
            out.write(audio)
            out.flush()
            # The recording is the one copy there is, so it is on the platter
            # before this returns: the row that names it is about to be
            # written, and a row pointing at a file the page cache lost is
            # exactly the loss this module exists to prevent.
            os.fsync(out.fileno())
        return path

    @staticmethod
    def drop(path):
        """Remove one recording. Missing is success: the only thing this is
        asked for is that the bytes are gone."""
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _one_of(value, allowed, what):
    if value not in allowed:
        raise ValueError("%r is not a %s this outbox knows: %s"
                         % (value, what, list(allowed)))


def _value(item, column):
    raw = getattr(item, column)
    if column in INTS:
        return int(raw or 0)
    return "" if raw is None else str(raw)


def _item(row):
    got = dict(row)
    return QueueItem(**{c: (int(got[c] or 0) if c in INTS else (got[c] or ""))
                        for c in COLUMNS})


def demo():
    import dataclasses

    # The dataclass is the authority on what a queued item is. A field added
    # there and not here is a column that silently never persists, which is
    # the worst bug this file could have, so the list is held against it by
    # name AND by order rather than maintained beside it.
    assert [f.name for f in dataclasses.fields(QueueItem)] == list(COLUMNS), \
        "QueueItem and COLUMNS have drifted: %s against %s" % (
            [f.name for f in dataclasses.fields(QueueItem)], list(COLUMNS))

    spool = SqliteSpool(":memory:")
    item = QueueItem(id="q-1", kind="audio", key="t-1", thread="enc-1",
                     operation="phc.op.consult-document",
                     capability="encounter.document", facility="all-plugins",
                     created_at="2026-10-31T10:00:00+00:00")
    spool.put(item)
    assert spool.get("q-1") == item, spool.get("q-1")
    assert [i.id for i in spool.items(state="ready")] == ["q-1"]
    assert spool.items(state="sent") == []

    taken = spool.claim("q-1", at="2026-10-31T10:01:00+00:00")
    assert taken.state == "sending" and taken.attempts == 1, taken
    assert spool.claim("q-1", at="later") is None, \
        "an item was claimed twice, so two pumps could both send it"

    spool.settle("q-1", state="sent", at="2026-10-31T10:02:00+00:00",
                 receipt="txn-9")
    row = spool.get("q-1")
    assert row.state == "sent" and row.receipt == "txn-9"
    assert row.sent_at == "2026-10-31T10:02:00+00:00", row

    # A state the outbox does not know is refused rather than written: a typo
    # in a state name would otherwise make an item invisible to every read.
    for bad in ({"state": "done"}, {"state": ""}):
        try:
            spool.settle("q-1", at="now", **bad)
            raise AssertionError("an unknown state was accepted: %s" % bad)
        except ValueError:
            pass

    print("ok   adapters/local spool: a row round trips with every field")
    print("ok   adapters/local spool: one item claims once, however many ask")
    print("ok   adapters/local spool: a state the outbox does not know is refused")


if __name__ == "__main__":
    demo()
