"""Property-based tests for ``part2_network.features.total_out``.

Covers Property 1 (total outflow equals the sum of a client's OUT amounts) of
the part2-network spec. The shared :func:`transactions_frames` strategy builds
frames shaped exactly like the reader's output so the feature can be exercised
directly without re-running the reader.
"""

import math

from hypothesis import given, settings

from part2_network.features import (
    client_universe,
    split_by_direction,
    total_out,
)
from tests.strategies import transactions_frames


# Feature: part2-network, Property: total outflow
@settings(max_examples=200)
@given(transactions_frames(min_rows=0, max_rows=80))
def test_total_out_equals_sum_of_client_out_amounts(txns):
    """Total_Out is the per-client OUT ``amount_php`` sum, aligned and zero-filled.

    Asserts, against an independent reference computed directly from the
    generated frame:

    - Every client in the sorted client universe appears exactly once in the
      result index, in ascending order (Requirement 2.2 alignment).
    - For each client, ``total_out`` equals the sum of ``amount_php`` over that
      client's OUT rows (Requirement 2.1).
    - A client with no OUT rows reports 0 (Requirement 2.2).
    - All values are non-negative (amounts are non-negative).

    Validates: Requirements 2.1, 2.2, 2.3
    """
    clients = client_universe(txns)
    outflows, _inflows, _ext = split_by_direction(txns)

    result = total_out(outflows, clients)

    # The result index is exactly the sorted client universe, each client once,
    # in ascending order (Requirement 2.2 alignment).
    assert list(result.index) == clients
    assert len(result.index) == len(set(clients))
    assert clients == sorted(clients)

    # Independent reference: sum amount_php over each client's OUT rows.
    for client in clients:
        out_rows = txns[(txns.direction == "OUT") & (txns.client_id == client)]
        expected = out_rows.amount_php.sum()

        actual = result.loc[client]

        if out_rows.empty:
            # A client with no OUT rows reports exactly 0 (Requirement 2.2).
            assert actual == 0
        else:
            # Floating-point summation is not associative: the feature's
            # groupby sum and this reference sum add the same amounts in a
            # different order, so they may differ in the last unit in the last
            # place. Compare with a tight tolerance rather than bit-exact
            # equality (Requirement 2.1).
            assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)

        # Amounts are non-negative, so every total is non-negative.
        assert actual >= 0
