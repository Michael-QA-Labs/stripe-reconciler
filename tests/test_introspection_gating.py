"""The test-only introspection endpoint must not exist outside testing.

GET /test/payments/{id} lets the suite read service state without touching the
database directly. That convenience is also a hole if it ships live, so the gate
gets a test from the first day rather than an assumption.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


def _client_with_testing(monkeypatch, value):
    """Rebuild the app with TESTING set, since routes are registered at import."""
    if value is None:
        monkeypatch.delenv("TESTING", raising=False)
    else:
        monkeypatch.setenv("TESTING", value)

    import service.config
    import service.main

    importlib.reload(service.config)
    importlib.reload(service.main)
    return TestClient(service.main.app)


def test_introspection_404s_when_testing_unset(monkeypatch):
    client = _client_with_testing(monkeypatch, None)
    assert client.get("/test/payments/1").status_code == 404


@pytest.mark.parametrize("value", ["false", "False", "0", ""])
def test_introspection_404s_when_testing_is_not_true(monkeypatch, value):
    """Anything other than a clear yes must leave the endpoint closed."""
    client = _client_with_testing(monkeypatch, value)
    assert client.get("/test/payments/1").status_code == 404


def test_introspection_available_when_testing_true(monkeypatch):
    client = _client_with_testing(monkeypatch, "true")
    # 404 here would mean the route is missing; the unknown id yields 404 too,
    # so assert on a known-absent payment returning the *route's* 404 body.
    response = client.get("/test/payments/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "payment not found"
