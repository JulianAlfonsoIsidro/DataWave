"""Property-based test for ``part2_network.features.spend_shares`` sum-to-one.

Covers Property 8 (spending shares sum to one for clients with outflow) of the
part2-network spec, validating Requirement 7.7.
"""

from __future__ import annotations

from hypothesis import given, settings

from part2_network.features import (
    client_universe,
    spend_shares,
    split_by_direction,
    total_out,
)
from tests.strategies import transactions_frames


# Requirement 7.7's absolute tolerance for the sum-to-one guarantee.
_SUM_TOL = 0.001


# Feature: part2-network, Property: spend shares sum to one
@settings(max_examples=200)
@given(transactions_frames(force_outflow=True))
def test_spend_shares_sum_to_one_for_clients_with_outflow(txns):
    """A client with Total_Out > 0 has the sum of its spend shares across every
    discovered ``spend_share_*`` column equal to 1 within an absolute tolerance
    of 0.001; a client with Total_Out == 0 has shares that sum to 0.

    ``force_outflow=True`` guarantees at least one OUT row so some client has
    ``total_out > 0`` (the Requirement 7.7 precondition). Every OUT row's
    normalized category maps to exactly one ``spend_share_*`` column (colliding
    raw categories are summed into a single column), so the shares partition
    Total_Out and their sum is 1 for any positive-outflow client.

    Validates: Requirement 7.7
    """
    clients = client_universe(txns)
    outflows, _inflows, _ext = split_by_direction(txns)

    total_out_series = total_out(outflows, clients)
    columns, shares = spend_shares(outflows, total_out_series, clients)

    for client in clients:
        client_total = float(total_out_series.loc[client])
        share_sum = sum(float(shares[column].loc[client]) for column in columns)

        if client_total > 0.0:
            # Positive Total_Out: every OUT amount maps to exactly one spend
            # column, so the shares partition Total_Out and sum to 1 within
            # 0.001 (Requirement 7.7).
            assert abs(share_sum - 1.0) <= _SUM_TOL, (
                client,
                client_total,
                share_sum,
            )
        else:
            # Zero Total_Out: every spend share is 0, so the sum is 0 — the
            # sum-to-one guarantee only applies to positive-outflow clients.
            assert share_sum == 0.0, (client, share_sum)
