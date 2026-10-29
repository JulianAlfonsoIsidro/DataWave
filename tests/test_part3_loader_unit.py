"""Example/edge-case unit tests for ``part3_segments.loader.load``.

These are concrete-example tests (not Hypothesis) covering the ordered
validation and type-coercion behavior of the Input_Loader against Requirements
1.1, 1.2, 1.3, and 1.4.

Each test builds a small, fully valid set of the five input CSVs in a pytest
``tmp_path`` and points a :class:`~part3_segments.config.Config` at them. Error
cases then remove a file or drop a required column from exactly one input,
leaving the other four valid, so the first structural defect reported is the
one under test.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from part3_segments.config import Config
from part3_segments.loader import load

# Canonical headers for each of the five inputs, in the column order the
# pipeline expects. Each ``_valid_*`` helper writes a small frame with these.
SCORES_HEADER = "promo_id,client_id,p_join,top_driver_1,top_driver_2,top_driver_3"
FEATURES_HEADER = "client_id,out_other_bank"
ADB_HEADER = "client_id,month,adb_php"
PROMO_HISTORY_HEADER = "promo_id,threshold_php"
PROMO_LEADS_HEADER = "promo_id,client_id,control_group,joined"


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write ``lines`` (newline-joined) to ``tmp_path/name`` and return it."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_inputs(tmp_path: Path) -> dict[str, Path]:
    """Write a small valid set of the five inputs and return their paths.

    The values are chosen so the happy-path coercion test can assert exact
    numeric values and that ``month`` stays a ``YYYY-MM`` string.
    """
    scores = _write(
        tmp_path,
        "scores.csv",
        [
            SCORES_HEADER,
            "P001,C0001,0.75,payroll,shopping,bills",
            "P001,C0002,0.25,bills,payroll,shopping",
            "P002,C0003,0.50,shopping,bills,payroll",
        ],
    )
    features = _write(
        tmp_path,
        "features_part2.csv",
        [
            FEATURES_HEADER,
            "C0001,1500.50",
            "C0002,0",
            "C0003,250.25",
        ],
    )
    adb = _write(
        tmp_path,
        "adb_monthly.csv",
        [
            ADB_HEADER,
            "C0001,2026-07,10000.00",
            "C0001,2026-08,12000.00",
            "C0002,2026-08,500.00",
            "C0003,2026-06,3000.00",
        ],
    )
    promo_history = _write(
        tmp_path,
        "promo_history.csv",
        [
            PROMO_HISTORY_HEADER,
            "P001,8000.00",
            "P002,2000.00",
        ],
    )
    promo_leads = _write(
        tmp_path,
        "promo_leads.csv",
        [
            PROMO_LEADS_HEADER,
            "P001,C0001,0,1",
            "P001,C0002,0,0",
            "P002,C0003,1,0",
        ],
    )
    return {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }


def _config_for(paths: dict[str, Path]) -> Config:
    """Build a Config whose five input paths point at ``paths``."""
    return Config(
        scores_path=paths["scores"],
        features_path=paths["features"],
        adb_monthly_path=paths["adb"],
        promo_history_path=paths["promo_history"],
        promo_leads_path=paths["promo_leads"],
    )


# --- Requirement 1.1, 1.4: valid set reads, coerces, keeps month a string ---


def test_valid_set_coerces_numerics_and_keeps_month_string(tmp_path: Path) -> None:
    """A small valid set reads, coerces numerics, keeps month YYYY-MM (1.1, 1.4).

    The returned dict is keyed by the five frame names; each numeric column is
    a numeric dtype with values intact, and ``adb.month`` stays an object
    (string) column of ``YYYY-MM`` values rather than being parsed to a date.
    """
    paths = _valid_inputs(tmp_path)

    frames = load(_config_for(paths))

    # All five frames are returned under their canonical keys (Requirement 1.1).
    assert set(frames) == {"scores", "features", "adb", "promo_history", "promo_leads"}

    # Numeric coercion of the four numeric columns (Requirement 1.4).
    assert pd.api.types.is_numeric_dtype(frames["scores"]["p_join"])
    assert pd.api.types.is_numeric_dtype(frames["features"]["out_other_bank"])
    assert pd.api.types.is_numeric_dtype(frames["adb"]["adb_php"])
    assert pd.api.types.is_numeric_dtype(frames["promo_history"]["threshold_php"])

    # Values survived coercion.
    assert frames["scores"]["p_join"].tolist() == [0.75, 0.25, 0.50]
    assert frames["features"]["out_other_bank"].tolist() == [1500.50, 0.0, 250.25]
    assert frames["adb"]["adb_php"].tolist() == [10000.00, 12000.00, 500.00, 3000.00]
    assert frames["promo_history"]["threshold_php"].tolist() == [8000.00, 2000.00]

    # month is kept as a YYYY-MM string, NOT parsed to a datetime (Req 1.4).
    assert not pd.api.types.is_datetime64_any_dtype(frames["adb"]["month"])
    assert frames["adb"]["month"].tolist() == [
        "2026-07",
        "2026-08",
        "2026-08",
        "2026-06",
    ]


# --- Requirement 1.2: a missing file raises FileNotFoundError naming the path -


@pytest.mark.parametrize(
    "missing_key",
    ["scores", "features", "adb", "promo_history", "promo_leads"],
)
def test_missing_file_raises_filenotfound_naming_path(
    tmp_path: Path, missing_key: str
) -> None:
    """Any of the five inputs missing raises FileNotFoundError naming it (1.2).

    A valid set is built, then exactly one file is removed. The loader must
    halt and name the absent path so the operator can locate it.
    """
    paths = _valid_inputs(tmp_path)
    missing_path = paths[missing_key]
    missing_path.unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        load(_config_for(paths))

    # The error names the missing path (Requirement 1.2).
    assert str(missing_path) in str(excinfo.value)


# --- Requirement 1.3: a missing required column raises ValueError naming it ---


@pytest.mark.parametrize(
    ("file_key", "file_name", "header", "row", "removed"),
    [
        (
            "scores",
            "scores.csv",
            SCORES_HEADER,
            "P001,C0001,0.75,payroll,shopping,bills",
            ["p_join", "top_driver_2"],
        ),
        (
            "features",
            "features_part2.csv",
            FEATURES_HEADER,
            "C0001,1500.50",
            ["out_other_bank"],
        ),
        (
            "adb",
            "adb_monthly.csv",
            ADB_HEADER,
            "C0001,2026-08,12000.00",
            ["month"],
        ),
        (
            "promo_history",
            "promo_history.csv",
            PROMO_HISTORY_HEADER,
            "P001,8000.00",
            ["threshold_php"],
        ),
        (
            "promo_leads",
            "promo_leads.csv",
            PROMO_LEADS_HEADER,
            "P001,C0001,0,1",
            ["control_group", "joined"],
        ),
    ],
)
def test_missing_required_column_raises_naming_file_and_columns(
    tmp_path: Path,
    file_key: str,
    file_name: str,
    header: str,
    row: str,
    removed: list[str],
) -> None:
    """A dropped required column raises ValueError naming file + columns (1.3).

    A valid set is built, then one input is rewritten with the ``removed``
    columns dropped from both its header and its single data row. The loader
    must name the affected file and every removed column.
    """
    paths = _valid_inputs(tmp_path)

    header_cols = header.split(",")
    row_values = row.split(",")
    keep_idx = [i for i, col in enumerate(header_cols) if col not in removed]
    new_header = ",".join(header_cols[i] for i in keep_idx)
    new_row = ",".join(row_values[i] for i in keep_idx)

    # Overwrite the targeted file with the trimmed header/row.
    paths[file_key] = _write(tmp_path, file_name, [new_header, new_row])

    with pytest.raises(ValueError) as excinfo:
        load(_config_for(paths))

    message = str(excinfo.value)
    # The affected file path is named (Requirement 1.3).
    assert str(paths[file_key]) in message
    # Every removed column is named (Requirement 1.3).
    for col in removed:
        assert col in message
