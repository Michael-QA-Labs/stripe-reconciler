# 04b_reorder_race: RESULT

**Completed** 2026-08-19. Stage 05 is now current.

The README's opening claim is now tested rather than asserted: the final state
is independent of delivery order. The stage also found a defect that made the
claim untestable through the front door, which is recorded below because it is
the more interesting result.

## What exists now

| Item | State |
|---|---|
| `tests/webhook/test_ordering.py` | 17 tests across the four contract cases |
| `service/main.py` | blocking `handle()` moved off the event loop, see below |
| `tests/webhook/` | 37 tests: 5 signature, 4 resolution, 11 handler, 17 ordering |
| Suite | 73 passing, 5 live deselected |

The four cases, and what each is pinned by:

- **Reordering.** All six permutations of `created`, `processing`, `succeeded`
  converge on `succeeded`. The contract asked for one reversal; the full
  permutation set is run instead, because the claim is about the set and one
  reversal would leave the general case asserted only by argument.
- **Duplicate event id.** A replay carrying a claim that outranks the recorded
  state, so rank cannot absorb it and only the `processed_events` primary key
  can. An identical replay would prove nothing, which is the mutant that
  survived at stage 02.
- **Stale after newer.** Five event types delivered after `succeeded`, none
  applied, none flagged. `payment_failed` is the one worth naming: Stripe
  genuinely returns a failed intent to `requires_payment_method`, and the table
  refuses that regression on purpose.
- **True concurrency.** Five contradictory events fired at one payment at once,
  converging on `refunded` as the highest rank in the set.

`D-014`'s contradictory pair gets its own test. Both orders end at `succeeded`,
so state stays order independent; what differs is legality, and only
`canceled` then `succeeded` records an anomaly. That asymmetry is the entire
argument for the ranking, and it is now executable rather than reasoned.

## Verification output

```
$ .venv/bin/pytest tests/webhook/
37 passed in 0.48s

$ .venv/bin/pytest tests/webhook/test_ordering.py --count 20
340 passed in 4.62s

$ .venv/bin/pytest -q
73 passed, 5 deselected in 0.77s
```

## The defect this stage found: deliveries were never concurrent

Open question 1 carried into this stage said concurrency was designed for but
unproven, and that this is where the design fails if it is going to. It did.

`POST /webhook` was an `async def` that called the synchronous, blocking
`webhook.handle()` directly, which runs it on the event loop. Eight deliveries
fired at once measured **1 request in flight out of 8**, elapsed 0.48s against
a serial expectation of 0.40s. Every delivery was serialized. `BEGIN IMMEDIATE`
and WAL, in place since stage 01, had never once been exercised.

The suite could not have caught this, because serialization makes every
ordering test pass. It is visible only by measuring concurrency, not by
asserting on state.

Why it matters beyond the test: this is head of line blocking. One slow write
delays every other request including `/health`, and Stripe retries responses it
considers slow. Retries are duplicate deliveries, so the receiver would have
been manufacturing the exact failure it exists to absorb.

Fixed by handing the blocking call to the threadpool with
`starlette.concurrency.run_in_threadpool`. Re-measured: **8 of 8 in flight**,
0.14s. Case 4 then exercises real contention.

**This is a change to `service/main.py`, which is not in this stage's declared
outputs.** It is recorded here rather than done quietly. The alternative was to
test concurrency below the front door by calling `handle()` from threads
directly, which would have proved the database lock works while leaving the
receiver serialized in production and the contract's "all four run against the
local receiver" unmet. Conventions require a bug to ship with its regression
test in the same commit, and case 4 is that test: it is meaningless against the
serialized handler.

**Reviewed and kept, 2026-08-20.** The change stands. The process did not:
exceeding a contract's declared outputs is a conversation to have at the moment
the blocker is found, not something to flag in the writeup afterwards. Stage 07
legitimately owns `service/main.py` for CI and deploy, so that is where this
file's changes belong from here.

## The human check, and what it found

Deleting the precedence check in `service/state_machine.py`:

```
$ .venv/bin/pytest tests/webhook/test_ordering.py
11 failed, 6 passed
```

Six tests survive deterministically, and every one of them should:

