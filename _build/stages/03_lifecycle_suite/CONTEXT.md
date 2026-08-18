# 03_lifecycle_suite — the real API, serially

One job: exercise the full payment lifecycle against live Stripe test mode, and
confirm the object model before any webhook handling depends on it.

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../02_transition_table/RESULT.md
- Reference (every run): ../../_shared/conventions.md
- Reference (rate limits, API version): ../../_shared/stripe-facts.md

Do NOT load: `../../_shared/scope-original.md`, `service/state_machine.py`, any
webhook code. This stage does not touch our receiver at all. It talks to Stripe
directly, and keeping it that way is what makes it a clean baseline.

## Process

1. Create `tests/lifecycle/`.
2. Mark every test `@pytest.mark.live` and register the marker in the pytest
   config. Stage 07's CI splits on this marker, so getting it right here is what
   makes that split possible later.
3. Configure the suite to run **serially**. Stripe test mode rate limits, and a
   parallel run that trips the limit produces failures that look like bugs.
4. Cover: create, confirm, capture (use a manual-capture PaymentIntent so
   capture is a distinct step), cancel, refund.
5. Assert on the Stripe object's `status` at each step, and record in
   `RESULT.md` which statuses the real API actually returned. Stage 02's table
   was written from documentation; this is the first contact with reality, and
   any mismatch is a finding worth recording rather than quietly accommodating.

## Outputs

- `tests/lifecycle/` with the five lifecycle tests
- Marker registration in the pytest config
- `_build/stages/03_lifecycle_suite/RESULT.md`

## Verify

```
pytest -m live
```

Green, with no receiver code involved.

## Human check

Open the Stripe dashboard's test-mode payments list and confirm the objects the
suite created are actually there, in the states the tests asserted. A suite that
passes against a mocked-out client would look identical from the terminal, and
this is the check that distinguishes them.
