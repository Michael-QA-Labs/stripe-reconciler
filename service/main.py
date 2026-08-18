from fastapi import FastAPI, HTTPException

from service import config

app = FastAPI(title="stripe-reconciler")


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
def receive_webhook():
    raise HTTPException(status_code=501, detail="not implemented until stage 04a")


# Registered only under TESTING. The route genuinely does not exist otherwise,
# rather than existing and refusing, so there is nothing to probe in production.
if config.TESTING:

    @app.get("/test/payments/{payment_id}")
    def get_payment(payment_id: str):
        raise HTTPException(status_code=404, detail="payment not found")
