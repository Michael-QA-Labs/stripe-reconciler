# The v1 pipeline

Nine stages, ending at a ship gate. Timebox each at 2 to 4 focused days. When
the box ends, cut scope and commit. Every stage leaves something committable.

## Why this project exists

Stripe guarantees at-least-once delivery, not ordered delivery. Events arrive
twice, arrive late, and arrive out of order. This receiver implements its own
sequencing and idempotency logic, and the test suite proves that logic works.
The tested logic is ours, not Stripe's, which is what makes the suite worth
reading.

## The stages

| # | Stage | Leaves behind |
|---|---|---|
| 00 | `00_prereqs` | Stripe CLI authenticated, signing secret captured, `.env.example` |
| 01 | `01_foundation` | FastAPI + SQLite WAL, four endpoints, **deployed to Render** |
| 02 | `02_transition_table` | `docs/transition-table.md` + `service/state_machine.py` |
| 03 | `03_lifecycle_suite` | create/confirm/capture/cancel/refund against live test mode |
| 04a | `04a_receiver_signatures` | webhook handler + signature suite incl. 299s/301s boundary |
| 04b | `04b_reorder_race` | the four ordering cases. Makes the headline claim true |
| 05 | `05_checkout_playwright` | hosted Checkout + browser tests |
| 06 | `06_idempotency` | `Idempotency-Key` handling on `POST /payments` |
| 07 | `07_ci_deploy_readme` | CI with three jobs, Allure on Pages, README |

## Factory and product

Two trees, deliberately separate.

- **Product**: `service/`, `web/`, `tests/`, `docs/`, `README.md`. What a
  recruiter opens. Nothing about the build process leaks into it.
- **Factory**: `_build/`. This tree. Committed, not gitignored, so it survives a
  machine change.

Where they overlap, one home per fact wins. The transition table's home is
`docs/transition-table.md`, because it ships as documentation and later feeds
Hypothesis and mutmut. `_shared/` links to it and does not copy it.

Product directories are created by the stage that first needs them, not up
front.

## Three deviations from the original scope

Recorded once, here, so nobody has to diff this against
`_shared/scope-original.md`.

1. **Deploy at stage 01, not stage 07.** As originally written, nothing is
   linkable for weeks and the two hardest environment problems (the dashboard
   webhook secret, cold-start latency) surface with no slack left. See `D-003`.
2. **Original step 4 splits into 04a and 04b.** Receiver plus state machine plus
   signature suite plus four concurrency cases does not fit one timebox. See
   `D-002`.
3. **Render's free tier has an ephemeral filesystem.** The original scope names
   cold starts but not this: the SQLite file is wiped on every spin-down and
   redeploy. It does not break v1, since tests run against a local instance, but
   it makes the live URL a demo endpoint rather than a durable store, and the
   README has to say so. See `D-005`.

## Stage contract shape

Every `stages/*/CONTEXT.md` carries four sections:

- **Inputs** — exact paths, split into working (from the previous stage) and
  reference (every run), plus an explicit *Do NOT load* line.
- **Process** — numbered steps, with hard limits restated.
- **Outputs** — repo-root-relative paths. Several stages write into the product
  tree rather than the factory.
- **Human check** — one concrete act, not "review the code".

At stage end, write `RESULT.md` beside the contract: what was built, the
verification command **with its actual pasted output**, gotchas hit, and open
questions. Decisions go to `DECISIONS.md` and get cited by id, not restated.

## Ship gate

v1 is done, and goes on the resume, when:

- [ ] All nine stages have a `RESULT.md`
- [ ] CI is green on a push
- [ ] The Render URL serves the full service
- [ ] Allure is published to Pages with a **populated** trend, verified across
      two consecutive runs
- [ ] The README leads with why the problem is hard, and every claim in it has a
      test behind it. Specifically: the unordered-delivery headline is backed by
      04b, and the real-versus-fixture CI split is backed by 07.
- [ ] **`_build/` scrubbed, file by file** (`D-009`). Nine `RESULT.md` files
      will have accumulated working notes. Anything that reads as private rather
      than as process gets cut.
- [ ] **Full-history secret scan**, not just a working-tree one:
      `git log -p | grep -nE 'sk_(live|test)_[A-Za-z0-9]|whsec_[A-Za-z0-9]{8}'`
      The pre-commit hook (`D-008`) only guards commits made with it enabled.
      This is the check that the repo is safe to make public.
- [ ] **A demo exists and has been run end to end**, not just a live URL that
      serves JSON. Someone opening the repo should be able to watch the thing
      work. What exactly the demo is gets defined at stage 05, once hosted
      Checkout exists and there is a flow worth showing.
- [ ] Repo flipped public, and only then

Then v2 (original steps 8 to 14) gets its own plan. Not before.
