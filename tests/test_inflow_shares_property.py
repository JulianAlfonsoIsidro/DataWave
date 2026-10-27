"""Property-based tests for ``part2_network.features.inflow_shares``.

Covers Property 5 (inflow-share bounds and definition) of the part2-network
spec, validating Requirements 6.1, 6.2, 6.3, and 6.4.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings

from part2_network.config import INFLOW_SHARE_COLUMNS, INFLOW_SOURCES
from part2_network.features import (
    client_universe,
    inflow_shares,
    split_by_direction,
)
from tests.strategies import transactions_frames


# Absolute tolerance for comparing the unrounded float shares against an
# independently computed reference (the function leaves values unrounded).
_TOL = 1e-9


# Feature: part2-network, Property: inflow-share bounds and definition
@settings(max_examples=200)
@given(transactions_frames())
def test_inflow_shares_bounds_and_definition(txns):
    """Each inflow share is a bounded source fraction of the client's total
    inflow, zero when total inflow is zero, and keyed by exactly the three
    expected columns on the sorted client universe.

    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    clients = client_universe(txns)
    _outflows, inflows, _ext = split_by_direction(txns)

    shares = inflow_shares(inflows, clients)

    # Result dict has exactly the three expected column keys (Requirement 6.6
    # column names, used here to characterize the Requirement 6.1 output).
    expected_columns = set(INFLOW_SHARE_COLUMNS.values())
    assert set(shares.keys()) == expected_columns

    # Each Series is indexed by the sorted client universe.
    for column, series in shares.items():
        assert list(series.index) == list(clients), column

    # Independent reference: per client, total inflow and per-source inflow sum
    # computed directly from the IN rows (Requirement 6.1 definition).
    inflow_total = inflows.groupby("client_id").amount_php.sum()
    per_source = {
        source: inflows[inflows.counterparty_category == source]
        .groupby("client_id")
        .amount_php.sum()
        for source in INFLOW_SOURCES
    }

    for client in clients:
        total = float(inflow_total.get(client, 0.0))

        for source in INFLOW_SOURCES:
            column = INFLOW_SHARE_COLUMNS[source]
            value = float(shares[column].loc[client])

            # Every share value is in [0, 1] for every client (Requirement 6.4).
            assert -_TOL <= value <= 1.0 + _TOL, (client, source, value)

            source_sum = float(per_source[source].get(client, 0.0))

            if total == 0.0:
                # Zero total inflow -> every share is 0 (Requirement 6.2).
                expected = 0.0
            else:
                # Share == source sum / total inflow, computed independently
                # (Requirements 6.1, 6.3 via a zero source_sum).
                expected = source_sum / total

            assert abs(value - expected) <= _TOL, (client, source, value, expected)

    # Clients with zero total inflow have all three shares == 0 (Requirement 6.2).
    for client in clients:
        if float(inflow_total.get(client, 0.0)) == 0.0:
            for column in expected_columns:
                assert float(shares[column].loc[client]) == 0.0, (client, column)
