# 00_prereqs — RESULT

**Completed** 2026-08-18. Stage 01 is now current.

## What exists now

| Item | State |
|---|---|
| Stripe CLI | 1.50.1, authenticated to sandbox `QA sandbox` |
| Allure CLI | 2.43.0 |
| venv | Python 3.13.13 at `.venv/` |
| `.env` | 4 keys, `-rw-------`, git-ignored |
| `.env.example` | committed, both webhook secrets named distinctly |
| Repo | `Michael-QA-Labs/stripe-reconciler`, **PRIVATE**, pushed |
| Repo secrets | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET_CLI` |
| Pinned API version | `2026-07-29.dahlia`, recorded in `_shared/stripe-facts.md` |

## Verification output

```
$ stripe --version
stripe version 1.50.1

$ stripe balance retrieve >/dev/null && echo authenticated OK
authenticated OK

$ .venv/bin/python --version
Python 3.13.13

$ allure --version
2.43.0

$ awk -F= '{...}' .env          # values never printed
  STRIPE_SECRET_KEY = [107 chars]
  STRIPE_WEBHOOK_SECRET_CLI = [70 chars]
  STRIPE_WEBHOOK_SECRET_DASHBOARD = [empty]
  TESTING = [5 chars]
  perms: -rw-------

$ git check-ignore -q .env && echo yes
yes

$ gh repo view stripe-reconciler --json visibility,url
repo: PRIVATE  https://github.com/Michael-QA-Labs/stripe-reconciler

$ gh secret list
STRIPE_SECRET_KEY           2026-08-18T19:16:48Z
STRIPE_WEBHOOK_SECRET_CLI   2026-08-18T19:16:49Z
```

API version, read from the `stripe-version` response header on `/v1/balance`:

```
HTTP/2 200
stripe-version: 2026-07-29.dahlia
```

## Gotchas hit

**The Stripe CLI was already installed.** The plan assumed it was not. Cost
nothing, but the contract now verifies auth explicitly rather than assuming a
fresh install.

**`stripe config --list` printed the test key into a terminal transcript.** The
key was a *restricted* key minted by `stripe login`, listed under **Restricted
keys** in the dashboard, not Standard keys. That is why the first attempt to
revoke it found no roll option on the secret key row. Revoked and replaced. See
`D-010`, which also carries the standing rule: pipe secrets, never echo them.

**`gh repo create --private` produced a PUBLIC repo.** It reported "Name already
exists on this account" and the repo landed public despite the flag, most likely
an account-level default visibility. Caught immediately; the repo was empty
(0 KB, nothing ever pushed) the whole time, so nothing was exposed. See `D-011`.

**Transient GitHub DNS failure** mid-verification. Resolved on retry. Noted only
because it looked briefly like an auth problem and is not one.

## Open questions for stage 01

1. **The `workflow` token scope is missing.** Current scopes are `gist`,
   `read:org`, `repo`. Pushing `.github/workflows/ci.yml` will be rejected.
   Fix when needed: `gh auth refresh -s workflow`. Not blocking until stage 07,
   recorded here so it is not a surprise then.
2. **Michael's GitHub account defaults new repos to public.** Worth changing at
   https://github.com/settings/repositories. Outside this repo's scope, but the
   next repo will do the same thing and may not be empty when it does.
3. `STRIPE_WEBHOOK_SECRET_DASHBOARD` is deliberately empty. Stage 01 fills it
   after the Render deploy, and it must also be added as a third repo secret at
   that point.
