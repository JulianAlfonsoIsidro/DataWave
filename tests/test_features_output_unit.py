"""Example/edge-case unit tests for ``part2_network.features.build``/``write``.

These are concrete-example tests (not Hypothesis) covering the output shape,
column order, rounding, and writing behavior of the Feature_Builder against
Requirement 8 (and the inflow-share column names of Requirement 6.6).
"""

from pathlib import Path

import pandas as pd

from part2_network.features import build, write

# The fixed, non-dynamic leading columns of the Features_File, in order:
# client_id first (Req 8.3), then the summary/ratio/month columns, then the
# three named inflow-share columns (Req 6.6).
FIXED_COLUMNS = [
    "client_id",
    "total_out",
    "out_other_bank",
    "ext_outflow_ratio",
    "months_with_ext_transfer",
    "inflow_share_payroll",
    "inflow_share_remittance",
    "inflow_share_business_receipts",
]

# Columns a validated transactions frame carries that the Feature_Builder reads.
TXN_COLUMNS = [
    "client_id",
    "txn_date",
    "direction",
    "amount_php",
    "counterparty_type",
    "counterparty_category",
]


def _txns(rows: list[dict]) -> pd.DataFrame:
    """Build a transactions frame from row dicts with a datetime ``txn_date``.

    Mirrors the reader's output contract: ``amount_php`` numeric and
    ``txn_date`` a ``datetime64`` column.
    """
    frame = pd.DataFrame(rows, columns=TXN_COLUMNS)
    frame["txn_date"] = pd.to_datetime(frame["txn_date"], format="%Y-%m-%d")
    frame["amount_php"] = pd.to_numeric(frame["amount_php"])
    return frame


def _empty_txns() -> pd.DataFrame:
    """Return a header-only (zero-row) transactions frame matching the schema."""
    frame = pd.DataFrame({column: [] for column in TXN_COLUMNS})
    frame["txn_date"] = pd.to_datetime(frame["txn_date"])
    frame["amount_php"] = pd.to_numeric(frame["amount_php"])
    return frame


# A small multi-client frame exercised across several assertions. Hand-built so
# every output value is computable by hand:
#
# C1: OUT 1000 (Other bank, Groceries) in 2026-07, OUT 500 (BPI, Bills) in
#     2026-08, OUT 500 (Other bank, Groceries) in 2026-09; IN 800 Payroll,
#     IN 200 Remittance.
#     total_out = 2000; out_other_bank = 1500 (two Other-bank OUTs);
#     ext_outflow_ratio = 1500/2000 = 0.75;
#     months_with_ext_transfer = 2 (2026-07, 2026-09);
#     inflow total = 1000; payroll 0.8, remittance 0.2, business 0.0;
#     spend_share_groceries = 1500/2000 = 0.75, spend_share_bills = 500/2000 = 0.25.
# C2: OUT 300 (Other bank, Bills) in 2026-07; IN 600 Business receipts.
#     total_out = 300; out_other_bank = 300; ratio = 1.0;
#     months_with_ext_transfer = 1;
#     inflow total = 600; payroll 0, remittance 0, business 1.0;
#     spend_share_bills = 1.0, spend_share_groceries = 0.0.
# C3: only an IN (no outflow). IN 1000 Payroll.
#     total_out = 0; out_other_bank = 0; ratio = 0; months = 0;
#     payroll 1.0, remittance 0, business 0;
#     all spend shares 0.
_SAMPLE_ROWS = [
    # C1
    {"client_id": "C1", "txn_date": "2026-07-05", "direction": "OUT",
     "amount_php": 1000.0, "counterparty_type": "Other bank",
     "counterparty_category": "Groceries"},
    {"client_id": "C1", "txn_date": "2026-08-10", "direction": "OUT",
     "amount_php": 500.0, "counterparty_type": "BPI",
     "counterparty_category": "Bills"},
    {"client_id": "C1", "txn_date": "2026-09-12", "direction": "OUT",
     "amount_php": 500.0, "counterparty_type": "Other bank",
     "counterparty_category": "Groceries"},
    {"client_id": "C1", "txn_date": "2026-07-01", "direction": "IN",
     "amount_php": 800.0, "counterparty_type": "BPI",
     "counterparty_category": "Payroll"},
    {"client_id": "C1", "txn_date": "2026-08-01", "direction": "IN",
     "amount_php": 200.0, "counterparty_type": "BPI",
     "counterparty_category": "Remittance"},
    # C2
    {"client_id": "C2", "txn_date": "2026-07-20", "direction": "OUT",
     "amount_php": 300.0, "counterparty_type": "Other bank",
     "counterparty_category": "Bills"},
    {"client_id": "C2", "txn_date": "2026-07-02", "direction": "IN",
     "amount_php": 600.0, "counterparty_type": "BPI",
     "counterparty_category": "Business receipts"},
    # C3
    {"client_id": "C3", "txn_date": "2026-09-09", "direction": "IN",
     "amount_php": 1000.0, "counterparty_type": "BPI",
     "counterparty_category": "Payroll"},
]


