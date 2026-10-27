"""Property test for Feature_Builder output cardinality.

# Feature: part2-network, Property: one row per distinct client

Property 11: Exactly one output row per distinct client.
**Validates: Requirements 8.2**

Also asserts the client_id-first column placement (Requirement 8.3) and the
zero-distinct-clients -> header-only frame behavior (Requirement 8.6). The
shared ``transactions_frames`` strategy has a non-empty client universe
(``min_clients=1``), so the empty case is covered by a separate hand-built
empty-frame assertion.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings

from part2_network.config import INFLOW_SHARE_COLUMNS, REQUIRED_COLUMNS
from part2_network.features import build
from tests.strategies import transactions_frames


@settings(max_examples=200)
@given(transactions_frames())
def test_build_has_exactly_one_row_per_distinct_client(txns):
    """build(txns) emits exactly one row per distinct client_id (Req 8.2)."""
    output = build(txns)

    distinct_clients = set(txns.client_id.unique())

    # The output's client_id set equals the input's distinct client set.
    assert set(output.client_id) == distinct_clients
    # No duplicate client_id rows, and exactly one row per distinct client.
    assert output.client_id.is_unique
    assert len(output) == len(distinct_clients)


@settings(max_examples=200)
@given(transactions_frames())
def test_build_has_client_id_as_first_column(txns):
    """client_id is the first column of the assembled frame (Req 8.3)."""
    output = build(txns)
    assert output.columns[0] == "client_id"


def test_build_empty_transactions_yields_header_only_frame():
    """Zero distinct clients -> zero rows but the header columns present (Req 8.6).

    The shared strategy always has a non-empty client universe, so the empty
    case is exercised here with a hand-built empty frame matching the schema
    ``reader.read`` produces.
    """
    columns = [
        "txn_id",
        "client_id",
        "txn_date",
        "direction",
        "amount_php",
        "counterparty_type",
        "counterparty_category",
    ]
    empty = pd.DataFrame({column: [] for column in columns})
    empty["amount_php"] = pd.to_numeric(empty["amount_php"], errors="raise")
    empty["txn_date"] = pd.to_datetime(
        empty["txn_date"], format="%Y-%m-%d", errors="raise"
    )

    output = build(empty)

    # Zero distinct clients => zero rows.
    assert len(output) == 0
    assert set(output.client_id) == set()
    # Columns are still present: client_id first, plus the fixed feature header
    # columns (no spend_share_* columns can be discovered from empty outflows).
    assert output.columns[0] == "client_id"
    expected_header = [
        "client_id",
        "total_out",
        "out_other_bank",
        "ext_outflow_ratio",
        "months_with_ext_transfer",
        *INFLOW_SHARE_COLUMNS.values(),
    ]
    assert list(output.columns) == expected_header
    # Sanity: the required input columns were all available to build from.
    assert set(REQUIRED_COLUMNS).issubset(empty.columns)
