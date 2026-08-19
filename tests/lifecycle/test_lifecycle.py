"""The five lifecycle steps, against live Stripe test mode.

Every assertion here is on a status the real API returned. Where reality and
docs/transition-table.md disagree, the disagreement is recorded in the stage
RESULT rather than smoothed over.
"""

import pytest

CARD = "pm_card_visa"


@pytest.mark.live
def test_create_leaves_the_intent_awaiting_a_payment_method(payment_intent):
    """A PaymentIntent with no payment method attached cannot go anywhere yet."""
    assert payment_intent.status == "requires_payment_method"


@pytest.mark.live
def test_confirm_succeeds_immediately_with_automatic_capture(stripe_client, payment_intent):
    """Default capture is automatic, so confirming a card settles in one step.

    This is the flow with no requires_capture in it, which is why the capture
    test below has to ask for manual capture explicitly.
    """
    confirmed = stripe_client.v1.payment_intents.confirm(
        payment_intent.id, {"payment_method": CARD}
    )

    assert confirmed.status == "succeeded"


@pytest.mark.live
def test_manual_capture_makes_authorize_and_capture_two_steps(stripe_client):
    """capture_method=manual is what puts a PaymentIntent in requires_capture.

    Stage 02 ranks requires_capture below processing on the strength of the
    documented claim that capturing moves the intent onward. This test is where
    that ordering meets the real API.
    """
    intent = stripe_client.v1.payment_intents.create(
        {
            "amount": 1000,
            "currency": "usd",
            "payment_method_types": ["card"],
            "capture_method": "manual",
        }
    )

    authorized = stripe_client.v1.payment_intents.confirm(
        intent.id, {"payment_method": CARD}
    )
    assert authorized.status == "requires_capture"

    captured = stripe_client.v1.payment_intents.capture(intent.id)
    assert captured.status == "succeeded"


@pytest.mark.live
def test_cancel_moves_an_unconfirmed_intent_to_canceled(stripe_client, payment_intent):
    """Cancellation is terminal, which is what makes it absorbing in the table."""
    canceled = stripe_client.v1.payment_intents.cancel(payment_intent.id)

    assert canceled.status == "canceled"


@pytest.mark.live
def test_refund_does_not_change_the_payment_intent_status(stripe_client, payment_intent):
    """The reason `refunded` is our state and not Stripe's.

    Refunding a succeeded payment leaves the PaymentIntent reading `succeeded`.
    The refund is visible on the Charge, not on the intent. Since D-006 makes
    the PaymentIntent canonical for us, a refund has nowhere to land unless we
    add a state for it, which is exactly what the transition table does.
    """
    succeeded = stripe_client.v1.payment_intents.confirm(
        payment_intent.id, {"payment_method": CARD}
    )
    assert succeeded.status == "succeeded"

    refund = stripe_client.v1.refunds.create({"payment_intent": payment_intent.id})
    assert refund.status == "succeeded"

    after = stripe_client.v1.payment_intents.retrieve(payment_intent.id)
    assert after.status == "succeeded"

    charge = stripe_client.v1.charges.retrieve(after.latest_charge)
    assert charge.refunded is True
