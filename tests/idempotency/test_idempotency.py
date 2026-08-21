"""Our Idempotency-Key handling, not Stripe's.

Passing a key through to Stripe and watching Stripe deduplicate would prove
nothing about this repo. Every test here substitutes the creation seam for a
counting fake, so "exactly one payment was created" is a real count rather than
an inference from the response body. A cached response can be perfectly correct
while a second payment leaked underneath it, and only the count catches that.

Running offline is not a convenience. The stage's verify command repeats this
suite twenty times, and against real Stripe that would be several hundred
PaymentIntent creations per run into a sandbox capped at 25 requests a second.
The same reasoning as D-015: an injected fake covers it offline, and one live
test proves the real client separately.

The semantics asserted here were measured against Stripe's own API rather than
assumed, on the pinned API version:

    same key, same body, sequential   200, the identical object
    same key, different body          400 IdempotencyError
    same key, concurrent              one 200, the rest 409

Ours matches, because a payments API that behaves differently from the one it
sits next to is a trap for whoever integrates with it.
"""

import importlib
from concurrent.futures import ThreadPoolExecutor

import pytest
import stripe
from fastapi.testclient import TestClient

KEY = "idem-key-under-test"
BODY = {"amount": 1500, "currency": "usd"}


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    """Rebuild the app against a temporary database.

    Routes are registered at import time under TESTING, so the modules are
    reloaded with the flag set, the same approach the webhook suite uses.
    """
    monkeypatch.setenv("TESTING", "true")

    from service import config, main

    importlib.reload(config)
    importlib.reload(main)

    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "idempotency.db"))
    return main


@pytest.fixture
def creations(app_module, monkeypatch):
    """Replace the creation seam with a counter that returns distinct ids.

    Distinct ids matter. If every fake creation returned the same id, a leaked
    second creation would be invisible in the response and the suite would pass
    while the guarantee was broken.
    """
    calls = []

    def fake_create(amount: int, currency: str) -> dict:
        calls.append((amount, currency))
        return {
            "id": f"pi_fake_{len(calls)}",
            "status": "requires_payment_method",
            "amount": amount,
        }

    monkeypatch.setattr(app_module, "_create_payment_intent", fake_create)
    return calls


@pytest.fixture
def client(app_module):
    with TestClient(app_module.app) as test_client:
        yield test_client


def post(client, body=None, key=KEY):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/payments", json=body or BODY, headers=headers)


def test_a_replay_with_the_same_key_returns_the_first_response(client, creations):
    """The contract's first case. The count is the assertion, not the status."""
    first = post(client)
    second = post(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(creations) == 1, f"expected one payment, got {len(creations)}"


def test_a_replay_with_a_different_body_is_refused(client, creations):
    """The contract's second case, and it matches Stripe's measured 400.

    Reusing a key for different work is a caller bug, and the useful thing to do
    with it is refuse loudly. Returning the first response instead would answer
    a question that was never asked.
    """
    post(client)
    changed = post(client, body={"amount": 9999, "currency": "usd"})

    assert changed.status_code == 400
    assert len(creations) == 1


def test_concurrent_duplicates_create_exactly_one_payment(client, creations):
    """The contract's third case, and the reason the primary key is the arbiter.

    Eight threads, one key. The assertion is on the count of payments created,
    not on the response codes: a mix of one 200 and seven 409s is correct, and
    so is any other split, because Stripe itself answers 409 while a request
    holding the key is still in flight. Two payments is the bug.

    Checking whether a key exists before inserting it would pass this most of
    the time, which is worse than failing. The window between the check and the
    insert is small enough to miss on a quiet machine and wide enough to lose
    money on a busy one.
    """
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: post(client), range(8)))

    assert len(creations) == 1, f"expected one payment, got {len(creations)}"

    accepted = [r for r in responses if r.status_code == 200]
    assert accepted, "every concurrent request was refused"
    assert {r.json()["id"] for r in accepted} == {"pi_fake_1"}
    assert all(r.status_code in (200, 409) for r in responses)


def test_an_expired_key_can_be_used_again(client, creations, app_module, monkeypatch):
    """The TTL, which the contract asks for but does not give a case.

    Expiry is proven by shortening the window rather than by controlling the
    clock or writing a stale row into the database. A zero hour TTL makes any
    existing key expired on sight, which is the same code path a real
    twenty-four hour expiry takes a day to reach.
    """
    post(client)
    assert len(creations) == 1

    monkeypatch.setattr(app_module, "IDEMPOTENCY_TTL_HOURS", 0)
    replayed = post(client)

    assert replayed.status_code == 200
    assert len(creations) == 2, "an expired key was still treated as spent"
    assert replayed.json()["id"] == "pi_fake_2"


def test_a_key_is_released_when_the_work_fails(client, creations, app_module, monkeypatch):
    """A failed attempt must not burn the key for the next twenty-four hours.

    Retrying after an error is the ordinary case, not an abuse. If the key were
    held, every retry would answer 409 until the TTL expired, and the caller's
    only recourse would be to invent a new key, which defeats the point of
    having one.
    """
    def explode(amount, currency):
        raise stripe.APIConnectionError("the network went away")

    monkeypatch.setattr(app_module, "_create_payment_intent", explode)
    # TestClient re-raises server exceptions rather than turning them into a
    # 500, so the failure is caught here. What matters is what the key does
    # afterwards, not which of the two the caller sees.
    with pytest.raises(stripe.APIConnectionError):
        post(client)

    monkeypatch.setattr(app_module, "_create_payment_intent",
                        lambda amount, currency: _fake(creations, amount))
    retried = post(client)

    assert retried.status_code == 200
    assert len(creations) == 1


def _fake(calls, amount):
    calls.append((amount, "usd"))
    return {"id": f"pi_fake_{len(calls)}", "status": "requires_payment_method", "amount": amount}


def test_without_a_key_every_request_is_a_new_payment(client, creations):
    """The header is optional, and its absence means no promise was asked for.

    Stripe behaves the same way. Caching regardless would silently change what
    an unkeyed request means, which is the kind of helpfulness that loses money.
    """
    assert post(client, key=None).status_code == 200
    assert post(client, key=None).status_code == 200

    assert len(creations) == 2


@pytest.mark.live
def test_the_real_client_creates_a_payment_intent():
    """The seam's default, exercised once against Stripe.

    Everything above substitutes the creator, so nothing else here would notice
    if the real call were broken. This is the one test that would.
    """
    from service import main

    intent = main._create_payment_intent(1500, "usd")

    assert intent["id"].startswith("pi_")
    assert intent["amount"] == 1500
    assert intent["status"] == "requires_payment_method"
