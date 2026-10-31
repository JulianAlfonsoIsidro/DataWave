"""Example/edge-case unit tests for ``part4_cards.loader.load``.

These are concrete-example tests (not Hypothesis) covering the ordered
validation and type-coercion behavior of the Input_Loader against Requirements
1.1, 1.2, 1.3, and 6.6.

Each test builds a small, fully valid set of the seven input CSVs in a pytest
``tmp_path`` and points a :class:`~part4_cards.config.Config` at them. Error
cases then remove a file or drop a required column from exactly one input,
leaving the others valid, so the first structural defect reported is the one
under test. The loader never writes anything, so error cases also assert that
no ``outputs/`` directory is created.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from part4_cards.config import Config
from part4_cards.loader import load

# Canonical headers for each of the seven inputs, in the column order the
# pipeline expects. Each ``_valid_*`` helper writes a small frame with these.
SEGMENTS_HEADER = (
    "promo_id,client_id,p_join,capacity_php,segment,top_driver_1,top_driver_2,top_driver_3"
)
SEGMENT_SUMMARY_HEADER = "promo_id,segment,n_clients"
NDB_HEADER = "client_id,flag_type,flag_date"
CONTACT_HISTORY_HEADER = "client_id,contact_date,campaign_id,channel"
CHANNEL_COSTS_HEADER = "channel,cost_php_per_message,source"
CUSTOMER_DNA_HEADER = "client_id,digital_app_user,email_valid,mobile_valid,segment"
PROMO_HISTORY_HEADER = "promo_id,mechanic,channels"


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write ``lines`` (newline-joined) to ``tmp_path/name`` and return it."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_inputs(tmp_path: Path) -> dict[str, Path]:
    """Write a small valid set of the seven inputs and return their paths.

    The values are chosen so the happy-path coercion test can assert exact
    numeric values and that ``contact_date`` stays a ``YYYY-MM-DD`` string.
    """
    segments = _write(
        tmp_path,
        "segments.csv",
        [
            SEGMENTS_HEADER,
            "P001,C0001,0.75,8000,Ready Toppers,payroll,shopping,bills",
            "P001,C0002,0.25,2000,Not Now,bills,payroll,shopping",
            "P002,C0003,0.50,5000,Untapped Wealth,shopping,bills,payroll",
        ],
    )
    segment_summary = _write(
        tmp_path,
        "segment_summary.csv",
        [
            SEGMENT_SUMMARY_HEADER,
            "P001,Ready Toppers,1",
            "P001,Not Now,1",
            "P002,Untapped Wealth,1",
        ],
    )
    ndb = _write(
        tmp_path,
        "ndb.csv",
        [
            NDB_HEADER,
            "C9999,manual,2026-01-01",
        ],
    )
    contact_history = _write(
        tmp_path,
        "contact_history.csv",
        [
            CONTACT_HISTORY_HEADER,
            "C0001,2026-07-15,CMP1,Email",
            "C0001,2026-08-20,CMP2,SMS",
            "C0003,2026-06-10,CMP3,In-app",
        ],
    )
    channel_costs = _write(
        tmp_path,
        "channel_costs.csv",
        [
            CHANNEL_COSTS_HEADER,
            "In-app,1.17,ops",
            "Email,0.053,ops",
            "SMS,0.264,ops",
        ],
    )
    customer_dna = _write(
        tmp_path,
        "customer_dna.csv",
        [
            CUSTOMER_DNA_HEADER,
            "C0001,1,1,0,A",
            "C0002,0,1,1,B",
            "C0003,1,0,1,C",
        ],
    )
    promo_history = _write(
        tmp_path,
        "promo_history.csv",
        [
            PROMO_HISTORY_HEADER,
            "P001,TOP_UP,\"Email, In-app\"",
            "P002,NEW_ACCOUNT,\"SMS, Email\"",
        ],
    )
    return {
        "segments": segments,
        "segment_summary": segment_summary,
        "ndb": ndb,
        "contact_history": contact_history,
        "channel_costs": channel_costs,
        "customer_dna": customer_dna,
        "promo_history": promo_history,
    }


def _config_for(paths: dict[str, Path], tmp_path: Path) -> Config:
    """Build a Config whose seven input paths point at ``paths``.

    The output paths are aimed at a ``tmp_path`` location so a test can assert
    the loader never creates it.
    """
    return Config(
        segments_path=paths["segments"],
        segment_summary_path=paths["segment_summary"],
        ndb_path=paths["ndb"],
        contact_history_path=paths["contact_history"],
        channel_costs_path=paths["channel_costs"],
        customer_dna_path=paths["customer_dna"],
        promo_history_path=paths["promo_history"],
        cards_out_path=tmp_path / "outputs" / "cards.json",
        leads_out_dir=tmp_path / "outputs" / "leads",
    )


# --- Requirement 1.1, 6.6: valid set reads, coerces, keeps contact_date str --


def test_valid_set_coerces_and_keeps_contact_date_string(tmp_path: Path) -> None:
    """A small valid set reads, coerces numerics, keeps contact_date (1.1, 6.6).

    The returned dict is keyed by the seven frame names; ``p_join``, the three
    DNA flags, and ``cost_php_per_message`` are coerced to numeric dtypes with
    values intact, the three DNA flags are integers, and
    ``contact_history.contact_date`` stays an object (string) column of
    ``YYYY-MM-DD`` values rather than being parsed to a date.
    """
    paths = _valid_inputs(tmp_path)

    frames = load(_config_for(paths, tmp_path))

    # All seven frames are returned under their canonical keys (Requirement 1.1).
    assert set(frames) == {
        "segments",
        "segment_summary",
        "ndb",
        "contact_history",
        "channel_costs",
        "customer_dna",
        "promo_history",
    }

    # p_join coerces to float with values intact (Requirement 1.1).
    assert pd.api.types.is_numeric_dtype(frames["segments"]["p_join"])
    assert frames["segments"]["p_join"].tolist() == [0.75, 0.25, 0.50]

    # The three DNA flags coerce to integers (Requirement 1.1).
    for flag in ("digital_app_user", "email_valid", "mobile_valid"):
        assert pd.api.types.is_integer_dtype(frames["customer_dna"][flag])
    assert frames["customer_dna"]["digital_app_user"].tolist() == [1, 0, 1]
    assert frames["customer_dna"]["email_valid"].tolist() == [1, 1, 0]
    assert frames["customer_dna"]["mobile_valid"].tolist() == [0, 1, 1]

    # cost_php_per_message coerces to float with values intact (Requirement 1.1).
    assert pd.api.types.is_numeric_dtype(frames["channel_costs"]["cost_php_per_message"])
    assert frames["channel_costs"]["cost_php_per_message"].tolist() == [1.17, 0.053, 0.264]

    # contact_date is kept as a YYYY-MM-DD string, NOT parsed to a datetime.
    assert not pd.api.types.is_datetime64_any_dtype(frames["contact_history"]["contact_date"])
    assert frames["contact_history"]["contact_date"].tolist() == [
        "2026-07-15",
        "2026-08-20",
        "2026-06-10",
    ]

    # The loader writes nothing, so no outputs directory appears (Requirement 6.6).
    assert not (tmp_path / "outputs").exists()


# --- Requirement 1.2: a missing file raises FileNotFoundError naming the path -


@pytest.mark.parametrize(
    "missing_key",
    [
        "segments",
        "segment_summary",
        "ndb",
        "contact_history",
        "channel_costs",
        "customer_dna",
        "promo_history",
    ],
)
def test_missing_file_raises_filenotfound_naming_path(
    tmp_path: Path, missing_key: str
) -> None:
    """Any of the seven inputs missing raises FileNotFoundError naming it (1.2).

    A valid set is built, then exactly one file is removed. The loader must
    halt and name the absent path, and must leave ``outputs/`` untouched.
    """
    paths = _valid_inputs(tmp_path)
    missing_path = paths[missing_key]
    missing_path.unlink()
    cfg = _config_for(paths, tmp_path)

    with pytest.raises(FileNotFoundError) as excinfo:
        load(cfg)

    # The error names the missing path (Requirement 1.2).
    assert str(missing_path) in str(excinfo.value)
    # No output directory was created on the halt (Requirements 1.2, 6.6).
    assert not (tmp_path / "outputs").exists()


# --- Requirement 1.3: a missing required column raises ValueError naming it ---


@pytest.mark.parametrize(
    ("file_key", "file_name", "header", "row", "removed"),
    [
        (
            "segments",
            "segments.csv",
            SEGMENTS_HEADER,
            "P001,C0001,0.75,8000,Ready Toppers,payroll,shopping,bills",
            ["p_join", "top_driver_1"],
        ),
        (
            "customer_dna",
            "customer_dna.csv",
            CUSTOMER_DNA_HEADER,
            "C0001,1,1,0,A",
            ["digital_app_user", "mobile_valid"],
        ),
        (
            "promo_history",
            "promo_history.csv",
            PROMO_HISTORY_HEADER,
            "P001,TOP_UP,Email",
            ["channels", "mechanic"],
        ),
        (
            "channel_costs",
            "channel_costs.csv",
            CHANNEL_COSTS_HEADER,
            "In-app,1.17,ops",
            ["cost_php_per_message"],
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
    must name the affected file and every removed column, and leave
    ``outputs/`` untouched.
    """
    paths = _valid_inputs(tmp_path)

    header_cols = header.split(",")
    row_values = row.split(",")
    keep_idx = [i for i, col in enumerate(header_cols) if col not in removed]
    new_header = ",".join(header_cols[i] for i in keep_idx)
    new_row = ",".join(row_values[i] for i in keep_idx)

    # Overwrite the targeted file with the trimmed header/row.
    paths[file_key] = _write(tmp_path, file_name, [new_header, new_row])
    cfg = _config_for(paths, tmp_path)

    with pytest.raises(ValueError) as excinfo:
        load(cfg)

    message = str(excinfo.value)
    # The affected file path is named (Requirement 1.3).
    assert str(paths[file_key]) in message
    # Every removed column is named (Requirement 1.3).
    for col in removed:
        assert col in message
    # No output directory was created on the halt (Requirements 1.3, 6.6).
    assert not (tmp_path / "outputs").exists()
