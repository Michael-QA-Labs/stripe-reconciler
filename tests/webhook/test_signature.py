"""The front door. Four cases from the contract, plus proof the helper is honest.

tests/helpers/signing.py computes the Stripe-Signature header from the
documented scheme rather than by calling into the SDK. That is deliberate: if
the helper used a private SDK function, an SDK upgrade could change both the
helper and the verifier together and the suite would keep passing while
verifying nothing.

So the first test here checks the helper against the real verifier. Everything
after it can then trust the helper.
"""

import json
import math
import time

import pytest
import stripe

from tests.helpers.signing import signature_header

SECRET = "whsec_test_secret_for_local_signing_only"
PAYLOAD = json.dumps({"id": "evt_1", "type": "payment_intent.succeeded"}).encode()


def test_helper_produces_a_header_the_sdk_accepts():
    """Written from the documented scheme, verified against the SDK's verifier."""
    header = signature_header(PAYLOAD, SECRET)

    event = stripe.Webhook.construct_event(PAYLOAD, header, SECRET)

    assert event["id"] == "evt_1"


def test_tampered_body_is_rejected():
    header = signature_header(PAYLOAD, SECRET)

    with pytest.raises(stripe.SignatureVerificationError):
        stripe.Webhook.construct_event(PAYLOAD + b" ", header, SECRET)


def test_tampered_signature_is_rejected():
    header = signature_header(PAYLOAD, SECRET)
    tampered = header[:-1] + ("0" if header[-1] != "0" else "1")

    with pytest.raises(stripe.SignatureVerificationError):
        stripe.Webhook.construct_event(PAYLOAD, tampered, SECRET)


def test_signature_299_seconds_old_is_accepted():
    """Just inside the SDK's 300 second tolerance, confirmed as DEFAULT_TOLERANCE.

    math.ceil, not int. int() truncates downward, so `int(time.time()) - 299`
    signs a timestamp that is really 299 plus the current fraction of a second
    old, up to 299.999. If the clock ticks over before the verifier reads it,
    the event is 300 seconds old and correctly rejected, and the test fails
    while testing nothing. ceil rounds the age down instead, so the payload is
    at most 299 seconds old whenever it is checked.

    The flake this avoids is worse than a normal one: repeated runs land in the
    same second, so it fails every time or never, which reads as a real bug.
    """
    header = signature_header(PAYLOAD, SECRET, timestamp=math.ceil(time.time()) - 299)

    event = stripe.Webhook.construct_event(PAYLOAD, header, SECRET)

    assert event["id"] == "evt_1"


def test_signature_301_seconds_old_is_rejected():
    """Correctly signed and still refused. A replayed payload is not a forged one.

    This is the pair that matters: without the 301 case, the 299 case would pass
    against a verifier that ignored timestamps entirely.
    """
    header = signature_header(PAYLOAD, SECRET, timestamp=math.ceil(time.time()) - 301)

    with pytest.raises(stripe.SignatureVerificationError):
        stripe.Webhook.construct_event(PAYLOAD, header, SECRET)
