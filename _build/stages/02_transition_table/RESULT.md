# 02_transition_table — RESULT

**Completed** 2026-08-19. Stage 03 is now current.

## What exists now

| Item | State |
|---|---|
| `docs/transition-table.md` | the oracle. 8 states with ranks, 11 events, illegal set, divergences, 12 worked orderings |
| `service/state_machine.py` | `STATE_RANK`, `EVENT_CLAIMS`, `STATES_NOTHING_LEAVES`, `apply()` returning a `Transition` |
| `tests/test_table_matches_code.py` | 16 tests: parses the published tables, replays every worked ordering |
| `D-014` | `succeeded` outranks `canceled`, with the reasoning |

The mechanism, in one line: every state has a rank, an event claims a state, and
the claim applies only if it ranks **strictly higher** than what is recorded.

That single rule produces all three properties the receiver needs, rather than
needing three mechanisms:

- state cannot regress, because lower ranks cannot apply
- duplicates are harmless, because equal is not strictly higher
- delivery order cannot change the outcome, because the final state is the
  highest rank in the **set** of events received, which is not a property of
  their sequence

`apply()` reports state and legality separately. Ranking already refuses every
backwards move, so the only illegal case left is a forward one that still cannot
be real: leaving `canceled`.

## Verification output

```
$ .venv/bin/python -m pytest tests/test_table_matches_code.py -q
................                                                         [100%]
16 passed in 0.01s

$ .venv/bin/python -m pytest -q
.................................                                        [100%]
33 passed in 0.35s
```

**Human check passed.** Michael traced `payment_intent.succeeded` and
`checkout.session.completed` in both delivery orders against the rank table by
hand, then against `apply()`, and confirmed both orderings land on `succeeded`.

```
delivery order: checkout.session.completed then payment_intent.succeeded
    claims processing (rank 50) vs current None      -> APPLIED
    claims succeeded  (rank 70) vs processing (50)   -> APPLIED
    FINAL: succeeded

delivery order: payment_intent.succeeded then checkout.session.completed
    claims succeeded  (rank 70) vs current None      -> APPLIED
    claims processing (rank 50) vs succeeded (70)    -> ABSORBED
    FINAL: succeeded
```

## Gotchas hit

**Hand mutation testing found a real gap in the guard test.** Three mutants were
applied to `apply()`. Changing the `canceled` rank and removing the illegal
check both died. Changing `<=` to `<` **survived**: a re-applied duplicate lands
on the state it already held, so every final-state assertion still passed. The
difference was only visible in `absorbed`, which nothing checked.
`test_duplicate_event_is_absorbed_not_reapplied` now covers it, verified by
re-applying the mutant and watching it fail. Worth repeating at stage 04b, and
it is the argument for mutmut in v2.

**`requires_capture` ranks below `processing`, not above.** First draft had them
the other way. The lifecycle documentation settles it: capturing an authorized
payment "moves it to `processing` or `succeeded`", so authorization precedes
processing. Getting this backwards would have made every manual-capture flow
absorb its own `processing` event.

**`refunded` is not a Stripe status.** The PaymentIntent `status` enum has seven
values. Refunds live on the Charge and Refund objects. The table labels
`refunded` as this project's own state rather than implying Stripe defines it.

**`charge.refunded` fires for partial refunds too**, documented as "sent when a
charge is refunded, including partial refunds". So a payment refunded by one
cent records identically to one refunded in full. Documented as a v1 limitation;
`partially_refunded` would slot between 70 and 80 without renumbering.

**`charge.refund.updated` is deprecated** by Stripe in favour of
`refund.updated`, despite still appearing in the CLI's trigger list.

**Every Stripe fact was read, not recalled.** An earlier pass of this stage
asserted event mappings and failure behaviour from memory. That is exactly what
`_shared/stripe-facts.md` forbids, and two of the assertions would have gone
into the table unverified. The status enum came from the object reference, the
failure and capture behaviour from the lifecycle page, cancellation rules from
the cancel endpoint, refund event behaviour from the refunds guide.

## Open questions for stage 03

1. **`checkout.session.expired` is in the table but not registered on the
   destination.** The `render-deployment` destination listens to 10 events; the
   table models 11. This one is the gap. It is a two-click edit, and unlike the
   refund events it is now decided, because the table gives it a meaning.

2. **The other refund events stay off, and that is now settled.** The table
   deliberately does not model `refund.created`, `refund.updated`, or
   `refund.failed`. `charge.refunded` alone carries the single `refunded` state
   v1 has. No further destination changes are needed.

3. **Anomaly handling is settled, see `D-015`.** At 04a: flag, log, persist the
   anomaly, and define a `fetch_payment_intent` seam that is never called.
   Refetching itself is v2, out of band. Keeps `state_machine.py` pure, keeps
   the webhook response off the network, and keeps the anomaly path testable
   without live Stripe. 04a's contract now lists `DECISIONS.md` as an input,
   which it did not before, so this is actually reachable from that stage.

4. **`requires_confirmation` has no event and is unverified empirically.** No
   webhook can produce it. Stage 03 creates PaymentIntents directly and is the
   first place it can be observed in an API response, which is the chance to
   confirm the state is real rather than theoretical.

5. **A README boundary, recorded so it cannot drift** (`D-014`). Duplicate,
   reordered, and late delivery are what actually happen to a business and are
   the headline. The `canceled`/`succeeded` clash catches our own bugs and must
   not be presented alongside them as though it were a production scenario.

6. **`init_db()` is still never called**, carried forward from stage 01. Stage
   04a wires it at startup, test-first. Nothing here changed that: the state
   machine is pure and touches no database.
