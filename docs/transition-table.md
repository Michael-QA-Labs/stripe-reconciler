# Payment state transition table

This table is the oracle. The receiver's ordering behaviour is defined here
first, in a form a person can read, and `service/state_machine.py` mirrors it.
The suites that prove unordered and duplicate delivery are handled test against
this table, not against the handler's opinion of itself.

Stripe guarantees at-least-once delivery, not ordered delivery. So the table
cannot be a list of "what happens next". It has to answer a harder question:
given an event that may be a duplicate, may be stale, and may have overtaken
three others, what is this payment's state now?

## The rule

Every state carries an integer rank. An event claims a state. That claim is
applied only if it ranks **strictly higher** than the state already recorded.
Anything equal or lower is absorbed, meaning it is logged and discarded.

That single rule produces the three properties the receiver needs:

- **State never regresses.** Lower ranks cannot be applied, by definition.
- **Duplicates are harmless.** A repeated event has equal rank, so it cannot
  advance anything. This holds even if the `processed_events` dedupe misses,
  which makes the two mechanisms independent rather than layered.
- **Order does not matter.** The final state is the highest rank among the
  events received, which is a property of the set, not of the sequence. Any
  delivery order of the same events reaches the same state.

The last one is the claim the project exists to demonstrate, so it is worth
being precise: this is not "we cope with reordering". It is that reordering
cannot change the outcome, because the outcome never depended on order.

## States and ranks

Higher rank wins. The gaps between numbers leave room to insert a state without
renumbering.

| State | Rank | Defined by |
|---|---|---|
| `requires_payment_method` | 10 | Stripe |
| `requires_confirmation` | 20 | Stripe |
| `requires_action` | 30 | Stripe |
| `requires_capture` | 40 | Stripe |
| `processing` | 50 | Stripe |
| `canceled` | 60 | Stripe |
| `succeeded` | 70 | Stripe |
| `refunded` | 80 | this project |

Two things about that table are not obvious.

**`refunded` is ours, not Stripe's.** The PaymentIntent `status` enum has seven
values and `refunded` is not among them. Refunds live on the Charge and Refund
objects. Since the PaymentIntent is the canonical record here (`D-006`), a
refund has to land somewhere, and it lands as a state ranked above `succeeded`.

**`requires_capture` ranks below `processing`.** Manual capture reaches
`requires_capture` when funds are authorized, and the Stripe lifecycle
documentation says that "attempting to capture the funds moves it to
`processing` or `succeeded` depending on the payment method". So authorization
precedes processing, not the other way round.

## Events and what they claim

| Event | Claims state |
|---|---|
| `payment_intent.created` | `requires_payment_method` |
| `payment_intent.requires_action` | `requires_action` |
| `payment_intent.amount_capturable_updated` | `requires_capture` |
| `payment_intent.processing` | `processing` |
| `payment_intent.partially_funded` | `processing` |
| `payment_intent.canceled` | `canceled` |
| `payment_intent.succeeded` | `succeeded` |
| `payment_intent.payment_failed` | `requires_payment_method` |
| `checkout.session.completed` | `processing` |
| `checkout.session.expired` | `canceled` |
| `charge.refunded` | `refunded` |

**No event claims `requires_confirmation`.** There is no
`payment_intent.requires_confirmation` event type. The state is real, and the
lifecycle documentation notes that "most integrations skip this state", but it
is observable only in API responses, which is where the stage 03 lifecycle suite
sees it. No webhook can produce it.

**An unknown event type claims nothing.** It is absorbed and logged, leaving
state untouched. The table is total: every input has a defined outcome.

**A payment seen for the first time** has no recorded state, so the first event
to arrive is applied whatever it claims. A payment whose first event is
`payment_intent.succeeded` starts at `succeeded`. That is correct, not a gap:
the earlier events either arrive later and are absorbed, or never arrive at all.

## Illegal transitions

Ranking already refuses everything that would move a payment backwards, so the
only transitions worth calling illegal are the ones that move *forwards* and
still cannot be real.

There is exactly one such case: **any transition out of `canceled`.**

Stripe is explicit that "a PaymentIntent can't be canceled after it has
succeeded", and that cancellation "can't be undone". So `canceled` is genuinely
terminal. A `succeeded` or `charge.refunded` event arriving for a payment
already recorded as `canceled` outranks it and is applied, because the
alternative is discarding evidence that money moved. But it is recorded as
illegal, because it means one of three things went wrong:

- two PaymentIntents were conflated through the session mapping,
- a payload was replayed,
- or the receiver has a bug.

All three deserve to be visible. `apply()` therefore reports two things that are
easy to confuse and must stay separate: **what state the payment is in**, and
**whether the path it took to get there was legal**.

Every other forward jump is legal, including jumps that skip states. A payment
that goes straight from `requires_payment_method` to `succeeded` has not done
anything wrong, it has simply had its intermediate events delivered late or not
at all. Flagging those would fire the anomaly on every reordered delivery and
teach a reader to ignore it.

## Where this table diverges from Stripe

