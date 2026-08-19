"""All four endpoints exist from day one, and the unbuilt ones say so.

Stubs return 501 rather than 200-with-nothing. A stub that returns success is
the kind of thing a later suite passes against without noticing.
"""

from fastapi.testclient import TestClient

from service.main import app

client = TestClient(app)


def test_payments_endpoint_exists_and_is_not_implemented():
    response = client.post("/payments", json={"amount": 1000})
    assert response.status_code == 501


def test_webhook_endpoint_rejects_an_unsigned_request():
    """Implemented at stage 04a, so it no longer stubs. It refuses instead.

    An unsigned body is the cheapest proof the front door is actually locked.
    The full signature suite lives in tests/webhook/test_signature.py.
    """
    response = client.post("/webhook", content=b"{}")
    assert response.status_code == 400


def test_unknown_route_is_404_not_501():
    """Guards against a catch-all that would make the 501s meaningless."""
    assert client.post("/nope").status_code == 404
