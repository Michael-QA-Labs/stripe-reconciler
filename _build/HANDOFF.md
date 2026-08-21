# Handoff: stripe-reconciler

State as of **2026-08-20**. Written for whoever picks up stage 07, human or
agent. Facts only; anything reconstructable from the repo or git log is left out.

Companion doc: `strpesession_summary.md` holds the older carried-forward notes
from the compacted 2026-08-18/19 session. This file supersedes it for current
state.

---

## Where things stand

- **8 of 9 stages closed.** Current stage is `07_ci_deploy_readme`, not started.
- **Suite: 81 passing by default, 9 live-only** (90 collected).
  - live = 5 lifecycle + 3 browser + 1 idempotency
- **30 commits total, 10 unpushed.** Nothing since stage 04a has reached GitHub.
- **19 decisions** recorded in `DECISIONS.md`, `D-001` through `D-019`.
- Repo `Michael-QA-Labs/stripe-reconciler`, **private**, default branch `main`.
- Live URL responds but is **stale**: serving the pre-05 build (`/app/` 404s,
  `POST /payments` still 501). A push triggers the Render redeploy.

| # | Stage | Status |
|---|---|---|
| 00 | `00_prereqs` | closed |
| 01 | `01_foundation` | closed |
| 02 | `02_transition_table` | closed |
| 03 | `03_lifecycle_suite` | closed |
| 04a | `04a_receiver_signatures` | closed |
| 04b | `04b_reorder_race` | closed |
| 05 | `05_checkout_playwright` | closed, human check discharged |
| 06 | `06_idempotency` | closed |
| 07 | `07_ci_deploy_readme` | **current, not started** |

---

## Blocking stage 07

### Hard blocker, needs a human

- **`gh auth` lacks the `workflow` scope.** Token scopes are `gist, read:org,
  repo`. GitHub rejects any push containing `.github/workflows/`, so `ci.yml`
  can be written but not pushed. Needs an interactive browser flow:
  ```
  gh auth refresh -s workflow
  ```
- Consider adding `read:user` at the same time. Without it the account plan
  cannot be read, and the plan decides the Pages question below.

### Sequencing conflict in the plan

- 07's human check asks whether the Allure link works **from a logged-out
  browser**. The repo is private, Pages is not enabled, and Pages from a
  private repo needs a paid plan.
- The ship gate deliberately puts "flip public" **last**.
- **The full-history secret scan is already clean: 0 matches.** That was the
  real gate on flipping public.
- Three ways out: flip public earlier now the scan is clean (recommended, but
  effectively one-way and a human decision); publish Allure as a CI artifact
  and defer Pages until after the flip; or confirm the plan supports private
  Pages and keep everything private.

### Four approvals outstanding

1. **Add `allure-pytest` and `pytest-cov`.** Neither is installed; 07 needs
   both. `requirements.txt` is not in 07's Outputs, and conventions say a new
   dependency is named or asked about.
2. **Split `requirements.txt` into service and dev.** Render's `buildCommand`
   is `pip install -r requirements.txt`, which currently installs **pytest,
   pytest-repeat, httpx2, playwright, pytest-playwright** onto the production
   service. Playwright alone is a 40MB download the service never imports.
3. **Coverage badge source.** No Codecov account. Cleanest without a third
   party: emit coverage in CI and publish a shields endpoint JSON beside the
   Allure site, which depends on the Pages decision.
4. **Demo GIF placement.** Built, 900x506, 17s, 552KB, currently outside the
   repo. `docs/` is the natural home; the README needs it at position 2.

### Unblocked, can be written now

- `README.md` and `.github/workflows/ci.yml` are declared outputs. Writing
  needs no scope; only pushing does.
- Architecture diagram can be Mermaid, which GitHub renders natively. No
  binary, no dependency.

---

## Standing instructions from the user

- **Never change or write code outside the declared scope.** A stage's
  `Outputs` list is the scope. An out-of-scope defect gets reported, not fixed.
- **Raise it before, not after.** Exceeding scope is a conversation to have at
  the moment the blocker is found, not a thing to flag in the writeup once the
  diff exists.
- **Design options as bullets with pros, cons, and an explanation.** No
  multiple-choice widgets.
- **Verify Stripe facts from docs, CLI, or the API. Never from memory.**
- **Execute rather than guess.** Revise a proposal for gaps before running it.
- **Mimic a real business that would actually test for this** is the tiebreaker
  when a design call is genuinely open.
- More UI and visuals is better for the portfolio.
- A demo must exist and have been run end to end before the repo goes public.

