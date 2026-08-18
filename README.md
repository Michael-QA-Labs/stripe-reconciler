# stripe-reconciler

A Stripe webhook receiver that implements its own event sequencing and
idempotency logic, plus the test suite that proves the logic works.

## Why this problem is hard

Stripe guarantees at-least-once delivery. It does not guarantee ordered
delivery. In practice that means three things happen to every production
webhook endpoint, and all three look like the same symptom (a payment stuck in
the wrong state) from the outside:

1. **The same event arrives more than once.** A retry after a timeout, or a
   redelivery, hands you an event id you have already processed. Processing it
   twice double-counts a capture or a refund.
2. **Events arrive out of order.** `payment_intent.succeeded` can land before
   the `payment_intent.processing` that preceded it. Handling each event as it
   comes, without asking whether it is stale, lets a payment regress from a
   settled state back to an in-flight one.
3. **Events arrive late.** An event delayed past a retry window can show up
   after the payment has already reached a terminal state, and must be absorbed
   rather than applied.

None of that is solved by Stripe's SDK. Signature verification proves an event
is authentic; it says nothing about whether the event is current. The
sequencing rule, the dedupe, and the idempotency store are the receiver's own
responsibility, which makes them the receiver's own bugs. This project writes
that logic explicitly, as a transition table where terminal states absorb and
state never regresses, and then tests it against duplicate, reordered, and late
delivery rather than asserting it works.

## Status

In progress. The service skeleton, the schema, and the health check exist; the
sequencing logic and its suites do not yet.
