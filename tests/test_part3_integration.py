"""Integration / smoke test for the full Part3_Segments_Pipeline (task 7.3).

Runs :func:`part3_segments.main.main` end-to-end against the *real* five inputs
(``outputs/scores.csv``, ``outputs/features_part2.csv``, ``data/adb_monthly.csv``,
``data/promo_history.csv``, ``data/promo_leads.csv``), redirecting the two
*output* files to a throwaway ``tmp_path`` location via the ``--segments-out`` /
``--summary-out`` CLI overrides so the committed ``outputs/segments.csv`` and
``outputs/segment_summary.csv`` are never clobbered. The five real inputs are
read from their real repo paths.

This is a smoke-level check: it asserts the pipeline exits 0, writes a
per-lead ``segments.csv`` with exactly one row per scored lead, writes a
``segment_summary.csv`` with exactly four rows per distinct promo present in the
scores file, and prints the summary to stdout (one line per summary cell). It
does not re-derive every segment assignment -- the unit and property suites
cover that.

Validates: Requirement 5.1.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from part3_segments.config import SEGMENTS
from part3_segments.main import main

# Repo root is two levels up from this test file: tests/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"

# The five real inputs the pipeline reads end-to-end.
SCORES = OUTPUTS_DIR / "scores.csv"
FEATURES_PART2 = OUTPUTS_DIR / "features_part2.csv"
ADB_MONTHLY = DATA_DIR / "adb_monthly.csv"
PROMO_HISTORY = DATA_DIR / "promo_history.csv"
PROMO_LEADS = DATA_DIR / "promo_leads.csv"

_REQUIRED_INPUTS = [
    SCORES,
    FEATURES_PART2,
    ADB_MONTHLY,
    PROMO_HISTORY,
    PROMO_LEADS,
]

# If any real input is absent the smoke test cannot run; skip rather than fail
# so the suite stays green in environments without the real data.
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in _REQUIRED_INPUTS),
    reason=(
        "real data files (outputs/scores.csv, outputs/features_part2.csv, "
        "data/adb_monthly.csv, data/promo_history.csv, data/promo_leads.csv) "
        "not present"
    ),
)


def test_pipeline_end_to_end_against_real_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Full pipeline runs clean and writes well-formed outputs (5.1).

    Drives ``main`` with the two output paths redirected into ``tmp_path`` while
    the five inputs are read from their real repo paths (the pipeline's canonical
    defaults, passed explicitly so the test is cwd-robust). Asserts exit code 0,
    one segments row per scored lead, four summary rows per distinct promo, and a
    printed summary with one line per summary cell.
    """
    segments_out = tmp_path / "segments.csv"
    summary_out = tmp_path / "segment_summary.csv"

    exit_code = main(
        [
            "--scores", str(SCORES),
            "--features", str(FEATURES_PART2),
            "--adb-monthly", str(ADB_MONTHLY),
            "--promo-history", str(PROMO_HISTORY),
            "--promo-leads", str(PROMO_LEADS),
            "--segments-out", str(segments_out),
            "--summary-out", str(summary_out),
        ]
    )

    # 5.1: a fully successful run returns exit code 0.
    assert exit_code == 0, "pipeline did not exit cleanly against the real data"

    # Both outputs were written to the tmp paths (not the committed outputs/).
    assert segments_out.exists(), "segments output was not written"
    assert summary_out.exists(), "summary output was not written"
    assert segments_out.parent == tmp_path
    assert summary_out.parent == tmp_path

    # Independent reference: the real scored leads.
    scores = pd.read_csv(SCORES, dtype=str, keep_default_na=False)
    n_leads = len(scores)
    distinct_promos = scores["promo_id"].nunique()
    assert n_leads > 0, "expected the real scores file to contain leads"
    assert distinct_promos > 0, "expected at least one distinct promo"

    # segments.csv has exactly one row per scored lead (Requirement 3.2 / 5.1).
    segments = pd.read_csv(segments_out, dtype=str, keep_default_na=False)
    assert len(segments) == n_leads, (
        f"segments rows ({len(segments)}) != scored leads ({n_leads})"
    )

    # segment_summary.csv has exactly four rows per distinct promo: the promo x
    # four-segment cross product (Requirements 4.1 / 5.1).
    summary = pd.read_csv(summary_out, dtype=str, keep_default_na=False)
    assert len(summary) == 4 * distinct_promos, (
        f"summary rows ({len(summary)}) != 4 x distinct promos "
        f"({4 * distinct_promos})"
    )
    # Every cell is one of the four known segment labels and each promo carries
    # all four segments exactly once.
    assert set(summary["segment"]) <= set(SEGMENTS)
    per_promo_segments = summary.groupby("promo_id")["segment"].apply(
        lambda s: sorted(s)
    )
    for promo_id, seg_list in per_promo_segments.items():
        assert seg_list == sorted(SEGMENTS), (
            f"promo {promo_id} is missing one or more of the four segments: "
            f"{seg_list}"
        )

    # The summary is printed to stdout: one non-empty line per summary cell
    # (Requirements 5.1, 5.2).
    printed = capsys.readouterr().out
    lines = [line for line in printed.splitlines() if line.strip()]
    assert lines, "expected the pipeline to print a non-empty summary"
    assert len(lines) == len(summary), (
        f"printed summary lines ({len(lines)}) != summary cells ({len(summary)})"
    )
