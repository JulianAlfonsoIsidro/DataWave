"""End-to-end integration test for the persona-segmentation feature (task 15.2).

Runs the real Persona_Pipeline / Persona_Core over the sample ``data/`` and
``outputs/`` (read-only inputs) and checks, in one place:

- Requirements 7.x -- the Persona_Mix over the real Part 4 cards sums to 100 per
  available cell, unavailable cells are empty, and no card field is changed
  (7.1, 7.3, 7.4, 7.5); persona scoping never alters assignments.
- Requirements 8.x -- the Campaign_Leads_Export (6 columns) and the full
  Persona_Labeled_Leads both carry one row per Part 4 lead and agree row-for-row
  (8.1, 8.3, 8.6, 8.7, 8.8, 8.9); the CLI writes the labeled leads CSV.
- Requirements 9.2-9.4 -- persona generation is a separate optional step:
  ``run_pipeline.py`` does not reference it, importing ``part5_personas`` leaves
  Part 1-4 untouched, and ``outputs/`` / ``data/`` stay byte-identical.

Covered runs: level ``all``, ``business-segment`` (field ``segment``),
``campaign`` (past promo ``P001``), plus a two-step ``all`` run grouped by
``age_band`` used to exercise the group-scoping helpers.

Clustering attributes always include a categorical column (an all-numeric
selection is a known unrelated issue and is deliberately not exercised).
Every produced file is written under pytest ``tmp_path`` only. Fits are done once
in module-scoped fixtures (k-prototypes is slow). ``tests/conftest.py`` supplies
``src`` on ``sys.path``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from app.persona_page import (
    ALL_GROUPS_LABEL,
    default_group,
    group_download_filename,
    group_options,
    scope_export_frame,
    scope_result_to_group,
)
from part5_personas.config import Config
from part5_personas.export import (
    CAMPAIGN_LEADS_EXPORT_COLUMNS,
    GROUP_COLUMN,
    PART4_LEAD_COLUMNS,
    PERSONA_LABEL_COLUMN,
    build_persona_labeled_leads,
    campaign_leads_export,
    load_part4_leads_universe,
)
from part5_personas.main import main as persona_main
from part5_personas.naming import RuleBasedNamer
from webapp_core.personas import PersonaRunSpec, persona_mix_by_cell, run_personas

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = ROOT / "outputs"

# At least one categorical column (age_band) -- an all-numeric selection is a known
# unrelated cluster.py issue and is not exercised here.
ATTRS = ["age_band", "digital_app_user", "total_out", "inflow_share_payroll"]
# Two-step run: group by age_band, cluster on a set that still has a categorical.
TWO_STEP_ATTRS = ["region", "digital_app_user", "total_out", "inflow_share_payroll"]
K = 3


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _hash_tree(root: Path) -> dict[str, str]:
    """SHA-256 of every file under ``root`` keyed by its relative posix path."""
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return out


def _cfg() -> Config:
    """Real sample inputs as absolute paths; assert no answer-key path is used."""
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
        "customer_dna_path",
        "product_ownership_path",
        "features_part2_path",
        "segments_path",
        "cards_path",
        "leads_dir",
        "promo_leads_path",
        "labeled_leads_out_path",
    ):
        assert "_answer_key" not in str(getattr(cfg, name))
    return cfg


def _exports(result, universe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assemble (campaign, full) exports the same way ``_build_exports`` does."""
    leads = universe[PART4_LEAD_COLUMNS].copy()
    full = build_persona_labeled_leads(leads, result.joined_attributes, result.labels)
    return campaign_leads_export(full), full


def _blank(series: pd.Series) -> pd.Series:
    """True where a label/group cell is empty (NaN or empty string)."""
    return series.isna() | (series.astype(str) == "")


def _cards_json(cards) -> str:
    return json.dumps(cards, sort_keys=True)


# --------------------------------------------------------------------------- #
# Module-scoped fixtures (each expensive run computed once)                    #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def cfg() -> Config:
    return _cfg()


