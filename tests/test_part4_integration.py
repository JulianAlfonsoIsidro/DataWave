"""Integration / smoke test for the full Part4_Cards_Pipeline (task 6.3).

Runs :func:`part4_cards.main.main` end-to-end against the *real* seven inputs
(``outputs/segments.csv``, ``outputs/segment_summary.csv``, ``data/ndb.csv``,
``data/contact_history.csv``, ``data/channel_costs.csv``, ``data/customer_dna.csv``,
``data/promo_history.csv``), redirecting the two *output* locations -- the cards
JSON and the per-Cell leads directory -- into a throwaway ``tmp_path`` via the
``--cards-out`` / ``--leads-out-dir`` CLI overrides so the committed
``outputs/cards.json`` and ``outputs/leads/`` are never clobbered. The seven real
inputs are read from their real repo paths (passed explicitly so the test is
cwd-robust).

This is a smoke-level check: it asserts the pipeline exits 0, writes a
``cards.json`` that is a JSON list with exactly one Card per (promo, segment)
Cell, writes exactly one per-Cell lead file under the leads directory per Cell,
and prints the summary to stdout (one line per Card). It does not re-derive every
Card field -- the unit and property suites cover that.

Validates: Requirement 6.1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from part4_cards.main import main

# Repo root is two levels up from this test file: tests/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"

# The seven real inputs the pipeline reads end-to-end.
SEGMENTS = OUTPUTS_DIR / "segments.csv"
SEGMENT_SUMMARY = OUTPUTS_DIR / "segment_summary.csv"
NDB = DATA_DIR / "ndb.csv"
CONTACT_HISTORY = DATA_DIR / "contact_history.csv"
CHANNEL_COSTS = DATA_DIR / "channel_costs.csv"
CUSTOMER_DNA = DATA_DIR / "customer_dna.csv"
PROMO_HISTORY = DATA_DIR / "promo_history.csv"

_REQUIRED_INPUTS = [
    SEGMENTS,
    SEGMENT_SUMMARY,
    NDB,
    CONTACT_HISTORY,
    CHANNEL_COSTS,
    CUSTOMER_DNA,
    PROMO_HISTORY,
]

# If any real input is absent the smoke test cannot run; skip rather than fail
# so the suite stays green in environments without the real data.
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in _REQUIRED_INPUTS),
    reason=(
        "real data files (outputs/segments.csv, outputs/segment_summary.csv, "
        "data/ndb.csv, data/contact_history.csv, data/channel_costs.csv, "
        "data/customer_dna.csv, data/promo_history.csv) not present"
    ),
)


def test_pipeline_end_to_end_against_real_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Full pipeline runs clean and writes well-formed outputs (6.1).

    Drives ``main`` with the cards JSON and the leads directory redirected into
    ``tmp_path`` while the seven inputs are read from their real repo paths (the
    pipeline's canonical defaults, passed explicitly so the test is cwd-robust).
    Asserts exit code 0, a ``cards.json`` list with exactly one Card per
    (promo, segment) Cell, exactly one per-Cell lead file per Cell under the
    leads directory, and a printed summary with one line per Card.
    """
    cards_out = tmp_path / "cards.json"
    leads_out_dir = tmp_path / "leads"

    exit_code = main(
        [
            "--segments", str(SEGMENTS),
            "--segment-summary", str(SEGMENT_SUMMARY),
            "--ndb", str(NDB),
            "--contact-history", str(CONTACT_HISTORY),
            "--channel-costs", str(CHANNEL_COSTS),
            "--customer-dna", str(CUSTOMER_DNA),
            "--promo-history", str(PROMO_HISTORY),
            "--cards-out", str(cards_out),
            "--leads-out-dir", str(leads_out_dir),
        ]
    )

    # 6.1: a fully successful run returns exit code 0.
    assert exit_code == 0, "pipeline did not exit cleanly against the real data"

    # Outputs were written to the tmp paths (not the committed outputs/).
    assert cards_out.exists(), "cards.json output was not written"
    assert leads_out_dir.exists(), "leads directory was not created"
    assert cards_out.parent == tmp_path
    assert leads_out_dir.parent == tmp_path

    # Independent reference: the real leads and their distinct (promo, segment)
    # Cells.
    segments = pd.read_csv(SEGMENTS, dtype=str, keep_default_na=False)
    assert len(segments) > 0, "expected the real segments file to contain leads"
    n_cells = segments.groupby(["promo_id", "segment"]).ngroups
    assert n_cells > 0, "expected at least one (promo, segment) Cell"

    # cards.json is a JSON list with exactly one Card per (promo, segment) Cell.
    cards = json.loads(cards_out.read_text(encoding="utf-8"))
    assert isinstance(cards, list), "cards.json must be a JSON list"
    assert len(cards) == n_cells, (
        f"card count ({len(cards)}) != distinct (promo, segment) Cells "
        f"({n_cells})"
    )
    # Every Card carries a unique (promo_id, segment) Cell key matching the data.
    card_cells = {(c["promo_id"], c["segment"]) for c in cards}
    assert len(card_cells) == len(cards), "cards.json has a duplicate Cell"
    reference_cells = set(
        map(tuple, segments[["promo_id", "segment"]].drop_duplicates().to_numpy())
    )
    assert card_cells == reference_cells, (
        "cards.json Cells do not match the distinct (promo, segment) Cells in "
        "the real data"
    )

    # Exactly one per-Cell lead file exists under the leads directory per Cell
    # (one file per Card).
    lead_files = sorted(leads_out_dir.glob("*.csv"))
    assert len(lead_files) == len(cards), (
        f"per-Cell lead files ({len(lead_files)}) != cards ({len(cards)})"
    )

    # The summary is printed to stdout: one non-empty line per Card
    # (Requirement 6.5, exercised by the 6.1 run).
    printed = capsys.readouterr().out
    lines = [line for line in printed.splitlines() if line.strip()]
    assert lines, "expected the pipeline to print a non-empty summary"
    assert len(lines) == len(cards), (
        f"printed summary lines ({len(lines)}) != cards ({len(cards)})"
    )
