# 05_checkout_playwright: the browser flow

One job: a real browser drives a real card through Stripe hosted Checkout, and
the resulting server-side state is asserted over a different protocol. That
cross-protocol assertion is what makes Playwright load-bearing here rather than
decorative.

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../04b_reorder_race/RESULT.md
- Reference (every run): ../../_shared/conventions.md
- Reference (test cards): ../../_shared/stripe-facts.md
- Reference (read D-006, session to PaymentIntent mapping): ../../DECISIONS.md

Do NOT load: `../../_shared/scope-original.md`, the ordering suite, the
signature suite. This stage does not modify the state machine.

## Process

1. Create `web/`: `index.html` with a Pay button, plus success and cancel pages.
   Minimal on purpose. Serve them from FastAPI with `StaticFiles`.
2. Add the Checkout Session branch to `POST /payments`, alongside the existing
   direct PaymentIntent branch. Session events map onto the PaymentIntent
   record, per `D-006`.
3. `tests/browser/test_checkout.py`:
   - **Success**: fill `4242 4242 4242 4242`, submit, then **poll the
     introspection endpoint** until the final state arrives. The browser action
     causes an async webhook; the assertion happens over HTTP against our own
     service. Do not assert on the Stripe success page alone, which would prove
     only that Stripe works.
   - **Decline**: `4000 0000 0000 0002`. The error surfaces to the user **and
     the payment never reaches a paid state**.

     **Corrected 2026-08-20, having been observed.** This step originally read
     "and no payment record is created", calling that the assertion that
     matters. It cannot be written, because it is false. A declined card still
     has a PaymentIntent behind it, and Stripe delivers `charge.failed`,
     `payment_intent.created`, and `payment_intent.payment_failed`. All three
     are registered and modelled, and the last two claim
     `requires_payment_method`, so a record is created and rank 10 is the
     correct state for it.

     The intent behind the original wording is right: a decline must not look
     like a payment. The assertion that expresses it is a claim about state,
     not about absence. Assert the record sits at `requires_payment_method` and
     never reaches `processing`, `succeeded`, or `refunded`. Asserting absence
     would have failed on the first honest run and invited someone to weaken
     the receiver to make it pass.
4. Constraints, all deliberate:
   - **Role and label locators only.** No CSS or XPath. Stripe redesigns hosted
     Checkout without notice, and role locators are what survive it.
   - **Three to five tests, no more.** This is the flakiest surface in the repo
     and it is scoped to stay small.
   - Trace and video on failure.
5. Write a polling helper with a timeout rather than a fixed sleep. A sleep long
   enough to be reliable is long enough to be annoying, and one short enough to
   be pleasant is flaky.

## Outputs

- `web/index.html`, `web/success.html`, `web/cancel.html`
- The Checkout Session branch in `service/main.py`
- `tests/browser/test_checkout.py`
- `_build/stages/05_checkout_playwright/RESULT.md`

## Verify

```
pytest tests/browser -m live --headed
pytest tests/browser -m live         # must also pass headless, since CI is headless
```

Add `--tracing=retain-on-failure --video=retain-on-failure` for step 4's trace
and video. They are flags rather than config so an ordinary run writes nothing.

Both, and both pasted into `RESULT.md`. Passing headed but not headless is a
common and expensive surprise to hit in stage 07.

**`-m live` is not optional here, and the original commands omitted it.** These
tests drive real hosted Checkout, so conventions make them `live`, and
`pyproject.toml` deselects that marker by default. Without the flag the command
collects nothing and reports success having run no tests, which is the worst
available outcome: a green stage that proved nothing. The alternative, leaving
them unmarked so the bare command works, would make every default run and every
CI job drive a real browser against real Stripe, breaking the promise that a
plain `pytest` needs no network and no key.

## Human check

Watch the headed run once, end to end. Confirm the browser genuinely reaches
Stripe's hosted page rather than a local form, and that the success assertion
happens after the redirect back. Then record a short GIF of it; stage 07's
README needs one, and the flow is already on screen right now.
