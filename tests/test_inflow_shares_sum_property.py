"""Property-based test for ``part2_network.features.inflow_shares`` sum-to-one.

Covers Property 6 (inflow shares sum to one when all inflows are known sources)
of the part2-network spec, validating Requirement 6.5.
"""

from __future__ import annotations

from hypothesis import given, settings

from part2_network.config import INFLOW_SHARE_COLUMNS
from part2_network.features import (
    client_universe,
    inflow_shares,
    split_by_direction,
)
from tests.strategies import transactions_frames


# Requirement 6.5's absolute tolerance for the sum-to-one guarantee.
_SUM_TOL = 0.001


# Feature: part2-network, Property: inflow shares sum to one
@settings(max_examples=200)
@given(transactions_frames(all_inflows_known_sources=True))
def test_inflow_shares_sum_to_one_for_known_sources(txns):
    """When every IN row's counterparty_category is one of the three known
    Inflow_Sources, a client with positive total inflow has its three inflow
    shares sum to 1 within an absolute tolerance of 0.001; a client with zero
    total inflow has shares that sum to 0.

    The ``all_inflows_known_sources=True`` strategy forces every IN row's
    ``counterparty_category`` into {Payroll, Remittance, Business receipts}, so
    the Requirement 6.5 precondition (all of a client's inflow categories are
    known sources) holds for every client with any inflow.

    Validates: Requirement 6.5
    """
    clients = client_universe(txns)
    _outflows, inflows, _ext = split_by_direction(txns)

    shares = inflow_shares(inflows, clients)
    columns = list(INFLOW_SHARE_COLUMNS.values())

    # Per-client total inflow computed independently from the IN rows.
    inflow_total = inflows.groupby("client_id").amount_php.sum()

    for client in clients:
        total = float(inflow_total.get(client, 0.0))
        share_sum = sum(float(shares[column].loc[client]) for column in columns)

        if total > 0.0:
            # Positive total inflow with all categories being known sources:
            # the three shares partition the full inflow, so they sum to 1
            # within 0.001 (Requirement 6.5).
            assert abs(share_sum - 1.0) <= _SUM_TOL, (client, total, share_sum)
        else:
            # Zero total inflow: every share is 0, so the sum is 0 — the
            # sum-to-one guarantee only applies to positive-inflow clients.
            assert share_sum == 0.0, (client, share_sum)