| Survivor | Why it survives |
|---|---|
| `[created,processing,succeeded]` | the in-order control. A permutation set where every member died would mean the in-order case was missing |
| `[processing,created,succeeded]` | ends on `succeeded`, so last-writer-wins coincides with the right answer |
| `contradictory_pair[canceled-then-succeeded]` | ends on `succeeded`, and legality is decided by `STATES_NOTHING_LEAVES`, not by rank |
| `duplicate_event_id_is_dropped_by_id_and_not_by_rank` | targets dedupe, a mechanism the table deliberately keeps independent of rank |
| `duplicate_does_not_wedge_the_payment` | same, and ends on `succeeded` |
| `concurrent_deliveries_of_one_event_id_do_not_error` | asserts only that contention does not raise |

Case 4 is the one that needs stating carefully. It kills the mutant, but
**probabilistically: 17 of 20 repeats fail, 3 pass.** On a single run it can
survive by luck, and it did on the first attempt. This is why the contract's
Verify block specifies `--count 20`, and the figure is recorded so a future
single green run is not mistaken for proof.

A second mutation was run to give the dedupe cases the same treatment, since
removing precedence cannot test them. Replacing the `processed_events` insert
and its `IntegrityError` rollback with `INSERT OR IGNORE`, precedence intact:

```
$ .venv/bin/pytest tests/webhook/test_ordering.py
1 failed, 16 passed

FAILED test_a_duplicate_event_id_is_dropped_by_id_and_not_by_rank
```

Exactly one test, and the right one. The two mechanisms are now independently
pinned: precedence kills the ordering cases, dedupe kills the duplicate case,
and neither substitutes for the other.

## Gotchas hit

**A test of mine claimed more than it could see.** The concurrent duplicate
case was originally named `..._apply_it_exactly_once` and survived *both*
mutations, which by the contract's own rule means it was not testing what it
claimed. "Applied exactly once" is not observable here: with dedupe removed the
repeats are absorbed by rank instead, because a duplicate claims equal rank and
equal is not strictly higher. Nothing reachable through the introspection
endpoint distinguishes the two. Renamed to
`test_concurrent_deliveries_of_one_event_id_do_not_error` and its docstring now
states what it does not prove. The single threaded case is what proves dedupe,
by replaying an id with a claim that outranks the recorded state.

**"One row in `processed_events`" is asserted behaviourally, not by counting.**
Conventions forbid tests reading the database, and the introspection endpoint
exposes no such count. The handler proceeds past its dedupe insert only when
that insert succeeded, so a state that did not advance on a higher-claiming
replay is the observable form of the row already being there. Counting it
directly would need either a schema-coupled test or a new endpoint, and neither
is in this stage's outputs.

## Open questions for stage 05

1. **`amount` can stay NULL permanently.** Only a PaymentIntent payload states
   the amount, and only an unabsorbed event writes it. A payment whose first
   and highest-ranked event is `charge.refunded` is created with `amount` NULL,
   and every later PaymentIntent event is absorbed on rank, so the amount is
   never recorded. Correct per the table, which says absorbed events are logged
   and discarded, but it means `amount` is not reliably populated.

   **Resolved 2026-08-19 as `D-017`**, just after this stage closed. Fixed in
   the webhook write path rather than deferred: stage 06's job is
   `POST /payments` and the `idempotency_keys` table, so it never touches this
   code, and parking the bug there would have hidden it behind two unrelated
   stages. An absorbed event now fills a missing amount under
   `WHERE amount IS NULL`, so a known figure is never replaced.
2. **Concurrency is proven for SQLite on one process.** Render runs one
   instance, so this matches production today. Two instances against one SQLite
   file would not be covered by anything here, and `D-005` already says the
   live URL is a demo endpoint rather than a durable store.
3. **`checkout.session.*` ordering is modelled but untested against real
   payloads.** Both session events are in the table and in `EVENT_CLAIMS`, and
   the ordering suite exercises them only through hand-built payloads whose
   shape comes from documentation. Stage 05 is the first chance to confirm the
   shape empirically, and it inherits open questions 3 and 4 from 04a unchanged.
4. **The threadpool now bounds delivery concurrency.** `run_in_threadpool`
   defaults to 40 workers. That is far above anything the sandbox can generate
   at 25 req/s, so it is not a live constraint, but it is now the ceiling and
   worth knowing before stage 07 makes any throughput claim in the README.
