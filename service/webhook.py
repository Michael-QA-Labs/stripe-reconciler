"""The webhook front door: verify, resolve, apply, persist, log.

The ordering logic itself lives in service/state_machine.py and is not
duplicated here. This module's job is everything around it: proving the request
came from Stripe, working out which payment it concerns, and writing the result
down exactly once.
"""

import json
import sqlite3
from typing import Callable

import stripe

from service import config, db, state_machine
from service.logging_setup import log_state_transition


def payment_intent_id_from(event) -> str | None:
    """Resolve which PaymentIntent an event concerns.

    This differs by event type and getting it wrong is silent. A
    `payment_intent.*` event carries the intent itself, so the id is the
    object's own. A `charge.refunded` event carries a Charge, and a
    `checkout.session.*` event carries a Session; both reference the intent by
    field. Reading `data.object.id` uniformly would store state against a
    charge id and quietly create payments that do not exist.

    Returns None when there is nothing to resolve, which is a real case: not
    every Checkout Session has a PaymentIntent.
    """
    obj = event["data"]["object"]

    if obj.get("object") == "payment_intent":
        return obj.get("id")

    return obj.get("payment_intent")


def _amount_from(event) -> int | None:
    """Only a PaymentIntent payload states the intent's amount.

    A Charge's amount can differ, a partial refund being the obvious case, so it
    is not treated as authoritative.
    """
    obj = event["data"]["object"]

    if obj.get("object") == "payment_intent":
        return obj.get("amount")

    return None


def verify(payload: bytes, signature_header: str) -> dict:
    """Verify the raw body against every signing secret we hold.

    Returns a plain dict, parsed here rather than the SDK's typed object. Two
    reasons. The SDK's objects are not mappings, so routing code written
    against them cannot be unit tested with ordinary dicts without the test and
    the runtime diverging. And the same reasoning behind the hand written
    signing helper applies: the less of our logic depends on SDK object
    semantics, the less an SDK upgrade can quietly change.

    Two secrets exist and they are not interchangeable: the CLI secret backs
    `stripe listen` locally, the dashboard secret backs the deployed endpoint.
    Which one signed a given request depends on where the service is running,
    and the deployment only has one of them. Trying each is what lets the same
    code serve both without an environment switch.
    """
    secrets = [
        secret
        for secret in (config.STRIPE_WEBHOOK_SECRET_CLI, config.STRIPE_WEBHOOK_SECRET_DASHBOARD)
        if secret
    ]

    failure = None
    for secret in secrets:
        try:
            stripe.Webhook.construct_event(payload, signature_header, secret)
            return json.loads(payload)
        except stripe.SignatureVerificationError as error:
            failure = error

    raise failure or stripe.SignatureVerificationError(
        "no signing secret is configured", signature_header, payload
    )


def handle(event, fetch_payment_intent: Callable | None = None) -> None:
    """Apply one verified event to the payment it concerns.

    fetch_payment_intent is the seam described in D-015 and is deliberately
    never called here. A production reconciler treats events as notifications
    and refetches the object from the API when something contradicts itself.
    Doing that inside the request would put a network call on the path Stripe
    waits for, and Stripe retries slow responses, which would manufacture the
    duplicate deliveries this service exists to absorb. The wiring is v2's.
    """
    event_id = event["id"]
    payment_id = payment_intent_id_from(event)

    conn = db.connect()
    # Manage transactions explicitly rather than letting the driver open them
    # implicitly, which is what BEGIN IMMEDIATE below requires.
    conn.isolation_level = None
    try:
        # IMMEDIATE takes the write lock now instead of on first write, so the
        # read of the current state and the write of the new one cannot
        # interleave with another delivery for the same payment.
        conn.execute("BEGIN IMMEDIATE")

        try:
            conn.execute("INSERT INTO processed_events (event_id) VALUES (?)", (event_id,))
        except sqlite3.IntegrityError:
            # Already processed. Insert first and let the primary key arbitrate,
            # rather than checking then inserting, which has a window.
            conn.execute("ROLLBACK")
            return

        if payment_id is None:
            conn.execute("COMMIT")
            return

        row = conn.execute("SELECT state FROM payments WHERE id = ?", (payment_id,)).fetchone()
        state_before = row["state"] if row else None

        transition = state_machine.apply(state_before, event["type"])
        amount = _amount_from(event)

        if state_before is None and transition.state_after is not None:
            conn.execute(
                "INSERT INTO payments (id, stripe_id, state, amount) VALUES (?, ?, ?, ?)",
                (payment_id, payment_id, transition.state_after, amount),
            )
        elif not transition.absorbed:
            # updated_at has a DEFAULT, but defaults only fire on insert, so an
            # update has to set it or the column silently goes stale.
            conn.execute(
                "UPDATE payments SET state = ?, amount = COALESCE(?, amount),"
                " updated_at = datetime('now') WHERE id = ?",
                (transition.state_after, amount, payment_id),
            )

        if not transition.legal:
            conn.execute(
                "INSERT INTO anomalies (event_id, payment_id, from_state, to_state)"
                " VALUES (?, ?, ?, ?)",
                (event_id, payment_id, state_before, transition.state_after),
            )

        conn.execute("COMMIT")
    finally:
        conn.close()

    log_state_transition(
        event_id=event_id,
        payment_id=payment_id,
        state_before=state_before or "none",
        state_after=transition.state_after or "none",
        absorbed=transition.absorbed,
    )
