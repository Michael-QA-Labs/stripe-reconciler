# 01_foundation — service skeleton, deployed

One job: a FastAPI service with all four endpoints scaffolded, a SQLite database
in WAL mode, and a **live URL**. Deploying now rather than at stage 07 is `D-003`.

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../00_prereqs/RESULT.md
- Reference (every run): ../../_shared/conventions.md
- Reference (API version, the two secrets): ../../_shared/stripe-facts.md

Do NOT load: `../../_shared/scope-original.md`, later stage contracts. In
particular do not write state machine logic here; that is stage 02, and writing
it before the transition table exists defeats the point of the table.

## Process

1. Create `service/` and `tests/`. These are the first product directories.
2. `service/config.py`: env loading, `TESTING` flag, and the **Stripe API
   version pinned as a literal constant** using the string captured in
   `stripe-facts.md`.
3. `service/db.py`: SQLite connection with `PRAGMA journal_mode=WAL`. Three
   tables:
   - `payments` (id, stripe_id, state, amount, created_at, updated_at)
   - `processed_events` (event_id primary key, received_at) for dedupe
   - `idempotency_keys` (key primary key, request_hash, response_json, created_at)
   Create all three now. Stages 04a and 06 fill them; the schema living in one
   place is worth more than deferring two tables.
4. `service/main.py`: four endpoints, scaffolded and returning honest stubs.
   - `POST /payments`
   - `POST /webhook`
   - `GET /health`
   - `GET /test/payments/{id}`, returning **404 unless `TESTING=true`**
5. Structured logging on the webhook path from the start: event id, payment id,
   state before, state after. Retrofitting this while debugging stage 04b races
   is the painful path.
6. `requirements.txt`, every version pinned with why-comments. Include
   `pytest-repeat`; stage 06 needs it for the flake check.
7. Seed `README.md` with the "why this problem is hard" paragraph only. Writing
   the framing first keeps the build pointed at it.
8. Deploy to Render, health check only. Then register the webhook endpoint in
   the Stripe dashboard, capture `STRIPE_WEBHOOK_SECRET_DASHBOARD`, and add it
   to `.env` and the GitHub repo secrets.

## Tests

- `tests/test_health.py`: 200 and the expected body.
- `tests/test_introspection_gating.py`: 404 when `TESTING` is unset, 200 when
  set. Small, but it means the safety gate on the test-only endpoint has a test
  from the first day rather than being assumed.

## Outputs

- `service/config.py`, `service/db.py`, `service/main.py`
- `tests/test_health.py`, `tests/test_introspection_gating.py`
- `requirements.txt`, `README.md` (seeded)
- A live Render URL
- `_build/stages/01_foundation/RESULT.md`, recording the URL

## Verify

```
pytest
curl https://<render-url>/health
```

Both go in `RESULT.md` with their actual output.

## Human check

Hit the deployed `/test/payments/1` in a browser and confirm it 404s. That
endpoint shipping live and open is the one mistake in this stage that would
matter, and confirming it against the real deployment is different from
confirming it against a local test.
