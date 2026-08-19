from contextlib import asynccontextmanager

import stripe
from fastapi import FastAPI, HTTPException, Request

from service import config, db, webhook


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
@app.post("/payments")
def create_payment():
    raise HTTPException(status_code=501, detail="not implemented until stage 06")


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

    webhook.handle(event)
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
