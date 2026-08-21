# 02_transition_table: write the oracle first

One job: the states-by-events table, legal and illegal, written **before** any
handler code. It is the oracle for stage 04b, and later for Hypothesis (v2 step
9) and mutation testing (v2 step 12). Everything downstream is cheaper because
it exists.

Timebox: 2 to 4 focused days. Most of it is thinking, not typing.

## Inputs

- Working (this run): ../01_foundation/RESULT.md
- Reference (every run): ../../_shared/conventions.md
- Reference (read D-006 and D-007): ../../DECISIONS.md

Do NOT load: `../../_shared/scope-original.md`, any test suite, any Playwright
config. No webhook handling is written in this stage.

## Process

1. Write `docs/transition-table.md`. This is the table's one home. It ships as
   documentation and later feeds Hypothesis and mutmut, so it lives in the
   product tree, not the factory.
2. States: `requires_payment_method`, `requires_confirmation`,
   `requires_action`, `processing`, `requires_capture`, `succeeded`, `canceled`,
   `refunded`.
3. Events: the `payment_intent.*` family, `charge.refunded`,
   `checkout.session.completed`, `checkout.session.expired`.
4. **Precedence rank**: an integer per state. Higher wins. Terminal states
   absorb. State never regresses. `event.created` is a tiebreaker only, used
   when two events rank equal. This ranking is the ordering mechanism, not
   documentation of one (`D-007`).
5. Legal and illegal transitions, both stated explicitly. An illegal transition
   left unstated is a gap in the oracle, and stage 04b cannot test against a gap.
6. Session-to-PaymentIntent mapping, since PaymentIntent is canonical (`D-006`).
   `checkout.session.completed` maps onto the PaymentIntent record.
7. `service/state_machine.py`: mirror the table as a plain dict plus an
   `apply()` function. This is the module a reader is meant to study, so name
   things clearly and comment the ordering rules.
8. `tests/test_table_matches_code.py`: parse the markdown table, assert it
   matches the dict. Roughly thirty lines. It is the cheapest available guard on
   the project's central claim, since a doc that has drifted from the code is
   worse than no doc. Cut it if it reads as ceremony, and record that in
   `RESULT.md` if you do.

## Outputs

- `docs/transition-table.md`
- `service/state_machine.py`
- `tests/test_table_matches_code.py`
- `_build/stages/02_transition_table/RESULT.md`

## Verify

```
pytest tests/test_table_matches_code.py
```

## Human check

Pick two events that could plausibly arrive in either order, for example
`payment_intent.succeeded` and `checkout.session.completed`. Trace both
orderings through the table by hand and confirm they land on the same final
state. If they do not, the precedence ranking is wrong, and finding that now
costs an hour instead of costing stage 04b entirely.
