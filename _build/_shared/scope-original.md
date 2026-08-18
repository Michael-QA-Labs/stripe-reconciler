# Origin record: the original project scope

**Do NOT load this by default.** It is roughly 4k tokens and would blow a
stage's context budget on its own. It is on every stage contract's do-not-load
line.

**This is not live instruction.** It records the original intent and the
reasoning behind the locked decisions. Where it differs from a stage
`CONTEXT.md`, the stage contract wins. The three known differences are recorded
in `../CONTEXT.md` under "Three deviations", so there is no need to diff.

Read it when you need to know *why* something was decided, and `DECISIONS.md`
does not cover it.

Punctuation normalized from the original paste (mojibake repaired, dashes
replaced per `conventions.md`). Content otherwise unchanged.

---

## Overview

A payment receiver service built from scratch and tested against Stripe test
mode. A portfolio piece that reads like production work: a real backend with
real state, not a script that calls someone else's API.

The core problem the project is built around: Stripe guarantees at-least-once
delivery, not ordered delivery. Events arrive twice, arrive late, and arrive out
of order. The receiver implements its own event-sequencing and idempotency logic
before any of it can be tested. That logic is mine, not Stripe's, which is what
makes the test suite worth reading.

Test scope covers the payment lifecycle, a browser-driven Checkout flow,
idempotency, webhook signature integrity, out-of-order and concurrent event
handling, retry and failure recovery, and Stripe's error taxonomy.

## Stack

- **Service**: FastAPI + SQLite (WAL mode)
- **Front end**: minimal page with a Pay button, redirect to Stripe hosted Checkout
- **Testing**: Playwright (Python) via `pytest-playwright`. Browser context for
  the Checkout flow, `APIRequestContext` for request-driven suites
- **Property testing**: Hypothesis, against the state machine transition table
- **Mutation testing**: `mutmut`, scoped to the state machine
- **Payments**: Stripe sandbox (test mode), Stripe CLI for webhook forwarding
  and fixture capture
- **CI**: GitHub Actions
- **Hosting**: Render or Railway free tier, so there's a live URL and a real
  webhook endpoint
- **Reporting**: Allure, published to GitHub Pages

## Architecture

```
/service     receiver app: webhook endpoint, payment endpoint, state machine,
             health check, test-only introspection endpoint
/web         minimal Checkout front end
/tests       Playwright/pytest suite
/fixtures    captured, signed Stripe webhook events for deterministic replay
/docs        transition table, test strategy, bug writeups
```

Endpoints:

- `POST /payments`: accepts an `Idempotency-Key` header, creates a PaymentIntent
  or Checkout Session, records it locally
- `POST /webhook`: verifies signature, routes by event type, applies the state machine
- `GET /health`: deploy/uptime check
- `GET /test/payments/{id}`: test-only introspection, gated behind `TESTING=true`
  (404 otherwise) so it can't ship live by accident

SQLite is the source of truth. Tests never read the database directly, they hit
the introspection endpoint. That keeps tests decoupled from implementation and
matches how a real team checks service state without giving tests a backdoor.

## Test pillars

1. **Lifecycle**: create, confirm, capture, cancel, refund, against the live
   Stripe test API.
2. **Browser end to end**: Playwright drives a real card entry through hosted
   Checkout, then asserts the resulting server-side state via the introspection
   endpoint. Browser action causes an async webhook that a different protocol
   verifies.
3. **Idempotency**: same key/same payload returns the cached result, same
   key/different payload returns 400, concurrent duplicates produce one charge.
   Targets `POST /payments`, my code, not Stripe's.
4. **Webhook integrity**: signature verification (valid, tampered), timestamp
   tolerance boundary at 299s and 301s, event type routing.
5. **Async and out-of-order**: reordered delivery, true concurrency via
   threading, duplicate delivery, stale and late events. Hand-written cases land
   in v1 (locally signed payloads); Hypothesis-generated sequences extend the
   same suite in v2.
6. **Failure and retry**: fault injection between write and commit, 500
   response, Stripe redelivery, assert state heals rather than corrupts. Plus an
   ack-latency threshold on `/webhook`.
7. **Error taxonomy**: card decline codes, rate limit errors, invalid request errors.

## Key decisions

**FastAPI over Flask.** Flask is already in the portfolio (Urban Scooter API).
Native async fits a service that reasons about concurrent event delivery.

**Real Stripe test mode, not a mock.** Stronger claim than another hand-rolled
mock server.

**Playwright for both browser and API.** The Checkout flow is what makes
Playwright load-bearing rather than decorative. Using `APIRequestContext` alone
for JSON calls would be `httpx` with extra imports, and a reviewer who knows the
tool would notice. With a real browser flow in the suite, one framework and one
report covers everything.

