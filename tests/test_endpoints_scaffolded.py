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


def test_root_redirects_to_the_demo_page():
    """The deployed URL is what someone pastes, so it must not answer an error.

    A named route rather than a mount at /, which would be a catch all and would
    make the 501 and 404 responses above meaningless.
    """
    response = client.get("/", follow_redirects=False)

    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/app/"


def test_the_schema_lists_exactly_the_three_real_routes():
    """D-013 leans on this, and until now nothing enforced it.

    The argument that the introspection gate is structural rather than a status
    code is only as good as the schema staying this small. The root redirect is
    deliberately absent because it is not part of the API surface, and
    /test/payments/{id} is absent because the route is not registered at all
    unless TESTING is true.
    """
    paths = client.get("/openapi.json").json()["paths"]

    assert sorted(paths) == ["/health", "/payments", "/webhook"]
