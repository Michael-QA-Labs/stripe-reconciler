# 06_idempotency: RESULT

**Completed** 2026-08-20. Stage 07 is now current.

`POST /payments` honors an `Idempotency-Key` correctly, including under
concurrency, and the semantics were measured against Stripe rather than
invented. The stage also redeemed the 501 that endpoint had been promising
since stage 01.

## What exists now

| Item | State |
|---|---|
| `service/main.py` | key handling ahead of the branch, direct PaymentIntent creation, TTL |
| `tests/idempotency/test_idempotency.py` | six offline tests plus one live |
| `D-018`, `D-019` | the 24 hour TTL, and the measured semantics |
| Suite | 81 passing by default, 9 live deselected |

Three things settled here:

- **Key handling sits ahead of the branch**, so hosted Checkout and direct
  creation are both covered by one implementation rather than two.
- **The primary key is the arbiter, not a preceding SELECT.** Insert first,
  catch the constraint violation, decide from the existing row. Checking then
  inserting leaves a window that is small enough to miss on a quiet machine and
  wide enough to lose money on a busy one.
- **Direct creation goes through a seam.** `_create_payment_intent` defaults to
  the real client and is substituted by the suite, which is what makes "exactly
  one payment was created" a count rather than an inference.

## Verification output

```
$ .venv/bin/pytest tests/idempotency/ --count 20
120 passed, 20 deselected in 0.91s

$ .venv/bin/pytest -q
81 passed, 9 deselected in 0.41s
```

Twenty repeats, as the contract requires. The suite is offline and finishes in
under a second, which is what makes twenty repeats reasonable at all.

## Stripe's own behaviour, measured before ours was written

The contract left the concurrent case's response open, saying only that
asserting on codes was the wrong thing to do. Rather than pick, the three cases
were fired at the sandbox on the pinned API version:

```
same key, same body, sequential   200, the identical object returned
same key, different body          400 IdempotencyError
same key, concurrent              one 200, the rest 409 "There is currently
                                  another in-progress request using this
                                  Idempotent Key"
```

Ours matches all three (`D-019`). The 409 is the interesting one: the contract
hinted that both threads getting 200 would be fine, and waiting for the
winner's response would have delivered that. It was rejected because an API
that behaves differently from the one it sits beside is a trap for whoever
integrates with both, and because the wait needs a timeout that is either too
short to help or long enough to hold a request open after the caller has given
up.

## Why the tests run offline

The verify command repeats this suite twenty times. Against real Stripe that is
several hundred PaymentIntent creations per run, into a sandbox capped at 25
requests a second, and the concurrent case alone would fire eight at once.

The contract already contains the argument: this stage tests **our**
implementation, and watching Stripe deduplicate would prove nothing about this
repo. `D-015` set the pattern at 04a. Six tests inject a counting fake and run
offline; one `live` test exercises the real client, because everything else
substitutes it and nothing else would notice if it broke.

The fake returns a **distinct id per call**. That detail is load bearing: with a
constant id, a leaked second creation would be invisible in the response body
and the suite would pass while the guarantee was broken.

## The human check, and what it found

Dropping the unique constraint on the key column:

```
$ .venv/bin/pytest tests/idempotency -k concurrent
AssertionError: expected one payment, got 8

$ .venv/bin/pytest tests/idempotency --count 20 -k concurrent
20 failed, 120 deselected

$ .venv/bin/pytest tests/idempotency
3 failed, 3 passed
FAILED test_a_replay_with_the_same_key_returns_the_first_response
FAILED test_a_replay_with_a_different_body_is_refused
FAILED test_concurrent_duplicates_create_exactly_one_payment
```

**Eight payments instead of one, failing twenty times out of twenty.** Worth
contrasting with 04b, where the equivalent mutation was killed only 17 times in
20 and survived one run by luck. This one fails deterministically because
without the constraint every request believes it owns the key, which is a total
failure rather than a race. Nothing here passes by timing.

Three of six tests fail under the mutation, and the three that survive should:
the TTL, the release-on-failure case, and the unkeyed case do not depend on the
constraint. Constraint restored afterwards and the suite is green again.

## Gotchas hit

**The endpoint's own stub test made a live call the moment the endpoint
worked.** `tests/test_endpoints_scaffolded.py` asserted `POST /payments` returns
501. Stage 06 exists to redeem that, so the assertion became false, and worse,
the request it makes started reaching real Stripe on every plain `pytest`,
which conventions forbid. Updated to substitute the seam and assert the
endpoint is implemented. This is the one file touched outside this stage's
declared outputs, and it is recorded here rather than quietly.

**`TestClient` re-raises server exceptions instead of returning 500.** The
release-on-failure test was written expecting a 500 and had to catch the
exception instead. What the test is about is what the key does afterwards, not
which of the two the caller sees.

## Deviations from the contract, stated rather than buried

- **Six offline tests, not the three the contract lists.** The three are all
  present and unchanged in meaning. Three were added to cover gaps the contract
  left open: the 24 hour TTL it asks to be implemented and recorded but gives no
  case for, the release of a key whose work failed, and the unkeyed request. A
  seventh is marked `live` and exercises the real client.
- **The TTL is tested by shortening the window, not by controlling the clock.**
  A zero hour TTL takes the same code path a real expiry reaches in a day, and
  needs neither a time-freezing dependency nor a stale row written directly into
  the database, which conventions forbid.

## Open questions for stage 07

1. **Expired keys are never deleted, only taken over.** A key that is used once
   and never reused stays in the table forever. Harmless for a demo whose
   filesystem is wiped on every redeploy (`D-005`), and wrong for anything
   durable. A sweep is v2's, and the table has no index beyond the primary key.
2. **The live idempotency test creates a real PaymentIntent each run.** It is
   one call, well inside limits, but stage 07's CI must run it with `-m live`
   serially and not in a matrix, or the count multiplies by however many jobs.
3. **`checkout.session.expired` is still unregistered**, 10 of 11 modelled
   events. Unchanged since 04a and now the only modelled event never observed.
4. **The demo GIF is built but uncommitted**, 900 by 506, 552KB. The ship gate
   wants a demo someone can watch, and stage 07 has to decide where a binary
   lives in a repo headed for public.
