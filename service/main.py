import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import stripe
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from service import config, db, webhook

# Resolved from this file rather than the working directory. Render's start
# command and a local uvicorn run do not share a CWD, and a relative path here
# fails only at runtime, on the deployment, where it is expensive to notice.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Every boot, not once by hand. Render wipes the filesystem on each
    # spin-down and redeploy (D-005), and CREATE TABLE IF NOT EXISTS makes
    # running this on every start free.
    db.init_db()
    yield


app = FastAPI(title="stripe-reconciler", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "stripe_api_version": config.STRIPE_API_VERSION}


# The two endpoints that carry the real logic exist from day one, and say
# plainly that they do nothing yet. A stub returning 200 is a stub a later
# suite can pass against without noticing.
# Matches Stripe's own key expiry (D-018). Module level so a test can shorten
# it and prove expiry without controlling the clock or touching the database.
IDEMPOTENCY_TTL_HOURS = 24


def _request_hash(payload: bytes) -> str:
    """Hash the raw body, not the parsed one.

    Two payloads that parse to equal dicts can differ byte for byte, and the
    guarantee being made is about the request that was sent.
    """
    return hashlib.sha256(payload).hexdigest()


def _claim_key(key: str, request_hash: str):
    """Try to take ownership of an idempotency key. Insert first, always.

    The primary key is the arbiter, not a preceding SELECT. Checking then
    inserting leaves a window where two concurrent requests both read "absent"
    and both proceed, and the window is exactly the case this stage exists to
    close. Insert first and let the constraint decide who won.

    Returns one of:
      ("owned",    None)    caller does the work and records the response
      ("cached",   payload) the work was already done under this key
      ("conflict", None)    another request holds the key and has not finished
      ("mismatch", None)    the key was first used with a different body
    """
    conn = db.connect()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO idempotency_keys (key, request_hash) VALUES (?, ?)",
                (key, request_hash),
            )
            conn.execute("COMMIT")
            return ("owned", None)
        except sqlite3.IntegrityError:
            pass

        row = conn.execute(
            "SELECT request_hash, response_json,"
            " (julianday('now') - julianday(created_at)) * 24.0 AS age_hours"
            " FROM idempotency_keys WHERE key = ?",
            (key,),
        ).fetchone()

        if row["age_hours"] >= IDEMPOTENCY_TTL_HOURS:
            # Expired keys are reusable, which is the whole point of a TTL. The
            # row is reset rather than deleted so the key keeps one home.
            conn.execute(
                "UPDATE idempotency_keys SET request_hash = ?, response_json = NULL,"
                " created_at = datetime('now') WHERE key = ?",
                (request_hash, key),
            )
            conn.execute("COMMIT")
            return ("owned", None)

        conn.execute("COMMIT")

        if row["request_hash"] != request_hash:
            return ("mismatch", None)
        if row["response_json"] is None:
            return ("conflict", None)
        return ("cached", json.loads(row["response_json"]))
    finally:
        conn.close()


def _record_response(key: str, response: dict) -> None:
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE idempotency_keys SET response_json = ? WHERE key = ?",
            (json.dumps(response), key),
        )
        conn.commit()
    finally:
        conn.close()


def _release_key(key: str) -> None:
    """Give the key back when the work failed.

    Without this a failed attempt leaves a row with no response, and every
    retry with that key answers 409 until the TTL expires. A caller retrying
    after an error is the ordinary case, not an abuse of the key.
    """
    conn = db.connect()
    try:
        conn.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()


def _create_payment_intent(amount: int, currency: str) -> dict:
    """The direct branch, and the seam the idempotency suite substitutes.

    Returning a plain dict rather than the SDK object keeps the response
    JSON-serializable for the key cache, and follows the same reasoning as
    webhook.verify: the less of our logic depends on SDK object semantics, the
    less an SDK upgrade can quietly change.
    """
    client = stripe.StripeClient(
        config.STRIPE_SECRET_KEY, stripe_version=config.STRIPE_API_VERSION
    )
    intent = client.v1.payment_intents.create(
        params={"amount": amount, "currency": currency}
    )
    return {"id": intent.id, "status": intent.status, "amount": intent.amount}


def _create_checkout_session(amount: int, currency: str, base_url: str):
    """Create a hosted Checkout Session for the demo page.

    Every parameter here was confirmed by a real call against the sandbox on the
    pinned API version, not taken from memory or from the SDK's type hints:
    stripe 15.5.0 does not ship introspectable param classes for this resource,
    and the CLI's local help covers only 19 common flags, which include neither
    line_items nor cancel_url.

    The client is constructed per call rather than at import. The secret key is
    absent in ordinary unit runs, and building a client at module scope would
    fail collection for the whole repo rather than just the paths that need it.

    The v1 namespace is deliberate. StripeClient.checkout is deprecated and
    emits a DeprecationWarning, and pyproject turns warnings into errors, so the
    old spelling fails the suite rather than merely aging badly.
    """
    client = stripe.StripeClient(
        config.STRIPE_SECRET_KEY, stripe_version=config.STRIPE_API_VERSION
    )
    return client.v1.checkout.sessions.create(
        params={
            "mode": "payment",
            "line_items": [
                {
                    "price_data": {
                        "currency": currency,
                        "product_data": {"name": "Reconciler test payment"},
                        "unit_amount": amount,
                    },
                    "quantity": 1,
                }
            ],
            # Absolute and derived from the incoming request, so the same code
            # works against localhost and the deployment without a setting.
            "success_url": f"{base_url}/app/success.html",
            "cancel_url": f"{base_url}/app/cancel.html",
        }
    )


