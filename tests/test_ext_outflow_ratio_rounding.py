"""Example/edge-case unit test for ext-outflow-ratio 4-decimal rounding.

Concrete-example test (not Hypothesis) for the rounding behavior required by
Requirement 4.4: Ext_Outflow_Ratio is produced as a number in [0, 1] rounded
to 4 decimal places.

``features.ext_outflow_ratio`` returns the ratio ``out_other_bank / total_out``
as a per-client Series left **unrounded** on purpose -- rounding to 4 decimals
is applied once at output assembly (task 7.1, not yet implemented). So this
test exercises the rounding at the 4-decimal level: it builds a small
hand-built transactions frame (matching the reader's output schema) whose
external-outflow ratios are *repeating* decimals (1/3 = 0.3333... and
2/7 = 0.2857...), plus a client with zero total outflow, then asserts that

  * the function's unrounded output is within 1e-6 of the exact fraction,
  * applying ``round(value, 4)`` yields the expected 4-decimal value that
    output assembly (task 7.1) will record, in [0, 1], and
  * a client whose Total_Out is 0 reports ratio 0 (Requirement 4.2), whose
    round to 4 decimals is 0.0.
"""

from __future__ import annotations

from fractions import Fraction

import pandas as pd

from part2_network.config import EXTERNAL_COUNTERPARTY_TYPE
from part2_network.features import (
    ext_outflow_ratio,
    out_other_bank,
    split_by_direction,
    total_out,
)


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


def _out(client_id: str, amount: float, counterparty_type: str) -> dict:
    """A single Outflow (``direction == "OUT"``) row for ``client_id``.

    ``counterparty_type`` of "Other bank" makes the row an External_Outflow
    (counted in Out_Other_Bank); any other value counts only toward Total_Out.
    """
    return {
        "client_id": client_id,
        "txn_date": "2026-07-15",
        "direction": "OUT",
        "amount_php": amount,
        "counterparty_type": counterparty_type,
        "counterparty_category": "E-commerce",
    }


def test_ext_outflow_ratio_rounds_to_four_decimals() -> None:
    """Ext_Outflow_Ratio respects 4-decimal rounding (Requirement 4.4).

    Three clients exercise non-terminating ratios and the zero-denominator
    guard:

      * C_THIRD has Out_Other_Bank 1 out of Total_Out 3 (1 external + 2
        other-counterparty outflow), so the true ratio is 1/3 = 0.3333...
        -> round(4) == 0.3333.
      * C_TWO_SEVENTHS has Out_Other_Bank 2 out of Total_Out 7, so the true
        ratio is 2/7 = 0.285714... -> round(4) == 0.2857.
      * C_NO_OUT has no Outflow transactions at all, so Total_Out == 0 and the
        ratio is forced to 0 (Requirement 4.2) -> round(4) == 0.0.
    """
    other = "Same bank"  # any counterparty_type that is NOT an External_Outflow
    rows = [
        # C_THIRD: 1 external out of 3 total -> ratio 1/3.
        _out("C_THIRD", 1.0, EXTERNAL_COUNTERPARTY_TYPE),
        _out("C_THIRD", 2.0, other),
        # C_TWO_SEVENTHS: 2 external out of 7 total -> ratio 2/7.
        _out("C_TWO_SEVENTHS", 2.0, EXTERNAL_COUNTERPARTY_TYPE),
        _out("C_TWO_SEVENTHS", 5.0, other),
        # C_NO_OUT: only an inflow, so Total_Out == 0 -> ratio 0.
        {
            "client_id": "C_NO_OUT",
            "txn_date": "2026-07-15",
            "direction": "IN",
            "amount_php": 100.0,
            "counterparty_type": "Same bank",
            "counterparty_category": "Payroll",
        },
    ]
    txns = _frame(rows)
    clients = ["C_NO_OUT", "C_THIRD", "C_TWO_SEVENTHS"]

    outflows, _, ext_outflows = split_by_direction(txns)
    total = total_out(outflows, clients)
    other_bank = out_other_bank(ext_outflows, clients)
    ratio = ext_outflow_ratio(total, other_bank)

    # Exact (true) fractions each non-zero-denominator ratio approximates.
    expected_fractions = {
        "C_THIRD": Fraction(1, 3),
        "C_TWO_SEVENTHS": Fraction(2, 7),
    }
    # Expected values AFTER output assembly rounds to 4 decimals (Req 4.4).
    expected_rounded = {
        "C_THIRD": 0.3333,  # 1/3 = 0.33333... -> 0.3333
        "C_TWO_SEVENTHS": 0.2857,  # 2/7 = 0.285714... -> 0.2857
    }

    for client, fraction in expected_fractions.items():
        raw = ratio.loc[client]

        # The feature leaves values unrounded: raw is within 1e-6 of the exact
        # fraction (the ratio really is the non-terminating value).
        assert abs(raw - float(fraction)) < 1e-6, (
            f"{client}: unrounded {raw!r} not within 1e-6 of "
            f"{fraction} ({float(fraction)!r})"
        )

        # Rounding to 4 decimals (the task 7.1 output step) yields the expected
        # 4-dp value, which matches round of the exact fraction too.
        assert round(raw, 4) == expected_rounded[client]
        assert round(raw, 4) == round(float(fraction), 4)

        # The rounded ratio stays within the inclusive [0, 1] range (Req 4.3)
        # and carries at most 4 fractional digits once rounded (Req 4.4).
        rounded = round(raw, 4)
        assert 0.0 <= rounded <= 1.0
        text = f"{rounded:.8f}".rstrip("0")
        decimals = text.split(".")[1] if "." in text else ""
        assert len(decimals) <= 4

    # Zero-denominator client: Total_Out is 0, so the ratio is exactly 0
    # (Requirement 4.2) and round(0, 4) == 0.0.
    assert total.loc["C_NO_OUT"] == 0
    assert ratio.loc["C_NO_OUT"] == 0
    assert round(ratio.loc["C_NO_OUT"], 4) == 0.0
