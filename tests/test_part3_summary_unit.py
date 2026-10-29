"""Example/edge-case unit tests for the Summary_Builder join rate and writer.

These are concrete-example tests (not Hypothesis) covering two scenario-specific
behaviors of :mod:`part3_segments.validation` against Requirements 4.3, 4.4,
and 4.6:

- The treated-lead Actual_Join_Rate counts only Treated_Leads
  (``control_group == 0``), is bounded in ``[0, 1]``, and never counts control
  rows (4.3); a (promo, segment) cell with zero treated leads carries an empty
  (NaN) rate (4.4).
- :func:`part3_segments.validation.write` creates the ``outputs/`` directory
  when absent and writes a single header row of the seven ``SUMMARY_COLUMNS``
  (4.6).

Each test builds a small, fully valid ``frames`` dict in memory (the five
coerced input frames the Input_Loader would return), runs
:func:`part3_segments.segments.assign` to produce the per-lead frame, then
exercises :func:`part3_segments.validation.build` / ``write``.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from part3_segments.config import SEGMENTS
from part3_segments.segments import assign
from part3_segments.validation import SUMMARY_COLUMNS, build, write


def _rate_for(summary: pd.DataFrame, promo_id: str, segment: str):
    """Return the ``actual_join_rate`` for a single (promo, segment) cell."""
    cell = summary[
        (summary["promo_id"] == promo_id) & (summary["segment"] == segment)
    ]
    assert len(cell) == 1, f"expected exactly one cell for {(promo_id, segment)}"
    return cell["actual_join_rate"].iloc[0]


# --- Requirements 4.3, 4.4: treated-only, bounded, empty-when-none ----------


def test_actual_join_rate_counts_treated_rows_only() -> None:
    """A control row with ``joined == 1`` must not raise the cell's rate (4.3).

    Two leads land in the same (promo, segment) cell. One is a Treated_Lead
    (``control_group == 0``) who did NOT join; the other is a control row
    (``control_group == 1``) who DID join. The rate must reflect the single
    treated lead only (0.0), ignoring the control joiner entirely.
    """
    scores = pd.DataFrame(
        {
            "promo_id": ["P001", "P001"],
            "client_id": ["C0001", "C0002"],
            # Equal p_join so both are at/above the promo median -> score_high.
            "p_join": [0.50, 0.50],
            "top_driver_1": ["payroll", "payroll"],
            "top_driver_2": ["bills", "bills"],
            "top_driver_3": ["shopping", "shopping"],
        }
    )
    features = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002"],
            # Both clients clear the threshold -> capacity_high, same cell.
            "out_other_bank": [0.0, 0.0],
        }
    )
    adb = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002"],
            "month": ["2026-08", "2026-08"],
            "adb_php": [10000.00, 10000.00],
        }
    )
    promo_history = pd.DataFrame(
        {"promo_id": ["P001"], "threshold_php": [5000.00]}
    )
    promo_leads = pd.DataFrame(
        {
            "promo_id": ["P001", "P001"],
            "client_id": ["C0001", "C0002"],
            # C0001 treated & did not join; C0002 control & joined.
            "control_group": [0, 1],
            "joined": [0, 1],
        }
    )
    frames = {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }

    leads = assign(frames)
    # Both leads must have landed in the same cell for this test to be valid.
    assert leads["segment"].nunique() == 1
    cell_segment = leads["segment"].iloc[0]

    summary = build(leads, promo_leads)
    rate = _rate_for(summary, "P001", cell_segment)

    # Only the treated non-joiner counts: rate is 0.0, not 0.5 or 1.0. The
    # control joiner is excluded entirely (Requirement 4.3).
    assert float(rate) == 0.0


def test_actual_join_rate_is_bounded_and_empty_when_no_treated() -> None:
    """Rate stays in ``[0, 1]`` across cells; a no-treated cell is empty (4.3, 4.4).

    A promo with a treated joiner, a treated non-joiner, and control rows
    yields a populated cell whose rate is a valid fraction in ``[0, 1]``. Every
    other (promo, segment) cell -- in particular those with no treated leads
    joined to them -- carries an empty (NaN) ``actual_join_rate`` rather than 0.
    """
    scores = pd.DataFrame(
        {
            "promo_id": ["P001", "P001", "P001", "P001"],
            "client_id": ["C0001", "C0002", "C0003", "C0004"],
            "p_join": [0.90, 0.80, 0.20, 0.10],
            "top_driver_1": ["payroll", "payroll", "bills", "bills"],
            "top_driver_2": ["bills", "bills", "payroll", "payroll"],
            "top_driver_3": ["shopping", "shopping", "shopping", "shopping"],
        }
    )
    features = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002", "C0003", "C0004"],
            "out_other_bank": [0.0, 0.0, 0.0, 0.0],
        }
    )
    adb = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002", "C0003", "C0004"],
            "month": ["2026-08", "2026-08", "2026-08", "2026-08"],
            # First two clear the threshold (high capacity), last two do not.
            "adb_php": [10000.00, 10000.00, 100.00, 100.00],
        }
    )
    promo_history = pd.DataFrame(
        {"promo_id": ["P001"], "threshold_php": [5000.00]}
    )
    promo_leads = pd.DataFrame(
        {
            "promo_id": ["P001", "P001", "P001", "P001"],
            "client_id": ["C0001", "C0002", "C0003", "C0004"],
            # C0001 & C0002 treated (one joined, one not); C0003 & C0004 control.
            "control_group": [0, 0, 1, 1],
            "joined": [1, 0, 1, 1],
        }
    )
    frames = {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }

    leads = assign(frames)
    summary = build(leads, promo_leads)

    # Every present rate is a valid fraction in [0, 1]; empties are NaN.
    present = summary["actual_join_rate"].dropna()
    assert len(present) >= 1
    assert ((present >= 0.0) & (present <= 1.0)).all()

    # C0001 & C0002 share the high-score/high-capacity cell "Ready Toppers":
    # one treated joined, one treated did not -> rate 0.5 (control rows absent).
    ready_rate = _rate_for(summary, "P001", "Ready Toppers")
    assert float(ready_rate) == 0.5

    # The low-capacity cells hold only control leads (C0003, C0004), so no
    # treated lead joins them: their rate must be empty (NaN), not 0 (4.4).
    empty_cells = 0
    for segment in SEGMENTS:
        rate = _rate_for(summary, "P001", segment)
        treated_clients_in_cell = leads[
            (leads["segment"] == segment)
            & (leads["client_id"].isin(["C0001", "C0002"]))
        ]
        if treated_clients_in_cell.empty:
            # No treated lead joined to this cell -> empty rate (Requirement 4.4).
            assert isinstance(rate, float) and math.isnan(rate), (
                f"cell {segment} has no treated leads but rate={rate!r}"
            )
            empty_cells += 1
    # At least one cell genuinely had zero treated leads.
    assert empty_cells >= 1


# --- Requirement 4.6: write creates outputs/ and a single header row --------


def test_write_creates_outputs_dir_and_single_header_row(tmp_path: Path) -> None:
    """``write`` makes ``outputs/`` and emits one header of the seven columns (4.6).

    The target lives under ``tmp_path/outputs`` which does not exist before the
    call. After writing, the directory exists, the file exists, and the first
    physical line is exactly the comma-joined seven ``SUMMARY_COLUMNS``.
    """
    scores = pd.DataFrame(
        {
            "promo_id": ["P001", "P001"],
            "client_id": ["C0001", "C0002"],
            "p_join": [0.75, 0.25],
            "top_driver_1": ["payroll", "bills"],
            "top_driver_2": ["bills", "payroll"],
            "top_driver_3": ["shopping", "shopping"],
        }
    )
    features = pd.DataFrame(
        {"client_id": ["C0001", "C0002"], "out_other_bank": [0.0, 0.0]}
    )
    adb = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002"],
            "month": ["2026-08", "2026-08"],
            "adb_php": [10000.00, 500.00],
        }
    )
    promo_history = pd.DataFrame(
        {"promo_id": ["P001"], "threshold_php": [5000.00]}
    )
    promo_leads = pd.DataFrame(
        {
            "promo_id": ["P001", "P001"],
            "client_id": ["C0001", "C0002"],
            "control_group": [0, 0],
            "joined": [1, 0],
        }
    )
    frames = {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }

    leads = assign(frames)
    summary = build(leads, promo_leads)

    parent = tmp_path / "outputs"
    out_path = parent / "segment_summary.csv"
    # Precondition: outputs/ does not exist yet (Requirement 4.6).
    assert not parent.exists()

    write(summary, out_path)

    # The outputs/ directory was created and the file written.
    assert parent.is_dir()
    assert out_path.is_file()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    # A single header row, exactly the seven SUMMARY_COLUMNS in order.
    assert lines[0] == ",".join(SUMMARY_COLUMNS)
    assert SUMMARY_COLUMNS == [
        "promo_id",
        "segment",
        "n_clients",
        "mean_p_join",
        "expected_joiners",
        "actual_join_rate",
        "top_driver_1",
    ]
    # Header plus one data row per (promo, segment) cell (one promo x 4 segments).
    assert len(lines) == 1 + 4 * 1


def test_write_empty_actual_join_rate_serializes_as_empty_field(
    tmp_path: Path,
) -> None:
    """A cell with no treated leads writes an empty ``actual_join_rate`` field (4.4, 4.6).

    When a cell's ``actual_join_rate`` is NaN (zero treated leads), the written
    CSV must carry an empty field for that column -- not ``0`` and not ``nan``.
    Reading the file back with pandas yields a NaN for that cell.
    """
    scores = pd.DataFrame(
        {
            "promo_id": ["P001", "P001"],
            "client_id": ["C0001", "C0002"],
            "p_join": [0.75, 0.25],
            "top_driver_1": ["payroll", "bills"],
            "top_driver_2": ["bills", "payroll"],
            "top_driver_3": ["shopping", "shopping"],
        }
    )
    features = pd.DataFrame(
        {"client_id": ["C0001", "C0002"], "out_other_bank": [0.0, 0.0]}
    )
    adb = pd.DataFrame(
        {
            "client_id": ["C0001", "C0002"],
            "month": ["2026-08", "2026-08"],
            "adb_php": [10000.00, 500.00],
        }
    )
    promo_history = pd.DataFrame(
        {"promo_id": ["P001"], "threshold_php": [5000.00]}
    )
    # Only one treated lead; most cells have zero treated leads -> empty rate.
    promo_leads = pd.DataFrame(
        {
            "promo_id": ["P001"],
            "client_id": ["C0001"],
            "control_group": [0],
            "joined": [1],
        }
    )
    frames = {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }

    leads = assign(frames)
    summary = build(leads, promo_leads)

    out_path = tmp_path / "outputs" / "segment_summary.csv"
    write(summary, out_path)

    # At least one cell has an empty rate on disk; reading back yields NaN.
    read_back = pd.read_csv(out_path)
    assert read_back["actual_join_rate"].isna().any()

    # Confirm the empty rate is a truly empty field, not the literal "nan"/"0".
    data_lines = out_path.read_text(encoding="utf-8").splitlines()[1:]
    rate_index = SUMMARY_COLUMNS.index("actual_join_rate")
    empty_field_seen = False
    for line in data_lines:
        fields = line.split(",")
        if fields[rate_index] == "":
            empty_field_seen = True
    assert empty_field_seen, "expected at least one empty actual_join_rate field"
