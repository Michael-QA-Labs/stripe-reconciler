# 06_idempotency — our key handling, not Stripe's

One job: `POST /payments` honors an `Idempotency-Key` header correctly, including
under concurrency. This tests our implementation. Stripe has its own idempotency
and testing that would prove nothing about this repo, which is a distinction the
README should also make.

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../05_checkout_playwright/RESULT.md
- Reference (every run): ../../_shared/conventions.md
- Reference (the 24-hour TTL): ../../_shared/stripe-facts.md

Do NOT load: `../../_shared/scope-original.md`, the browser suite, the ordering
suite.

## Process

1. Implement key handling in `POST /payments` against the `idempotency_keys`
   table created in stage 01: key, request body hash, cached response JSON,
   created_at.
2. **A unique constraint on the key is what makes the concurrent case correct
   rather than merely usually correct.** Insert-first and let the constraint
   arbitrate; do not check-then-insert, which has a window between the two.
3. TTL: 24 hours, matching Stripe's own key expiry. Record it in `DECISIONS.md`
   with that reasoning.
4. `tests/idempotency/`, three cases:
   - Same key, same payload: returns the cached result, no second charge.
   - Same key, **different** payload: returns **400**.
   - Concurrent duplicates: N threads, one key, exactly one charge created.
5. The concurrent case asserts on the count of charges, not on response codes.
   Two threads both getting 200 is fine; two charges is the bug.

## Outputs

- Key handling in `service/main.py`
- `tests/idempotency/`
- A `DECISIONS.md` entry for the TTL
- `_build/stages/06_idempotency/RESULT.md`

## Verify

```
pytest tests/idempotency/ --count 20
```

Twenty passes, not one. A concurrency test that has passed once has not told you
anything yet. Paste the full run into `RESULT.md`, including the count.

## Human check

Drop the unique constraint on the key column and rerun the concurrent case. It
should fail. If it still passes twenty times, the test is not actually
concurrent, most likely because the threads are serializing on something else,
and the constraint is currently untested. Restore it afterward and note the
result in `RESULT.md`.
