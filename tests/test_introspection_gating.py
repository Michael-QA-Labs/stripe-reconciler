"""The test-only introspection endpoint must not exist outside testing.

GET /test/payments/{id} lets the suite read service state without touching the
database directly. That convenience is also a hole if it ships live, so the gate
gets a test from the first day rather than an assumption.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


def _client_with_testing(monkeypatch, value, tmp_path):
    """Rebuild the app with TESTING set, since routes are registered at import.

    The endpoint reads the database from stage 04a onward, so it gets a real
    but empty one. The gate being tested is whether the route exists at all,
    which is unrelated to what it would find.
    """
    if value is None:
        monkeypatch.delenv("TESTING", raising=False)
    else:
        monkeypatch.setenv("TESTING", value)

    import service.config
    import service.db
    import service.main

    importlib.reload(service.config)
    importlib.reload(service.main)

    monkeypatch.setattr(service.config, "DATABASE_PATH", str(tmp_path / "gating.db"))
    service.db.init_db()

    return TestClient(service.main.app)


def test_introspection_404s_when_testing_unset(monkeypatch, tmp_path):
    client = _client_with_testing(monkeypatch, None, tmp_path)
    assert client.get("/test/payments/1").status_code == 404


@pytest.mark.parametrize("value", ["false", "False", "0", ""])
def test_introspection_404s_when_testing_is_not_true(monkeypatch, tmp_path, value):
    """Anything other than a clear yes must leave the endpoint closed."""
    client = _client_with_testing(monkeypatch, value, tmp_path)
    assert client.get("/test/payments/1").status_code == 404


def test_introspection_available_when_testing_true(monkeypatch, tmp_path):
    client = _client_with_testing(monkeypatch, "true", tmp_path)
    # 404 here would mean the route is missing; the unknown id yields 404 too,
    # so assert on a known-absent payment returning the *route's* 404 body.
    response = client.get("/test/payments/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "payment not found"
