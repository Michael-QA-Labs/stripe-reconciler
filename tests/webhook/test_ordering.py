"""Delivery order cannot change the outcome. This is the stage the README rests on.

Stripe guarantees at-least-once delivery, not ordered delivery, so a receiver
that is correct only for the happy sequence is not correct. Every case here
runs against the local receiver through POST /webhook with locally signed
payloads, and reads state back through GET /test/payments/{id} rather than the
database, per conventions.

The oracle is docs/transition-table.md, not this file's opinion. The rule it
defines is that every state has a rank and a claim is applied only if it ranks
strictly higher than what is recorded. The consequence being proven here is
that the final state is the highest rank among the events received, which is a
property of the set rather than of the sequence.
"""

from concurrent.futures import ThreadPoolExecutor
from itertools import permutations

import pytest

from service.state_machine import STATE_RANK
from tests.helpers.signing import signature_header
from tests.webhook.conftest import (
    SECRET,
    charge_object,
    make_event,
    payment_intent_object,
)


def post(client, event_id, event_type, obj=None):
    payload = make_event(event_id, event_type, obj or payment_intent_object())
    return client.post(
        "/webhook",
        content=payload,
        headers={"Stripe-Signature": signature_header(payload, SECRET)},
    )


def state_of(client, payment_id="pi_1"):
    return client.get(f"/test/payments/{payment_id}").json()


# Case 1: reordering.

LIFECYCLE = (
    ("evt_created", "payment_intent.created"),
    ("evt_processing", "payment_intent.processing"),
    ("evt_succeeded", "payment_intent.succeeded"),
)

ORDERINGS = list(permutations(LIFECYCLE))
ORDERING_IDS = [",".join(event_type.split(".")[-1] for _, event_type in o) for o in ORDERINGS]


@pytest.mark.parametrize("order", ORDERINGS, ids=ORDERING_IDS)
def test_final_state_is_independent_of_delivery_order(client, order):
    """Every permutation of one lifecycle converges on the same state.

    The contract asks for succeeded before processing. All six orderings are
    run instead, because the claim is about the set and testing one reversal
    would leave the general case asserted only by argument.
    """
    for event_id, event_type in order:
        assert post(client, event_id, event_type).status_code == 200

    assert state_of(client)["state"] == "succeeded"


@pytest.mark.parametrize(
    "order",
    [("payment_intent.canceled", "payment_intent.succeeded"),
     ("payment_intent.succeeded", "payment_intent.canceled")],
    ids=["canceled-then-succeeded", "succeeded-then-canceled"],
)
def test_the_contradictory_pair_converges_but_only_one_order_is_an_anomaly(client, order):
    """D-014, and the one place where order changes something visible.

    succeeded outranks canceled, so both orders end at succeeded and the state
    is order independent as everywhere else. What differs is legality: arriving
    at succeeded *out of* canceled is a transition the table calls impossible,
    so it is recorded as an anomaly. The reverse order never leaves canceled at
    all, because canceled cannot outrank succeeded, so nothing is flagged.

    This asymmetry is the whole reason D-014 ranks succeeded above canceled.
    Rank canceled higher instead and the contradiction is silently absorbed,
    the illegal transition machinery becomes dead code, and a mapping bug in
    our own receiver passes unnoticed.
    """
    for index, event_type in enumerate(order):
        assert post(client, f"evt_{index}", event_type).status_code == 200

    payment = state_of(client)
    assert payment["state"] == "succeeded"
    assert payment["anomaly_count"] == (1 if order[0].endswith("canceled") else 0)


# Case 2: duplicate event id.


def test_a_duplicate_event_id_is_dropped_by_id_and_not_by_rank(client):
    """The replay claims more than the original, so only dedupe can absorb it.

    Redelivering the same event id with an identical payload proves nothing:
    the repeat claims a state of equal rank, and equal is not strictly higher,
    so the rank rule alone would absorb it and a broken dedupe would look
    healthy. That is the mutant that survived at stage 02.

    So the replay here carries a claim that outranks what is recorded. If the
    processed_events primary key did not arbitrate, the state would advance.

    This also stands in for "one row in processed_events", which is not visible
    through the introspection endpoint and which conventions forbid reading
    from the database. The handler proceeds past its dedupe insert only when
    that insert succeeded, so a state that did not advance is the observable
    form of the row already being there.
    """
    assert post(client, "evt_1", "payment_intent.processing").status_code == 200
    assert post(client, "evt_1", "charge.refunded", charge_object()).status_code == 200

    assert state_of(client)["state"] == "processing"