@pytest.fixture(scope="module")
def hashes_before(cfg) -> dict[str, dict[str, str]]:
    """Hash outputs/ and data/ BEFORE any persona run (fixtures depend on this)."""
    return {"outputs": _hash_tree(OUTPUTS_DIR), "data": _hash_tree(DATA_DIR)}


@pytest.fixture(scope="module")
def cards() -> list[dict]:
    return json.loads((OUTPUTS_DIR / "cards.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def universe(cfg, hashes_before) -> pd.DataFrame:
    return load_part4_leads_universe(cfg.leads_dir)


@pytest.fixture(scope="module")
def all_spec() -> PersonaRunSpec:
    return PersonaRunSpec(level="all", clustering_attributes=ATTRS, k=K)


@pytest.fixture(scope="module")
def all_run(cfg, all_spec, hashes_before):
    return run_personas(all_spec, RuleBasedNamer(), cfg)


@pytest.fixture(scope="module")
def segment_run(cfg, hashes_before):
    spec = PersonaRunSpec(
        level="business-segment",
        clustering_attributes=ATTRS,
        k=K,
        business_segment_field="segment",
    )
    return run_personas(spec, RuleBasedNamer(), cfg)


@pytest.fixture(scope="module")
def campaign_run(cfg, hashes_before):
    spec = PersonaRunSpec(
        level="campaign", clustering_attributes=ATTRS, k=K, campaign_pool="P001"
    )
    return run_personas(spec, RuleBasedNamer(), cfg)


@pytest.fixture(scope="module")
def two_step_run(cfg, hashes_before):
    spec = PersonaRunSpec(
        level="all",
        clustering_attributes=TWO_STEP_ATTRS,
        grouping_attributes=["age_band"],
        k=K,
    )
    return run_personas(spec, RuleBasedNamer(), cfg)


@pytest.fixture(scope="module")
def cli_output(tmp_path_factory, cfg, hashes_before) -> tuple[int, Path]:
    """Run the persona CLI once, every override flag pointing at real inputs and
    the output at a pytest tmp dir."""
    out = tmp_path_factory.mktemp("persona_cli") / "persona_labeled_leads.csv"
    argv = [
        "--customer-dna", str(cfg.customer_dna_path),
        "--product-ownership", str(cfg.product_ownership_path),
        "--features-part2", str(cfg.features_part2_path),
        "--segments", str(cfg.segments_path),
        "--cards", str(cfg.cards_path),
        "--leads-dir", str(cfg.leads_dir),
        "--promo-leads", str(cfg.promo_leads_path),
        "--labeled-leads-out", str(out),
    ]
    return persona_main(argv), out


# --------------------------------------------------------------------------- #
# 1-2. Runs and exports                                                        #
# --------------------------------------------------------------------------- #
def _check_exports(result, universe, tmp_path, tag) -> tuple[pd.DataFrame, pd.DataFrame]:
    campaign, full = _exports(result, universe)

    # Exact columns / superset.
    assert list(campaign.columns) == CAMPAIGN_LEADS_EXPORT_COLUMNS
    assert len(CAMPAIGN_LEADS_EXPORT_COLUMNS) == 6
    assert set(CAMPAIGN_LEADS_EXPORT_COLUMNS) < set(full.columns)
    assert len(full.columns) > 6

    # One row per Part 4 lead, no duplicates.
    for frame in (campaign, full):
        assert len(frame) == len(universe)
        assert not frame["client_id"].duplicated().any()
        assert set(frame["client_id"]) == set(universe["client_id"])

    # Row-for-row agreement.
    pd.testing.assert_frame_equal(
        campaign[["client_id", PERSONA_LABEL_COLUMN, GROUP_COLUMN]],
        full[["client_id", PERSONA_LABEL_COLUMN, GROUP_COLUMN]],
    )

    # CSV round-trip (files only under tmp_path).
    c_path = tmp_path / f"{tag}_campaign.csv"
    f_path = tmp_path / f"{tag}_full.csv"
    campaign.to_csv(c_path, index=False)
    full.to_csv(f_path, index=False)
    c_back = pd.read_csv(c_path)
    f_back = pd.read_csv(f_path)
    assert list(c_back.columns) == CAMPAIGN_LEADS_EXPORT_COLUMNS
    assert list(f_back.columns) == list(full.columns)
    assert len(c_back) == len(f_back) == len(universe)
    assert c_back["client_id"].tolist() == campaign["client_id"].tolist()
    assert f_back["client_id"].tolist() == full["client_id"].tolist()
    return campaign, full


def _too_small_groups(result) -> set[str]:
    return {ps.group_key for ps in result.persona_sets if ps.too_small}


def test_all_run_exports(all_run, universe, tmp_path):
    """Level ``all``: every lead labeled; group is the empty key ``""``."""
    assert [ps.group_key for ps in all_run.persona_sets] == [""]
    campaign, full = _check_exports(all_run, universe, tmp_path, "all")
    assert not _blank(full[PERSONA_LABEL_COLUMN]).any()
    # Level all has a single group keyed "" (no grouping): stored as empty string.
    assert full[GROUP_COLUMN].notna().all()
    assert (full[GROUP_COLUMN].astype(str) == "").all()


def test_segment_run_exports(segment_run, universe, tmp_path):
    """Level ``business-segment``: every in-pool lead has a label and group."""
    campaign, full = _check_exports(segment_run, universe, tmp_path, "segment")
    small = _too_small_groups(segment_run)
    assert not small, f"unexpected too-small segments in sample data: {small}"
    assert not _blank(full[PERSONA_LABEL_COLUMN]).any()
    assert not _blank(full[GROUP_COLUMN]).any()
    # Group values are the customer_dna segment values clustered.
    assert set(full[GROUP_COLUMN]) <= {ps.group_key for ps in segment_run.persona_sets}


def test_campaign_run_exports(campaign_run, universe, cfg, tmp_path):
    """Level ``campaign`` (P001): in-pool labeled; out-of-pool empty label/group."""
    campaign, full = _check_exports(campaign_run, universe, tmp_path, "campaign")
    pool = set(load_part4_leads_universe(cfg.leads_dir, promo_id="P001")["client_id"])
    assert 0 < len(pool) < len(universe), "need both in-pool and out-of-pool leads"

    in_pool = full["client_id"].isin(pool)
    assert not _blank(full.loc[in_pool, PERSONA_LABEL_COLUMN]).any()
    # Campaign level with no grouping uses group "" (present, not missing) in-pool.
    assert full.loc[in_pool, GROUP_COLUMN].notna().all()
    assert (full.loc[in_pool, GROUP_COLUMN].astype(str) == "").all()
    # Out-of-pool: empty label and group.
    assert _blank(full.loc[~in_pool, PERSONA_LABEL_COLUMN]).all()
    assert full.loc[~in_pool, GROUP_COLUMN].isna().all()
    assert set(campaign_run.labels["client_id"]) == pool


# --------------------------------------------------------------------------- #
# 3. Mix                                                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("run_fixture", ["all_run", "segment_run", "campaign_run"])
def test_persona_mix_over_real_cards(request, run_fixture, cards):
    run = request.getfixturevalue(run_fixture)
    before = copy.deepcopy(cards)
    before_json = _cards_json(cards)

    mixes = persona_mix_by_cell(run.labels, cards)

    # Cards untouched, byte-for-byte.
    assert cards == before
    assert _cards_json(cards) == before_json

    assert len(mixes) == len(cards)
    assert any(m.available for m in mixes.values())
    for card in cards:
        mix = mixes[(card["promo_id"], card["segment"])]
        if mix.available:
            assert mix.shares
            assert sum(mix.shares.values()) == pytest.approx(100.0, abs=1e-6)
        else:
            assert mix.shares == {}


def test_campaign_mix_only_has_pool_cells(campaign_run, cards):
    """Only P001 cells can carry shares for the P001 campaign run."""
    mixes = persona_mix_by_cell(campaign_run.labels, cards)
    for (promo_id, _segment), mix in mixes.items():
        if promo_id != "P001":
            assert not mix.available and mix.shares == {}


# --------------------------------------------------------------------------- #
# 4. Two-step flow with group scoping                                          #
# --------------------------------------------------------------------------- #
def test_two_step_group_scoping(two_step_run, universe, cards):
    result = two_step_run
    options = group_options(result)
    assert options and options[-1] == ALL_GROUPS_LABEL
    group_keys = options[:-1]
    assert len(group_keys) > 1

    # Snapshots of the unscoped result and cards.
    labels_before = result.labels.copy(deep=True)
    sets_before = [(ps.group_key, [p.name for p in ps.personas]) for ps in result.persona_sets]
    cards_before = _cards_json(cards)
    campaign, full = _exports(result, universe)
    full_before = full.copy(deep=True)

    full_label = dict(zip(result.labels["client_id"], result.labels[PERSONA_LABEL_COLUMN]))

    clusterable = [ps.group_key for ps in result.persona_sets if not ps.too_small]
    assert clusterable
    assert default_group(options) == options[0]

    for chosen in clusterable[:3]:
        scoped = scope_result_to_group(result, chosen)

        # Persona sets only for the chosen group.
        assert [ps.group_key for ps in scoped.persona_sets] == [chosen]
        scoped_names = {p.name for ps in scoped.persona_sets for p in ps.personas}

        # Scoped labels only that group's leads, assignments unchanged.
        assert len(scoped.labels) > 0
        assert (scoped.labels[GROUP_COLUMN] == chosen).all()
        assert set(scoped.labels[PERSONA_LABEL_COLUMN]) <= scoped_names
        for cid, label in zip(scoped.labels["client_id"], scoped.labels[PERSONA_LABEL_COLUMN]):
            assert full_label[cid] == label

        # Scoped export frames (compact and full) only that group's leads.
        s_campaign = scope_export_frame(campaign, chosen)
        s_full = scope_export_frame(full, chosen)
        # Exports hold Part 4 leads only; labels cover every clustered customer, so
        # compare against the labeled clients that are also Part 4 leads.
        expected_ids = set(scoped.labels["client_id"]) & set(universe["client_id"])
        assert expected_ids
        for frame in (s_campaign, s_full):
            assert len(frame) == len(expected_ids)
            assert (frame[GROUP_COLUMN] == chosen).all()
            assert set(frame["client_id"]) == expected_ids
        assert group_download_filename("campaign_leads", chosen).endswith(".csv")
        assert group_download_filename("campaign_leads", chosen) != "campaign_leads.csv"

        # Scoped mix: only this group's leads, shares still sum to 100.
        mixes = persona_mix_by_cell(scoped.labels, cards)
        assert any(m.available for m in mixes.values())
        total_scoped_by_cell = {}
        for mix in mixes.values():
            if mix.available:
                assert set(mix.shares) <= scoped_names
                assert sum(mix.shares.values()) == pytest.approx(100.0, abs=1e-6)
        assert _cards_json(cards) == cards_before

    # The original result is unchanged after scoping several groups.
    pd.testing.assert_frame_equal(result.labels, labels_before)
    assert [(ps.group_key, [p.name for p in ps.personas]) for ps in result.persona_sets] == sets_before
    pd.testing.assert_frame_equal(full, full_before)
    # "All groups" restores the unscoped view.
    assert scope_result_to_group(result, ALL_GROUPS_LABEL) is result


# --------------------------------------------------------------------------- #
# 5. Names                                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "run_fixture", ["all_run", "segment_run", "campaign_run", "two_step_run"]
)
def test_persona_names_unique_and_clean(request, run_fixture):
    run = request.getfixturevalue(run_fixture)
    for ps in run.persona_sets:
        names = [p.name for p in ps.personas]
        assert len(names) == len(set(names))
        assert all("(cluster" not in n for n in names)


# --------------------------------------------------------------------------- #
# 6. Determinism                                                               #
# --------------------------------------------------------------------------- #
def test_all_run_is_deterministic(all_run, all_spec, cfg):
    again = run_personas(all_spec, RuleBasedNamer(), cfg)
    pd.testing.assert_frame_equal(all_run.labels, again.labels)

    def digest(run):
        return [
            (ps.group_key, p.name, p.description, list(p.actions))
            for ps in run.persona_sets
            for p in ps.personas
        ]

    assert digest(all_run) == digest(again)


# --------------------------------------------------------------------------- #
# 7. CLI                                                                       #
# --------------------------------------------------------------------------- #
def test_cli_writes_labeled_leads_to_tmp_only(cli_output, universe):
    code, out = cli_output
    assert code == 0
    assert out.exists()
    assert not str(out).startswith(str(OUTPUTS_DIR))
    assert not (OUTPUTS_DIR / "persona_labeled_leads.csv").exists()
    frame = pd.read_csv(out)
    assert len(frame) == len(universe)
    assert not frame["client_id"].duplicated().any()
    assert PERSONA_LABEL_COLUMN in frame.columns and GROUP_COLUMN in frame.columns


# --------------------------------------------------------------------------- #
# 8. Pipeline isolation                                                        #
# --------------------------------------------------------------------------- #
def test_run_pipeline_excludes_personas():
    import run_pipeline

    names = [name for name, _module in run_pipeline._STAGES]
    assert names == ["part2_network", "part1_optin", "part3_segments", "part4_cards"]
    assert not any("persona" in n for n in names)
    text = (ROOT / "src" / "run_pipeline.py").read_text(encoding="utf-8").lower()
    assert "part5_personas" not in text
    assert "persona" not in text


def test_stage_packages_do_not_reference_personas():
    for pkg in ("part1_optin", "part2_network", "part3_segments", "part4_cards"):
        for path in (ROOT / "src" / pkg).rglob("*.py"):
            assert "part5_personas" not in path.read_text(encoding="utf-8"), path


def test_importing_personas_leaves_stages_unchanged():
    import part1_optin.main as m1
    import part2_network.main as m2
    import part3_segments.main as m3
    import part4_cards.main as m4
    import run_pipeline

    mains = [m.main for m in (m1, m2, m3, m4)]
    stages = tuple(run_pipeline._STAGES)

    import part5_personas  # noqa: F401
    import webapp_core.personas  # noqa: F401

    assert [m.main for m in (m1, m2, m3, m4)] == mains
    assert tuple(run_pipeline._STAGES) == stages


def test_stage_imports_do_not_load_part5_personas():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    code = (
        "import part1_optin, part2_network, part3_segments, part4_cards, sys; "
        "print('part5_personas' in sys.modules)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False"

    # Importing part5_personas adds no part1-4 modules beyond those it needs.
    code2 = (
        "import part1_optin, part2_network, part3_segments, part4_cards, sys; "
        "pre = {k for k in sys.modules if k.split('.')[0] in "
        "('part1_optin','part2_network','part3_segments','part4_cards')}; "
        "import part5_personas; "
        "post = {k for k in sys.modules if k.split('.')[0] in "
        "('part1_optin','part2_network','part3_segments','part4_cards')}; "
        "print(pre == post)"
    )
    proc2 = subprocess.run(
        [sys.executable, "-c", code2],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc2.returncode == 0, proc2.stderr
    assert proc2.stdout.strip() == "True"


# --------------------------------------------------------------------------- #
# 7 (cont.). Isolation -- must run last: depends on every fixture above        #
# --------------------------------------------------------------------------- #
def test_outputs_and_data_byte_identical(
    hashes_before, all_run, segment_run, campaign_run, two_step_run, cli_output, cards
):
    after = {"outputs": _hash_tree(OUTPUTS_DIR), "data": _hash_tree(DATA_DIR)}
    assert after["outputs"] == hashes_before["outputs"]
    assert after["data"] == hashes_before["data"]
    assert hashes_before["outputs"], "outputs/ should not be empty"
