# 03_lifecycle_suite — RESULT

**Completed** 2026-08-19. Stage 04a is now current.

## What exists now

| Item | State |
|---|---|
| `tests/lifecycle/conftest.py` | session-scoped `StripeClient` pinned to `2026-07-29.dahlia`, plus a per-test PaymentIntent fixture |
| `tests/lifecycle/test_lifecycle.py` | five tests: create, confirm, manual capture, cancel, refund |
| `pyproject.toml` | `addopts = ["-m", "not live"]`, so live tests are opt in |
| Marker | `live` was already registered at stage 01, so only the opt-in default was new |

No receiver code is involved anywhere in this directory. The suite talks to
Stripe directly, which is what makes it a clean baseline for 04a to diverge from.

**The client is pinned deliberately.** Without `stripe_version`, the SDK follows
the account's default API version, so the suite could pass against a version the
transition table never described. The pin is why `STRIPE_API_VERSION` is a
literal constant rather than a lookup.

## Verification output

```
$ .venv/bin/python -m pytest -m live -v
test_create_leaves_the_intent_awaiting_a_payment_method   PASSED
test_confirm_succeeds_immediately_with_automatic_capture  PASSED
test_manual_capture_makes_authorize_and_capture_two_steps PASSED
test_cancel_moves_an_unconfirmed_intent_to_canceled       PASSED
test_refund_does_not_change_the_payment_intent_status     PASSED
5 passed, 33 deselected in 5.68s

$ .venv/bin/python -m pytest
33 passed, 5 deselected in 0.39s
```

## Statuses the real API returned

Contract step 5. Stage 02's table was written from documentation; this is the
first contact with reality.

| Step | Returned |
|---|---|
| create, no payment method | `requires_payment_method` |
| confirm, automatic capture | `succeeded` |
| confirm, `capture_method="manual"` | `requires_capture` |
| capture | `succeeded` |
| cancel an unconfirmed intent | `canceled` |
| refund a succeeded intent | intent stays `succeeded`, charge reads `refunded: true` |

**No mismatches with `docs/transition-table.md`.** Two things that were
inferences are now observations:

1. **`refunded` really is this project's state, not Stripe's.** Refunding leaves
   the PaymentIntent reading `succeeded`; the refund lands on the Charge. This
   was previously deduced from the seven-value status enum. It is now measured,
   and it is the clearest single justification for the table's extra state.
2. **`requires_capture` is reachable only under `capture_method="manual"`.** The
   automatic flow goes straight to `succeeded`, which is why stage 02 had to
   rank `requires_capture` against `processing` on documentation alone.

**Human check passed.** Michael looked up three objects by id in the test-mode
dashboard and confirmed each matched what the tests asserted:

| Object | Confirmed as |
|---|---|
| `pi_3U6Hd0QqVBpO9CGf0pzxUG0d` | succeeded, capture method manual |
| `pi_3U6Hd2QqVBpO9CGf0rgw2a2A` | canceled |
| `pi_3U6Hd2QqVBpO9CGf0zmuJ86m` | succeeded, carrying a 1000 refund |

## Gotchas hit

**The SDK deprecated the accessors this suite was written against.**
`StripeClient.payment_intents` is superseded by `StripeClient.v1.payment_intents`
in 15.5.0. Because `filterwarnings = ["error"]` is set, this failed the first run
outright instead of printing a warning nobody reads, and it was fixed before the
old form was written across five tests. That convention paid for itself here.

**Object counts in the dashboard do not reconcile with the API, by design.**
The API reported 12 PaymentIntents; the dashboard's payments view showed fewer.
Intents at `requires_payment_method` and `requires_confirmation` never produced a
charge and sit under Incomplete, and refunded payments are filed as Refunded
rather than Succeeded. This is worth writing down because it is the project's own
thesis in miniature: **the dashboard is a filtered view, the API is the source of
truth**, which is the same reasoning behind `D-015`. It also means counts are a
poor human check; looking up specific ids in specific states is the check that a
mocked suite could not fake.

**Live tests are not idempotent in object count.** Each run creates five more
PaymentIntents. Inherent to testing against a real API, and harmless in a
sandbox, but it means the dashboard accumulates and any future assertion about
totals would be wrong by the next run.

## Open questions for stage 04a

1. **`checkout.session.expired` is still not registered on the destination.**
   Carried from stage 02. It cannot fire until stage 05 creates Checkout
   Sessions, so it is not blocking, but the table models 11 events and the
   destination listens to 10.

2. **Serial execution is currently accidental, not configured.** `pytest-xdist`
   is not installed, so nothing runs in parallel today. The moment it arrives,
   `-m live` needs `-n0` or equivalent, because the sandbox is capped at 25
   req/s and a parallel live run produces failures that look like bugs.

3. **`init_db()` is still never called**, carried from stage 01. Stage 04a is
   the stage that wires it at startup, test-first, because it is the first code
   that writes to the database.

4. **The anomaly seam is specified and unbuilt** (`D-015`). 04a flags, logs and
   persists an illegal transition, and defines a `fetch_payment_intent` callable
   that nothing calls. 04a's contract now lists `DECISIONS.md` as an input, so
   this is reachable from that stage.

5. **CI will need `STRIPE_SECRET_KEY` for the live job.** The repo secret exists
   already. Stage 07 splits on the `live` marker, and the opt-in default added
   here is what makes a fixture-only job possible.
