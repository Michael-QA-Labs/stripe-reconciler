"""The schema is created on every boot, not once by hand.

Render's free tier wipes the filesystem on every spin-down and redeploy
(D-005), so a database created once by a manual step would vanish. Creating it
at startup is the only placement that survives that, and CREATE TABLE IF NOT
EXISTS makes running it every boot free.
"""

from fastapi.testclient import TestClient

from service import config, db, main


def test_startup_creates_the_schema(tmp_path, monkeypatch):
    path = tmp_path / "startup.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(path))

    # Entering the context manager is what runs the app's lifespan.
    with TestClient(main.app):
        pass

    conn = db.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    assert {"payments", "processed_events", "idempotency_keys", "anomalies"} <= tables
