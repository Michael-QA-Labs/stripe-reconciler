# 04a_receiver_signatures — RESULT

**Completed** 2026-08-19. Stage 04b is now current.

## What exists now

| Item | State |
|---|---|
| `service/webhook.py` | verify, resolve, apply, dedupe, persist, log |
| `service/main.py` | `POST /webhook` live, `GET /test/payments/{id}` reads real state, schema created in the app lifespan |
| `service/db.py` | fourth table, `anomalies` (`D-015`) |
| `tests/helpers/signing.py` | Stripe-Signature computed from the documented scheme, settable timestamp |
| `tests/webhook/` | 20 tests: 5 signature, 4 resolution, 11 handler |
| Suite | 56 passing, 5 live deselected |

Three things settled here that later stages lean on:

- **Verification tries every configured secret.** The deployment holds only the
  dashboard secret, local runs hold the CLI one. Trying each is what lets the
  same code serve both without an environment switch.
- **Dedupe inserts the event id first** and lets the primary key arbitrate,
  inside `BEGIN IMMEDIATE` so the read of current state and the write of the new
  one cannot interleave with a concurrent delivery. 04b depends on this.
- **Only a signature failure answers non-2xx.** Duplicates, stale events,
  unknown types and unresolvable payments all answer 200, because Stripe retries
  non-2xx and manufacturing retries is the failure this service absorbs.

`fetch_payment_intent` exists on `handle()` and is never called, exactly as
`D-015` specifies.

## Verification output

```
$ .venv/bin/python -m pytest tests/webhook -q
....................                                                     [100%]
20 passed in 0.24s

$ .venv/bin/python -m pytest -q
........................................................                 [100%]
56 passed, 5 deselected in 0.54s
```

## The manual check, and what it found

```
$ stripe listen --forward-to localhost:8000/webhook
Ready! You are using Stripe API Version [2026-07-29.dahlia].

$ stripe trigger payment_intent.succeeded
Trigger succeeded!
```

Delivery results, all accepted:

```
--> charge.succeeded          <--  [200] POST http://localhost:8000/webhook
--> payment_intent.succeeded  <--  [200] POST http://localhost:8000/webhook
--> payment_intent.created    <--  [200] POST http://localhost:8000/webhook
--> charge.updated            <--  [200] POST http://localhost:8000/webhook
```

The receiver's structured log for those four deliveries:

```
{"event_id": "evt_3U6IVYQqVBpO9CGf0AjUkfXU", "payment_id": "pi_3U6IVYQqVBpO9CGf0KGAVNCW", "state_before": "none", "state_after": "none", "absorbed": true}
{"event_id": "evt_3U6IVYQqVBpO9CGf0PRkvaUb", "payment_id": "pi_3U6IVYQqVBpO9CGf0KGAVNCW", "state_before": "none", "state_after": "succeeded", "absorbed": false}
{"event_id": "evt_3U6IVYQqVBpO9CGf0SdU8jFO", "payment_id": "pi_3U6IVYQqVBpO9CGf0KGAVNCW", "state_before": "succeeded", "state_after": "succeeded", "absorbed": true}
{"event_id": "evt_3U6IVYQqVBpO9CGf0gmkV8gE", "payment_id": "pi_3U6IVYQqVBpO9CGf0KGAVNCW", "state_before": "succeeded", "state_after": "succeeded", "absorbed": true}
```

Resulting state, read through the introspection endpoint:

```
{"id":"pi_3U6IVYQqVBpO9CGf0KGAVNCW","state":"succeeded","amount":2000,
 "updated_at":"2026-08-19 23:02:57","anomaly_count":0}
```

**Stripe delivered `payment_intent.created` after `payment_intent.succeeded`**,
third line, and the receiver absorbed it rather than regressing to
`requires_payment_method`. That is the project's headline claim occurring in a
real delivery rather than a constructed test, on the first trigger. Stage 04b
proves it deliberately; this is it happening by accident, and it is the log
excerpt the README should quote.

Lines one and four are `charge.succeeded` and `charge.updated`, event types the
table does not model. Both resolved to the correct payment and were absorbed
without error, which is the unknown-event path working.

**Human check passed.** Michael changed the accepting case from 299 to 301 and
confirmed it fails with `Timestamp outside the tolerance zone`, then reverted.
A boundary test that passes at both values tests nothing.

## Gotchas hit

**The transition logger emitted nothing in production, and the suite hid it.**
Nothing configured the `stripe_reconciler` logger, so `INFO` fell below the root
logger's default `WARNING` and every transition line was dropped under uvicorn.
The existing tests passed because `caplog` sets a level on the logger it
captures. The service looked fully instrumented and was silent. Only the manual
`stripe listen` check could have found this, which is the argument for the
contract having a manual step at all. Fixed in `logging_setup.py`, with a
regression test that asserts the effective level rather than relying on
`caplog`.

**The SDK's event objects are not mappings.** `StripeObject` has no `.get()` and
cannot be passed to `dict()`. The deeper problem was a type mismatch about to
ship: unit tests passed plain dicts while the runtime path would have passed
typed SDK objects, so the tests were not exercising the real thing. `verify()`
now returns a plain dict parsed from the payload it already verified. Same
reasoning as the hand written signing helper: the less of our logic depends on
SDK object semantics, the less an SDK upgrade can silently change.

**The tolerance test was a disguised flake.** `int(time.time()) - 299`
truncates downward, so the payload is really 299 plus the current fraction of a
second old, up to 299.999, against a limit of 300. Repeated runs land in the
same second, so it fails all eight times or none, which reads as a
deterministic bug and sends you debugging the wrong thing. It did. `math.ceil`
rounds the age down instead, so the payload is at most 299 seconds old whenever
it is checked. Verified across 25 repeats.

**Two existing tests were invalidated by this stage and updated, not deleted.**
`/webhook` no longer returns 501, so that test now asserts an unsigned request
is refused with 400. And the introspection endpoint reads the database now, so
the gating test needed a real but empty one.

## Open questions for stage 04b

1. **Concurrency is designed for but unproven.** `BEGIN IMMEDIATE` serialises
   the read-modify-write, and WAL is on from stage 01, but no test yet fires
   concurrent deliveries at one payment. That is 04b's job, and if the design is
   wrong this is where it shows.

2. **`pytest-xdist` is still not installed.** Serial execution is accidental
   rather than configured. When 04b or 07 adds it, `-m live` needs `-n0`,
   because the sandbox is capped at 25 req/s.

3. **`checkout.session.expired` is still not registered on the destination.**
   Carried since stage 02. It cannot fire until stage 05.

4. **The `checkout.session.*` payload shape is still unverified.** Resolution
   for those events reads `data.object.payment_intent`, which is documented but
   not observed, because no Checkout Session has existed yet. Stage 05 is the
   first chance to confirm it against a real payload. `charge.refunded` was
   verified against a real event; this one was not.

5. **Anomalies are written but never read except by tests.** `anomaly_count` on
   the introspection endpoint is the only surface. If stage 05's demo wants to
   show one, it needs somewhere to appear.
