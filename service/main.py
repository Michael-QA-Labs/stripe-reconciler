from contextlib import asynccontextmanager
from pathlib import Path

import stripe
from fastapi import Body, FastAPI, HTTPException, Request
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


@app.post("/payments")
async def create_payment(request: Request, body: dict | None = Body(default=None)):
    """Two branches, one of which is still honestly unbuilt.

    The Checkout branch is stage 05's. Direct PaymentIntent creation is stage
    06's, along with Idempotency-Key handling, and it still answers 501 rather
    than pretending: a stub that returns success is one a later suite passes
    against without noticing.

    A Session carries no PaymentIntent when it is created. The id appears only
    once the customer begins paying, which is why session events are resolved to
    the intent they reference (D-006) rather than assumed to carry one, and why
    the handler treats a session without an intent as a real case.
    """
    if (body or {}).get("mode") != "checkout":
        raise HTTPException(status_code=501, detail="not implemented until stage 06")

    session = await run_in_threadpool(
        _create_checkout_session,
        body.get("amount", 2000),
        body.get("currency", "usd"),
        str(request.base_url).rstrip("/"),
    )
    return {"id": session.id, "url": session.url}


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


# Mounted at /app rather than /. A mount at the root is a catch all: it answers
# every unmatched path, which turns the honest 501 and 404 responses above into
# whatever the static handler feels like returning, and
# test_unknown_route_is_404_not_501 exists to refuse exactly that. Same origin
# either way, so the page can POST to /payments with no CORS handling.
app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
