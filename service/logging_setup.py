"""Structured logging for the webhook path.

One line of JSON per state transition, on one named logger. Stage 04b reads
these while debugging reordered and concurrent deliveries, so the fields it
needs (which event, which payment, and the state either side) are fixed here
rather than retrofitted mid-debug.
"""

import json
import logging

logger = logging.getLogger("stripe_reconciler")


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
