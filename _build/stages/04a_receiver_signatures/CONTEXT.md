# 04a_receiver_signatures — the handler and the front door

One job: a working `POST /webhook` that verifies signatures, routes by event
type, applies the state machine, and dedupes on event id. Plus the signature
suite that proves the front door holds.

Split from stage 04b so the ordering cases get their own timebox rather than
being what falls off the end of this one (`D-002`).

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../03_lifecycle_suite/RESULT.md
- Working (the oracle, from stage 02): ../../../docs/transition-table.md
- Working (from stage 02): ../../../service/state_machine.py
- Reference (every run): ../../_shared/conventions.md
- Reference (signature scheme, the two secrets, tolerance): ../../_shared/stripe-facts.md

Do NOT load: `../../_shared/scope-original.md`, `../04b_reorder_race/CONTEXT.md`,
anything Playwright. Ordering and concurrency are the next stage; mixing them in
here is what blew the original single step 4.

## Process

1. `service/webhook.py`:
   - Verify with `stripe.Webhook.construct_event` over the **raw request body**.
     In FastAPI that is `await request.body()`, not the parsed model. A
     re-serialized payload is a different byte string and fails verification.
   - Route by event type, apply `state_machine.apply()`, persist.
   - Dedupe on event id via `processed_events`. An event id already present is
     acknowledged and dropped without re-applying.
   - Log event id, payment id, state before, state after, using the structured
     logging wired in stage 01.
2. `tests/helpers/signing.py`: compute the Stripe signature header directly from
   the documented scheme (HMAC-SHA256 over `{timestamp}.{raw_body}`), with a
   settable timestamp. Write it against the documented scheme rather than a
   private SDK function, so an SDK upgrade does not silently break the whole
   suite. This helper is also what stage 04b runs on, so it is worth getting
   clean.
3. `tests/webhook/test_signature.py`, four cases:
   - valid signature accepted
   - tampered body rejected
   - tampered signature rejected
   - **tolerance boundary: 299s accepted, 301s rejected**
4. Manual end-to-end confirmation, which no automated test in this stage covers:
   ```
   stripe listen --forward-to localhost:8000/webhook
   stripe trigger payment_intent.succeeded
   ```
   Confirm the state moves and the log line appears.

## Outputs

- `service/webhook.py`
- `tests/helpers/signing.py`
- `tests/webhook/test_signature.py`
- `_build/stages/04a_receiver_signatures/RESULT.md`, including the pasted log
  line from the manual check

## Verify

```
pytest tests/webhook/
stripe listen --forward-to localhost:8000/webhook   # manual, with stripe trigger
```

## Human check

Confirm the tolerance test actually fails when the boundary is moved. Change
299 to 301 in the accepting case and watch it fail, then change it back. A
boundary test that passes for both values is testing nothing, and this is a
thirty-second way to know which one you have.
