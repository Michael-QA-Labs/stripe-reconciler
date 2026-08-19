# Decisions

One home for every settled "why". Append-only, newest at the bottom. Cite by id
(`see D-004`) from `RESULT.md` files rather than restating the reasoning.

A decision that gets reversed is not deleted. Add a new entry that supersedes it
and say so in both.

---

## D-001: Python 3.13, not 3.14
**Stage** Act 0 | **Date** 2026-08-18

3.11, 3.13 and 3.14 are all installed. Pinning 3.13: it is the newest version
with mature wheels across playwright, and later mutmut. Same reasoning already
recorded in `~/projects/groundtruth-rag/requirements.txt` for torch.

## D-002: Original scope step 4 splits into 04a and 04b
**Stage** Act 0 | **Date** 2026-08-18

Step 4 as written is the receiver, the state machine, the signature suite, and
four concurrency cases. That is two stages of work in one timebox, and the
concurrency cases are the ones that would get cut when the box ran out. They are
also the ones the README's headline claim depends on, so they get their own
stage and their own gate.

## D-003: Deploy at stage 01, not stage 07
**Stage** Act 0 | **Date** 2026-08-18

The original scope defers deployment to the last step. That means nothing is
linkable for three to five weeks, and the two hardest environment problems (the
dashboard signing secret, cold-start latency) surface when there is no slack
left. A health-check-only Render deploy costs about an hour on day one and turns
stage 07 into a redeploy.

Secondary reason, and the honest one: a project with nothing demoable for weeks
is the failure mode that ended the last one.

## D-004: `_build/` is committed, not gitignored
**Stage** Act 0 | **Date** 2026-08-18

It survives a machine change and is not lost with a working directory. Showing
the process is a small asset for a portfolio repo rather than clutter, and the
factory/product split keeps it out of the way of anyone reading only the
service.

## D-005: SQLite stays, despite Render's ephemeral filesystem
**Stage** Act 0 | **Date** 2026-08-18

Render's free tier wipes the filesystem on every spin-down and redeploy, so the
deployed database is not durable. Not fixing this in v1: every test runs against
a local instance, so no suite depends on deployed persistence. The live URL is a
demo endpoint, and the README says so alongside the cold-start note. Postgres is
listed in v2's "what would change at scale" section, which is the honest place
for it.

## D-006: PaymentIntent is the canonical object
**Stage** Act 0 | **Date** 2026-08-18 | Carried over from the original scope

Hosted Checkout emits `checkout.session.completed` alongside the underlying
`payment_intent.*` events, and those can arrive in either order. Session events
map onto the PaymentIntent record. Without one source of truth picked up front,
the reorder suite in 04b is unfalsifiable.

## D-007: Ordering by state precedence, not raw timestamp
**Stage** Act 0 | **Date** 2026-08-18 | Carried over from the original scope

The transition table itself resolves order: terminal states absorb, state never
regresses. `event.created` is a tiebreaker only, used when two events would
otherwise rank the same. More defensible under clock skew than timestamp-first
ordering, and it means the table built in stage 02 **is** the ordering
mechanism, with no separate sequencing scheme to design or justify.

## D-008: A pre-commit hook blocks secrets, not just `.gitignore`
**Stage** Act 0 | **Date** 2026-08-18

`.gitignore` protects `.env` and nothing else. It does nothing about a key
pasted into `service/config.py`, a test fixture, or a debugging print, which is
the realistic way this repo would leak, since it handles real Stripe keys
throughout.

`.githooks/pre-commit` greps staged **added lines** for `sk_live_`, `sk_test_`,
`pk_live_`, `rk_live_`, `whsec_` followed by key material, and PEM private key
headers. It also refuses any commit staging `.env`, since `git add -f` bypasses
`.gitignore`.

Hand-rolled rather than gitleaks: no dependency, runs in milliseconds, and the
threat model here is one vendor's key formats. Enabled with
`git config core.hooksPath .githooks`, which means a fresh clone must run that
line; stage 07's README says so.

Verified by staging a fake `whsec_` value and confirming the commit was blocked.
Only added lines are scanned, so removing a leaked key is never itself blocked.

## D-009: Repo is private during the build, scrubbed before going public
**Stage** Act 0 | **Date** 2026-08-18

`gh repo create --private`. It flips public only at the ship gate, and only
after `_build/` is reviewed file by file, since the factory ships with the repo
(`D-004`) and stage `RESULT.md` files will accumulate working notes over three
to five weeks. Anything reading as private rather than as process gets cut at
that review. The scrub is a ship gate checklist item, not an intention.

## D-010: Secrets are piped, never echoed. First test key rolled
**Stage** 00 | **Date** 2026-08-18

`stripe config --list` prints `test_mode_api_key` in full. It was run once
during stage 00 setup, putting that key into a terminal transcript.

