"""All four endpoints exist from day one, and the unbuilt ones say so.

Stubs return 501 rather than 200-with-nothing. A stub that returns success is
the kind of thing a later suite passes against without noticing.
"""

from fastapi.testclient import TestClient

from service import main
from service.main import app

client = TestClient(app)


def test_payments_endpoint_is_implemented(monkeypatch):
    """Stage 06 redeemed the 501 this test used to assert.

    The creation seam is substituted rather than called. Without that this file
    would make a real Stripe call on every plain `pytest`, and a default run is
    supposed to need no network and no key.
    """
    monkeypatch.setattr(
        main,
        "_create_payment_intent",
        lambda amount, currency: {"id": "pi_stub", "status": "requires_payment_method",
                                  "amount": amount},
    )

    response = client.post("/payments", json={"amount": 1000})

    assert response.status_code == 200
    assert response.json()["id"] == "pi_stub"


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
