"""Example/smoke unit tests for :func:`webapp_core.run_promo.run_promo`.

These cover the two behaviors of the promo-run orchestrator the design calls
out as example/edge tests rather than Hypothesis properties (Requirements 3.4,
3.5):

- the **empty-audience contract** (Requirement 3.4): when the eligibility
  filter keeps no client, ``run_promo`` returns a :class:`RunResult` with empty
  ``scored`` / ``segments_df`` frames, ``cards == []`` and an empty
  ``sendable_by_segment`` instead of raising -- exercised without a real model
  by picking ``eligible_segments`` that match no Customer_DNA segment, so the
  empty branch triggers *before* any scoring, and
- a **tiny-audience smoke test** (Requirement 3.5): a handful of genuinely
  eligible clients scored with the real reloaded Part 1 model yields a non-empty
  ``cards`` list with exactly one card per populated ``(promo_id, segment)``
  cell -- i.e. one card per distinct Segment_Label that actually received at
  least one client.

These are concrete example/smoke tests, not property tests. The smoke test
loads the real trained model from ``outputs/`` and the real ``data/`` frames,
restricting the audience to <=20 clients so scoring (and its SHAP drivers) stays
fast and hermetic.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from part1_optin.config import Config as Part1Config
from webapp_core.model_io import load_model
from webapp_core.run_promo import PromoSpec, RunResult, run_promo

# Project paths: the real trained artifacts and the real data/ frames are the
# simplest reliable source for the smoke test's model and audience.
ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"


def _promo_spec(**overrides) -> PromoSpec:
    """A PromoSpec with sensible defaults, overridable per test."""
    defaults = dict(
        promo_id="NEW-001",
        product_type="Savings",
        mechanic="TOP_UP",
        threshold_php=100_000.0,
        reward="Bonus interest",
        eligible_segments=["Affluent-Gold"],
        min_adb=0.0,
        channels=["email", "sms"],
    )
    defaults.update(overrides)
    return PromoSpec(**defaults)


def test_run_promo_empty_audience_returns_empty_result():
    """No eligible client -> empty RunResult, no cards (Requirement 3.4).

    ``eligible_segments`` is a segment that matches no Customer_DNA row, so
    :func:`~webapp_core.audience.select_eligible_clients` returns empty and
    ``run_promo`` takes its empty branch *before* scoring. The model and config
    are therefore never exercised, so passing ``None`` for both is safe and
    keeps the test fast and hermetic.
    """
    customer_dna = pd.read_csv(DATA_DIR / "customer_dna.csv")
    adb_monthly = pd.read_csv(DATA_DIR / "adb_monthly.csv")
    features = pd.read_csv(OUTPUTS_DIR / "features_part2.csv")

    data = {
        "customer_dna": customer_dna,
        "adb_monthly": adb_monthly,
        "features": features,
    }

    # A DNA segment no client has -> the eligible audience is empty.
    spec = _promo_spec(eligible_segments=["__no_such_segment__"])

    result = run_promo(spec, model=None, config=None, data=data)

    assert isinstance(result, RunResult)
    assert result.promo_spec is spec
    assert result.cards == []
    assert result.sendable_by_segment == {}
    assert result.scored.empty
    assert result.segments_df.empty


def test_run_promo_empty_audience_when_min_adb_excludes_everyone():
    """A min_adb no client can meet also yields the empty result (Req 3.4).

    A real DNA segment is kept, but the ADB floor is set absurdly high so every
    client in that segment is filtered out on the ADB predicate -- the empty
    branch still triggers before scoring, so ``model``/``config`` stay unused.
    """
    customer_dna = pd.read_csv(DATA_DIR / "customer_dna.csv")
    adb_monthly = pd.read_csv(DATA_DIR / "adb_monthly.csv")
    features = pd.read_csv(OUTPUTS_DIR / "features_part2.csv")

    data = {
        "customer_dna": customer_dna,
        "adb_monthly": adb_monthly,
        "features": features,
    }

    spec = _promo_spec(
        eligible_segments=["Affluent-Gold"], min_adb=1e18
    )

    result = run_promo(spec, model=None, config=None, data=data)

    assert result.cards == []
    assert result.sendable_by_segment == {}
    assert result.scored.empty
    assert result.segments_df.empty


def test_run_promo_tiny_audience_one_card_per_populated_cell():
    """A tiny eligible audience yields one card per populated cell (Req 3.5).

    Loads the real Part 1 model and config and a tiny slice of the real
    ``data/`` frames (<=20 clients), runs the full pipeline, and asserts:

    - ``cards`` is non-empty, and
    - there is exactly one card per populated ``(promo_id, segment)`` cell --
      i.e. ``len(cards)`` equals the number of distinct Segment_Labels that
      actually received at least one client in ``segments_df``.
    """
    model = load_model(OUTPUTS_DIR)
    config = Part1Config()

    customer_dna = pd.read_csv(DATA_DIR / "customer_dna.csv")
    adb_monthly = pd.read_csv(DATA_DIR / "adb_monthly.csv")
    features = pd.read_csv(OUTPUTS_DIR / "features_part2.csv")

    # Restrict to a tiny eligible audience: the first <=15 Affluent-Gold
    # clients. Keeping the full adb/features frames is fine -- only these
    # clients are selected and scored -- but subsetting them too keeps the join
    # cheap and the run fast.
    tiny_ids = (
        customer_dna.loc[
            customer_dna["segment"] == "Affluent-Gold", "client_id"
        ]
        .head(15)
        .tolist()
    )
    assert tiny_ids, "expected some Affluent-Gold clients in the fixture data"

    data = {
        "customer_dna": customer_dna[customer_dna["client_id"].isin(tiny_ids)],
        "adb_monthly": adb_monthly[adb_monthly["client_id"].isin(tiny_ids)],
        "features": features[features["client_id"].isin(tiny_ids)],
    }

    spec = _promo_spec(eligible_segments=["Affluent-Gold"], min_adb=0.0)

    result = run_promo(spec, model=model, config=config, data=data)

    # The audience was non-empty, so the run produced scored rows and cards.
    assert not result.segments_df.empty
    assert len(result.scored) == len(tiny_ids)
    assert result.cards, "a non-empty eligible audience must yield cards"

    # One card per populated (promo_id, segment) cell. Every row of
    # segments_df carries this promo's id, so the distinct populated cells are
    # exactly the distinct Segment_Labels that received at least one client.
    populated_cells = result.segments_df[["promo_id", "segment"]].drop_duplicates()
    assert len(result.cards) == len(populated_cells)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