The key turned out to be a **restricted** key minted by `stripe login`, valid 90
days, listed under *Restricted keys* on the dashboard API keys page under the
device name `Mac`. Not the account's standard secret key, which is why the
Standard keys rows offered no roll option and the first attempt to fix this
looked in the wrong place.

It was **revoked** in the dashboard on 2026-08-18 rather than left to expire,
even though it was sandbox-scoped, permission-restricted, and already expiring
2026-11-16. Confirmed dead: `stripe balance retrieve` fails against it.

The reasoning is habit, not blast radius. "It was only test mode" is the
argument that fails later, on a key where it matters.

Standing rules from this:

- Never run `stripe config --list` bare. To check a key exists:
  `stripe config --list | grep -c test_mode_api_key`.
- `.env` is written by **piping** values into the file under `umask 077`, never
  by echoing them into a shell first.
- Verify `.env` with `wc -l`, never `cat`.

## D-011: Verify repo visibility, do not trust the `--private` flag
**Stage** 00 | **Date** 2026-08-18

`gh repo create stripe-reconciler --private --source=. --push` reported "Name
already exists on this account" and the repo landed **PUBLIC**, despite the
flag. Likely an account-level default visibility winning over it. Caught
immediately and flipped with `gh repo edit --visibility private`. The repo was
empty (0KB, nothing ever pushed) for the whole window, so nothing was exposed.

Standing rule: after any repo creation, assert visibility rather than assume it.

```
gh repo view <name> --json visibility -q .visibility
```

This is also a ship gate item, since the gate deliberately flips the repo public
and that step must be the only thing that ever does.

## D-012: Render config is a committed `render.yaml`, not dashboard-only
**Stage** 01 | **Date** 2026-08-18

The service is configured by a Blueprint file in the repo rather than by hand in
the Render dashboard. Three reasons: the config is reviewable in a clone, the
`TESTING=false` gate on `GET /test/payments/{id}` is visible next to the code it
protects rather than buried in a web form, and stage 07 becomes a redeploy
instead of a reconfiguration.

Secrets stay out of the file. `STRIPE_SECRET_KEY` and
`STRIPE_WEBHOOK_SECRET_DASHBOARD` are declared with `sync: false`, which tells
Render to prompt for the value once and keep it in its own store.
`STRIPE_WEBHOOK_SECRET_CLI` is deliberately absent: it backs `stripe listen`
locally and has no meaning on the deployed endpoint.

## D-013: `/docs` and `/openapi.json` stay publicly served
**Stage** 01 | **Date** 2026-08-18

FastAPI serves interactive Swagger UI at `/docs` by default. It is left on
deliberately rather than disabled in production.

The repo is a portfolio artifact, and a live link where someone can see and
exercise the API surface is worth more than the small amount of information it
reveals. There is nothing sensitive behind it: the schema lists exactly three
routes, and the test-only introspection endpoint is absent from it entirely,
which is itself the clearest available evidence that the `TESTING` gate is
structural rather than a status code.

Standing preference this reflects: where a choice trades a little exposure for
something a reader can see and click, the visible option wins on this project.

Revisit only if the service ever holds real data, which under `D-005` it does
not.

## D-014: `succeeded` outranks `canceled`
**Stage** 02 | **Date** 2026-08-19

The only rank in `docs/transition-table.md` that Stripe's documentation does not
decide. Stripe forbids the transition ("a PaymentIntent can't be canceled after
it has succeeded"), so it has no position on what a receiver should record if it
ever sees the contradiction.

The contradiction only arises from our own side: two PaymentIntents conflated
through the session mapping, a replayed payload, or a case stage 04b builds
deliberately.

Decided on the cost asymmetry a real business would face, not on intuition:

- Recording `canceled` for a payment that actually captured money leaves a
  customer charged with no record of it. That reaches you as a support ticket, a
  duplicate charge, or a chargeback. Finance hears it from the customer.
- Recording `succeeded` for a payment that was actually canceled is caught by
  the next reconciliation sweep against Stripe, which is a thing any real
  business runs regardless.

Second reason, and the one that would survive if the first were a coin flip:
this ranking is what keeps the anomaly **visible**. Because `succeeded` is
higher, the contradictory ordering is applied over `canceled` and flagged
illegal by the "nothing leaves `canceled`" rule. Rank `canceled` higher instead
and the contradictory event is absorbed silently, the illegal-transition
machinery becomes dead code, and a genuine mapping bug in our own receiver
passes unnoticed.

Scope note: this case is a defensive assertion that catches our bugs. It is not
a scenario a real business plans for, and the README must not present it
alongside duplicate, reordered, and late delivery, which are the cases that
actually happen.

Cheap to reverse: one integer in `STATE_RANK` and one row in the table, with
`test_state_ranks_match_the_table` failing if only one is changed.