---

## Security rules still in force

- **Never run `stripe config --list` bare.** To check a key exists:
  `stripe config --list | grep -c test_mode_api_key`.
- **`stripe listen` prints the signing secret in its startup banner.** Redact
  on read: `sed -E 's/whsec_[A-Za-z0-9]+/whsec_[REDACTED]/g'`.
- **`.env` is written by piping under `umask 077`**, verified with `wc -l`,
  never `cat`. Identify which signing secret a file holds **by length**:
  CLI = 70 chars, dashboard = 38. Both start `whsec_`, so the prefix proves
  nothing.
- Secrets never reach chat or a transcript. A transcript leak already forced
  one key rotation at stage 00.
- After any repo visibility change, **assert it** rather than trusting a flag:
  `gh repo view <name> --json visibility -q .visibility`.
- Pre-commit hook at `.githooks/pre-commit`, enabled with
  `git config core.hooksPath .githooks`. Greps staged **added** lines only.

---

## Conventions that were added mid-build

Both live in `_shared/conventions.md`, which every stage loads every run.

- **Cite a decision, route it.** A file citing `D-NNN` must list `DECISIONS.md`
  in its Inputs. Four of nine stages were wrong before this rule existed.
- **Outputs name principal artifacts.** A supporting file serving a named
  artifact is implied. Anything else, meaning a new module, endpoint,
  dependency, or committed asset, is named in the contract or asked about
  first.

---

## Decisions worth knowing

- `D-002` original step 4 split into 04a and 04b
- `D-003` deploy at stage 01, not 07
- `D-005` SQLite stays despite Render's ephemeral filesystem; the live URL is a
  demo endpoint, not a durable store, **and the README must say so**
- `D-006` PaymentIntent is the canonical record
- `D-007` order by state precedence, not raw timestamp
- `D-013` `/docs` and `/openapi.json` stay public; the schema listing exactly
  three routes is the evidence the introspection gate is structural
- `D-014` `succeeded` outranks `canceled`, which is what keeps the anomaly
  visible instead of silently absorbed
- `D-015` anomalies persist now, refetch deferred to v2 behind an unused seam
- `D-016` 04b runs over the context band rather than being restructured
- `D-017` an absorbed event fills a missing `amount`, never replaces one
- `D-018` idempotency keys expire after 24 hours, checked at read time
- `D-019` key semantics mirror Stripe's, measured not assumed

---

## Open questions carried into 07

1. **Expired idempotency keys are never deleted**, only taken over. Harmless
   for an ephemeral demo, wrong for anything durable. Sweep is v2's.
2. **The live idempotency test creates a real PaymentIntent each run.** CI must
   run it with `-m live`, serially, not in a matrix, or the count multiplies.
3. **`checkout.session.expired` is still unregistered**, 10 of 11 modelled
   events. It fires only after a session sits abandoned 24 hours, so no test
   can produce one. The only modelled event never observed.
4. **CI must run `playwright install chromium`**, or collection passes and the
   browser launch fails.
5. **`D-005`'s ephemeral-filesystem note must reach the README** before public.
6. **The README claim wording matters**: state is order-independent, and the
   *record* briefly was not (`D-017`). Phrase the headline as a claim about
   **state**.

---

## Hard-won lessons, so they are not rediscovered

- **A green suite hides things.** Every stage that found a real defect found it
  by measuring or mutating, never by a passing assertion: the mute logger, the
  surviving `<=` mutant, the never-concurrent deliveries (1 request in flight
  of 8), the permanently-NULL amount.
- **A concurrency test that passes once has told you nothing.** 04b's case 4
  kills its mutant only **17 times in 20**. 06's kills it 20 of 20 because the
  failure is total rather than a race. Always use `--count 20`.
- **A command that passes by running nothing is the worst failure mode.** 05's
  verify block omitted `-m live` and collected zero tests while reporting
  success.
- **A contract can be wrong.** 05's decline case asserted "no payment record is
  created", which is false, and the obvious way to make it pass would have been
  to stop recording failed payments.
- **Hosted Checkout takes ~15s to render headless.** Before that the DOM is a
  skeleton whose card accordion falsely reports itself open. Wait on conditions,
  never on sleeps, and screenshot before theorising.
- **The ICM validator was blind to `04a`/`04b`** until its stage-name regex was
  widened to `^\d{2}[a-z]?[_-]`. That fix lives in `~/.claude/skills/icm-tools/`,
  **outside this repo**, and will not travel with a clone.
