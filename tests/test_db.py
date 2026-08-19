"""The database contract stages 04a and 06 will depend on.

WAL mode matters more than it looks. Stage 04b fires concurrent webhook
deliveries at one payment; without WAL, SQLite raises "database is locked" under
concurrent writes, and that error is indistinguishable at a glance from a real
state-machine bug. Turning it on here means a lock error later is a genuine
finding.
"""

import sqlite3

from service import db


def test_connection_uses_wal_mode(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    assert mode.lower() == "wal"


def test_init_creates_the_three_tables(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(path)

    conn = db.connect(path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()

    tables = {row[0] for row in rows}
    assert {"payments", "processed_events", "idempotency_keys"} <= tables


def test_processed_events_rejects_duplicate_event_id(tmp_path):
    """Webhook dedupe leans on this constraint, not on a check-then-insert."""
    path = tmp_path / "test.db"
    db.init_db(path)
    conn = db.connect(path)

    conn.execute("INSERT INTO processed_events (event_id) VALUES ('evt_1')")
    conn.commit()

    try:
        conn.execute("INSERT INTO processed_events (event_id) VALUES ('evt_1')")
        conn.commit()
        duplicate_allowed = True
    except sqlite3.IntegrityError:
        duplicate_allowed = False
    finally:
        conn.close()

    assert not duplicate_allowed


def test_idempotency_keys_rejects_duplicate_key(tmp_path):
    """Stage 06's concurrent case is correct because of this constraint.

    Insert-first-and-let-the-constraint-arbitrate has no window; a
    check-then-insert does.
    """
    path = tmp_path / "test.db"
    db.init_db(path)
    conn = db.connect(path)

    conn.execute(
        "INSERT INTO idempotency_keys (key, request_hash) VALUES ('k1', 'h1')"
    )
    conn.commit()

    try:
        conn.execute(
            "INSERT INTO idempotency_keys (key, request_hash) VALUES ('k1', 'h2')"
        )
        conn.commit()
        duplicate_allowed = True
    except sqlite3.IntegrityError:
        duplicate_allowed = False
    finally:
        conn.close()

    assert not duplicate_allowed


def test_init_creates_the_anomalies_table(tmp_path):
    """Illegal transitions are persisted, not just logged (D-015).

    A payment can accumulate more than one, and an on-call engineer needs to
    query them after a restart, so they get a table rather than a column.
    """
    path = tmp_path / "test.db"
    db.init_db(path)

    conn = db.connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(anomalies)")}
    conn.close()

    assert {"event_id", "payment_id", "from_state", "to_state", "detected_at"} <= columns
