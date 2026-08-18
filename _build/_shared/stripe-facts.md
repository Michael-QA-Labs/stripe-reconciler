# Stripe facts

Every fact here carries a source. Volatile ones are **captured at stage 00 from
the actual account and CLI**, not asserted from memory, because they change and
a stale number here would silently poison the suites that depend on it.

## Captured at stage 00, 2026-08-18

| Fact | Value | Source |
|---|---|---|
| **Pinned API version** | **`2026-07-29.dahlia`** | `stripe-version` response header on a live call to `/v1/balance` |
| Stripe CLI | 1.50.1 (brew `stripe-cli`) | `stripe --version` |
| Account | sandbox `QA sandbox`, `acct_1U5diKQqVBpO9CGf` | `stripe config --list` |
| CLI key expiry | 2026-11-16 (90 days from `stripe login`) | CLI config |
| CLI signing secret | in `.env`, never here | `stripe listen --print-secret` |
| Dashboard signing secret | in `.env`, empty until stage 01 deploys | Dashboard webhook settings |

These are settled. Do not re-derive them mid-stage. Pin the API version as a
literal constant in `service/config.py` at stage 01, so captured fixtures cannot
silently rot when Stripe ships a change.

## Rate and concurrency limits

Verified against https://docs.stripe.com/rate-limits on 2026-08-18.

| Limit | Value |
|---|---|
| Global, **sandbox** | **25 requests/second** (live mode is 100) |
| Individual endpoint | 25 requests/second |
| **PaymentIntents updates** | **1000 per PaymentIntent object, per hour** |

That PaymentIntent cap matters for stage 04b. The concurrency case fires many
events at a *single* payment, so if any variant of it ever talks to Stripe
rather than to our own receiver, it can hit a per-object ceiling that looks
nothing like a global rate limit.

**A 429 is not always a rate limit.** Responses carry a
`Stripe-Rate-Limited-Reason` header (`global-rate`, `endpoint-rate`,
`global-concurrency`, `endpoint-concurrency`, `resource-specific`). A 429
**without** that header, with code `lock_timeout`, means another request or an
internal Stripe process holds a lock on the object. Different cause, similar
mitigation. Worth distinguishing in stage 11's error taxonomy (v2) rather than
lumping all 429s together.

Live-API suites run serially. Suites hitting our own receiver with locally
signed payloads never touch Stripe and parallelize freely.

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

