# Session summary — stripe-reconciler

Carried forward from the compacted session of 2026-08-18/19. Decisions and
state only; anything reconstructable from the repo or git history is left out.

## Where the pipeline stands

Six of nine stages closed. Current stage is **`05_checkout_playwright`**. 04b
closed on 2026-08-19: the four ordering cases pass, and the headline claim is
tested rather than asserted.

| # | Stage | Status |
|---|---|---|
| 00 | `00_prereqs` | closed |
| 01 | `01_foundation` | closed |
| 02 | `02_transition_table` | closed |
| 03 | `03_lifecycle_suite` | closed |
| 04a | `04a_receiver_signatures` | closed (`bdff68a`) |
| 04b | `04b_reorder_race` | closed |
| 05 | `05_checkout_playwright` | **current** |
| 06 | `06_idempotency` | open |
| 07 | `07_ci_deploy_readme` | open |

Suite at close of 04b: **75 passed, 5 deselected** (`.venv/bin/pytest -q`),
including the two `D-017` regression tests added just after the stage closed.
Live tests are opt-in via `-m live`; the default `addopts` deselects them.

Pipeline rule, unchanged: nothing advances until a person has read the previous
stage's `RESULT.md`.

## Standing instructions from the user

- **"Mimic a real business that would actually test for this in a real
  scenario."** This is the deciding criterion whenever a design call is
  genuinely open. It decided `D-014`.
- **Always list bullet points, pros, cons, and an explanation** for design
  decisions. No multiple-choice widgets.
- **Follow the plan; do not answer without being 100% confident.** Verify Stripe
  facts from docs, CLI, or the API — never from memory. This was a correction,
  not a preference.
- **Execute rather than guess.** Revise a proposal for gaps before running it.
- The more UI and visuals, the better for the portfolio.
- Before the repo goes public, a demo must exist and have been run end to end.

## Security rules that remain in force

From `D-010`, `D-011`, `D-008`, `D-009`:

- **Never run `stripe config --list` bare** — it prints the key in full. To
  check a key exists: `stripe config --list | grep -c test_mode_api_key`.
- **`.env` is written by piping values into the file under `umask 077`**, never
  by echoing them into a shell first.
- **Verify `.env` with `wc -l`, never `cat`.** Identify which signing secret a
  file holds by **length**: CLI = 70 chars, dashboard = 38. Both start
  `whsec_`, so the prefix proves nothing.
- Secrets never reach chat or a transcript. A transcript leak already forced one
  key rotation at stage 00.
- After any repo creation, **assert visibility** rather than trusting
  `--private`: `gh repo view <name> --json visibility -q .visibility`.
- Pre-commit hook at `.githooks/pre-commit`, enabled with
  `git config core.hooksPath .githooks`. Greps staged **added** lines only.
- Repo stays **private** until the ship gate, which requires a full-history
  secret scan, not a working-tree one.

## Decisions

`D-001` … `D-011` are recorded in `DECISIONS.md` and unchanged. Three were made
in this session:

- **`D-012`** — Render is configured by a committed `render.yaml`, secrets
  declared `sync: false`.
- **`D-013`** — `/docs` and `/openapi.json` stay publicly served. The schema
  listing exactly three routes is the clearest available evidence that the
  `TESTING` gate on the introspection endpoint is structural.
- **`D-014`** — **`succeeded` outranks `canceled`.** Decided on the cost
  asymmetry a real business faces, and, more durably, because this ranking is
  what keeps the anomaly *visible*. Rank `canceled` higher and the contradictory
  event is absorbed silently and the illegal-transition machinery becomes dead
  code. Scope note: this case catches **our** bugs. The README must not present
  it alongside duplicate, reordered, and late delivery, which are the cases that
  actually happen.
- **`D-017`** — An absorbed event fills a missing `amount` and never replaces
  one. Found closing 04b: a refund seen first left a NULL amount nothing could
  fill, which made the *record* order dependent even though the state was not.
- **`D-016`** — 04b runs over the context band rather than being restructured.
  Made 2026-08-19, after the validator fix made the figure visible for the first
  time.
- **`D-015`** — At 04a: flag, log, and persist anomalies; define a
  `fetch_payment_intent` seam that defaults to `None` and is never called.
  Refetch is v2, out of band via `BackgroundTasks`. Protects three things that
  are expensive to undo: `state_machine.py` stays pure and importable as an
  oracle, the webhook response never blocks on a network call, and the anomaly
  path never needs live Stripe to test.

A routing gap was fixed alongside `D-015`: 04a's contract did not list
`DECISIONS.md` as an input, so the decision would have been unreachable from
inside the stage.

**The check on later contracts is done (2026-08-19).** It was a pattern, not a
one-off: contracts cite decisions in prose but route them in Inputs, and the two
were never kept in sync. Four of nine were wrong. Fixed: 04b now routes `D-014`
and `D-015` (it had `D-007` only, and `D-014` names 04b as the stage that builds
the contradiction case); 05 now routes `DECISIONS.md` at all (it cited `D-006`
with no path to it). Accepted without change: 00 cites `D-010` and `D-001`, 01
cites `D-003`, and neither routes `DECISIONS.md`. Both stages are closed and
their `RESULT.md` files were written against those contracts, so editing them
now would rewrite a record rather than fix a live gap. Recorded here so it is
not rediscovered as a defect.

