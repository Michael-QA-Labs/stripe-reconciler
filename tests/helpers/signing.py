"""Compute a Stripe-Signature header from the documented scheme.

Deliberately not a call into the SDK. Stripe signs the string
`{timestamp}.{raw_body}` with HMAC-SHA256 and presents it as
`t={timestamp},v1={hex_digest}`. Implementing that directly means an SDK
upgrade cannot change the signer and the verifier in step and leave the suite
passing while it verifies nothing.

The settable timestamp is what makes the tolerance boundary testable at all:
the SDK rejects anything older than 300 seconds, and stage 04a tests 299 and
301 on either side of it. Stage 04b runs on this helper too.
"""

import hashlib
import hmac
import time


def signature_header(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Sign payload as Stripe would, optionally backdating it.

    timestamp defaults to now. Pass `int(time.time()) - 301` to produce a header
    that is correctly signed but outside the tolerance window, which is a
    different failure from a bad signature and the suite tests both.
    """
    if timestamp is None:
        timestamp = int(time.time())

    signed_payload = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()

    return f"t={timestamp},v1={digest}"