Two Stripe transitions are legitimate and this table refuses them. Both are
regressions, and both are refused by the same rule that makes ordering work.
They are stated here rather than discovered later.

**1. A failed payment attempt.** Stripe documents that "if the payment attempt
fails (for example, due to a decline), the PaymentIntent's status returns to
`requires_payment_method` so that the payment can be retried". Rank 10 cannot
beat anything already recorded, so `payment_intent.payment_failed` is absorbed
for any payment past its first state.

**2. Manual confirmation after an action.** With `confirmation_method: manual`,
a PaymentIntent "returns to the `requires_confirmation` state after handling
`next_action`s". Rank 20 cannot beat `requires_action` at 30, so that regression
is absorbed too.

The consequence is worth stating plainly: **the recorded state is a high water
mark, the furthest progress ever observed, not Stripe's instantaneous status.**
For reconciliation, which is what this service does, the high water mark is the
useful number. A payment that reached `succeeded` did receive money, whatever
happened afterwards. Anything needing live status should read the PaymentIntent
from the API instead.

**Partial refunds collapse.** `charge.refunded` is "sent when a charge is
refunded, including partial refunds", so a payment refunded by one cent is
recorded identically to one refunded in full. Modelling that properly needs a
`partially_refunded` state and an amount comparison, which v1 does not do.

## Checkout sessions map onto the PaymentIntent

Hosted Checkout emits `checkout.session.*` events alongside the underlying
`payment_intent.*` events, and the two streams can arrive in either order. The
PaymentIntent is the canonical record (`D-006`), so session events are resolved
to the PaymentIntent they belong to and applied to that record.

- `checkout.session.completed` claims `processing` rather than `succeeded`. The
  session completing means the customer finished the flow, not that funds
  settled. Claiming `processing` lets the PaymentIntent's own events carry the
  outcome, and guarantees the session event can never overshoot the truth.
- `checkout.session.expired` claims `canceled`. Expiry is how a Checkout
  PaymentIntent gets invalidated, and Stripe's internally generated
  `cancellation_reason` values include `expired`.

## Ties

`event.created` breaks ties when two events rank equally. Because ranks are
unique per state, equal rank means both events claim the *same* state, so the
tiebreak never changes the resulting state. It decides which event is recorded
as responsible for the transition.

This matters less than it sounds, and that is the point: if the tiebreaker could
change the outcome, the outcome would depend on clock accuracy across Stripe's
infrastructure. It cannot, so it does not.

## Worked orderings

Each pair below is the same set of events delivered in two different orders.

| Events, in delivery order | Final state | Illegal |
|---|---|---|
| `payment_intent.created`, `payment_intent.processing`, `payment_intent.succeeded` | `succeeded` | no |
| `payment_intent.succeeded`, `payment_intent.processing`, `payment_intent.created` | `succeeded` | no |
| `payment_intent.succeeded`, `payment_intent.canceled` | `succeeded` | no |
| `payment_intent.canceled`, `payment_intent.succeeded` | `succeeded` | yes |
| `checkout.session.completed`, `payment_intent.succeeded` | `succeeded` | no |
| `payment_intent.succeeded`, `checkout.session.completed` | `succeeded` | no |
| `payment_intent.succeeded`, `charge.refunded` | `refunded` | no |
| `charge.refunded`, `payment_intent.succeeded` | `refunded` | no |
| `payment_intent.succeeded`, `payment_intent.succeeded` | `succeeded` | no |
| `charge.refunded`, `payment_intent.processing` | `refunded` | no |
| `payment_intent.processing`, `payment_intent.payment_failed` | `processing` | no |
| `payment_intent.canceled`, `charge.refunded` | `refunded` | yes |

The `Illegal` column records whether any event in that ordering was applied over
a `canceled` state. It is asserted by `tests/test_table_matches_code.py`, so
these rows are executable, not illustrative.

Every pair converges. The `canceled` and `succeeded` pair converges *and* the
impossible ordering is flagged, which is the case that motivated separating
state from legality.

## Events deliberately not in this table

Named here so their absence reads as a decision rather than an oversight.

| Event | Why not |
|---|---|
| `checkout.session.async_payment_succeeded` | the underlying `payment_intent.succeeded` already carries this |
| `checkout.session.async_payment_failed` | same, via `payment_intent.payment_failed` |
| `refund.created`, `refund.updated`, `refund.failed` | refund lifecycle detail beyond the single `refunded` state v1 models |
| `charge.refund.updated` | deprecated by Stripe in favour of `refund.updated` |
| `charge.dispute.*` | disputes are not modelled in v1 |

## Sources

Every Stripe fact above was read from the documentation for the pinned API
version `2026-07-29.dahlia`, not recalled. The status enum comes from the
PaymentIntent object reference, the failure and capture behaviour from the
intent lifecycle page, the cancellation rules from the cancel endpoint
reference, and the refund event behaviour from the refunds guide.

The one thing no Stripe document decides is `succeeded` outranking `canceled`.
Stripe forbids that transition, so it has no opinion on what a receiver should
record if it ever sees it. Ranking `succeeded` higher means a stale
cancellation can never void a payment that took money.
