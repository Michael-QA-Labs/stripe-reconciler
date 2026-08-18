"""Configuration, read once at import.

Values come from the environment, falling back to .env for local development.
Existing environment variables win over .env, which is what lets tests override
TESTING with monkeypatch.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Pinned deliberately, not read from the account. A captured fixture is only
# valid for the version it was captured against, so this changes only when
# fixtures are re-captured on purpose. Captured 2026-08-18; see
# _build/_shared/stripe-facts.md.
STRIPE_API_VERSION = "2026-07-29.dahlia"

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET_CLI = os.getenv("STRIPE_WEBHOOK_SECRET_CLI", "")
STRIPE_WEBHOOK_SECRET_DASHBOARD = os.getenv("STRIPE_WEBHOOK_SECRET_DASHBOARD", "")

# Gates the test-only introspection endpoint. Anything other than an explicit
# "true" leaves it closed, so a typo or an empty value fails safe.
TESTING = os.getenv("TESTING", "").strip().lower() == "true"

DATABASE_PATH = os.getenv("DATABASE_PATH", "payments.db")
