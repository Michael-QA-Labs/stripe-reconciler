"""A real browser drives a real card, and the result is asserted over HTTP.

The cross-protocol part is what makes Playwright load-bearing here rather than
decorative. The browser causes a payment; the assertion is made against our own
receiver through `GET /test/payments/{id}`, after Stripe has delivered a webhook
that the browser never sees. Asserting on Stripe's own success page would prove
only that Stripe works.

Marked `live` for the whole module. These tests drive real hosted Checkout, so
they are deselected by default and stage 07's fixture-only CI job never touches
them. Run them with `-m live`.

Everything about the page flow below was observed against the real page rather
than assumed. Three things were not obvious:

1. Hosted Checkout takes roughly fifteen seconds to render headless. Before
   that the DOM is a skeleton, and a card accordion in it reports itself open
   while no card fields exist. Every wait here is a condition with a timeout,
   never a sleep.
2. No payment method is preselected, and the card radio sits under an accordion
   button that swallows ordinary clicks.
3. Link enrolment is checked by default, which makes phone number required.
   Unchecking it keeps an unrelated dependency out of the payment path.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import stripe

from service import config

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]

SUCCESS_CARD = "4242424242424242"
DECLINE_CARD = "4000000000000002"

# Rendering is the slow part, not the payment. Fifteen seconds is the observed
# floor headless, so the budget is generous enough that a slow run is not a
# failure and short enough that a genuinely stuck page does not hang the suite.
RENDER_TIMEOUT_MS = 60_000
WEBHOOK_TIMEOUT_S = 45

PAID_STATES = ("processing", "succeeded", "refunded")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base_url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    raise RuntimeError("the receiver never became healthy")


@pytest.fixture(scope="module")
def receiver(tmp_path_factory):
    """A local receiver with a listener forwarding real Stripe events to it.

    Both processes are spawned here rather than assumed to be running, so the
    verify command is self-contained and stage 07's CI can run it unattended.

    It has to be local. The introspection endpoint is registered only under
    TESTING and is genuinely absent on the deployment (D-013), so there is
    nothing on Render to poll. That is the gate working, not a gap.

    The listener's startup banner prints the signing secret. Its output is read
    to detect readiness and is never logged or echoed anywhere.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    database = tmp_path_factory.mktemp("browser") / "checkout.db"

    environment = {
        **os.environ,
        "TESTING": "true",
        "DATABASE_PATH": str(database),
    }
    service = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "service.main:app", "--port", str(port),
         "--log-level", "warning"],
        cwd=REPO_ROOT,
        env=environment,
    )
    listener = None
    try:
        _wait_for_health(base_url)

        listener = subprocess.Popen(
            ["stripe", "listen", "--forward-to", f"{base_url}/webhook"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            line = listener.stdout.readline()
            if not line:
                break
            # Never printed: this line carries the signing secret.
            if "Ready!" in line:
                break
        else:
            raise RuntimeError("the listener never reported ready")

        yield base_url
    finally:
        for process in (listener, service):
            if process is None:
                continue
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            # Closed explicitly. Left to the garbage collector it raises an
            # ignored ResourceWarning during teardown, and pyproject turns
            # warnings into errors, so the suite fails after passing.
            if process.stdout is not None:
                process.stdout.close()


@pytest.fixture(scope="module")
def stripe_client():
    return stripe.StripeClient(
        config.STRIPE_SECRET_KEY, stripe_version=config.STRIPE_API_VERSION
    )


def start_checkout(base_url: str) -> dict:
    """Create a Session through our own endpoint, the way the demo page does."""
    request = urllib.request.Request(
        f"{base_url}/payments",
        data=json.dumps({"mode": "checkout", "amount": 2000, "currency": "usd"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pay_with(page, card: str) -> None:
    """Fill hosted Checkout and submit. Role and label locators only.

    No CSS and no test ids: Stripe redesigns this page without notice, and the
    accessible names are what survive it. Two of the obvious locators are traps.
    `get_by_label("CVC")` also matches the card icon and trips strict mode, and
    a button named "Pay" also matches the hidden Apple Pay button, so both are
    addressed by role with an exact name.
    """
    card_option = page.get_by_role("radio", name="Card")
    card_option.wait_for(state="visible", timeout=RENDER_TIMEOUT_MS)
    # An accordion button overlays the radio and intercepts pointer events, so
    # the control is set directly rather than clicked through the overlay.
    card_option.check(force=True)

    number = page.get_by_role("textbox", name="Card number")
    number.wait_for(state="visible", timeout=RENDER_TIMEOUT_MS)
    number.fill(card)
    page.get_by_role("textbox", name="Expiration").fill("12 / 34")
    page.get_by_role("textbox", name="CVC").fill("123")

    for name, value in (("Cardholder name", "Test Person"),
                        ("Email", "browser-suite@example.com"),
                        ("ZIP", "12345")):
        field = page.get_by_role("textbox", name=name)
        if field.count():
            field.fill(value)

    enrol = page.get_by_role("checkbox", name="Save my information for faster checkout")
    if enrol.count() and enrol.first.is_checked():
        enrol.first.uncheck(force=True)

    page.get_by_role("button", name="Pay", exact=True).first.click()


def poll_state(base_url: str, payment_id: str, timeout: float = WEBHOOK_TIMEOUT_S):
    """Poll the receiver until the payment appears, or give up loudly.

    A fixed sleep long enough to be reliable is long enough to be annoying, and
    one short enough to be pleasant is flaky. The webhook is asynchronous and
    arrives after the browser has already moved on, so polling is the only
    honest way to wait for it.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"{base_url}/test/payments/{payment_id}", timeout=5
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            last = error.code
            time.sleep(0.5)
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise AssertionError(
        f"no webhook recorded {payment_id} within {timeout}s (last status {last})"
    )


def assert_no_record(base_url: str, identifier: str) -> None:
    """The receiver must hold nothing under this id."""
    try:
        with urllib.request.urlopen(
            f"{base_url}/test/payments/{identifier}", timeout=5
        ) as response:
            raise AssertionError(
                f"a record exists for {identifier}: {json.load(response)}"
            )
    except urllib.error.HTTPError as error:
        assert error.code == 404, f"expected 404 for {identifier}, got {error.code}"


def intent_id_for(stripe_client, session_id: str) -> str:
    """A Session carries no PaymentIntent until the customer starts paying.

    That is why this is read back after the attempt rather than captured at
    creation, and it is the same reason the receiver treats a session without an
    intent as a real case rather than an error.
    """
    session = stripe_client.v1.checkout.sessions.retrieve(session_id)
    assert session.payment_intent, "the attempt produced no PaymentIntent"
    return session.payment_intent


def test_a_paid_card_is_recorded_as_succeeded_by_the_webhook(page, receiver, stripe_client):
    """The whole point of the stage: browser causes it, HTTP proves it.

    The redirect is checked first because it is what the customer sees, but it
    is not the assertion that matters. Stripe's success page proves Stripe
    works. The state polled afterwards proves our receiver took delivery of an
    event the browser never saw and recorded it correctly.
    """
    session = start_checkout(receiver)
    page.goto(session["url"], wait_until="load")
    pay_with(page, SUCCESS_CARD)

    page.wait_for_url("**/app/success.html", timeout=RENDER_TIMEOUT_MS)
    # wait_for, not is_visible: the URL changes before the document renders, and
    # is_visible is a point in time check rather than a wait. It passed here on
    # timing luck and failed on the cancel page, which is the same bug the
    # contract warns about for the webhook poll.
    page.get_by_text("Payment complete").wait_for(state="visible", timeout=RENDER_TIMEOUT_MS)

    payment = poll_state(receiver, intent_id_for(stripe_client, session["id"]))
    assert payment["state"] == "succeeded"
    assert payment["amount"] == 2000
    assert payment["anomaly_count"] == 0


def test_a_declined_card_surfaces_the_error_and_never_reaches_a_paid_state(
    page, receiver, stripe_client
):
    """A decline must not look like a payment, which is a claim about state.

    The contract originally asked this to assert that no payment record is
    created. That is false and was corrected once observed: a declined card
    still has a PaymentIntent, and Stripe delivers charge.failed,
    payment_intent.created, and payment_intent.payment_failed. The last two
    claim requires_payment_method, so a record exists and rank 10 is right for
    it. Asserting absence would fail honestly and tempt someone to weaken the
    receiver until it passed.
    """
    session = start_checkout(receiver)
    page.goto(session["url"], wait_until="load")
    pay_with(page, DECLINE_CARD)

    error = page.get_by_role("alert").filter(has_text="declined")
    error.first.wait_for(state="visible", timeout=RENDER_TIMEOUT_MS)
    assert "/app/success.html" not in page.url

    payment = poll_state(receiver, intent_id_for(stripe_client, session["id"]))
    assert payment["state"] == "requires_payment_method"
    assert payment["state"] not in PAID_STATES


def test_abandoning_checkout_records_nothing_at_all(page, receiver, stripe_client):
    """The one case where asserting absence is correct, and why.

    The decline case cannot assert that no record exists, because a declined
    card still has a PaymentIntent behind it. Abandoning the session is
    different in kind: the customer leaves before paying, so Stripe never
    creates an intent, no event is delivered, and there is nothing to record.

    The second assertion is the interesting one. A payment is keyed on the
    PaymentIntent because that is the canonical record (D-006), and session
    events are resolved to the intent they reference rather than stored under
    their own id. Querying the receiver by session id proves it did not create
    a phantom payment keyed on the wrong object, which is the failure that
    resolution exists to prevent and which nothing else here would catch.
    """
    session = start_checkout(receiver)
    page.goto(session["url"], wait_until="load")

    # Wait for the page to actually finish rendering before leaving it. The
    # back link is visible in the skeleton, seconds before the rest exists, and
    # clicking it then is not what a customer abandoning a payment does. The
    # card radio is the marker for a rendered page, as in the tests above.
    page.get_by_role("radio", name="Card").wait_for(
        state="visible", timeout=RENDER_TIMEOUT_MS
    )

    # Matched on the prefix: the full accessible name carries the account's
    # display name, which is not ours to depend on.
    back = page.get_by_role("link", name="Back to")
    back.wait_for(state="visible", timeout=RENDER_TIMEOUT_MS)
    back.click()

    page.wait_for_url("**/app/cancel.html", timeout=RENDER_TIMEOUT_MS)
    page.get_by_text("Not completed").wait_for(state="visible", timeout=RENDER_TIMEOUT_MS)

    abandoned = stripe_client.v1.checkout.sessions.retrieve(session["id"])
    assert abandoned.payment_status == "unpaid"
    assert abandoned.payment_intent is None, "an abandoned session created an intent"

    assert_no_record(receiver, session["id"])
