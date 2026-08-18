# 04b_reorder_race — make the headline claim true

One job: prove that the final state is independent of delivery order. This is
the stage the README's opening sentence rests on. Without it, the project claims
something it has not tested.

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../04a_receiver_signatures/RESULT.md
- Working (from stage 04a): ../../../tests/helpers/signing.py
- Working (the oracle, from stage 02): ../../../docs/transition-table.md
- Reference (every run): ../../_shared/conventions.md
- Reference (read D-007): ../../DECISIONS.md

Do NOT load: `../../_shared/scope-original.md`, anything Playwright, anything
about fixtures. **No captured fixture files in v1.** The signing secret is known
locally, so every payload here is constructed and signed at test time. Fixture
capture is v2 step 8, and reaching for it now is scope creep that also needs a
live listener.

## Process

Four hand-written cases in `tests/webhook/test_ordering.py`. All four run
against the local receiver with locally signed payloads. No live listener.

1. **Reordering**: deliver `payment_intent.succeeded` before
   `payment_intent.processing`. Final state is `succeeded` under both orderings.
2. **Duplicate event id**: deliver the same event twice. One state change, one
   record in `payments`, one row in `processed_events`.
3. **Stale after newer**: deliver an older event after a terminal state has been
   reached. It is absorbed, not applied. State does not regress.
4. **True concurrency**: `ThreadPoolExecutor` firing conflicting events
   simultaneously at the same payment. No interleaved corruption, and the final
   state is legal under the table.

The invariant across all four: **final state is independent of delivery order.**

If a `database is locked` error appears, check that WAL mode from stage 01 is
actually on before treating it as a state machine bug. That distinction is why
WAL was set up in stage 01 rather than here.

## Outputs

- `tests/webhook/test_ordering.py`
- `_build/stages/04b_reorder_race/RESULT.md`

## Verify

```
pytest tests/webhook/
pytest tests/webhook/test_ordering.py --count 20    # concurrency is not proven by one pass
```

## Human check

Temporarily delete the precedence check in `service/state_machine.py` and rerun.
**Record in `RESULT.md` which of the four cases still passed.** Any case that
survives without precedence is not testing what it claims to, and needs
strengthening before this stage closes.

This is a poor-man's mutation test and a preview of v2 step 12. It is also the
only cheap way to know whether the suite has teeth, since all four cases passing
is exactly what a suite that asserts nothing looks like.
