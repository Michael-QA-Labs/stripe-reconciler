"""Structured webhook logging, wired before it is needed.

Stage 04b debugs races across reordered and concurrent deliveries. Doing that
without event id, payment id, and the state either side of the transition is
the painful path, and retrofitting logging mid-debug is worse.
"""

import json
import logging

from service.logging_setup import log_state_transition


def test_transition_log_is_json_with_the_fields_04b_will_need(caplog):
    with caplog.at_level(logging.INFO, logger="stripe_reconciler"):
        log_state_transition(
            event_id="evt_123",
            payment_id="pi_456",
            state_before="processing",
            state_after="succeeded",
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].getMessage())

    assert payload["event_id"] == "evt_123"
    assert payload["payment_id"] == "pi_456"
    assert payload["state_before"] == "processing"
    assert payload["state_after"] == "succeeded"


def test_absorbed_transition_is_still_logged(caplog):
    """A rejected or absorbed event is exactly what 04b needs to see."""
    with caplog.at_level(logging.INFO, logger="stripe_reconciler"):
        log_state_transition(
            event_id="evt_stale",
            payment_id="pi_456",
            state_before="succeeded",
            state_after="succeeded",
            absorbed=True,
        )

    payload = json.loads(caplog.records[0].getMessage())
    assert payload["absorbed"] is True
