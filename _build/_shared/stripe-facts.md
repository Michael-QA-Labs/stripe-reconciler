# Stripe facts

Every fact here carries a source. Volatile ones are **captured at stage 00 from
the actual account and CLI**, not asserted from memory, because they change and
a stale number here would silently poison the suites that depend on it.

## Capture at stage 00 (currently unfilled)

| Fact | Value | How to capture |
|---|---|---|
| Pinned API version | _TBD at stage 00_ | Dashboard → Developers → API version, or `stripe --version` plus the account default. Record the exact string. |
| CLI signing secret | in `.env`, never here | `stripe listen --print-secret` |
| Dashboard signing secret | in `.env`, never here | Dashboard → Webhooks → the Render endpoint, after stage 01 deploys |
| Test-mode rate limit | _TBD at stage 00_ | Stripe docs, rate limits page. Around 25 req/s historically; confirm before relying on it. |

Once filled, these are settled. Do not re-derive them mid-stage.

## Two signing secrets, and they are not interchangeable

This is the single most common way to lose an afternoon on this project.

- `STRIPE_WEBHOOK_SECRET_CLI` backs `stripe listen` during local development,
  and backs every locally signed payload in stages 04a and 04b.
- `STRIPE_WEBHOOK_SECRET_DASHBOARD` backs the deployed Render endpoint,
  registered in the dashboard at stage 01.

Both are named distinctly in `.env.example` from stage 00 onward. A signature
test failing for no apparent reason is this, roughly every time.

## Signature verification

- `stripe.Webhook.construct_event(payload, sig_header, secret)` verifies an
  HMAC-SHA256 over `{timestamp}.{raw_body}` and rejects anything outside the
  timestamp tolerance.
- **Default tolerance is 300 seconds.** Stage 04a tests the boundary at 299s
  (accept) and 301s (reject). Confirm the default in the installed SDK rather
  than trusting this line.
- The payload must be the **raw request body**. Re-serialized JSON produces a
  different byte string and fails verification. In FastAPI that means
  `await request.body()`, not the parsed model.
- Stage 04a writes `tests/helpers/signing.py` to compute the header directly
  from the documented scheme, with a settable timestamp. Deliberately not a
  private SDK function, so it survives SDK upgrades.

## Test cards

| Card | Behavior | Used in |
|---|---|---|
| `4242 4242 4242 4242` | succeeds | 05 |
| `4000 0000 0000 0002` | generic decline | 05 |
| `4000 0025 0000 3155` | forces a 3DS iframe challenge | v2 step 11, not v1 |

## Idempotency

- Stripe's own idempotency keys expire after **24 hours**. Stage 06 matches that
  TTL for our `POST /payments` key store, which is the defensible choice.
- Stage 06 tests **our** idempotency implementation, not Stripe's. The
  distinction matters when writing the README.

## Rate limits and parallelism

- Live-API suites (stage 03, and stage 11 in v2) run **serially**.
- Suites that hit our own receiver with locally signed payloads never touch
  Stripe and parallelize freely.
