# Feature: part2-network, Property: spend-share column set
"""Property-based test for the Spending_Share column set (Property 9).

Covers the global column discovery and shape guarantees of
``part2_network.features.spend_shares`` (Requirements 7.2, 7.3):

- the discovered column set equals exactly the set of ``spend_share_column``
  mapped over every distinct ``counterparty_category`` seen on *any* client's
  OUT rows (global discovery, Req 7.2), computed here independently;
- every column name carries the ``spend_share_`` prefix and is well-formed
  (Req 7.3 -- deep normalization is covered by Property 10, here a sanity
  check on the prefix);
- the column list is deterministic, ordered by normalized name
  (``columns == sorted(columns)``);
- the same complete set appears for every client: each column's Series has one
  entry per client in the sorted universe (Req 7.2, "same complete set in
  every row"); and
- the ``shares`` dict keys equal exactly ``set(columns)``.

**Validates: Requirements 7.2, 7.3**
"""

from hypothesis import given, settings

from part2_network.config import SPEND_SHARE_PREFIX
from part2_network.features import (
    client_universe,
    spend_share_column,
    spend_shares,
    split_by_direction,
    total_out,
)
from tests.strategies import transactions_frames


@settings(max_examples=200)
@given(transactions_frames())
def test_spend_share_column_set_matches_global_outflow_categories(txns):
    clients = client_universe(txns)
    outflows, _inflows, _ext = split_by_direction(txns)
    total_out_series = total_out(outflows, clients)

    columns, shares = spend_shares(outflows, total_out_series, clients)

    # Expected column set computed independently: map every distinct
    # counterparty_category on ANY client's OUT rows through spend_share_column
    # (global discovery across all clients, Req 7.2). Normalization can collide
    # two raw categories onto one name, so a set absorbs the collision.
    expected_columns = {
        spend_share_column(category)
        for category in outflows.counterparty_category.unique()
    }
    assert set(columns) == expected_columns

    # Every column is well-formed: carries the spend_share_ prefix (Req 7.3;
    # deep normalization is Property 10's job).
    for column in columns:
        assert column.startswith(SPEND_SHARE_PREFIX)

    # Deterministic ordering: sorted ascending by normalized column name, per
    # the spend_shares docstring.
    assert columns == sorted(columns)

    # shares dict keys == the column set.
    assert set(shares.keys()) == set(columns)

    # The same complete set appears for every client: each column's Series has
    # exactly one entry per client in the sorted universe (Req 7.2).
    for column in columns:
        series = shares[column]
        assert list(series.index) == clients
        assert len(series) == len(clients)