def test_a_duplicate_does_not_wedge_the_payment_for_later_events(client):
    """Dedupe drops the event, not the payment. A rollback must not leave state stuck."""
    post(client, "evt_1", "payment_intent.processing")
    post(client, "evt_1", "payment_intent.processing")

    assert post(client, "evt_2", "payment_intent.succeeded").status_code == 200
    assert state_of(client)["state"] == "succeeded"


# Case 3: stale after newer.

STALE_CLAIMS = [
    "payment_intent.created",
    "payment_intent.requires_action",
    "payment_intent.amount_capturable_updated",
    "payment_intent.processing",
    "payment_intent.payment_failed",
]


@pytest.mark.parametrize("stale_type", STALE_CLAIMS, ids=[t.split(".")[-1] for t in STALE_CLAIMS])
def test_a_stale_event_after_a_terminal_state_is_absorbed_not_applied(client, stale_type):
    """State is a high water mark, so nothing below it can be written over it.

    payment_failed is the case worth naming: Stripe genuinely returns a failed
    PaymentIntent to requires_payment_method so it can be retried, and the
    table deliberately refuses that regression. The recorded state is the
    furthest progress ever observed, not Stripe's instantaneous status.

    None of these is an anomaly. Absorbing a late event is the design working,
    and flagging it would fire on every reordered delivery and teach a reader
    to ignore the flag.
    """
    assert post(client, "evt_1", "payment_intent.succeeded").status_code == 200
    assert post(client, "evt_2", stale_type).status_code == 200

    payment = state_of(client)
    assert payment["state"] == "succeeded"
    assert payment["anomaly_count"] == 0


# Case 4: true concurrency.

CONFLICTING = [
    ("evt_c1", "payment_intent.created", payment_intent_object()),
    ("evt_c2", "payment_intent.processing", payment_intent_object()),
    ("evt_c3", "payment_intent.canceled", payment_intent_object()),
    ("evt_c4", "payment_intent.succeeded", payment_intent_object()),
    ("evt_c5", "charge.refunded", charge_object()),
]


def test_concurrent_conflicting_deliveries_converge_without_corruption(client):
    """Five contradictory events at one payment, fired at once, no sequencing.

    This is the case BEGIN IMMEDIATE and WAL exist for. Each delivery reads the
    current state and writes the next one, and without the write lock taken up
    front those two steps interleave and a higher rank gets overwritten by a
    lower one that read stale state.

    The expected state is refunded because it is the highest rank in the set,
    and that expectation does not depend on who wins any race: the rule is
    monotonic, so whatever order the threads land in, rank 80 is applied and
    nothing below it can replace it. A test that accepted several states would
    be asserting almost nothing, which is why this asserts exactly one.

    A "database is locked" failure here is a WAL problem from stage 01, not a
    state machine problem. That distinction is why WAL was set up there.
    """
    with ThreadPoolExecutor(max_workers=len(CONFLICTING)) as pool:
        responses = list(pool.map(lambda event: post(client, *event), CONFLICTING))

    assert [response.status_code for response in responses] == [200] * len(CONFLICTING)

    payment = state_of(client)
    assert payment["state"] in STATE_RANK
    assert payment["state"] == "refunded"


def test_concurrent_deliveries_of_one_event_id_do_not_error(client):
    """Eight threads, one event id, contending on the dedupe insert.

    What this proves and what it does not is worth being exact about, because
    the obvious stronger claim is unprovable here. Under contention the losing
    threads hit the primary key, ROLLBACK, and return, all while holding or
    waiting on BEGIN IMMEDIATE. This asserts that path does not deadlock, does
    not raise, and does not answer anything but 200, since a 5xx would make
    Stripe retry and manufacture the very duplicates being absorbed.

    It does NOT prove the event was applied exactly once. Nothing observable
    through the introspection endpoint can: with dedupe removed the repeats are
    absorbed by rank instead, because a duplicate claims a state of equal rank
    and equal is not strictly higher. That independence is the table's design
    rather than a gap in it, and the single threaded case above is what proves
    dedupe specifically, by replaying an id with a claim that outranks the
    recorded state so that rank cannot do the absorbing.
    """
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(lambda _: post(client, "evt_same", "payment_intent.succeeded"), range(8))
        )

    assert [response.status_code for response in responses] == [200] * 8
    assert state_of(client)["state"] == "succeeded"
