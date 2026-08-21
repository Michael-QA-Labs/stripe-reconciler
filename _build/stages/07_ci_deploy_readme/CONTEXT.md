# 07_ci_deploy_readme: make it linkable

One job: CI that splits correctly, a published Allure report with a real trend,
the full service on the live URL, and a README that earns three minutes of a
stranger's attention.

Timebox: 2 to 4 focused days.

## Inputs

- Working (this run): ../06_idempotency/RESULT.md
- Working (every prior RESULT.md, for the README's claims and the stage 05 GIF): ../
- Reference (the ship gate checklist): ../../CONTEXT.md
- Reference (the README's reasoning comes from here): ../../DECISIONS.md
- Reference (every run): ../../_shared/conventions.md

Do NOT load: `../../_shared/scope-original.md`.

## Process

1. `.github/workflows/ci.yml`, three jobs:

   | Job | Runs | Gating |
   |---|---|---|
   | `fast` | signature, ordering, idempotency. No live Stripe | blocking, parallel |
   | `live` | the lifecycle suite | blocking, **serial**, skipped on fork PRs |
   | `browser` | Playwright Checkout | **non-blocking** (`continue-on-error`), traces uploaded |

   The `live` job is skipped on fork PRs because Actions withholds secrets from
   them, so it would fail for a reason that has nothing to do with the code.
   Knowing which tests to gate on is a deliberate call, and the README says so
   rather than leaving a reader to infer it.
2. Redeploy Render with the full service. Confirm the dashboard webhook secret
   registered in stage 01 still matches.
3. Publish Allure to GitHub Pages **with history configured across runs**. The
   classic failure is a report that renders with an empty trend chart because
   history is not carried between runs.
4. Write the README in this order:
   1. One sentence on why the problem is hard: at-least-once, unordered delivery
   2. Demo GIF of the Checkout flow (recorded in stage 05)
   3. Architecture diagram
   4. Live URL
   5. Coverage badge (the mutation score is v2, so do not promise it yet)
   6. Link to the published Allure report
   7. The real-versus-fixture CI split and the reasoning behind it
5. State the two constraints honestly in the README: Render's ephemeral
   filesystem (`D-005`) and cold starts that Stripe's retries heal. Naming a
   known limitation reads as engineering judgment. Having a reader discover it
   reads as an oversight.

## Outputs

- `.github/workflows/ci.yml`
- Allure published to Pages, with history
- Full service live on Render
- `README.md`, complete
- `_build/stages/07_ci_deploy_readme/RESULT.md`

## Verify

```
git push                                  # CI green
curl https://<render-url>/health
```

Then push a second time. **Two consecutive runs**, because that is the only way
to see whether the Allure trend actually populated. One run always looks fine.

## Human check

Open the repo as a stranger would, from the GitHub landing page, and give it
three minutes. Does the first sentence explain why this is hard? Does the GIF
play? Does the Allure link work from a logged-out browser?

Then check every claim in the README has a test behind it. Two specifically: the
unordered-delivery headline is backed by stage 04b, and the CI split is backed
by this stage. A claim without a test is the one thing that would undo the point
of the project.

## Then: the ship gate

Work through the checklist in `../../CONTEXT.md`. Put it on the resume before
starting v2.