def test_build_exact_column_order() -> None:
    """build() emits the fixed columns then spend_share_* in sorted order.

    client_id first (Req 8.3), the fixed summary/ratio/month/inflow columns in
    their canonical order (Req 6.6), then every discovered spend_share_* column
    sorted ascending by name.
    """
    features = build(_txns(_SAMPLE_ROWS))

    # Discovered spend-share columns: Groceries and Bills -> normalized and
    # sorted ascending by output name (bills before groceries).
    expected = FIXED_COLUMNS + ["spend_share_bills", "spend_share_groceries"]
    assert list(features.columns) == expected


def test_build_one_row_per_client_ascending() -> None:
    """build() yields one row per client in ascending client_id order (8.2, 8.5)."""
    features = build(_txns(_SAMPLE_ROWS))

    assert features["client_id"].tolist() == ["C1", "C2", "C3"]
    # One row per distinct client, no duplicates.
    assert len(features) == features["client_id"].nunique() == 3


def test_build_known_rounded_values() -> None:
    """build() reports the hand-computed, requirement-rounded feature values.

    Covers total_out at 2 decimals (Req 2.3), ext_outflow_ratio at 4 decimals
    (Req 4.4), inflow/spend shares at 6 decimals (Reqs 6.4, 7.6), and
    months_with_ext_transfer as an integer (Req 5.3/5.5).
    """
    features = build(_txns(_SAMPLE_ROWS)).set_index("client_id")

    # C1 values.
    c1 = features.loc["C1"]
    assert c1["total_out"] == 2000.00
    assert c1["out_other_bank"] == 1500.00
    assert c1["ext_outflow_ratio"] == 0.75
    assert int(c1["months_with_ext_transfer"]) == 2
    assert c1["inflow_share_payroll"] == 0.8
    assert c1["inflow_share_remittance"] == 0.2
    assert c1["inflow_share_business_receipts"] == 0.0
    assert c1["spend_share_groceries"] == 0.75
    assert c1["spend_share_bills"] == 0.25

    # C2 values: a client whose entire outflow is external (ratio 1.0).
    c2 = features.loc["C2"]
    assert c2["total_out"] == 300.00
    assert c2["out_other_bank"] == 300.00
    assert c2["ext_outflow_ratio"] == 1.0
    assert int(c2["months_with_ext_transfer"]) == 1
    assert c2["inflow_share_business_receipts"] == 1.0
    assert c2["spend_share_bills"] == 1.0
    assert c2["spend_share_groceries"] == 0.0

    # C3 values: no outflow at all -> zeros for every outflow-derived feature.
    c3 = features.loc["C3"]
    assert c3["total_out"] == 0.0
    assert c3["out_other_bank"] == 0.0
    assert c3["ext_outflow_ratio"] == 0.0
    assert int(c3["months_with_ext_transfer"]) == 0
    assert c3["inflow_share_payroll"] == 1.0
    assert c3["spend_share_groceries"] == 0.0
    assert c3["spend_share_bills"] == 0.0

    # months_with_ext_transfer has no fractional component (Req 5.3).
    assert (features["months_with_ext_transfer"] % 1 == 0).all()


def test_write_creates_missing_directory_and_no_index(tmp_path: Path) -> None:
    """write() creates a missing outputs dir and writes no index column.

    The target ``outputs`` directory does not exist beforehand; write() must
    create it (Req 8.4), produce a header row (Req 8.1), keep client_id first
    with no leading index column, and preserve the row count.
    """
    features = build(_txns(_SAMPLE_ROWS))

    outputs_dir = tmp_path / "outputs"
    out_path = outputs_dir / "features_part2.csv"
    assert not outputs_dir.exists()

    write(features, out_path)

    # Directory and file created (Req 8.4).
    assert outputs_dir.is_dir()
    assert out_path.is_file()

    # Read back: header present, no index column leaking in, first column is
    # client_id (Req 8.1, 8.3), and the row count matches the built frame.
    reloaded = pd.read_csv(out_path)
    assert list(reloaded.columns) == list(features.columns)
    assert reloaded.columns[0] == "client_id"
    # No unnamed index column was written.
    assert not any(str(col).startswith("Unnamed") for col in reloaded.columns)
    assert len(reloaded) == len(features) == 3


def test_build_and_write_empty_clients_header_only(tmp_path: Path) -> None:
    """Zero distinct clients yields a header-only file (Req 8.6).

    build() on an empty transactions frame produces the fixed header columns
    with no rows; write() emits only that header row, and a read-back shows
    zero data rows with the fixed header present.
    """
    features = build(_empty_txns())

    # No rows, and the fixed header columns are present (no spend_share_*
    # columns can be discovered from an empty outflow slice).
    assert len(features) == 0
    assert list(features.columns) == FIXED_COLUMNS

    out_path = tmp_path / "outputs" / "features_part2.csv"
    write(features, out_path)

    assert out_path.is_file()
    reloaded = pd.read_csv(out_path)
    assert len(reloaded) == 0
    assert list(reloaded.columns) == FIXED_COLUMNS
