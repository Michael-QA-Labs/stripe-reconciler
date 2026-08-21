# 07_ci_deploy_readme: RESULT

**Completed** 2026-08-21. v1 is at the ship gate.

CI splits three ways and gates on the two that are ours. The Allure report is
published with a trend that populated across consecutive runs rather than
looking fine on one. The live URL serves the whole service instead of the
pre-05 build it had been stuck on. The repo is public.

## What exists now

| Item | State |
|---|---|
| `.github/workflows/ci.yml` | four jobs: `fast`, `live`, `browser`, `report` |
| Allure report | https://michael-qa-labs.github.io/stripe-reconciler/ , 87 tests |
| Coverage badge | shields endpoint JSON published beside the report |
| `README.md` | all seven contract positions, both honesty notes |
| `requirements.txt` / `requirements-dev.txt` | split, service half proven by clean venv |
| `docs/demo-checkout.gif` | committed, 900x506, 17s |
| Render | full service live, `/app/` and `POST /payments` both answering |
| Repo | **public**, asserted per `D-011` |
| `_build/` | scrubbed per `D-009` |

The CI split, and what each job gates on:

| Job | Runs | Gating |
|---|---|---|
| `fast` | 81 offline tests | blocking |
| `live` | 6 tests, lifecycle plus one real PaymentIntent | blocking, serial, skipped on fork PRs |
| `browser` | 3 tests against hosted Checkout | non-blocking, traces uploaded |
| `report` | merges `fast` and `live` results, publishes | after both, `main` only |

81 + 6 + 3 is 90, every collected test, so the split orphans nothing.

## Verification output

Three consecutive runs on `main`. Overall conclusion `success` on all three,
since `browser` is `continue-on-error`.

```
$ gh run view 32448580548 --json conclusion,jobs
overall: success
  fast, no Stripe: success
  live, real Stripe test mode: success
  browser, hosted Checkout: success
  allure report to Pages: success
```

The trend, which is the thing one run cannot prove:

```
$ gh run view 32448580548 --log   (report job)
carried 5 history files forward
report carries history: 5 files

$ curl .../widgets/history-trend.json
  2 data point(s) in the trend
    {'failed': 0, 'broken': 0, 'skipped': 0, 'passed': 87, 'total': 87}
    {'failed': 0, 'broken': 0, 'skipped': 0, 'passed': 87, 'total': 87}
```

The deployment, no longer stale:

```
$ curl https://stripe-reconciler-w6m7.onrender.com/health
{"status":"ok","stripe_api_version":"2026-07-29.dahlia"}   200

$ curl -L .../app/          200   <title>Pay · stripe-reconciler</title>
$ curl -X POST .../payments 200   (was 501 on the pre-05 build)

$ curl .../openapi.json | jq '.paths | keys'
  ['/health', '/payments', '/webhook']
```

Exactly three routes still, so `D-013`'s argument that the introspection gate is
structural survives the redeploy.

Published report and badge, both reachable logged out:

```
$ curl .../coverage.json
{"schemaVersion": 1, "label": "coverage", "message": "96%", "color": "brightgreen"}

$ curl -o /dev/null -w '%{http_code}' 'https://img.shields.io/endpoint?url=.../coverage.json'
200
```

## Two dependencies the plan had not recorded

Both found by reading the fixtures rather than by a red CI run.

**The browser suite shells out to `stripe listen`**, so the Stripe CLI is a real
dependency of this pipeline even though pip knows nothing about it. Pinned at
1.50.3 and installed from the release tarball. It authenticates from
`STRIPE_API_KEY`, confirmed against the CLI's own help.

**That listener signs with the CLI secret**, which had to be stable per account
rather than minted per session for a stored repo secret to work at all. Verified
before writing the job by hashing `stripe listen --print-secret` across two
invocations and against `.env`, comparing digests only and never values. It is
stable, and the first CI run confirmed it end to end: the success test asserts
server-side state after a real webhook delivery, and it passed.

## Gotchas hit

**Render was installing the test stack into production.** `buildCommand` is
`pip install -r requirements.txt`, which was pulling pytest, pytest-repeat,
httpx2, playwright and pytest-playwright onto the web service. Playwright alone
is a 40MB download and a browser binary the service never imports. Split into
`requirements.txt` for the service and `requirements-dev.txt` for everything
else. `render.yaml` needed no change, which is the reason for splitting that
direction rather than renaming both files. The service half was proven complete
rather than plausible by installing it alone into a clean 3.13 venv and
importing the app.

**Pages from a private repo needs a paid plan.** The plan reads `free`, so the
sequencing conflict the handoff described had only two exits, not three, and the
"keep everything private" option was never available. `read:user` is what made
that answerable rather than a guess.

**A hardcoded coverage figure went stale within one run.** The README said 97
percent in prose next to a live badge; the next run measured 96. Removed both
prose figures. The badge is the number now, because a figure typed into a
sentence goes stale the first time the suite changes and nothing fails when it
does.

**The generated report's history check cannot be a gate on the first run.**
There is legitimately nothing to carry the first time, so asserting on it would
fail the run that creates the branch. It logs instead, and the trend is proven
across two runs, which is what the contract asked for anyway.

## Open questions for the ship gate and v2

1. **`test_abandoning_checkout_records_nothing_at_all` is flaky in CI**, failing
   two runs of three and passing the third. It passes locally. On the first
   failure the trace video shows the cancel page fully rendered with the badge
   visible at 20 seconds, while `get_by_text("Not completed")` waited its full
   60 second timeout against it. That is not slowness, and the intermittency
   says it is not a plain locator bug either. The page already exposes
   `data-testid="outcome"` on that span, which is the obvious thing to try.
   **This is stage 05's file and was left untouched**, reported rather than
   fixed. The job is non-blocking, so it degrades to a report with traces.
2. **`checkout.session.expired` is still unregistered**, 10 of 11 modelled
   events. It fires only after a session sits abandoned 24 hours, so no test can
   produce one. Unchanged since 04a and still the only modelled event never
   observed.
3. **Expired idempotency keys are never deleted**, only taken over. Harmless
   while the filesystem is wiped on every redeploy (`D-005`), wrong for anything
   durable. A sweep is v2's.
4. **The mutation score is claimed nowhere**, deliberately. Each stage did it by
   hand and recorded the figures; automating with mutmut is v2's.
5. **The ICM validator's stage-name fix lives outside this repo**, in
   `~/.claude/skills/icm-tools/`, and will not travel with a clone.
