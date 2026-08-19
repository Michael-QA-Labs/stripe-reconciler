"""SQLite access. WAL mode, three tables, no ORM.

SQLite is the source of truth for payment state. Tests never read it directly;
they go through GET /test/payments/{id}, which keeps them decoupled from this
schema and matches how a real team inspects service state.
"""

import sqlite3
from pathlib import Path

from service import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id           TEXT PRIMARY KEY,
    stripe_id    TEXT UNIQUE,
    state        TEXT NOT NULL,
    amount       INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Webhook dedupe. Stripe delivers at least once, so the same event id arrives
-- more than once as a matter of course. The primary key is the dedupe: insert
-- and let the constraint arbitrate, rather than checking then inserting.
CREATE TABLE IF NOT EXISTS processed_events (
    event_id     TEXT PRIMARY KEY,
    received_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Idempotency-Key handling for POST /payments. The primary key is what makes
-- the concurrent case correct rather than merely usually correct.
-- Illegal transitions, persisted rather than only logged (D-015). The only one
-- the table defines is leaving `canceled`, which cannot happen legitimately, so
-- a row here means two payments were conflated, a payload was replayed, or the
-- receiver has a bug. All three are worth finding after a restart.
CREATE TABLE IF NOT EXISTS anomalies (
    event_id     TEXT PRIMARY KEY,
    payment_id   TEXT NOT NULL,
    from_state   TEXT NOT NULL,
    to_state     TEXT NOT NULL,
    detected_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key           TEXT PRIMARY KEY,
    request_hash  TEXT NOT NULL,
    response_json TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | Path | None = None) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
