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

## D-015: Anomalies are persisted and surfaced at 04a, refetch is deferred to v2
**Stage** 02 (for 04a) | **Date** 2026-08-19

`apply()` reports `legal=False` when an event is applied over `canceled`
(`D-014`). A production reconciler would treat events as notifications and
refetch the PaymentIntent from the API before trusting one. That behaviour is
right, and building it at 04a is not.

**At 04a**: flag, log via `log_state_transition()`, and persist the anomaly so it
survives a restart and is queryable. Define the handler to accept a
`fetch_payment_intent` callable that defaults to `None` and is never called.

**At v2**: wire a real fetcher, invoked out of band via `BackgroundTasks`.

Three constraints this protects, each of which is expensive to undo:

- **`service/state_machine.py` stays pure.** It imports nothing from `stripe`.
  That is what lets 04b, and later Hypothesis and mutmut, use it as an oracle
  with no fixtures and no network.
- **The webhook response never blocks on a network call.** Stripe retries slow
  or failed responses, so a blocking refetch would manufacture the duplicate
  deliveries this project exists to handle.
- **The anomaly path never requires live Stripe to test.** Sandbox is capped at
  25 req/s with 1000 updates per PaymentIntent per hour, so a live-dependent
  anomaly test is flaky in CI by construction. An injected fake covers it
  offline; one `@pytest.mark.live` test proves the real client separately.

The seam is the point: turning refetching on later becomes wiring, not redesign.


## D-016: 04b runs over the context band rather than being restructured
**Stage** 04b | **Date** 2026-08-19

The ICM validator reports 04b at roughly 9.7k tokens of context (entry file plus
contract plus resolved inputs) against a healthy band of 2k to 8k, and 04a at
roughly 11.6k. Both were invisible until the validator's stage-name pattern was
widened to match the letter-suffixed folders `D-002` created, so neither figure
had ever been weighed.

Run 04b as it stands. No split, no L3 extraction.

- The band is a report line, not an error. `icm-tools` is explicit that a clean
  run says the workspace is well formed, not that it is the right shape, and
  that the 2k to 8k claim exists partly to be tested against real workspaces
  rather than repeated.
- Every input 04b lists is genuinely used. The weight is `transition-table.md`
  as the oracle and `signing.py` for constructing payloads, and the stage cannot
  do its job without either.
- Restructuring the stage that carries the README's headline claim, immediately
  before running it, to satisfy a soft heuristic is the more expensive mistake.
  `D-002` already split this work once for a reason that was concrete.

Tripwire, not a reversal: if 04b degrades in a way that looks context-driven, an
agent losing the precedence rule or the oracle partway through the stage, this
is the first thing to revisit, and pushing `docs/transition-table.md` into an L3
file the contract points at is the move. Cheap to do later, because the contract
already routes the path rather than inlining the content.


## D-017: An absorbed event fills a missing amount, and never replaces one
**Stage** 04b | **Date** 2026-08-19

Found closing 04b. Only a PaymentIntent payload is trusted for the intent's
amount, because a Charge's amount can differ on a partial refund. And the
amount is written only on a path that is not absorbed. Both rules are right on
their own, and together they leave a hole.

`charge.refunded` carries a Charge, so it supplies no amount, and it claims
`refunded`, the top rank. A payment whose first event is a refund is therefore
created with a NULL amount that nothing can ever fill: every later
PaymentIntent event is absorbed on rank and skips the write. Measured before
the fix, the same two events in the two orders:

```
refunded then succeeded:  state=refunded  amount=None
succeeded then refunded:  state=refunded  amount=2000
```

This is not exotic. The filesystem is ephemeral (`D-005`) and the schema is
recreated on every boot, so the database is empty after each redeploy and a
refund on an older payment arrives as a first sighting.

It also matters to how the project describes itself. State is order
independent, and that claim holds. The *record* was not, and a reader hearing
"delivery order cannot change the outcome" would reasonably assume otherwise.
Stage 07 should phrase the README's claim as being about state.

Three options were weighed:

- **Leave it, and let the v2 refetch supply the amount.** Honest about
  provenance, since the amount genuinely is not in the payload received, and
  `D-015` already defers refetching to v2. Rejected because v1 is the demo, and
  a reconciler that cannot state an amount is not reconciling.
- **Treat the Charge's amount as a fallback.** Removes every NULL. Rejected
  outright: a partial refund's Charge amount is not the intent's, and the table
  already says partial refunds collapse. It would record a number that looks
  authoritative and is wrong, which is worse than recording nothing.
- **Fill only what is missing.** Chosen. An absorbed event carrying an amount
  writes it under `WHERE amount IS NULL`, so a known figure is never replaced
  and a stale or partial one cannot displace a good one.

`updated_at` is deliberately not touched by that write. No state changed, and
an absorbed event must not look like a transition.

Cost is one extra UPDATE on absorbed deliveries, which are the majority. It is
a single indexed write on the primary key, against a receiver that already
takes `BEGIN IMMEDIATE` per delivery, so it is not the bottleneck.

Pinned by `test_an_absorbed_event_still_fills_an_amount_the_record_does_not_have`,
which fails without the fix, and by
`test_an_absorbed_event_never_overwrites_an_amount_already_known`, which fails
against the careless version of the same fix that omits the `IS NULL` guard.
