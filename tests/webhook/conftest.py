"""A client with a temp database, a known signing secret, and TESTING on.

The introspection route is registered at import time only when TESTING is true
(stage 01 made it genuinely absent otherwise), so reaching it means reloading
the modules with the flag set. That is the same approach
tests/test_introspection_gating.py already uses.
"""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

SECRET = "whsec_test_secret_for_local_signing_only"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTING", "true")

    from service import config, main

    importlib.reload(config)
    importlib.reload(main)

    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "webhook.db"))
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET_CLI", SECRET)
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET_DASHBOARD", "")

    with TestClient(main.app) as test_client:
        yield test_client


def make_event(event_id, event_type, obj):
    return json.dumps({"id": event_id, "type": event_type, "data": {"object": obj}}).encode()


def payment_intent_object(pi_id="pi_1", amount=1000):
    return {"id": pi_id, "object": "payment_intent", "amount": amount}


def charge_object(pi_id="pi_1", charge_id="ch_1"):
    return {"id": charge_id, "object": "charge", "payment_intent": pi_id}


def session_object(pi_id="pi_1", session_id="cs_1"):
    return {"id": session_id, "object": "checkout.session", "payment_intent": pi_id}
