"""Integration / smoke test for the full Part2_Network_Pipeline.

Runs :func:`part2_network.main.main` end-to-end against the *real* data files
(``data/transactions.csv`` and ``data/promo_leads.csv``), writing the features
output to a throwaway ``tmp_path`` location so the committed
``outputs/features_part2.csv`` is never touched.

This is a smoke-level check (Task 10.2): it asserts the pipeline exits cleanly,
produces a well-formed per-client Features_File, and prints a quartile report
plus an overall inner-join rate -- it does not re-derive every feature value
(that is covered by the unit and property tests).

Validates: Requirements 1.1, 8.1, 8.2, 9.3, 9.7, 9.8.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from part2_network.main import main

# Repo root is two levels up from this test file: tests/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSACTIONS = REPO_ROOT / "data" / "transactions.csv"
PROMO_LEADS = REPO_ROOT / "data" / "promo_leads.csv"

# If the real data is absent the smoke test cannot run; skip rather than fail.
pytestmark = pytest.mark.skipif(
    not (TRANSACTIONS.exists() and PROMO_LEADS.exists()),
    reason="real data files (data/transactions.csv, data/promo_leads.csv) not present",
)

# Matches a printed quartile line, e.g. "Q1: count=12 join_rate=0.2500".
_QUARTILE_RE = re.compile(
    r"^(Q[1-4]):\s*count=(\d+)\s+join_rate=([0-9.]+)\s*$"
)
# Matches the overall inner-join rate line.
_OVERALL_RE = re.compile(r"^Overall inner-join rate:\s*([0-9.]+)\s*$")


def _distinct_client_ids(path: Path) -> set[str]:
    """Return the set of distinct ``client_id`` values in a transactions CSV."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {row["client_id"] for row in reader}


def test_pipeline_end_to_end_against_real_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Full pipeline runs clean and writes a well-formed Features_File (1.1, 8.1, 8.2).

    Drives ``main`` with explicit real input paths (resolved from the repo root
    so the test is cwd-robust) and a tmp output path, then checks the exit code,
    the written CSV's shape, and the printed report.
    """
    out_path = tmp_path / "features.csv"

    exit_code = main(
        [
            "--transactions",
            str(TRANSACTIONS),
            "--promo-leads",
            str(PROMO_LEADS),
            "--out",
            str(out_path),
        ]
    )

    # 1.1 / 8.1: a successful run returns exit code 0.
    assert exit_code == 0

    # 8.1: the Features_File was written to the tmp path and is non-empty.
    assert out_path.exists()
    assert out_path.stat().st_size > 0

    # The committed real output must be untouched by this test.
    with out_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert len(rows) >= 2, "expected a header plus at least one data row"
    header = rows[0]
    data_rows = rows[1:]

    # 8.3-style smoke check: client_id is the first column.
    assert header[0] == "client_id"
    # Dynamic spend-share columns are present in the header.
    assert any(col.startswith("spend_share_") for col in header)

    # 8.2: exactly one row per distinct client in the real transactions.
    expected_clients = _distinct_client_ids(TRANSACTIONS)
    assert len(data_rows) == len(expected_clients)

    output_clients = [row[0] for row in data_rows]
    # client_id values are unique (one row per client).
    assert len(output_clients) == len(set(output_clients))
    # ...and match the distinct clients seen in the transactions input.
    assert set(output_clients) == expected_clients

    # 9.7 / 9.8: the report printed quartile lines and an overall join-rate line.
    printed = capsys.readouterr().out
    lines = [line for line in printed.splitlines() if line.strip()]

    quartile_matches = [
        m for m in (_QUARTILE_RE.match(line) for line in lines) if m
    ]
    overall_matches = [
        m for m in (_OVERALL_RE.match(line) for line in lines) if m
    ]

    # At least the four quartiles should print for the full real dataset (9.7).
    assert len(quartile_matches) == 4
    assert [m.group(1) for m in quartile_matches] == ["Q1", "Q2", "Q3", "Q4"]

    # Each per-quartile join rate parses as a float in [0, 1] (9.6/9.7).
    for match in quartile_matches:
        rate = float(match.group(3))
        assert 0.0 <= rate <= 1.0

    # 9.8: the overall inner-join rate line is present and in [0, 1].
    assert len(overall_matches) == 1
    overall_rate = float(overall_matches[0].group(1))
    assert 0.0 <= overall_rate <= 1.0


def test_pipeline_missing_transactions_fails_without_output(
    tmp_path: Path,
) -> None:
    """A missing Transactions_File exits non-zero and writes no output (1.x).

    The Transaction_Reader validates before anything is written, so pointing
    ``--transactions`` at a non-existent file must return 1 and leave the
    ``--out`` path uncreated.
    """
    out_path = tmp_path / "features.csv"
    missing = tmp_path / "missing.csv"

    exit_code = main(
        [
            "--transactions",
            str(missing),
            "--promo-leads",
            str(PROMO_LEADS),
            "--out",
            str(out_path),
        ]
    )

    assert exit_code == 1
    # No output file is produced when the reader rejects the input.
    assert not out_path.exists()
