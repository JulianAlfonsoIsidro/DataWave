"""Property-based test for ``part2_network.features.months_with_ext_transfer``.

Covers Property 4 (months with external transfer is a bounded distinct-month
count) of the part2-network spec.
"""

import pandas as pd
from hypothesis import given, settings

from part2_network.features import (
    client_universe,
    months_with_ext_transfer,
    split_by_direction,
    transaction_months,
)
from tests.strategies import transactions_frames


def _reference_months_with_ext_transfer(txns: pd.DataFrame, clients: list) -> dict:
    """Independent reference: distinct YYYY-MM months per client with an
    External_Outflow.

    Computed directly from the raw frame without reusing the production
    groupby: filter to OUT rows whose ``counterparty_type`` is exactly
    "Other bank", derive each row's ``YYYY-MM`` month, and count the distinct
    months per client. Clients with no such rows map to 0 (Requirements 5.1,
    5.2, 5.4).
    """
    expected = {client: set() for client in clients}
    for _, row in txns.iterrows():
        if row["direction"] != "OUT":
            continue
        if row["counterparty_type"] != "Other bank":
            continue
        month = pd.Timestamp(row["txn_date"]).strftime("%Y-%m")
        expected[row["client_id"]].add(month)
    return {client: len(months) for client, months in expected.items()}


# Feature: part2-network, Property: months with external transfer
# Property 4: Months with external transfer is a bounded distinct-month count
@settings(max_examples=200)
@given(transactions_frames())
def test_months_with_ext_transfer_is_bounded_distinct_month_count(txns):
    """``months_with_ext_transfer`` equals the distinct count of months with an
    external outflow per client, is a non-negative integer in [0, 3], and is 0
    for clients with no external outflows.

    Validates: Requirements 5.1, 5.2, 5.3, 5.4
    """
    clients = client_universe(txns)
    _outflows, _inflows, ext_outflows = split_by_direction(txns)
    result = months_with_ext_transfer(ext_outflows, clients)

    # Indexed by the sorted client universe (Requirements 8.2, 8.5).
    assert list(result.index) == clients

    # Integer dtype (Requirement 5.3, "no fractional component").
    assert pd.api.types.is_integer_dtype(result.dtype)

    # Independent reference per client.
    expected = _reference_months_with_ext_transfer(txns, clients)

    # Number of distinct months each client actually transacted in (any
    # direction) — an upper bound on months with an external outflow.
    all_months = transaction_months(txns)
    months_transacted = {client: set() for client in clients}
    for client, month in zip(txns.client_id, all_months):
        months_transacted[client].add(month)

    for client in clients:
        value = int(result.loc[client])

        # Non-negative integer in [0, 3] (Requirement 5.3). The dataset spans
        # three observed months, so the count can never exceed 3.
        assert 0 <= value <= 3

        # Matches the independent reference (Requirements 5.1, 5.4): multiple
        # external outflows in the same month count that month once.
        assert value == expected[client]

        # Clients with no external outflows report 0 (Requirement 5.2).
        if expected[client] == 0:
            assert value == 0

        # Bounded by the number of distinct months the client transacted in,
        # which is itself bounded by the 3-month dataset span.
        assert value <= len(months_transacted[client])
        assert len(months_transacted[client]) <= 3