The root cause is that `DECISIONS.md` records where a decision was *made*, never
where it must be *read*, so routing depended on somebody remembering. Closed by
a rule in `_shared/conventions.md`, which every stage already loads every run:
cite a `D-number` and you must list `DECISIONS.md` in Inputs. `conventions.md`
was itself an offender, citing `D-001`.

Residual risk, unclosed: a stage needing a decision it never mentions in prose.
That is 04b's actual defect and no citation rule catches it. Only a forward
`Consumed by` field on each decision would, which is real work parked for 07.

## Gotchas hit, and what they cost

1. **`httpx` vs `httpx2`.** Starlette 1.6's `TestClient` needs `httpx2`; plain
   `httpx` warns, and `filterwarnings = ["error"]` turns that into a failure.
   Pinned `httpx2==2.12.0`.
2. **macOS cached an NXDOMAIN** for the fresh Render host. `dig` resolved,
   `getaddrinfo` did not. Worked around with `curl --resolve host:443:<ip>`.
3. **Rank ordering was wrong** from memory — corrected against the lifecycle
   docs: `requires_capture` = 40, `processing` = 50.
4. **A mutant survived at stage 02.** Changing `<=` to `<` in `apply()` passed
   every test, because a re-applied duplicate lands on the state it already
   held. Killed by `test_duplicate_event_is_absorbed_not_reapplied`.
5. **`StripeObject` is not a Mapping** — no `.get()`, no `dict()`. The deeper
   problem was unit tests passing plain dicts where runtime passes typed SDK
   objects. Fixed by having `verify()` return a plain dict.
6. **The 299-second boundary flake.** `int(time.time()) - 299` truncates
   downward, so the payload is up to 299.999s old against a 300s limit.
   Repeated runs land in the same second, so it fails **all** or **none** —
   which reads as a deterministic bug, not a flake. Fixed with `math.ceil`.
7. **The logger was silent in production.** Nothing configured the
   `stripe_reconciler` logger, so INFO fell below root's WARNING. Tests passed
   because `caplog` sets the level itself. Found *only* by the manual
   `stripe listen` check in the 04a contract. Fixed at import in
   `logging_setup.py`, with a regression test asserting the effective level.
   This is the argument for stage contracts carrying a manual step at all.

8. **The ICM validator was blind to 04a and 04b.** Its stage-name pattern was
   `^\d{2}[_-]`, which requires `_` or `-` in the third position, so the two
   letter-suffixed stages created by `D-002` matched nothing and every check
   silently skipped them. A clean "0 errors" covered seven stages, not nine, and
   the stage with the original routing gap was one of the two invisible ones.
   Widened to `^\d{2}[a-z]?[_-]` in `~/.claude/skills/icm-tools/scripts/`,
   verified strictly widening by exhaustive comparison before trusting it. A
   passing validator that cannot see the thing it is validating is worse than no
   validator, because it is believed.

## The artifact worth quoting in the README

On the first real trigger, **Stripe delivered `payment_intent.created` after
`payment_intent.succeeded`**, and the receiver absorbed it rather than
regressing. The project's thesis, occurring by accident, in real delivery rather
than a constructed test. Pasted verbatim in `04a/RESULT.md`.

## Open questions carried into 04b and beyond

1. **Concurrency was designed for but unproven, and it did fail.** 04b found
   that `POST /webhook` was an `async def` calling blocking `handle()` on the
   event loop, so deliveries were serialized: 1 in flight out of 8 fired at
   once. `BEGIN IMMEDIATE` and WAL had never been exercised. Fixed with
   `run_in_threadpool`, re-measured at 8 of 8. See `04b/RESULT.md`.
2. **`pytest-xdist` is not installed.** Serial execution is accidental rather
   than configured. When it is added, `-m live` needs `-n0` — the sandbox caps
   at 25 req/s and 1000 updates per PaymentIntent per hour.
3. **`checkout.session.expired` is still not registered** on the destination:
   10 registered against 11 modelled. It cannot fire until stage 05.
4. **`checkout.session.*` payload shape is unverified.** Resolution reads
   `data.object.payment_intent` from documentation only. `charge.refunded` was
   verified empirically; this was not. Stage 05 is the first chance.
5. **Anomalies are written but never read**, except as `anomaly_count` on the
   introspection endpoint.
6. **04a and 04b exceed the 8k context band**, at roughly 11.6k and 9.7k tokens
   (entry + contract + inputs). Both pull `docs/transition-table.md` and a
   source file as working inputs. This was invisible until the validator regex
   was fixed. **Settled as `D-016`: 04b runs at 9.7k as it stands**, no split
   and no L3 extraction, with a tripwire if the stage degrades in a way that
   looks context-driven.
7. **`gh auth refresh -s workflow` is still pending** and blocks stage 07.
8. **`D-005`'s ephemeral-filesystem note must reach the README** before the repo
   goes public. The live URL is a demo endpoint, not a durable store.

## The 04a record, confirmed

The caveat here is resolved. Michael confirmed on 2026-08-19 that the boundary
move from 299 to 301 was directly observed and failed as expected with
`Timestamp outside the tolerance zone`. `04a/RESULT.md` stands as written; no
amendment needed.