**PaymentIntent is the canonical object.** Hosted Checkout emits
`checkout.session.completed` alongside the underlying `payment_intent.*` events,
and those can arrive in either order. Session events map onto the PaymentIntent
record. Without picking one source of truth up front, the reorder suite becomes
unfalsifiable.

**Transition table before handler code.** States by events, legal and illegal,
written first. It's the oracle for the reorder suite, the Hypothesis properties,
and the mutation testing. Everything downstream is cheaper because it exists.

**Ordering by state precedence, not raw timestamp.** The transition table itself
resolves order: terminal states absorb, state never regresses. `event.created`
is a tiebreaker only, used when two events would otherwise rank the same. More
defensible under clock skew than timestamp-first ordering, and it means the
table already committed to in step 2 *is* the ordering mechanism, with no
separate sequencing scheme to design or justify.

**Reorder/race cases pulled into v1.** They don't require fixture capture. The
webhook signing secret is known locally, so payloads can be constructed and
signed with `stripe.WebhookSignature` and replayed in any order without a live
listener. This closes the gap between the README's headline claim (unordered
delivery) and what v1 actually proves before it ships.

**Fixture replay for CI, live CLI listener for local.** GitHub Actions can't run
a live `stripe listen` session headlessly. Signature and race tests run against
captured signed fixtures in CI. The full live flow stays a documented local check.

**Browser suite is a separate, non-blocking CI job.** Tests against a
third-party hosted page are the flakiest thing in the repo, since Stripe
redesigns Checkout without notice. Role and label locators only, three to five
tests, trace and video on failure. Knowing which tests to gate on is a
deliberate call, and the README says so.

**Mutation testing over coverage percentage.** Coverage says a line ran. It
doesn't say an assertion would have caught it breaking. Mutation score on the
state machine is the only cheap proof the suite has teeth.

**WAL mode on SQLite**, so `database is locked` errors under concurrent writes
don't get mistaken for real state-machine bugs in the race tests.

**API version pinned explicitly**, in code and in the webhook endpoint config,
so captured fixtures don't silently rot when Stripe ships a change.

## Locked decisions

Previously open, resolved here so v1 starts without ambiguity:

- **Sequence tracking**: state precedence from the transition table, timestamp
  as tiebreaker only. See Key decisions above.
- **PaymentIntent vs Checkout Session**: both. Session for the browser flow,
  direct PaymentIntent for the lifecycle suite. One extra branch in
  `POST /payments`.
- **Async model for ack-latency**: FastAPI `BackgroundTasks`. It runs
  in-process, so a crash between ack and processing loses the event. That's not
  a flaw, it's the fault-injection target for step 10. Documented as such, not
  discovered as a surprise mid-build.

## Known constraints

- Two different signing secrets exist: the CLI (`stripe listen`) secret for
  local dev, and the dashboard-registered secret for the deployed Render
  endpoint. Both go in `.env.example`, named clearly, so this isn't a debugging
  session later.
- Render/Railway free tiers spin down when idle. A cold start can make the first
  webhook delivery time out; Stripe retries, so state heals. A working demo of
  step 10, but noisy for live-demo timing and the ack-latency assertions. Either
  add a scheduled keep-warm ping or note the behavior in the README as a known
  constraint. Confirm current free-tier terms for both providers before
  committing, since they change.
- Stripe test mode rate limits at roughly 25 requests/second. Live-API suites
  (lifecycle, error taxonomy) run serially. Fixture suites hit the receiver, not
  Stripe, so they parallelize freely.
- GitHub Actions doesn't expose secrets to fork PRs. Live-API jobs are gated to
  pushes on my own branches, and the README says why.
- Fixtures drift when Stripe changes payload shape. A weekly scheduled job
  re-captures or diffs against live.
- Reordering and stale-event handling depend on transition-table precedence,
  with `event.created` as tiebreaker. This is business logic in the receiver,
  not test scaffolding.

## Operational details

- Structured logging on every webhook: event ID, payment ID, state before/after.
  Needed for debugging race tests; painful without it.
- `.env.example` committed with every variable named, before the first real commit.
- Allure on Pages needs history/trend handling configured across CI runs, or the
  trend charts stay empty. Set this up in step 7, not discovered later.

## Prerequisites

**Accounts and tools**

- Stripe account with a sandbox enabled. Test mode needs an email only, no bank
  details or identity verification.
- Stripe CLI installed and authenticated (`stripe login`). Verify
  `stripe listen --print-secret` returns a value before writing any code, since
  that secret backs the entire fixture and signature suite.
