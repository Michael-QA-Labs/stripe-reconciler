from fastapi.testclient import TestClient

from service.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_reports_ok_and_pinned_api_version():
    """The health check names the pinned Stripe API version.

    Deploys are the place this matters: a service running an API version other
    than the one fixtures were captured against is the failure this surfaces,
    and reading it from /health is cheaper than reading it from the logs.
    """
    response = client.get("/health")
    body = response.json()

    assert body["status"] == "ok"
    assert body["stripe_api_version"] == "2026-07-29.dahlia"