async def _dispatch_payment(request: Request, body: dict) -> dict:
    """Two branches: hosted Checkout, or a PaymentIntent created directly.

    A Session carries no PaymentIntent when it is created. The id appears only
    once the customer begins paying, which is why session events are resolved to
    the intent they reference (D-006) rather than assumed to carry one, and why
    the handler treats a session without an intent as a real case.
    """
    amount = body.get("amount", 2000)
    currency = body.get("currency", "usd")

    if body.get("mode") == "checkout":
        session = await run_in_threadpool(
            _create_checkout_session, amount, currency,
            str(request.base_url).rstrip("/"),
        )
        return {"id": session.id, "url": session.url}

    return await run_in_threadpool(_create_payment_intent, amount, currency)


@app.post("/payments")
async def create_payment(request: Request, body: dict | None = Body(default=None)):
    """Create a payment, at most once per Idempotency-Key.

    The key is handled before the branch, so both hosted Checkout and direct
    creation are covered by one implementation rather than two.

    The semantics match what Stripe's own API was measured doing, rather than
    what would be convenient: a replay with the same body returns the first
    response, a replay with a different body is a 400, and a request arriving
    while the first is still in flight is a 409. The header is optional, and
    without it nothing is cached, which is also Stripe's behaviour.

    This is our implementation, not Stripe's. Passing a key through to Stripe
    and observing that Stripe deduplicates would prove nothing about this repo.
    """
    body = body or {}
    key = request.headers.get("Idempotency-Key")

    if not key:
        return await _dispatch_payment(request, body)

    payload = await request.body()
    state, cached = await run_in_threadpool(_claim_key, key, _request_hash(payload))

    if state == "mismatch":
        raise HTTPException(
            status_code=400,
            detail="this Idempotency-Key was first used with a different request body",
        )
    if state == "conflict":
        raise HTTPException(
            status_code=409,
            detail="another request with this Idempotency-Key is still in flight",
        )
    if state == "cached":
        return cached

    try:
        result = await _dispatch_payment(request, body)
    except Exception:
        # The work failed, so the key was never spent. Holding it would answer
        # 409 to every retry until the TTL expired.
        await run_in_threadpool(_release_key, key)
        raise

    await run_in_threadpool(_record_response, key, result)
    return result


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Verify, then apply. Anything we handled answers 200.

    The body must be the raw bytes. A re-serialized payload is a different byte
    string and fails verification, so this reads request.body() rather than a
    parsed model.

    Only a signature failure is an error status. Duplicates, stale events,
    unknown types and payments we cannot resolve all answer 200, because Stripe
    retries non-2xx responses and a retry storm is the very thing this service
    exists to handle. Manufacturing our own would be self-inflicted.
    """
    payload = await request.body()

    try:
        event = webhook.verify(payload, request.headers.get("Stripe-Signature", ""))
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="signature verification failed")

    # handle() is synchronous and does blocking SQLite work. Calling it
    # directly from this async endpoint ran it on the event loop, which
    # serialized every delivery: stage 04b measured 1 request in flight out of
    # 8 fired at once. That is head of line blocking, so a slow write delays
    # every other request including /health, and Stripe retries responses it
    # considers slow. Retries are duplicate deliveries, which is the failure
    # this service exists to absorb rather than to manufacture. Handing the
    # blocking call to the threadpool is what makes concurrent deliveries
    # actually concurrent, and what puts BEGIN IMMEDIATE and WAL to work.
    await run_in_threadpool(webhook.handle, event)
    return {"received": True}


# Registered only under TESTING. The route genuinely does not exist otherwise,
# rather than existing and refusing, so there is nothing to probe in production.
if config.TESTING:

    @app.get("/test/payments/{payment_id}")
    def get_payment(payment_id: str):
        """How the suite reads service state, instead of touching the database.

        anomaly_count is here because an illegal transition is recorded rather
        than applied blindly (D-015), and a test asserting that needs a way to
        see it that does not reach into the schema.
        """
        conn = db.connect()
        try:
            row = conn.execute(
                "SELECT id, state, amount, updated_at FROM payments WHERE id = ?",
                (payment_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="payment not found")

            anomalies = conn.execute(
                "SELECT COUNT(*) FROM anomalies WHERE payment_id = ?", (payment_id,)
            ).fetchone()[0]
        finally:
            conn.close()

        return {
            "id": row["id"],
            "state": row["state"],
            "amount": row["amount"],
            "updated_at": row["updated_at"],
            "anomaly_count": anomalies,
        }


# A named route, not a mount. The root used to answer 404, which is correct for
# an unmatched path and wrong as a front door: the deployed URL is what someone
# pastes, and a raw error body is the first thing they see.
#
# include_in_schema=False keeps /openapi.json listing exactly the three real
# routes, which is what D-013 leans on as evidence that the introspection gate
# is structural rather than a status code. A redirect is not part of the API
# surface, so it does not belong in the schema.
#
# This does not reintroduce the catch all the mount below avoids: it matches the
# root and nothing else, so an unknown path still 404s.
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/app/")


# Mounted at /app rather than /. A mount at the root is a catch all: it answers
# every unmatched path, which turns the honest 501 and 404 responses above into
# whatever the static handler feels like returning, and
# test_unknown_route_is_404_not_501 exists to refuse exactly that. Same origin
# either way, so the page can POST to /payments with no CORS handling.
app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