- GitHub repo with Actions enabled, secret key and webhook secret stored as repo
  secrets.
- Python 3.11+, virtualenv.
- `.env` in `.gitignore` before the first commit.

**Concepts to have solid**

- HMAC signature verification: what `stripe.Webhook.construct_event()` checks and why
- Idempotency key behavior, including Stripe's 24-hour key expiry
- SQLite WAL mode and locking under concurrent writes
- Python concurrency for I/O-bound work (`concurrent.futures.ThreadPoolExecutor`)
- Playwright's `APIRequestContext`, distinct from its browser API
- State machine design for legal payment transitions

---

# v1: ship and link

Seven steps to something demoable and linkable. This is the version that goes on
the resume. Timebox each step (2 to 4 focused days); when the box ends, cut
scope to fit and commit. Every step should produce something committable.

**1. Foundation.** FastAPI + SQLite (WAL). Endpoints scaffolded, including
`/health`. Stripe sandbox created, CLI authenticated, signing secret captured.
API version pinned. Repo, venv, pytest and Playwright config. `.env` ignored,
`.env.example` committed.

**2. Transition table.** States by events, legal and illegal, written in `/docs`
before any handler code. Include the precedence ranking that resolves ordering.
This table is the ordering mechanism, not just documentation.

**3. Lifecycle suite.** Create, confirm, capture, cancel, refund against live
test mode. Serial. Green before touching webhooks.

**4. Receiver, signatures, and reorder/race suite.** Implement the state machine
off the table. Signature tests: valid, tampered, tolerance boundary at 299s and
301s. Wire CLI forwarding and confirm verification manually end to end. Then the
four hand-written cases against locally signed payloads: reordering, duplicate
event ID, stale event after newer, true concurrency via threads. This is what
makes the README's headline claim true before v1 ships.

**5. Checkout and Playwright.** Minimal front end, Pay button, hosted Checkout,
success page. Browser test fills `4242 4242 4242 4242`, submits, then polls
introspection and asserts final state. Add the decline card
(`4000 0000 0000 0002`) and assert the error surfaces to the user with no
payment record created. Trace and video on failure.

**6. Idempotency suite.** Same key same payload, same key different payload
returns 400, concurrent duplicates produce one charge.

**7. CI, deploy, README.** Actions workflow: live suites serial, browser suite
separate and non-blocking. Deploy to Render for a live URL and a real webhook
endpoint. Allure published to Pages, history/trend config verified. README with
architecture diagram, demo GIF, live link.

**Ship gate. Put it on the resume before starting v2.**

---

# v2: depth

Added while already interviewing. Each step is independently shippable.

**8. Fixture capture.** Run real flows through the CLI, capture signed payloads,
save as JSON. Add the weekly drift job. Used to expand CI's fixture-replay
coverage beyond what v1's locally-signed payloads already cover.

**9. Property-based sequencing.** Hand the transition table to Hypothesis and
generate sequences on top of the four hand-written cases from step 4.
Invariants: state never regresses, terminal states absorb, final state is
delivery-order independent.

**10. Failure modes.** Fault injection between state write and commit, return
500, let Stripe retry, assert state heals. Ack-latency threshold on `/webhook`
so slow processing doesn't trigger a retry storm.

**11. Error taxonomy.** Decline codes, rate limit, invalid request. Optionally
the 3DS card (`4000 0025 0000 3155`) through the browser, which forces an iframe
challenge.

**12. Mutation testing.** `mutmut` against the state machine module. Nightly
job, not per-push, since it reruns the suite once per mutant. Publish the score
in the README and explain the survivors. Documenting why a survivor was accepted
is worth more than the number.

**13. Bug writeup.** One real bug found by step 9 or 10. Repro steps, expected
vs actual, severity, root cause, fix, regression test. One page in `/docs/bugs/`.

**14. Polish.** `TEST_STRATEGY.md` covering risk-based prioritization, what's
out of scope and why, equivalence classes and boundaries. README opens with why
the problem is hard. Closing section on what would change at scale: Postgres
over SQLite, queue-backed processing, dead-letter handling.

---

## What the README leads with

Interviewers spend about three minutes before deciding. In order:

1. One sentence on why the problem is hard (at-least-once, unordered delivery)
2. Demo GIF of the Checkout flow
3. Architecture diagram
4. Live URL
5. Mutation score and coverage badge
6. Link to the published Allure report
7. Link to the bug writeup
8. The real-vs-fixture CI split and the reasoning behind it

By the ship gate, items 1 and 8 are both backed by working tests. The reorder
suite in step 4 covers item 1, and the fixture-vs-live split from step 7 covers
item 8. Nothing on this list is a claim without a test behind it at the point it
goes on the resume.
