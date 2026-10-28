"""Property-based test for the Active_Product_Count feature block.

# Feature: part1-optin, Property 4: Active product counts equal the Active-status row counts per product_type

Covers Property 4 of the part1-optin spec: for every lead, each assembled
``active_count_<product_type>`` column equals the number of
Product_Ownership_File rows for that lead's client with ``status == "Active"``
for that ``product_type`` (Requirements 2.3, 2.4). A client/product pair with
no Active rows -- including a client absent from the file entirely -- is 0
(Requirement 2.4).

This is a reduction property, so it is asserted against an INDEPENDENT
reference recompute (per the tasks.md Notes). The reference below never reuses
the Feature_Assembler: it re-derives each expected count directly from the
generated Product_Ownership frame by filtering to Active rows and counting per
(client_id, product_type), so a divergence signals a real counting bug.

The test exercises the real file-reading path: it writes every generated
source frame to a temporary CSV, points a :class:`part1_optin.config.Config` at
them, and runs :meth:`Feature_Assembler.fit_transform`.

No path in this test references a ``*_answer_key*`` file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings

from part1_optin.config import Config
from part1_optin.features import ACTIVE_COUNT_PREFIX, ACTIVE_STATUS, Feature_Assembler

from tests.strategies_part1 import consistent_datasets


def _reference_active_counts(
    ownership: pd.DataFrame,
) -> dict[tuple[str, str], int]:
    """Independently recompute Active counts per (client_id, product_type).

    Re-derives the expected Active_Product_Count without reusing the
    Feature_Assembler: keep only rows whose ``status`` equals
    :data:`ACTIVE_STATUS` ("Active", Requirement 2.3), then tally one count per
    ``(client_id, product_type)`` pair. Pairs with no Active rows never appear
    in the returned mapping and resolve to ``0`` at lookup time, which is the
    absent-pair / absent-client zero (Requirement 2.4).
    """
    active = ownership[ownership["status"] == ACTIVE_STATUS]
    counts: dict[tuple[str, str], int] = {}
    for row in active.itertuples(index=False):
        key = (row.client_id, row.product_type)
        counts[key] = counts.get(key, 0) + 1
    return counts


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(consistent_datasets())
def test_active_product_counts_equal_active_status_row_counts(dataset):
    """Each active_count column equals the per-type Active-status row count.

    **Validates: Requirements 2.3, 2.4**
    """
    leads = dataset["leads"]
    ownership = dataset["product_ownership"]

    # Independent reference: expected Active count per (client, product_type).
    expected_counts = _reference_active_counts(ownership)

    # Write every generated source frame to a temp CSV and point a Config at
    # them so the real read_csv assembly path runs. A self-managed temp dir
    # keeps each Hypothesis example isolated (Hypothesis cannot drive a
    # function-scoped pytest fixture per example).
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        paths = {
            "promo_leads_path": tmp / "promo_leads.csv",
            "customer_dna_path": tmp / "customer_dna.csv",
            "product_ownership_path": tmp / "product_ownership.csv",
            "adb_monthly_path": tmp / "adb_monthly.csv",
            "contact_history_path": tmp / "contact_history.csv",
            "ndb_path": tmp / "ndb.csv",
            "features_part2_path": tmp / "features_part2.csv",
            "promo_history_path": tmp / "promo_history.csv",
        }
        dataset["leads"].to_csv(paths["promo_leads_path"], index=False)
        dataset["customer_dna"].to_csv(paths["customer_dna_path"], index=False)
        dataset["product_ownership"].to_csv(
            paths["product_ownership_path"], index=False
        )
        dataset["adb_monthly"].to_csv(paths["adb_monthly_path"], index=False)
        dataset["contact_history"].to_csv(paths["contact_history_path"], index=False)
        dataset["ndb"].to_csv(paths["ndb_path"], index=False)
        dataset["part2_features"].to_csv(paths["features_part2_path"], index=False)
        dataset["promo_history"].to_csv(paths["promo_history_path"], index=False)

        config = Config(**paths)
        assembler = Feature_Assembler(config)

        X, schema = assembler.fit_transform(leads)

    # The active-count columns discovered at fit time, one per distinct
    # product_type present in the ownership frame (Requirement 2.3).
    active_count_columns = [
        column
        for column in schema.columns
        if column.startswith(ACTIVE_COUNT_PREFIX)
    ]

    # --- Column discovery: exactly the distinct non-null product_types. ---
    expected_product_types = sorted(ownership["product_type"].dropna().unique())
    expected_columns = [
        f"{ACTIVE_COUNT_PREFIX}{product_type}"
        for product_type in expected_product_types
    ]
    assert active_count_columns == expected_columns

    # --- One row per lead, aligned to the leads frame. ---
    assert len(X) == len(leads)

    # --- Reduction: each cell equals the independent per-type Active count,
    #     with absent (client, product_type) pairs and absent clients at 0
    #     (Requirements 2.3, 2.4). ---
    client_ids = leads["client_id"].tolist()
    for column in active_count_columns:
        product_type = column[len(ACTIVE_COUNT_PREFIX):]
        actual = X[column].tolist()
        for client_id, value in zip(client_ids, actual):
            expected = expected_counts.get((client_id, product_type), 0)
            assert int(value) == expected
