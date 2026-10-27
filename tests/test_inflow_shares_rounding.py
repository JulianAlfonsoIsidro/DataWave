"""Example/edge-case unit test for inflow-share 6-decimal rounding.

Concrete-example test (not Hypothesis) for the rounding behavior required by
Requirement 6.4: each Inflow_Share is produced as a number in [0, 1] rounded
to 6 decimal places.

``features.inflow_shares`` returns a dict of ``{column: per-client Series}``
left **unrounded** on purpose -- rounding to 6 decimals is applied once at
output assembly (task 7.1, not yet implemented). So this test exercises the
rounding at the 6-decimal level: it builds a small hand-built transactions
frame whose inflow shares are *repeating* decimals (split in 1/3 : 1/3 : 1/3
and 1/7 ratios so the true shares are non-terminating -- 0.333333..., and
0.142857.../0.285714...), then asserts that

  * the function's unrounded output is within 1e-6 of the exact fraction, and
  * applying ``round(value, 6)`` yields the expected 6-decimal value that
    output assembly (task 7.1) will record.
"""

from __future__ import annotations

from fractions import Fraction

import pandas as pd

from part2_network.config import INFLOW_SHARE_COLUMNS
from part2_network.features import inflow_shares, split_by_direction


def _frame(rows: list[dict]) -> pd.DataFrame:
    """Build a transactions frame matching the reader's output schema.

    Columns and dtypes mirror what ``reader.read`` yields: ``client_id`` /
    ``direction`` / counterparty columns as objects, ``amount_php`` float, and
    ``txn_date`` as ``datetime64``.
    """
    columns = [
        "client_id",
        "txn_date",
        "direction",
        "amount_php",
        "counterparty_type",
        "counterparty_category",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["amount_php"] = pd.to_numeric(frame["amount_php"], errors="raise")
    frame["txn_date"] = pd.to_datetime(
        frame["txn_date"], format="%Y-%m-%d", errors="raise"
    )
    return frame


def _in(client_id: str, amount: float, category: str) -> dict:
    """A single Inflow (``direction == "IN"``) row for ``client_id``."""
    return {
        "client_id": client_id,
        "txn_date": "2026-07-15",
        "direction": "IN",
        "amount_php": amount,
        "counterparty_type": "Same bank",
        "counterparty_category": category,
    }


def test_inflow_shares_round_to_six_decimals() -> None:
    """Inflow shares respect 6-decimal rounding (Requirement 6.4).

    Two clients with non-terminating share fractions:

      * C_THIRDS splits inflow equally across the three sources, so each true
        share is 1/3 = 0.333333... -> round(6) == 0.333333.
      * C_SEVENTHS has total inflow 7 split 1 (Payroll) / 2 (Remittance) /
        4 (Business receipts), so the true shares are 1/7 = 0.142857...,
        2/7 = 0.285714..., and 4/7 = 0.571428... -> round(6) == 0.142857,
        0.285714, 0.571429.
    """
    rows = [
        # C_THIRDS: 10 / 10 / 10 across the three sources -> each share 1/3.
        _in("C_THIRDS", 10.0, "Payroll"),
        _in("C_THIRDS", 10.0, "Remittance"),
        _in("C_THIRDS", 10.0, "Business receipts"),
        # C_SEVENTHS: 1 / 2 / 4 (total 7) -> shares 1/7, 2/7, 4/7.
        _in("C_SEVENTHS", 1.0, "Payroll"),
        _in("C_SEVENTHS", 2.0, "Remittance"),
        _in("C_SEVENTHS", 4.0, "Business receipts"),
    ]
    txns = _frame(rows)
    clients = ["C_SEVENTHS", "C_THIRDS"]

    _, inflows, _ = split_by_direction(txns)
    shares = inflow_shares(inflows, clients)

    payroll = INFLOW_SHARE_COLUMNS["Payroll"]
    remittance = INFLOW_SHARE_COLUMNS["Remittance"]
    business = INFLOW_SHARE_COLUMNS["Business receipts"]

    # Exact (true) fractions each unrounded value is expected to approximate.
    expected_fractions = {
        "C_THIRDS": {
            payroll: Fraction(1, 3),
            remittance: Fraction(1, 3),
            business: Fraction(1, 3),
        },
        "C_SEVENTHS": {
            payroll: Fraction(1, 7),
            remittance: Fraction(2, 7),
            business: Fraction(4, 7),
        },
    }

    # Expected values AFTER output assembly rounds to 6 decimals (Req 6.4).
    expected_rounded = {
        "C_THIRDS": {
            payroll: 0.333333,
            remittance: 0.333333,
            business: 0.333333,
        },
        "C_SEVENTHS": {
            payroll: 0.142857,  # 1/7 = 0.1428571... -> 0.142857
            remittance: 0.285714,  # 2/7 = 0.2857142... -> 0.285714
            business: 0.571429,  # 4/7 = 0.5714285... -> 0.571429
        },
    }

    for client, per_column in expected_fractions.items():
        for column, fraction in per_column.items():
            raw = shares[column].loc[client]

            # The feature leaves values unrounded: raw is within 1e-6 of the
            # exact fraction (the share really is the non-terminating value).
            assert abs(raw - float(fraction)) < 1e-6, (
                f"{client}/{column}: unrounded {raw!r} not within 1e-6 of "
                f"{fraction} ({float(fraction)!r})"
            )

            # Rounding to 6 decimals (the task 7.1 output step) yields the
            # expected 6-dp value, and that value matches round of the exact
            # fraction too.
            assert round(raw, 6) == expected_rounded[client][column]
            assert round(raw, 6) == round(float(fraction), 6)

    # A rounded share stays within [0, 1] and carries at most 6 decimals, so
    # the recorded string never exceeds 6 fractional digits (Req 6.4).
    for column in (payroll, remittance, business):
        for client in clients:
            rounded = round(shares[column].loc[client], 6)
            assert 0.0 <= rounded <= 1.0
            # No more than 6 digits after the decimal point once rounded.
            text = f"{rounded:.10f}".rstrip("0")
            decimals = text.split(".")[1] if "." in text else ""
            assert len(decimals) <= 6
