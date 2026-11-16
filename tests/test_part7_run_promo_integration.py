"""Integration tests for ``run_promo`` threshold handling (Part 7).

Covers Requirements 5.5, 5.9, and 10.3:

- Balance Increase segments match an independently recomputed per-client
  capacity check (Requirements 5.5, 10.3),
- old ``PromoSpec`` calls without ``threshold_type`` / ``threshold_pct`` still
  work (Requirement 5.9), and
- Part 3 source files are untouched by the run (Requirement 5.9).

Concrete integration tests only (no Hypothesis). They use the real fitted
model from ``outputs/`` and a tiny slice of the real ``data/`` frames.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from part1_optin.config import Config as Part1Config
from webapp_core.model_io import load_model
from webapp_core.run_promo import PromoSpec, run_promo
from webapp_core.threshold import ThresholdType

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"
PART3_DIR = ROOT / "src" / "part3_segments"

PCT = 50.0


def _spec(**overrides) -> PromoSpec:
    defaults = dict(
        promo_id="NEW-001",
        product_type="Savings",
        mechanic="TOP_UP",
        threshold_php=100_000.0,
        reward="Bonus interest",
        eligible_segments=["Affluent-Gold"],
        min_adb=0.0,
        channels=["In-app", "Email", "SMS"],
    )
    defaults.update(overrides)
    return PromoSpec(**defaults)


@pytest.fixture(scope="module")
def tiny_data() -> dict[str, pd.DataFrame]:
    dna = pd.read_csv(DATA_DIR / "customer_dna.csv")
    adb = pd.read_csv(DATA_DIR / "adb_monthly.csv")
    features = pd.read_csv(OUTPUTS_DIR / "features_part2.csv")
    ids = dna.loc[dna["segment"] == "Affluent-Gold", "client_id"].head(40).tolist()
    assert ids, "expected Affluent-Gold clients in the fixture data"
    return {
        "customer_dna": dna[dna["client_id"].isin(ids)],
        "adb_monthly": adb[adb["client_id"].isin(ids)],
        "features": features[features["client_id"].isin(ids)],
    }


@pytest.fixture(scope="module")
def model_and_config():
    return load_model(OUTPUTS_DIR), Part1Config()


def _part3_hashes() -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(PART3_DIR.glob("*.py"))
    }


def test_balance_increase_segments_match_recomputed_capacity(
    tiny_data, model_and_config
):
    model, config = model_and_config
    spec = _spec(
        threshold_type=ThresholdType.BALANCE_INCREASE, threshold_pct=PCT
    )

    result = run_promo(spec, model=model, config=config, data=tiny_data)
    seg = result.segments_df
    assert not seg.empty

    # Independent recomputation of per-client capacity_high.
    adb = tiny_data["adb_monthly"]
    latest = adb.loc[adb.groupby("client_id")["month"].idxmax()].set_index(
        "client_id"
    )["adb_php"]
    amounts = (PCT / 100.0) * seg["client_id"].map(latest).astype(float)
    capacity_high = (seg["capacity_php"].astype(float) >= amounts) & amounts.notna()
    score_high = seg["p_join"] >= seg["p_join"].median()

    expected = np.select(
        [
            score_high & capacity_high,
            score_high & ~capacity_high,
            ~score_high & capacity_high,
            ~score_high & ~capacity_high,
        ],
        ["Ready Toppers", "Willing but Stretched", "Untapped Wealth", "Not Now"],
        default="",
    )
    assert seg["segment"].tolist() == expected.tolist()
    # Cards are built from the re-derived segments: one per populated cell.
    assert len(result.cards) == seg["segment"].nunique()


def test_old_promo_spec_without_threshold_fields_still_works(
    tiny_data, model_and_config
):
    model, config = model_and_config
    spec = _spec()  # no threshold_type / threshold_pct

    assert spec.threshold_type is None
    assert spec.threshold_pct is None

    result = run_promo(spec, model=model, config=config, data=tiny_data)
    seg = result.segments_df

    assert not seg.empty
    assert result.cards
    assert result.non_excluded is not None

    # Fixed-threshold behavior: capacity_php vs threshold_php (Part 3 rule).
    capacity_high = seg["capacity_php"] >= spec.threshold_php
    score_high = seg["p_join"] >= seg["p_join"].median()
    ready = score_high & capacity_high
    assert set(seg.loc[ready, "segment"]) <= {"Ready Toppers"}
    assert (seg.loc[ready, "segment"] == "Ready Toppers").all()


def test_part3_files_untouched_by_run(tiny_data, model_and_config):
    model, config = model_and_config
    before = _part3_hashes()
    assert before, "expected Part 3 source files"

    run_promo(
        _spec(threshold_type=ThresholdType.BALANCE_INCREASE, threshold_pct=PCT),
        model=model,
        config=config,
        data=tiny_data,
    )
    assert _part3_hashes() == before

    # Also confirm git sees no change to Part 3 sources (skip without git).
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", "src/part3_segments"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git unavailable")
    if proc.returncode != 0:
        pytest.skip("not a git work tree")
    tracked_changes = [
        line
        for line in proc.stdout.splitlines()
        if not line.startswith("??") and "__pycache__" not in line
    ]
    assert tracked_changes == []
