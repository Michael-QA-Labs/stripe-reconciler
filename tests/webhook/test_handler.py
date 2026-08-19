"""POST /webhook end to end, asserted through the introspection endpoint.

Conventions forbid tests reading the database directly, so every assertion
here goes through GET /test/payments/{id}. That keeps the suite decoupled from
the schema and matches how a real team inspects service state.
"""

from tests.helpers.signing import signature_header
from tests.webhook.conftest import (
    SECRET,
    charge_object,
    make_event,
    payment_intent_object,
    session_object,
)


def post(client, payload, secret=SECRET):
    return client.post(
        "/webhook",
        content=payload,
        headers={"Stripe-Signature": signature_header(payload, secret)},
    )


def state_of(client, payment_id):
    return client.get(f"/test/payments/{payment_id}").json()


def test_a_valid_event_is_accepted_and_recorded(client):
    payload = make_event("evt_1", "payment_intent.succeeded", payment_intent_object())

    assert post(client, payload).status_code == 200
    assert state_of(client, "pi_1")["state"] == "succeeded"


def test_an_unknown_payment_is_created_on_first_sighting(client):
    payload = make_event("evt_1", "payment_intent.processing", payment_intent_object("pi_new"))
    post(client, payload)

    assert state_of(client, "pi_new")["state"] == "processing"


def test_a_bad_signature_is_rejected(client):
    payload = make_event("evt_1", "payment_intent.succeeded", payment_intent_object())

    response = post(client, payload, secret="whsec_the_wrong_secret_entirely")

    assert response.status_code == 400


def test_a_replayed_event_id_is_dropped_without_reapplying(client):
    """Dedupe is on event id, and it must win even when the replay claims more.

    The replay here claims `refunded`, which outranks `succeeded`. If dedupe
    were missing, the state would advance and this test would catch it. Rank
    alone would not, because refunded is a legitimate next state.
    """
    post(client, make_event("evt_1", "payment_intent.succeeded", payment_intent_object()))
    post(client, make_event("evt_1", "charge.refunded", charge_object()))

    assert state_of(client, "pi_1")["state"] == "succeeded"


def test_a_stale_event_is_absorbed_by_rank(client):
    post(client, make_event("evt_1", "payment_intent.succeeded", payment_intent_object()))
    post(client, make_event("evt_2", "payment_intent.processing", payment_intent_object()))

    assert state_of(client, "pi_1")["state"] == "succeeded"


def test_a_refund_arrives_as_a_charge_and_still_finds_the_payment(client):
    """The resolution gap: data.object is a Charge, not a PaymentIntent."""
    post(client, make_event("evt_1", "payment_intent.succeeded", payment_intent_object()))
    post(client, make_event("evt_2", "charge.refunded", charge_object()))

    assert state_of(client, "pi_1")["state"] == "refunded"


def test_an_illegal_transition_is_applied_and_recorded(client):
    """D-014 and D-015: leaving canceled is impossible, so it is flagged and kept."""
    post(client, make_event("evt_1", "payment_intent.canceled", payment_intent_object()))
    post(client, make_event("evt_2", "payment_intent.succeeded", payment_intent_object()))

    payment = state_of(client, "pi_1")
    assert payment["state"] == "succeeded"
    assert payment["anomaly_count"] == 1


def test_a_legal_transition_records_no_anomaly(client):
    post(client, make_event("evt_1", "payment_intent.processing", payment_intent_object()))
    post(client, make_event("evt_2", "payment_intent.succeeded", payment_intent_object()))

    assert state_of(client, "pi_1")["anomaly_count"] == 0


def test_an_unknown_event_type_is_acknowledged_and_changes_nothing(client):
    """Never 5xx for something we handled. Stripe retries 5xx and that makes duplicates."""
    payload = make_event("evt_1", "customer.subscription.created", {"id": "sub_1", "object": "subscription"})

    assert post(client, payload).status_code == 200


def test_a_session_without_a_payment_intent_is_acknowledged(client):
    session = session_object()
    session["payment_intent"] = None
    payload = make_event("evt_1", "checkout.session.completed", session)

    assert post(client, payload).status_code == 200


def test_amount_is_taken_only_from_payment_intent_payloads(client):
    """A Charge's amount is not necessarily the intent's, so it is not trusted."""
    post(client, make_event("evt_1", "payment_intent.succeeded", payment_intent_object(amount=2500)))

    assert state_of(client, "pi_1")["amount"] == 2500
