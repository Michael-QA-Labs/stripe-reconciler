# 05_checkout_playwright: RESULT

**Completed** 2026-08-20. Stage 06 is now current.

A real browser drives a real card through Stripe hosted Checkout, and the
resulting server-side state is asserted over HTTP against our own receiver.
The stage also proved one of the contract's own assertions false, which is
recorded below because it is the more useful result.

## What exists now

| Item | State |
|---|---|
| `web/` | three pages plus a shared stylesheet, served at `/app` |
| `service/main.py` | Checkout Session branch on `POST /payments`, `StaticFiles` mount |
| `tests/browser/test_checkout.py` | three tests, marked `live`, spawning their own receiver and listener |
| `requirements.txt` | `playwright==1.62.0`, `pytest-playwright==0.9.0`, exact pins |
| Suite | 75 passing by default, 7 live deselected (5 lifecycle, 2 browser) |

Three things settled here that stage 06 and 07 lean on:

- **`POST /payments` has two branches and only one is built.** Checkout is
  this stage's and works. Direct PaymentIntent creation is stage 06's and still
  answers 501, so `test_payments_endpoint_exists_and_is_not_implemented` needed
  no edit and no file outside this stage's outputs was touched.
- **The static mount is at `/app`, not `/`.** A root mount is a catch all that
  answers every unmatched path, which turns the honest 501 and 404 responses
  into whatever the static handler returns.
  `test_unknown_route_is_404_not_501` caught exactly that when the mount was
  briefly at `/`. The OpenAPI schema still lists exactly three routes, so
  `D-013`'s argument that the introspection gate is structural is unaffected.
- **The browser tests spawn their own receiver and listener.** They have to run
  against a local instance: the introspection endpoint is registered only under
  `TESTING` and is genuinely absent on the deployment, so there is nothing on
  Render to poll. That is the gate working, not a gap.

## Verification output

```
$ .venv/bin/pytest tests/browser -m live --headed --video=on
3 passed in 25.88s

$ .venv/bin/pytest tests/browser -m live
3 passed in 23.77s

$ .venv/bin/pytest -q
75 passed, 7 deselected in 0.42s
```

Headed and headless both pass, which is the surprise the contract wanted
surfaced here rather than in stage 07's CI.

## The contract asserted something false, and it was corrected

Contract step 3 asked the decline case to assert that **no payment record is
created**, and called that "the assertion that matters". It is false.

A declined card still has a PaymentIntent behind it. Driving
`4000 0000 0000 0002` through the real page, Stripe delivered:

```
--> charge.failed
--> payment_intent.created
--> payment_intent.payment_failed
```

All three are registered on the destination and modelled in the table. The last
two claim `requires_payment_method`, so the receiver creates a record, and rank
10 is the correct state for it:

```
{"state":"requires_payment_method","amount":2000,"anomaly_count":0}
```

The intent behind the original wording is right: a decline must not look like a
payment. The assertion that expresses it is a claim about **state**, not about
absence. The test now asserts the record sits at `requires_payment_method` and
is not in any paid state.

Worth being blunt about why this mattered. Written as specified, the test would
have failed on its first honest run, and the obvious way to make it pass is to
stop recording failed payments, which would have thrown away the evidence that
a payment was attempted at all. A contract can be wrong, and a test written to
satisfy a wrong contract is worse than no test.

## The thesis happened again, live, in the browser flow

The successful payment delivered its events in this order:

```
--> charge.succeeded
--> payment_intent.succeeded
--> payment_intent.created        <-- after succeeded
--> checkout.session.completed
--> charge.updated
```

`payment_intent.created` arrived **after** `payment_intent.succeeded` for the
second time in this project, and the record reads `succeeded` with
`anomaly_count: 0`. Real out of order delivery, in a real browser flow, absorbed
correctly and without being constructed.

`checkout.session.completed` arrived after `payment_intent.succeeded` too. It
claims `processing` at rank 50 against `succeeded` at 70, so it was absorbed
exactly as the table said it would be.

**This closes 04a's open question 4.** Session to PaymentIntent resolution was
implemented from documentation and had never been observed. It is now: the
session event carried a `payment_intent`, resolved to the right record, and was
absorbed on rank.

