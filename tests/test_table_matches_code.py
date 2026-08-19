"""The documentation and the code must agree, and this test is what makes that true.

docs/transition-table.md is the oracle. service/state_machine.py mirrors it.
A doc that has drifted from the code is worse than no doc, because a reader
trusts it. Rather than asking anyone to keep the two in step by hand, this
parses the published tables and asserts the code reproduces them.

The worked orderings in the doc are replayed through apply(), so the examples a
reader checks by hand are the same examples CI checks on every push.
"""

import pathlib

import pytest

from service import state_machine

TABLE_DOC = pathlib.Path(__file__).parent.parent / "docs" / "transition-table.md"


def _rows_under(header_prefix):
    """Return the data rows of the markdown table whose header starts with header_prefix."""
    lines = TABLE_DOC.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header_prefix))
    rows = []
    for line in lines[start + 2 :]:  # skip the header and its |---| separator
        if not line.startswith("|"):
            break
        rows.append([cell.strip().strip("`") for cell in line.split("|")[1:-1]])
    return rows


def test_state_ranks_match_the_table():
    documented = {state: int(rank) for state, rank, _ in _rows_under("| State | Rank |")}
    assert documented == state_machine.STATE_RANK


def test_event_claims_match_the_table():
    documented = {event: claims for event, claims in _rows_under("| Event | Claims state |")}
    assert documented == state_machine.EVENT_CLAIMS


@pytest.mark.parametrize("events,expected_state,expected_illegal", [
    (row[0].split("`, `"), row[1], row[2] == "yes")
    for row in _rows_under("| Events, in delivery order |")
])
def test_worked_orderings_replay_as_documented(events, expected_state, expected_illegal):
    state, saw_illegal = None, False
    for event_type in events:
        result = state_machine.apply(state, event_type)
        state = result.state_after
        saw_illegal = saw_illegal or not result.legal

    assert state == expected_state
    assert saw_illegal == expected_illegal


def test_unknown_event_is_absorbed_without_changing_state():
    result = state_machine.apply("processing", "customer.subscription.created")

    assert result.state_after == "processing"
    assert result.absorbed is True


def test_duplicate_event_is_absorbed_not_reapplied():
    """Found by mutating <= to < in apply(), which no other test caught.

    A duplicate claims the state it already holds, so the final state looks
    correct either way. The difference is only visible in absorbed, and it
    matters: stage 04b asserts that redelivery is a no-op, and stage 04a's
    dedupe is meant to be a second independent guard rather than the only one.
    """
    result = state_machine.apply("succeeded", "payment_intent.succeeded")

    assert result.absorbed is True
    assert result.state_after == "succeeded"
