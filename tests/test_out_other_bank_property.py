"""Property-based tests for ``part2_network.features.out_other_bank``.

Covers Property 2 (outflow to other banks equals the sum of a client's
External_Outflow amounts) of the part2-network spec. Each generated frame is
fed straight into the Feature_Builder helpers and the resulting Out_Other_Bank
Series is checked against an independent reference computation.
"""

import pandas as pd
from hypothesis import given, settings

from part2_network.config import EXTERNAL_COUNTERPARTY_TYPE
from part2_network.features import (
    client_universe,
    out_other_bank,
    split_by_direction,
    total_out,
)
from tests.strategies import transactions_frames


def _reference_out_other_bank(txns: pd.DataFrame, clients: list) -> pd.Series:
    """Independently recompute Out_Other_Bank per client from raw rows.

    Sums ``amount_php`` over rows where ``direction == "OUT"`` AND
    ``counterparty_type == "Other bank"`` (Requirements 3.1, 3.2), then aligns
    onto the sorted client universe with gaps zero-filled (Requirement 3.3).
    This deliberately avoids the ``split_by_direction`` slices so it is a true
    independent reference rather than a restatement of the implementation.
    """
    mask = (txns.direction == "OUT") & (
        txns.counterparty_type == EXTERNAL_COUNTERPARTY_TYPE
    )
    per_client = txns[mask].groupby("client_id").amount_php.sum()
    return per_client.reindex(clients).fillna(0.0)


# Feature: part2-network, Property: outflow to other banks
@settings(max_examples=200)
@given(transactions_frames())
def test_out_other_bank_matches_independent_reference(txns):
    """Out_Other_Bank equals the independently-computed External_Outflow sum.

    - Each client's value equals the sum of ``amount_php`` over rows where
      ``direction == "OUT"`` AND ``counterparty_type == "Other bank"``
      (Requirement 3.1).
    - Rows whose ``counterparty_type`` is missing/blank or not equal to
      "Other bank" are excluded, verified by the independent recomputation
      (Requirement 3.2).
    - Out_Other_Bank <= Total_Out for every client, since External_Outflow is a
      subset of Outflow (strong cross-feature invariant).
    - Clients with no External_Outflow report 0 (Requirement 3.3).
    - The result is indexed by the sorted client universe, one value per client
      (Requirements 8.2, 8.5).

    Validates: Requirements 3.1, 3.2, 3.3, 3.4
    """
    clients = client_universe(txns)
    _, _, ext_outflows = split_by_direction(txns)
    outflows, _, _ = split_by_direction(txns)

    result = out_other_bank(ext_outflows, clients)
    expected = _reference_out_other_bank(txns, clients)

    # Index is exactly the sorted client universe, one value per client.
    assert list(result.index) == clients
    assert len(result) == len(clients)

    # Per-client value matches the independent reference (Req 3.1, 3.2).
    pd.testing.assert_series_equal(
        result.astype(float),
        expected.astype(float),
        check_names=False,
        check_dtype=False,
    )

    # External outflow is a subset of outflow: Out_Other_Bank <= Total_Out.
    totals = total_out(outflows, clients)
    tolerance = 1e-6
    assert ((result <= totals + tolerance) | (result.isna())).all()

    # Clients with no External_Outflow report exactly 0 (Req 3.3).
    ext_client_set = set(ext_outflows.client_id.unique())
    for client in clients:
        if client not in ext_client_set:
            assert result.loc[client] == 0
