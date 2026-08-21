# 01_foundation: RESULT

**Completed** 2026-08-18. Stage 02 is now current.

Live URL: **https://stripe-reconciler-w6m7.onrender.com**

## What exists now

| Item | State |
|---|---|
| `service/config.py` | env loading, `TESTING` flag, API version pinned as a literal |
| `service/db.py` | SQLite in WAL mode, all three tables |
| `service/main.py` | four endpoints, honest stubs |
| `service/logging_setup.py` | JSON transition logging on logger `stripe_reconciler` |
| `tests/` | 17 tests, all passing |
| `requirements.txt` | 7 direct dependencies, exact pins, why-comments |
| `README.md` | seeded with the "why this problem is hard" framing only |
| `render.yaml` | Blueprint, see `D-012` |
| Render service | free tier, `stripe-reconciler-w6m7`, health check green |
| Stripe event destination | `render-deployment`, snapshot payloads, API version `2026-07-29.dahlia`, 9 events |
| `STRIPE_WEBHOOK_SECRET_DASHBOARD` | captured, in `.env`, Render env, and repo secrets |

Endpoint behaviour, identical locally and deployed:

| Route | Response |
|---|---|
| `GET /health` | 200, reports the pinned API version |
| `GET /test/payments/{id}` | route not registered unless `TESTING=true` |
| `POST /payments` | 501, "not implemented until stage 06" |
| `POST /webhook` | 501, "not implemented until stage 04a" |

## Verification output

```
$ .venv/bin/python -m pytest -q
.................                                                        [100%]
17 passed in 0.22s
```

The suite also passes in a throwaway venv built from `requirements.txt` alone,
which is what proves the pin list is complete rather than merely plausible:

```
$ uv venv --python 3.13 verify-venv && uv pip install -r requirements.txt
$ verify-venv/bin/python -m pytest -q
.................                                                        [100%]
17 passed in 0.61s
```

Deployed service:

```
$ curl https://stripe-reconciler-w6m7.onrender.com/health
{"status":"ok","stripe_api_version":"2026-07-29.dahlia"}
HTTP 200  total 22.385399s

$ curl https://stripe-reconciler-w6m7.onrender.com/test/payments/1
{"detail":"Not Found"} HTTP 404

$ curl -X POST https://stripe-reconciler-w6m7.onrender.com/webhook
{"detail":"not implemented until stage 04a"} HTTP 501

$ curl -X POST https://stripe-reconciler-w6m7.onrender.com/payments
{"detail":"not implemented until stage 06"} HTTP 501
```

The introspection gate proved structurally, not just by status code. The
deployed OpenAPI schema does not contain the route at all:

```
$ curl https://stripe-reconciler-w6m7.onrender.com/openapi.json | jq '.paths | keys'
  /health   ['get']
  /payments ['post']
  /webhook  ['post']
```

Secrets, by length and permission only, never by value (`D-010`):

```
$ awk -F= ... .env
  STRIPE_SECRET_KEY                 = [107 chars]
  STRIPE_WEBHOOK_SECRET_CLI         = [70 chars]   (whsec_ prefix ok)
  STRIPE_WEBHOOK_SECRET_DASHBOARD   = [38 chars]   (whsec_ prefix ok)
  TESTING                           = [5 chars]
  perms: -rw-------      gitignored: yes

$ gh secret list
STRIPE_SECRET_KEY                 2026-08-18T19:16:48Z
STRIPE_WEBHOOK_SECRET_CLI         2026-08-18T19:16:49Z
STRIPE_WEBHOOK_SECRET_DASHBOARD   2026-08-18T20:48:41Z
```

**Human check passed.** Michael opened
`https://stripe-reconciler-w6m7.onrender.com/test/payments/1` in a browser and
got `{"detail":"Not Found"}`.

## Gotchas hit

**Starlette 1.6 requires `httpx2`, and plain `httpx` warns.** `TestClient` now
imports `httpx2`, falling back to `httpx` with a deprecation warning.
`pyproject.toml` sets `filterwarnings = ["error"]`, so the fallback path would
have failed the entire suite rather than degrading quietly. `requirements.txt`
pins `httpx2==2.12.0`. A stray `httpx` remains in `.venv` and is deliberately
not listed; the clean-venv run above is what confirms it is unnecessary.

**The two webhook secrets differ in length: 70 (CLI) versus 38 (dashboard).**
Both start `whsec_`, so the prefix identifies nothing. The length does, and
reading it satisfies `D-010` because no value reaches the screen. Recorded in
`_shared/stripe-facts.md`.

**The macOS system resolver cached NXDOMAIN for the new Render hostname.**
`dig` returned the record while `getaddrinfo` failed, so `curl` could not reach
the service even though the service was fine. Worked around with
`curl --resolve host:443:216.24.57.7`. The real fix is
`sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`. Worth knowing:
this looks exactly like a failed deploy and is not one.

**Cold start measured at 22 seconds**, not the 50-plus often quoted for
Render's free tier. Slow enough to matter for stage 05's Playwright timeouts
and for the README's honesty note (`D-005`).

**Render did not need any dashboard configuration.** The Blueprint (`D-012`)
supplied build command, start command, health check path and the `TESTING=false`
gate. Only the two `sync: false` secrets were entered by hand.

## Open questions for stage 02

1. **`init_db()` is never called.** The schema exists in `service/db.py` and is
   tested, but nothing invokes it at startup, so the deployed instance has no
   tables. Deliberate: no code reads or writes the database until the webhook
   handler exists, so no test can fail on it today. **Stage 04a must wire this
   up**, and should do so test-first rather than discovering it mid-handler.

2. **Refund events, partially registered.** `charge.refunded` was added to the
   destination on 2026-08-18, after stage close, bringing it to 10 events.
   `refund.created` and `refund.updated` are still absent: whether the receiver
   needs them depends on whether the table treats a pending refund as a distinct
   state, which is stage 02's question. Editing a destination's event list
   changes neither its URL nor its signing secret.

3. **The dashboard signing secret is set but unproven.** Nothing verifies its
   value until a signed delivery is checked against it, which first happens in
   stage 04a. If signature verification fails there, suspect this before
   suspecting the code, and check the length tell first.

4. **`/docs` and `/openapi.json` are publicly served.** Settled, see `D-013`.

5. **The `workflow` token scope is still missing**, carried forward from stage
   00. `gh auth refresh -s workflow` before stage 07 pushes `.github/workflows/`.

6. **D-005's ephemeral filesystem note has not reached the README yet.** The
   README currently carries the framing paragraph only. The live URL is a demo
   endpoint and the README must say so before the repo goes public. Related: the
   ship gate now also requires a demo that has been run end to end, not just a
   live URL, with the demo itself defined at stage 05.
