"""Transaction_Reader: load and structurally validate the transactions CSV.

This is the only component permitted to halt the Part2_Network_Pipeline. It
validates in a fixed order so the first structural defect is the one reported,
and it never writes anything, so any raised error leaves ``outputs/`` untouched
(the halt-without-output guarantee of Requirement 1).
"""

from pathlib import Path

import pandas as pd

from part2_network.config import REQUIRED_COLUMNS


def read(path: Path) -> pd.DataFrame:
    """Load and validate the Transactions_File.

    Returns a frame guaranteed to have all required columns, a numeric
    ``amount_php`` column, and a ``datetime64`` ``txn_date`` column.

    Validation runs in a fixed order; each failure raises before the next
    check so the first structural problem is reported:

    1. Existence -- raise ``FileNotFoundError`` naming the path (Req 1.2).
    2. Read -- ``pd.read_csv(path, dtype=str, keep_default_na=False)`` so raw
       values can be inspected before coercion.
    3. Empty -- zero data rows raises ``ValueError`` (Req 1.6).
    4. Columns -- any missing required column raises ``ValueError`` listing
       every missing column (Req 1.3).
    5. ``amount_php`` coercion -- unparseable values raise ``ValueError``
       naming the column and >=1 offending row id (Req 1.4, 1.5).
    6. ``txn_date`` coercion -- unparseable values raise ``ValueError`` in the
       same style (Req 1.4, 1.5).

    Args:
        path: Path to the transactions CSV.

    Returns:
        The validated, type-coerced transactions frame.

    Raises:
        FileNotFoundError: If ``path`` does not exist (Req 1.2).
        ValueError: If the file is empty, missing required columns, or has
            unparseable ``amount_php`` / ``txn_date`` values
            (Req 1.3, 1.4, 1.5, 1.6).
    """
    path = Path(path)

    # 1. Existence (Requirement 1.2).
    if not path.exists():
        raise FileNotFoundError(f"Transactions file not found: {path}")

    # 2. Read raw string values so they can be checked before coercion.
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)

    # 3. Empty-frame check (Requirement 1.6).
    if len(frame) == 0:
        raise ValueError(
            f"Transactions file contains no transaction records: {path}"
        )

    # 4. Missing-column check (Requirement 1.3).
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(
            "Transactions file is missing required column(s): "
            + ", ".join(missing_columns)
        )

    # 5. Coerce amount_php to numeric; unparseable values become NaN
    #    (Requirements 1.4, 1.5).
    amount = pd.to_numeric(frame["amount_php"], errors="coerce")
    _raise_on_unparseable(frame, amount.isna(), "amount_php")
    frame["amount_php"] = amount

    # 6. Coerce txn_date to datetime; unparseable values become NaT
    #    (Requirements 1.4, 1.5).
    txn_date = pd.to_datetime(
        frame["txn_date"], format="%Y-%m-%d", errors="coerce"
    )
    _raise_on_unparseable(frame, txn_date.isna(), "txn_date")
    frame["txn_date"] = txn_date

    return frame


def _raise_on_unparseable(
    frame: pd.DataFrame, bad_mask: pd.Series, column: str
) -> None:
    """Raise a ``ValueError`` naming ``column`` and >=1 offending row id.

    The offending row identifier is taken from ``txn_id`` when that column is
    present, falling back to the zero-based row index otherwise (Req 1.5).
    """
    if not bad_mask.any():
        return

    offending_positions = [
        position
        for position, is_bad in enumerate(bad_mask.to_numpy())
        if is_bad
    ]

    if "txn_id" in frame.columns:
        identifiers = frame["txn_id"].iloc[offending_positions].tolist()
        identifier_label = "txn_id"
    else:
        identifiers = offending_positions
        identifier_label = "row index"

    # Report at least one offending identifier; cap the list so the message
    # stays readable when many rows are unparseable.
    shown = identifiers[:5]
    shown_text = ", ".join(str(value) for value in shown)
    if len(identifiers) > len(shown):
        shown_text += ", ..."

    raise ValueError(
        f"Column '{column}' has {len(offending_positions)} unparseable "
        f"value(s); offending {identifier_label}(s): {shown_text}"
    )
