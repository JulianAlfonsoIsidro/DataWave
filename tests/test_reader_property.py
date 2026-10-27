"""Property-based tests for ``part2_network.reader.read``.

Covers Property 14 (unparseable-value reporting) of the part2-network spec.
"""

import csv

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from part2_network.config import REQUIRED_COLUMNS
from part2_network.reader import read


# The full on-disk header. ``txn_id`` is present so the reader reports it as the
# offending row identifier (Requirement 1.5); the required columns guarantee the
# frame is otherwise structurally valid so the first defect reached is the
# injected unparseable value.
HEADER = ["txn_id"] + REQUIRED_COLUMNS

# A set of raw strings that pandas cannot coerce to a number (for amount_php)
# nor to a YYYY-MM-DD date (for txn_date). These are deliberately unparseable by
# both coercions so the same pool works regardless of which column is corrupted.
UNPARSEABLE = ["abc", "n/a", "N.A.", "twelve", "--", "??", "oops", "1.2.3"]


def _valid_row(index: int) -> dict:
    """Build one structurally-valid transaction row (all raw strings)."""
    return {
        "txn_id": f"T{index:04d}",
        "client_id": f"C{index % 7:03d}",
        "txn_date": "2026-07-15",
        "direction": "OUT" if index % 2 == 0 else "IN",
        "amount_php": f"{100 + index}.00",
        "counterparty_type": "Other bank",
        "counterparty_category": "Grocery",
    }


def _write_csv(path, rows):
    """Write ``rows`` (list of dicts keyed by HEADER) to ``path`` as CSV."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


# Feature: part2-network, Property 14: Unparseable values are reported with
# column and offending row
@settings(max_examples=100)
@given(
    data=st.data(),
    corrupt_column=st.sampled_from(["amount_php", "txn_date"]),
    n_rows=st.integers(min_value=1, max_value=8),
)
def test_unparseable_values_report_column_and_offending_row(
    tmp_path_factory, data, corrupt_column, n_rows
):
    """An injected unparseable value halts the reader with a ValueError that
    names the affected column and at least one offending row identifier.

    Validation order checks ``amount_php`` before ``txn_date``. When
    ``amount_php`` is corrupted the error must name ``amount_php``. When only
    ``txn_date`` is corrupted (``amount_php`` left valid), the error must name
    ``txn_date``.

    Validates: Requirements 1.4, 1.5
    """
    rows = [_valid_row(i) for i in range(n_rows)]

    # Choose at least one row to corrupt (a non-empty subset of the rows).
    bad_positions = data.draw(
        st.lists(
            st.integers(min_value=0, max_value=n_rows - 1),
            min_size=1,
            max_size=n_rows,
            unique=True,
        )
    )
    bad_value = data.draw(st.sampled_from(UNPARSEABLE))

    for position in bad_positions:
        rows[position][corrupt_column] = bad_value

    csv_path = tmp_path_factory.mktemp("txns") / "transactions.csv"
    _write_csv(csv_path, rows)

    with pytest.raises(ValueError) as excinfo:
        read(csv_path)

    message = str(excinfo.value)

    # The error names the corrupted column...
    assert corrupt_column in message
    # ...and because amount_php is validated before txn_date, corrupting
    # amount_php must never surface as a txn_date error.
    if corrupt_column == "amount_php":
        assert "txn_date" not in message

    # ...and includes at least one offending row identifier. Since txn_id is
    # present, offending identifiers are the txn_id values of corrupted rows.
    offending_ids = [rows[position]["txn_id"] for position in bad_positions]
    assert any(identifier in message for identifier in offending_ids)
