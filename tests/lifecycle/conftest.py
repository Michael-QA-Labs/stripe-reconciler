"""Live Stripe test mode. No receiver code is involved in this directory.

These tests talk to Stripe directly. That is the point: stage 02's transition
table was written from documentation, and this suite is the first contact with
what the API actually returns. A mismatch here is a finding, not something to
quietly accommodate.
"""

import pytest
from stripe import StripeClient

from service import config


@pytest.fixture(scope="session")
def stripe_client():
    """A client pinned to the API version the transition table was written for.

    Without the pin the SDK follows the account's default version, so these
    tests could pass against a version the table never described. Pinning is the
    whole reason STRIPE_API_VERSION is a literal constant.
    """
    if not config.STRIPE_SECRET_KEY:
        pytest.skip("STRIPE_SECRET_KEY is not set")

    return StripeClient(
        config.STRIPE_SECRET_KEY,
        stripe_version=config.STRIPE_API_VERSION,
    )


@pytest.fixture
def payment_intent(stripe_client):
    """An unconfirmed card PaymentIntent, fresh per test.

    Each test creates its own so a failure cannot cascade into the next one.
    Objects are deliberately left behind: the stage's human check is opening the
    dashboard and finding them in the states these tests asserted.
    """
    return stripe_client.v1.payment_intents.create(
        {"amount": 1000, "currency": "usd", "payment_method_types": ["card"]}
    )
