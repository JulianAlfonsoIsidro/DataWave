"""Streamlit AppTest smoke tests for every tab of the full app (spec part7 task 17.2).

Opens ``app/main.py`` headlessly with NO AWS / Bedrock variables set (and
``dotenv.load_dotenv`` blocked) and asserts that New Promo (both sub-tabs),
Results with a seeded real run, What-If, Personas, Ask Assistant and Past Promos
render without raising (Requirements 1.9, 10.9). The tabs are all rendered by one
script run, so each test checks its tab's own content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:  # app modules do ``import theme``
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from part1_optin.config import Config as Part1Config  # noqa: E402
from webapp_core.model_io import load_model  # noqa: E402
from webapp_core.run_promo import PromoSpec, run_promo  # noqa: E402

AWS_VARS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "BEDROCK_MODEL_ID")
TIMEOUT = 120


@pytest.fixture(scope="module")
def seeded_run():
    """A small real RunResult (Affluent-Gold, default channels) from the fitted model."""
    data = {
        "customer_dna": pd.read_csv(ROOT / "data" / "customer_dna.csv"),
        "adb_monthly": pd.read_csv(ROOT / "data" / "adb_monthly.csv"),
        "features": pd.read_csv(ROOT / "outputs" / "features_part2.csv"),
    }
    spec = PromoSpec(
        promo_id="NEW-001",
        product_type="Savings",
        mechanic="TOP_UP",
        threshold_php=50_000.0,
        reward="Bonus",
        eligible_segments=["Affluent-Gold"],
        min_adb=0.0,
        channels=["In-app", "Email", "SMS"],
    )
    return run_promo(
        spec,
        model=load_model(ROOT / "outputs"),
        config=Part1Config(),
        data=data,
    )


@pytest.fixture()
def no_aws(monkeypatch):
    """Remove the AWS / Bedrock variables and make load_dotenv a no-op."""
    for name in AWS_VARS:
        monkeypatch.delenv(name, raising=False)
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _open(seed=None) -> AppTest:
    at = AppTest.from_file(str(APP_DIR / "main.py"), default_timeout=TIMEOUT)
    if seed is not None:
        at.session_state["run_result"] = seed
    at.run()
    return at


def _texts(at: AppTest) -> str:
    parts = [str(m.value) for m in at.markdown]
    parts += [str(s.value) for s in at.subheader]
    parts += [str(i.value) for i in at.info]
    parts += [str(c.value) for c in at.caption]
    return "\n".join(parts)


def test_new_promo_both_tabs_render(no_aws):
    at = _open()
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert any("Upload" in label for label in labels)
    assert any("Fill In" in label for label in labels)
    assert "Design A Promo" in [s.value for s in at.subheader]
    assert any(b.label == "Run Analysis" for b in at.button)


def test_results_with_seeded_run_renders(no_aws, seeded_run):
    assert seeded_run.cards, "seeded run should produce cards"
    at = _open(seeded_run)
    assert not at.exception
    subs = [s.value for s in at.subheader]
    for name in ("Results Grid", "Decision Cards", "Download Leads"):
        assert name in subs
    # Part 9: Export Summary moved into the Results action bar (no heading).
    labels = [w.proto.label for w in at.get("download_button")]
    assert "Export Summary" in labels


def test_whatif_with_seeded_run_renders(no_aws, seeded_run):
    at = _open(seeded_run)
    assert not at.exception
    assert "What-If: Vary The Threshold" in [s.value for s in at.subheader]


def test_whatif_and_results_without_run_show_info(no_aws):
    at = _open()
    assert not at.exception
    assert sum("Run a promo first" in i.value for i in at.info) >= 2


def test_personas_tab_renders(no_aws):
    at = _open()
    assert not at.exception
    assert "persona_run" in {b.key for b in at.button}


def test_ask_assistant_renders_without_aws(no_aws):
    at = _open()
    assert not at.exception
    assert not at.error


def test_past_promos_renders(no_aws):
    at = _open()
    assert not at.exception