## What the real page required, none of it in the contract

1. **Hosted Checkout takes roughly fifteen seconds to render headless.** Every
   DOM probe before that reads a skeleton. The skeleton contains a card
   accordion that reports itself **open** while no card fields exist, which
   sends you looking for an iframe that is not there. Screenshotting the page
   was what ended twenty minutes of wrong theories.
2. **No payment method is preselected**, and the card radio sits under an
   accordion button that intercepts pointer events. `check(force=True)` on the
   radio is what works; clicking the label or the button does not.
3. **Link enrolment is checked by default**, which makes phone number a
   required field and silently blocks submission. Unchecking it keeps an
   unrelated dependency out of the payment path.
4. **Two obvious locators are traps.** `get_by_label("CVC")` also matches the
   card icon's `aria-label` and trips strict mode. A button named `Pay` also
   matches the hidden Apple Pay button, and `.first` picks the hidden one. Both
   are addressed by role with an exact name, which the contract's role-only
   constraint was already pushing toward.

## Gotchas hit

**The verify command as written ran zero tests.** Browser tests drive real
hosted Checkout, so conventions make them `live`, and `pyproject.toml`
deselects that marker by default. `pytest tests/browser` collected nothing and
reported success. Corrected in the contract to `-m live`, with the reasoning
recorded beside it. A command that passes by running nothing is the worst
available failure mode, because it looks like the best one.

**A leaked pipe failed the suite after it passed.** The listener's stdout was
left to the garbage collector, which raises an ignored `ResourceWarning` during
teardown, and `filterwarnings = ["error"]` turns that into an error. The run
reported `2 passed, 1 error`. Closed explicitly in the fixture.

**Checkout parameters could not be verified from the SDK.** stripe 15.5.0 ships
no introspectable param classes for this resource, and the CLI's local help
covers only 19 common flags, including neither `line_items` nor `cancel_url`.
They were confirmed by a real call against the sandbox instead. Related:
`StripeClient.checkout` is deprecated in favour of `StripeClient.v1.checkout`,
and since warnings are errors the old spelling fails the suite rather than
merely aging badly.

## Deviations from the contract, stated rather than buried

- **A third scenario was added rather than padding to the contract's count.**
  The contract names two scenarios and asks for three to five tests. The gap
  was closed with abandonment, not by splitting an assertion across two tests
  sharing a payment, which would make them order dependent and turn one defect
  into two red tests. Abandonment earns its place: it is the one case where
  asserting that **no record exists** is correct, because the customer leaves
  before paying and Stripe never creates an intent. It is the assertion the
  contract originally wanted, applied to the case where it holds.
- **`web/_style.css` is no longer a deviation.** `conventions.md` now states
  that an Outputs list names principal artifacts and that a supporting file
  serving one of them is implied, while anything else is not. The stylesheet
  serves the three named pages.
- **The GIF exists.** 900 by 506, 17 seconds, 552KB, built from the headed
  recording with `ffmpeg` and `gifski`. It is held outside the repo pending a
  decision on where a committed binary should live, since the convention above
  says a committed asset is named or asked about rather than assumed.

## Closed here, and open questions for stage 06

1. **The human check is discharged.** Michael watched the headed run end to
   end on 2026-08-20 and confirmed it working: the browser reaches Stripe's
   own hosted page rather than a local form, and the success assertion happens
   after the redirect back. Every gate this stage carries is now closed.
2. **`checkout.session.expired` is still not registered** on the destination,
   10 of 11 modelled events. It fires only when a session is abandoned for
   24 hours, so neither browser test can produce one. It remains the only
   modelled event never observed.
3. **The demo now exists but is not yet the ship gate's demo.** `/app` serves a
   working flow against the deployment, but the ship gate asks for something
   someone can watch end to end. What that is was meant to be defined at this
   stage; the recordings are the raw material and stage 07 has to decide the
   form.
4. **Browser tests are excluded from the default run by marker, not by
   directory.** Stage 07's CI split must select on `-m live` and also run
   `playwright install chromium`, or collection passes and the launch fails.
