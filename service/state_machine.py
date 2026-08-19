"""The ordering mechanism, mirroring docs/transition-table.md.

Read the table first. This module is deliberately a transcription of it, and
tests/test_table_matches_code.py fails if the two ever drift apart.

The whole design is one rule: every state has a rank, an event claims a state,
and the claim is applied only if it ranks strictly higher than what is already
recorded. Nothing else sequences events. There is no separate ordering scheme,
no timestamp comparison deciding outcomes, and no buffer holding events until
their predecessors arrive.

That rule is what makes delivery order irrelevant. The final state is the
highest rank among the events received, which is a property of the set of
events rather than of their sequence, so any permutation lands in the same
place. It also makes duplicates harmless for free: a repeated event claims a
state of equal rank, and equal is not strictly higher.
"""

from typing import NamedTuple

# Higher wins. Gaps leave room to insert a state without renumbering.
# requires_capture sits below processing because manual capture authorizes
# first and processes second: capturing an authorized payment moves it to
# processing or succeeded, never the reverse.
# refunded is this project's state, not Stripe's. The PaymentIntent status enum
# has seven values and does not include it; refunds live on the Charge. Since
# the PaymentIntent is the canonical record (D-006), a refund lands here.
STATE_RANK = {
    "requires_payment_method": 10,
    "requires_confirmation": 20,
    "requires_action": 30,
    "requires_capture": 40,
    "processing": 50,
    "canceled": 60,
    "succeeded": 70,
    "refunded": 80,
}

# What each event asserts the payment has reached. Note that no event claims
# requires_confirmation: Stripe has no such event type, and that state is
# visible only in API responses.
EVENT_CLAIMS = {
    "payment_intent.created": "requires_payment_method",
    "payment_intent.requires_action": "requires_action",
    "payment_intent.amount_capturable_updated": "requires_capture",
    "payment_intent.processing": "processing",
    "payment_intent.partially_funded": "processing",
    "payment_intent.canceled": "canceled",
    "payment_intent.succeeded": "succeeded",
    "payment_intent.payment_failed": "requires_payment_method",
    "checkout.session.completed": "processing",
    "checkout.session.expired": "canceled",
    "charge.refunded": "refunded",
}

# Ranking already refuses every backwards move, so the only transitions worth
# calling illegal are forward ones that still cannot be real. Stripe states that
# a PaymentIntent cannot be canceled after succeeding and that cancellation
# cannot be undone, which makes canceled genuinely terminal. Leaving it means
# two payments were conflated, a payload was replayed, or we have a bug.
STATES_NOTHING_LEAVES = frozenset({"canceled"})


class Transition(NamedTuple):
    """The outcome of one event, keeping two questions apart.

    state_after answers "what state is this payment in".
    legal answers "was the path it took to get here possible".

    Collapsing those into one value forces a false choice: either refuse
    evidence that money moved, or hide an impossible transition. Reporting both
    means the state stays order independent while the anomaly stays visible.
    """

    state_after: str | None
    absorbed: bool
    legal: bool


def apply(current_state: str | None, event_type: str) -> Transition:
    """Resolve one event against the state already recorded.

    current_state is None for a payment seen for the first time, in which case
    the event is applied whatever it claims. A payment whose first event is
    payment_intent.succeeded starts at succeeded, and any earlier events that
    arrive afterwards are absorbed on rank.
    """
    claimed = EVENT_CLAIMS.get(event_type)

    # An event we do not model changes nothing. The table is total: every input
    # has a defined outcome, so unknown types are absorbed rather than raising.
    if claimed is None:
        return Transition(current_state, absorbed=True, legal=True)

    if current_state is None:
        return Transition(claimed, absorbed=False, legal=True)

    # Strictly higher, so equal rank is absorbed. That is what makes a
    # duplicate delivery a no-op without consulting processed_events.
    if STATE_RANK[claimed] <= STATE_RANK[current_state]:
        return Transition(current_state, absorbed=True, legal=True)

    return Transition(
        claimed,
        absorbed=False,
        legal=current_state not in STATES_NOTHING_LEAVES,
    )
