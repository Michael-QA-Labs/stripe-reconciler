"""Structured logging for the webhook path.

One line of JSON per state transition, on one named logger. Stage 04b reads
these while debugging reordered and concurrent deliveries, so the fields it
needs (which event, which payment, and the state either side) are fixed here
rather than retrofitted mid-debug.
"""

import json
import logging
import sys

logger = logging.getLogger("stripe_reconciler")

# Configure on import, because nothing else does. Without this the logger
# inherits the root logger's default WARNING level, so every INFO transition
# line is dropped and the service looks instrumented while emitting nothing.
# Tests did not catch it: caplog sets a level on the logger it captures, so the
# suite passed against a logger that was silent under uvicorn. The stage 04a
# manual check against `stripe listen` is what surfaced it.
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)


def log_state_transition(
    event_id: str,
    payment_id: str,
    state_before: str,
    state_after: str,
    absorbed: bool = False,
) -> None:
    """Record one transition attempt.

    absorbed marks an event the table refused: a duplicate, a stale event, or
    one arriving after a terminal state. Those are logged like any other,
    because "nothing changed, and here is why" is what a reorder bug looks
    like from the outside.
    """
    logger.info(
        json.dumps(
            {
                "event_id": event_id,
                "payment_id": payment_id,
                "state_before": state_before,
                "state_after": state_after,
                "absorbed": absorbed,
            }
        )
    )
