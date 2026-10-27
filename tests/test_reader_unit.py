"""Example/edge-case unit tests for ``part2_network.reader.read``.

These are concrete-example tests (not Hypothesis) covering the ordered
validation and type-coercion behavior of the Transaction_Reader against
Requirements 1.1-1.6.
"""

from pathlib import Path

import pandas as pd
import pytest

from part2_network.reader import read

# A header line with every required column plus txn_id (used as the row
# identifier in error messages) in the canonical Transactions_File order.
HEADER = (
    "txn_id,client_id,txn_date,direction,amount_php,"
    "counterparty_id,counterparty_type,counterparty_category,channel"
)


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write ``lines`` (newline-joined) to ``tmp_path/name`` and return it."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_missing_file_raises_filenotfound_naming_path(tmp_path: Path) -> None:
    """A non-existent path raises FileNotFoundError naming the path (1.2)."""
    missing = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError) as excinfo:
        read(missing)

    # The error must name the missing path so the operator can locate it.
    assert str(missing) in str(excinfo.value)


def test_header_only_file_raises_no_records_error(tmp_path: Path) -> None:
    """A header-only file (zero data rows) raises a no-records error (1.6)."""
    path = _write(tmp_path, "empty.csv", [HEADER])

    with pytest.raises(ValueError) as excinfo:
        read(path)

    message = str(excinfo.value).lower()
    assert "no transaction records" in message


def test_valid_csv_reads_and_coerces_dtypes(tmp_path: Path) -> None:
    """A fully valid CSV reads and coerces amount_php/txn_date dtypes (1.1).

    Happy path: the returned frame has a numeric ``amount_php`` column and a
    datetime ``txn_date`` column, with values intact.
    """
    rows = [
        HEADER,
        "T1,C1,2026-07-15,OUT,1500.50,X1,Other bank,Bills,InstaPay",
        "T2,C1,2026-08-03,IN,2000.00,X2,BPI,Payroll,Internal",
        "T3,C2,2026-09-21,OUT,750.25,X3,Other bank,Shopping,PESONet",
    ]
    path = _write(tmp_path, "valid.csv", rows)

    frame = read(path)

    assert len(frame) == 3
    # amount_php coerced to a numeric dtype.
    assert pd.api.types.is_numeric_dtype(frame["amount_php"])
    # txn_date coerced to a datetime dtype.
    assert pd.api.types.is_datetime64_any_dtype(frame["txn_date"])
    # Values survived coercion.
    assert frame["amount_php"].tolist() == [1500.50, 2000.00, 750.25]
    assert frame["txn_date"].tolist() == [
        pd.Timestamp("2026-07-15"),
        pd.Timestamp("2026-08-03"),
        pd.Timestamp("2026-09-21"),
    ]


def test_missing_required_column_raises_naming_column(tmp_path: Path) -> None:
    """A CSV missing a required column raises ValueError listing it (1.3)."""
    # Header without the required ``direction`` column.
    header = (
        "txn_id,client_id,txn_date,amount_php,"
        "counterparty_id,counterparty_type,counterparty_category,channel"
    )
    rows = [
        header,
        "T1,C1,2026-07-15,1500.50,X1,Other bank,Bills,InstaPay",
    ]
    path = _write(tmp_path, "missing_col.csv", rows)

    with pytest.raises(ValueError) as excinfo:
        read(path)

    assert "direction" in str(excinfo.value)


def test_non_numeric_amount_raises_naming_amount_php(tmp_path: Path) -> None:
    """A non-numeric amount_php raises ValueError naming amount_php (1.4/1.5)."""
    rows = [
        HEADER,
        "T1,C1,2026-07-15,OUT,1500.50,X1,Other bank,Bills,InstaPay",
        # amount_php is not parseable as a number.
        "T2,C1,2026-08-03,IN,not-a-number,X2,BPI,Payroll,Internal",
    ]
    path = _write(tmp_path, "bad_amount.csv", rows)

    with pytest.raises(ValueError) as excinfo:
        read(path)

    message = str(excinfo.value)
    assert "amount_php" in message
    # At least one offending row identifier is reported (Req 1.5).
    assert "T2" in message


def test_malformed_date_raises_naming_txn_date(tmp_path: Path) -> None:
    """A malformed txn_date raises ValueError naming txn_date (1.4/1.5)."""
    rows = [
        HEADER,
        "T1,C1,2026-07-15,OUT,1500.50,X1,Other bank,Bills,InstaPay",
        # txn_date is not a valid YYYY-MM-DD calendar date.
        "T2,C1,2026-13-40,IN,2000.00,X2,BPI,Payroll,Internal",
    ]
    path = _write(tmp_path, "bad_date.csv", rows)

    with pytest.raises(ValueError) as excinfo:
        read(path)

    message = str(excinfo.value)
    assert "txn_date" in message
    # At least one offending row identifier is reported (Req 1.5).
    assert "T2" in message
