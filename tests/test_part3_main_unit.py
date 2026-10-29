"""Example/edge unit tests for the Part3_Segments Reporter + error propagation.

Targeted (non-Hypothesis) tests for :mod:`part3_segments.main`, covering the
Reporter's printed summary and the loader-error halt-without-output guarantee:

- The Reporter prints exactly one line per (promo, segment) summary cell -- four
  segments times the number of distinct promos -- and each printed line carries
  the seven summary fields in order: ``promo_id``, ``segment``, ``n_clients``,
  ``mean_p_join``, ``expected_joiners``, ``actual_join_rate``, and
  ``top_driver_1`` (Requirement 5.2). A cell with no treated leads / no leads
  renders its ``actual_join_rate`` and ``top_driver_1`` as a blank field
  (Requirement 5.3). Both output files (``segments.csv`` and
  ``segment_summary.csv``) are written under ``tmp_path`` (Requirement 5.1).
- A loader error (``--scores`` pointed at a non-existent path, the other four
  inputs valid) propagates out of :func:`main` as ``FileNotFoundError`` before
  any output is produced: nothing is printed to stdout and neither output file
  is created (Requirement 5.4).

A small but complete set of the five inputs is built in ``tmp_path`` with two
distinct promos, so the summary is 4 x 2 = 8 cells and includes empty cells
exercising the blank-field rendering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from part3_segments.config import SEGMENTS
from part3_segments.main import main


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write ``lines`` (newline-joined) to ``tmp_path/name`` and return it."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_inputs(tmp_path: Path) -> dict[str, Path]:
    """Write a small valid set of the five inputs and return their paths.

    Two distinct promos (P001, P002) yield 4 x 2 = 8 summary cells. The treated
    (``control_group == 0``) promo-leads cover only some cells, so other cells
    have zero treated leads and therefore an empty ``actual_join_rate``, and
    unpopulated cells have a blank ``top_driver_1`` -- both exercise the
    blank-field rendering of Requirement 5.3.
    """
    scores = _write(
        tmp_path,
        "scores.csv",
        [
            "promo_id,client_id,p_join,top_driver_1,top_driver_2,top_driver_3",
            "P001,C0001,0.80,payroll,shopping,bills",
            "P001,C0002,0.20,bills,payroll,shopping",
            "P002,C0003,0.60,shopping,bills,payroll",
            "P002,C0004,0.40,payroll,bills,shopping",
        ],
    )
    features = _write(
        tmp_path,
        "features_part2.csv",
        [
            "client_id,out_other_bank",
            "C0001,1500.50",
            "C0002,0",
            "C0003,250.25",
            "C0004,100.00",
        ],
    )
    adb = _write(
        tmp_path,
        "adb_monthly.csv",
        [
            "client_id,month,adb_php",
            "C0001,2026-07,10000.00",
            "C0001,2026-08,12000.00",
            "C0002,2026-08,500.00",
            "C0003,2026-06,3000.00",
            "C0004,2026-08,1000.00",
        ],
    )
    promo_history = _write(
        tmp_path,
        "promo_history.csv",
        [
            "promo_id,threshold_php",
            "P001,8000.00",
            "P002,2000.00",
        ],
    )
    promo_leads = _write(
        tmp_path,
        "promo_leads.csv",
        [
            "promo_id,client_id,control_group,joined",
            # Treated leads (control_group == 0) attach to their cells.
            "P001,C0001,0,1",
            "P001,C0002,0,0",
            # A control-group row (control_group == 1) is never counted.
            "P002,C0003,1,0",
            # P002/C0004 has no treated promo-lead row, so its cell has an
            # empty actual_join_rate.
        ],
    )
    return {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }


def _argv(paths: dict[str, Path], tmp_path: Path) -> list[str]:
    """Build a main() argv pointing at ``paths`` with outputs under tmp_path."""
    return [
        "--scores", str(paths["scores"]),
        "--features", str(paths["features"]),
        "--adb-monthly", str(paths["adb"]),
        "--promo-history", str(paths["promo_history"]),
        "--promo-leads", str(paths["promo_leads"]),
        "--segments-out", str(tmp_path / "outputs" / "segments.csv"),
        "--summary-out", str(tmp_path / "outputs" / "segment_summary.csv"),
    ]


# --- Requirements 5.1, 5.2, 5.3: printed summary + outputs written -----------


def test_main_prints_one_line_per_cell_with_seven_fields(
    tmp_path: Path, capsys
) -> None:
    """main prints one 7-field line per summary cell and writes both outputs.

    With two distinct promos, the summary has 4 x 2 = 8 cells, so the Reporter
    prints exactly 8 lines (Requirement 5.2). Each line is tab-separated and
    carries the seven summary fields in order: ``promo_id``, ``segment``,
    ``n_clients``, ``mean_p_join``, ``expected_joiners``, ``actual_join_rate``,
    ``top_driver_1``. At least one cell has an empty ``actual_join_rate`` and an
    empty ``top_driver_1`` rendered as a blank field (Requirement 5.3). The run
    returns 0 and writes both output files under ``tmp_path`` (Requirement 5.1).

    _Requirements: 5.2, 5.3_
    """
    paths = _valid_inputs(tmp_path)
    segments_out = tmp_path / "outputs" / "segments.csv"
    summary_out = tmp_path / "outputs" / "segment_summary.csv"

    exit_code = main(_argv(paths, tmp_path))

    assert exit_code == 0

    # Both output files were written (Requirement 5.1).
    assert segments_out.exists()
    assert summary_out.exists()

    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line != ""]

    # One line per (promo, segment) cell = 4 segments x 2 distinct promos.
    distinct_promos = 2
    assert len(lines) == len(SEGMENTS) * distinct_promos

    # Every line has exactly the seven summary fields (tab-separated). A blank
    # trailing field (empty top_driver_1) still yields seven fields because the
    # separators are preserved.
    for line in lines:
        fields = line.split("\t")
        assert len(fields) == 7, f"expected 7 fields, got {len(fields)}: {line!r}"
        promo_id, segment = fields[0], fields[1]
        assert promo_id in {"P001", "P002"}
        assert segment in SEGMENTS

    # At least one cell renders an empty actual_join_rate AND an empty
    # top_driver_1 as blank fields (Requirement 5.3). An empty (unpopulated)
    # cell has n_clients == "0", a blank rate (index 5) and a blank driver
    # (index 6).
    blank_rate_and_driver = [
        line.split("\t")
        for line in lines
        if line.split("\t")[5] == "" and line.split("\t")[6] == ""
    ]
    assert blank_rate_and_driver, (
        "expected at least one cell with an empty actual_join_rate and "
        "top_driver_1 rendered as blank"
    )

    # Every printed field for every cell is a string (no NaN leaked into the
    # output); the empty rate/driver are "" rather than the literal "nan".
    for line in lines:
        for field in line.split("\t"):
            assert field != "nan"
            assert field.lower() != "nan"


# --- Requirement 5.4: loader error -> no output, no summary printed ----------


def test_main_loader_error_writes_nothing_and_prints_no_summary(
    tmp_path: Path, capsys
) -> None:
    """A loader error halts main before any output or print (Requirement 5.4).

    Pointing ``--scores`` at a non-existent file (the other four inputs valid)
    makes ``loader.load`` raise ``FileNotFoundError`` before the Segmenter runs.
    ``main`` does not catch it, so it propagates out; nothing is printed to
    stdout and neither ``segments.csv`` nor ``segment_summary.csv`` is created.

    _Requirements: 5.4_
    """
    paths = _valid_inputs(tmp_path)
    # Clobber scores with a path that does not exist so the loader halts first.
    missing_scores = tmp_path / "does_not_exist_scores.csv"
    paths["scores"].unlink()
    paths["scores"] = missing_scores
    assert not missing_scores.exists()

    segments_out = tmp_path / "outputs" / "segments.csv"
    summary_out = tmp_path / "outputs" / "segment_summary.csv"

    with pytest.raises(FileNotFoundError) as excinfo:
        main(_argv(paths, tmp_path))

    # The error names the missing scores path (loader halt-without-output).
    assert str(missing_scores) in str(excinfo.value)

    # Nothing printed to stdout: no summary (Requirement 5.4).
    captured = capsys.readouterr()
    assert captured.out == ""

    # Neither output file was created (Requirement 5.4).
    assert not segments_out.exists()
    assert not summary_out.exists()
