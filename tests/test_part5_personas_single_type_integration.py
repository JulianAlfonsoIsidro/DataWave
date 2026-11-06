"""Integration tests for single-type persona runs on the real sample data (task 5.5).

A numeric-only and a categorical-only ``run_personas`` run (Requirement 2.13) over
``data/`` and ``outputs/`` (read-only inputs, no ``_answer_key`` input). Nothing is
written outside pytest ``tmp_path``. Fits are slow, so runs are module-scoped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from part5_personas.config import Config
from part5_personas.export import (
    CAMPAIGN_LEADS_EXPORT_COLUMNS,
    PART4_LEAD_COLUMNS,
    PERSONA_LABEL_COLUMN,
    build_persona_labeled_leads,
    campaign_leads_export,
    load_part4_leads_universe,
)
from part5_personas.naming import RuleBasedNamer
from webapp_core.personas import PersonaRunSpec, persona_mix_by_cell, run_personas

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = ROOT / "outputs"
K = 3

SELECTIONS = {
    "numeric": ["total_out", "inflow_share_payroll", "spend_share_grocery"],
    "categorical": ["age_band", "region", "sec_class"],
}


@pytest.fixture(scope="module")
def cfg() -> Config:
    cfg = Config(
        customer_dna_path=DATA_DIR / "customer_dna.csv",
        product_ownership_path=DATA_DIR / "product_ownership.csv",
        features_part2_path=OUTPUTS_DIR / "features_part2.csv",
        segments_path=OUTPUTS_DIR / "segments.csv",
        cards_path=OUTPUTS_DIR / "cards.json",
        leads_dir=OUTPUTS_DIR / "leads",
        promo_leads_path=DATA_DIR / "promo_leads.csv",
    )
    for name in (
        "customer_dna_path", "product_ownership_path", "features_part2_path",
        "segments_path", "cards_path", "leads_dir", "promo_leads_path",
    ):
        assert "_answer_key" not in str(getattr(cfg, name))
    return cfg


@pytest.fixture(scope="module")
def cards() -> list[dict]:
    return json.loads((OUTPUTS_DIR / "cards.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def universe(cfg) -> pd.DataFrame:
    return load_part4_leads_universe(cfg.leads_dir)


def _spec(kind: str) -> PersonaRunSpec:
    return PersonaRunSpec(level="all", clustering_attributes=SELECTIONS[kind], k=K)


@pytest.fixture(scope="module", params=sorted(SELECTIONS))
def kind(request) -> str:
    return request.param


@pytest.fixture(scope="module")
def run(kind, cfg):
    return run_personas(_spec(kind), RuleBasedNamer(), cfg)


def test_personas_built_and_every_lead_assigned(run):
    assert len(run.persona_sets) == 1
    ps = run.persona_sets[0]
    assert not ps.too_small
    assert len(ps.personas) == K
    assert sum(p.profile.size for p in ps.personas) == len(run.labels)
    labels = run.labels[PERSONA_LABEL_COLUMN]
    assert not (labels.isna() | (labels.astype(str) == "")).any()
    assert not run.labels["client_id"].duplicated().any()
    assert set(labels) == {p.name for p in ps.personas}


def test_names_unique_and_clean(run):
    names = [p.name for ps in run.persona_sets for p in ps.personas]
    assert len(names) == len(set(names))
    assert all("(cluster" not in n for n in names)


def test_elbow_costs_present(run):
    elbow = run.persona_sets[0].elbow_costs
    assert set(elbow) == {2, 3, 4, 5, 6}
    assert all(isinstance(v, float) for v in elbow.values())


def test_deterministic(run, kind, cfg):
    again = run_personas(_spec(kind), RuleBasedNamer(), cfg)
    pd.testing.assert_frame_equal(run.labels, again.labels)
    names = lambda r: [p.name for ps in r.persona_sets for p in ps.personas]  # noqa: E731
    assert names(run) == names(again)


def test_exports_one_row_per_part4_lead(run, universe):
    leads = universe[PART4_LEAD_COLUMNS].copy()
    full = build_persona_labeled_leads(leads, run.joined_attributes, run.labels)
    compact = campaign_leads_export(full)
    assert list(compact.columns) == CAMPAIGN_LEADS_EXPORT_COLUMNS
    assert len(CAMPAIGN_LEADS_EXPORT_COLUMNS) == 6
    for frame in (compact, full):
        assert len(frame) == len(universe)
        assert not frame["client_id"].duplicated().any()
        assert set(frame["client_id"]) == set(universe["client_id"])


def test_persona_mix_over_real_cards(run, cards):
    before = json.dumps(cards, sort_keys=True)
    mixes = persona_mix_by_cell(run.labels, cards)
    assert json.dumps(cards, sort_keys=True) == before
    assert any(m.available for m in mixes.values())
    for m in mixes.values():
        if m.available:
            assert sum(m.shares.values()) == pytest.approx(100.0, abs=1e-6)
        else:
            assert m.shares == {}
