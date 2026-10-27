"""Property-based tests for ``part2_network.features.spend_shares``.

Covers Property 7 (spend-share bounds and definition) of the part2-network
spec, validating Requirements 7.1, 7.4, 7.5, and 7.6.
"""

from __future__ import annotations

from collections import defaultdict

from hypothesis import given, settings

from part2_network.features import (
    client_universe,
    spend_share_column,
    spend_shares,
    split_by_direction,
    total_out,
)
from tests.strategies import transactions_frames


# Absolute tolerance for comparing the unrounded float shares against an
# independently computed reference (the function leaves values unrounded).
_TOL = 1e-9


# Feature: part2-network, Property: spend-share bounds and definition
@settings(max_examples=200)
@given(transactions_frames())
def test_spend_shares_bounds_and_definition(txns):
    """Each spend share is a bounded category fraction of the client's
    Total_Out, zero when Total_Out is zero, and every Series is keyed by the
    sorted client universe.

    Validates: Requirements 7.1, 7.4, 7.5, 7.6
    """
    clients = client_universe(txns)
    outflows, _inflows, _ext = split_by_direction(txns)
    total_out_series = total_out(outflows, clients)

    columns, shares = spend_shares(outflows, total_out_series, clients)

    # The share dict exposes exactly the discovered columns.
    assert set(shares.keys()) == set(columns)

    # Each Series is indexed by the sorted client universe (Requirement 7.4
    # alignment: every discovered column carries one value per client).
    for column in columns:
        assert list(shares[column].index) == list(clients), column

    # Independent reference. Map each raw OUT category through the same
    # normalization so distinct raw categories that collide on one output
    # column are summed together (Requirement 7.3), mirroring the function's
    # collision handling without reusing its pivot. Build per-client,
    # per-normalized-column outflow sums and per-client Total_Out directly.
    ref_category_sum: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    ref_total_out: dict[str, float] = defaultdict(float)
    for _, row in outflows.iterrows():
        client = row["client_id"]
        column = spend_share_column(row["counterparty_category"])
        amount = float(row["amount_php"])
        ref_category_sum[client][column] += amount
        ref_total_out[client] += amount

    for client in clients:
        total = ref_total_out.get(client, 0.0)

        for column in columns:
            value = float(shares[column].loc[client])

            # Every share value is in [0, 1] for every client/column
            # (Requirement 7.6 bounds).
            assert -_TOL <= value <= 1.0 + _TOL, (client, column, value)

            category_sum = ref_category_sum.get(client, {}).get(column, 0.0)

            if total == 0.0:
                # Total_Out == 0 -> every spend share is 0 (Requirement 7.5).
                expected = 0.0
            else:
                # share == category sum / Total_Out, computed independently;
                # a client with no outflow in the category has category_sum 0
                # and therefore a 0 share (Requirements 7.1, 7.4).
                expected = category_sum / total

            assert abs(value - expected) <= _TOL, (
                client,
                column,
                value,
                expected,
            )

    # Clients with Total_Out == 0 have every spend share == 0 (Requirement 7.5).
    for client in clients:
        if ref_total_out.get(client, 0.0) == 0.0:
            for column in columns:
                assert float(shares[column].loc[client]) == 0.0, (client, column)
