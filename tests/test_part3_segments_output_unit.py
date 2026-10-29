"""Example/edge-case unit tests for the Segments_File writer.

These are concrete-example tests (not Hypothesis) covering the file-side-effect
and header behavior of :func:`part3_segments.segments.write` against
Requirements 3.1 and 3.3.

Each test builds a small, fully valid ``frames`` dict in memory (the five
coerced input frames the Input_Loader would return), runs
:func:`part3_segments.segments.assign` to produce the per-lead frame, then
writes it with :func:`part3_segments.segments.write` to a path under a
``tmp_path`` subdirectory that does not yet exist. The tests assert that the
missing parent directory is created (3.3) and that the CSV header is exactly
the eight ordered output columns (3.1).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from part3_segments.segments import SEGMENTS_FILE_COLUMNS, assign, write

# The exact ordered header the Segments_File must carry (Requirement 3.1).
EXPECTED_HEADER = [
    "promo_id",
    "client_id",
    "p_join",
    "capacity_php",
    "segment",
    "top_driver_1",
    "top_driver_2",
    "top_driver_3",
]


def _valid_frames() -> dict[str, pd.DataFrame]:
    """Build a small valid set of the five coerced input frames.

    Mirrors what ``loader.load`` returns: numeric columns are already numeric
    and ``month`` is a ``YYYY-MM`` string. Two promos and three clients are
    enough to exercise ``assign`` end to end and produce a non-trivial
    multi-row Segments_File.
    """
    scores = pd.DataFrame(
        {
            "promo_id": ["P001", "P001", "P002"],
            "client_id": ["C0001", "C0002", "C0003"],
            "p_join": [0.75, 0.25, 0.50],
            "top_driver_1": ["payroll", "bills", "shopping"],
            "top_driver_2": ["shopping", "payroll", "bills"],
            "top_driver_3": ["bills", "shopping", "payroll"],
        }
    )
    features = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002", "C0003"],
            "out_other_bank": [1500.50, 0.0, 250.25],
        }
    )
    adb = pd.DataFrame(
        {
            "client_id": ["C0001", "C0001", "C0002", "C0003"],
            "month": ["2026-07", "2026-08", "2026-08", "2026-06"],
            "adb_php": [10000.00, 12000.00, 500.00, 3000.00],
        }
    )
    promo_history = pd.DataFrame(
        {
            "promo_id": ["P001", "P002"],
            "threshold_php": [8000.00, 2000.00],
        }
    )
    promo_leads = pd.DataFrame(
        {
            "promo_id": ["P001", "P001", "P002"],
            "client_id": ["C0001", "C0002", "C0003"],
            "control_group": [0, 0, 1],
            "joined": [1, 0, 0],
        }
    )
    return {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }


# --- Requirement 3.1: header equals the exact ordered column list -----------


def test_segments_file_header_is_exact_ordered_columns(tmp_path: Path) -> None:
    """The written Segments_File header is exactly the eight ordered columns (3.1).

    After assigning and writing, reading the CSV back yields a header whose
    columns, in order, are ``promo_id``, ``client_id``, ``p_join``,
    ``capacity_php``, ``segment``, ``top_driver_1``, ``top_driver_2``,
    ``top_driver_3`` and nothing else. The intermediate columns ``assign``
    produces (``latest_adb``, ``threshold_php``, ``capacity_high``, ...) must
    not appear.
    """
    leads = assign(_valid_frames())
    out_path = tmp_path / "outputs" / "segments.csv"

    write(leads, out_path)

    written = pd.read_csv(out_path)
    # Columns are exactly the eight required ones, in order (Requirement 3.1).
    assert list(written.columns) == EXPECTED_HEADER
    # The module's declared column list agrees with the requirement order.
    assert SEGMENTS_FILE_COLUMNS == EXPECTED_HEADER
    # One row per Lead in the scores frame carried through.
    assert len(written) == 3


def test_segments_file_header_only_as_first_line(tmp_path: Path) -> None:
    """Exactly one header row precedes the data rows (3.1).

    Reading the raw file, the first physical line is the comma-joined ordered
    header and the file has one data line per Lead, confirming a single header
    row rather than a repeated or missing header.
    """
    leads = assign(_valid_frames())
    out_path = tmp_path / "outputs" / "segments.csv"

    write(leads, out_path)

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == ",".join(EXPECTED_HEADER)
    # Header line plus three data rows.
    assert len(lines) == 1 + 3


# --- Requirement 3.3: writing to a path with an absent parent creates it ----


def test_write_creates_absent_parent_directory(tmp_path: Path) -> None:
    """Writing to a path whose parent is absent creates the directory (3.3).

    The target lives under ``tmp_path/outputs`` which does not exist before the
    call. ``write`` must create the parent directory and produce the file.
    """
    leads = assign(_valid_frames())
    parent = tmp_path / "outputs"
    out_path = parent / "segments.csv"

    # Precondition: the parent directory does not exist yet.
    assert not parent.exists()

    write(leads, out_path)

    # The parent directory was created and the file written (Requirement 3.3).
    assert parent.is_dir()
    assert out_path.is_file()


def test_write_creates_nested_absent_parents(tmp_path: Path) -> None:
    """A deeper absent parent chain is created too (3.3).

    ``write`` uses ``mkdir(parents=True)``, so a path several levels below an
    existing directory still succeeds without a pre-existing intermediate
    directory.
    """
    leads = assign(_valid_frames())
    out_path = tmp_path / "a" / "b" / "outputs" / "segments.csv"

    assert not out_path.parent.exists()

    write(leads, out_path)

    assert out_path.parent.is_dir()
    assert out_path.is_file()
