"""Which PaymentIntent an event belongs to depends on the event type.

Verified against a real charge.refunded event from the sandbox: its
data.object is a Charge, and the PaymentIntent id sits at
data.object.payment_intent, not data.object.id. Treating every event uniformly
would write state against a charge id and create phantom payment rows.
"""

from service.webhook import payment_intent_id_from

from tests.webhook.conftest import charge_object, payment_intent_object, session_object


def _event(obj):
    return {"id": "evt_1", "type": "x", "data": {"object": obj}}


def test_payment_intent_events_use_the_object_id():
    assert payment_intent_id_from(_event(payment_intent_object("pi_9"))) == "pi_9"


def test_charge_events_use_the_payment_intent_field():
    """Confirmed empirically: data.object is a charge, the intent id is a field on it."""
    assert payment_intent_id_from(_event(charge_object("pi_9"))) == "pi_9"


def test_checkout_session_events_use_the_payment_intent_field():
    assert payment_intent_id_from(_event(session_object("pi_9"))) == "pi_9"


def test_a_session_without_a_payment_intent_resolves_to_nothing():
    """Not every Checkout Session has one. That is a skip, not an exception."""
    session = session_object()
    session["payment_intent"] = None

    assert payment_intent_id_from(_event(session)) is None
