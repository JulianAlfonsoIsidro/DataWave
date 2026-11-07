"""Streamlit AppTest smoke test of the Personas tab (spec part6 task 14.15).

Renders ``app.persona_page.render_persona_tab`` headlessly on a small sampled
Joined_Attribute_Set (~300 rows, k=2) and checks, end to end through the real
widgets: personas render with the default attributes at "All leads"; the
single-type warning appears for numeric-only and categorical-only selections and
not for a mix (Requirements 6.11); the group dropdown appears for a split run and
scoping a group scopes the output (Requirements 3.16, 3.17); an invalid grouping
field surfaces the actionable error as-is (Requirements 3.5, 3.20). Task 14.16:
"Expected Joiners By Persona" shows an info message without a New Promo run and
renders the per-card persona table when one is in session state (Requirement 7).
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:  # persona_page does ``import theme``
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import app.persona_page as persona_page  # noqa: E402
import webapp_core.personas as core_personas  # noqa: E402
from part5_personas import join as join_module  # noqa: E402
from part5_personas.config import Config  # noqa: E402
from part5_personas.grouping import _segment_field_message  # noqa: E402

N_SAMPLE = 300
GROUP_KEY = "persona_group_select"


def _page() -> None:
    """Script body for AppTest: just the Personas tab, no set_page_config/hero."""
    from app.persona_page import render_persona_tab

    render_persona_tab()


@pytest.fixture(scope="module")
def sample():
    """A ~300-row sample of the real joined set (built once per module)."""
    full, report = join_module.build_joined_attributes(Config())
    return full.sample(n=N_SAMPLE, random_state=42).reset_index(drop=True), report


@pytest.fixture()
def app_test(monkeypatch, sample):
    """AppTest on the Personas tab with the join patched to the small sample."""
    frame, report = sample

    def _fake_join(cfg):  # noqa: ANN001
        return frame.copy(), dict(report)

    monkeypatch.setattr(join_module, "build_joined_attributes", _fake_join)
    monkeypatch.setattr(core_personas, "build_joined_attributes", _fake_join)
    st.cache_data.clear()
    at = AppTest.from_function(_page, default_timeout=60)
    at.run()
    assert not at.exception
    yield at
    st.cache_data.clear()


def _warnings(at: AppTest) -> list[str]:
    return [w.value for w in at.warning]


def _select(at: AppTest, **by_group: list[str]) -> None:
    """Set the four attribute multiselects (keys persona_attr_<group>)."""
    names = {
        "demo": "Demographics",
        "life": "Lifestyle",
        "prod": "Products owned",
        "spend": "Spending behavior",
    }
    for short, group in names.items():
        at.multiselect(key=f"persona_attr_{group}").set_value(by_group.get(short, []))


def _build(at: AppTest) -> None:
    at.number_input(key="persona_k_input").set_value(2)
    at.button(key="persona_run").click()
    at.run()


def _subheaders(at: AppTest) -> list[str]:
    return [s.value for s in at.subheader]


def _segment_markers(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown if str(m.value).startswith("**Segment: ")]


def test_default_attributes_all_leads_render_personas(app_test):
    at = app_test
    _build(at)
    assert not at.exception
    assert not at.error
    assert "Personas" in _subheaders(at)
    assert "How the Personas Differ" in _subheaders(at)
    assert len(at.dataframe) >= 1
    assert len(at.dataframe[0].value) == 2  # k=2 -> two persona rows
    assert any("Built 2 personas" in s.value for s in at.success)
    assert GROUP_KEY not in {s.key for s in at.selectbox}  # single set: no dropdown


def test_single_type_warning_numeric_categorical_and_mixed(app_test):
    at = app_test
    numeric_warning = persona_page._NUMERIC_ONLY_WARNING
    categorical_warning = persona_page._CATEGORICAL_ONLY_WARNING

    _select(at, spend=["total_out", "inflow_share_payroll"])
    at.run()
    assert numeric_warning in _warnings(at)
    assert categorical_warning not in _warnings(at)

    _select(at, demo=["age_band", "region"])
    at.run()
    assert categorical_warning in _warnings(at)
    assert numeric_warning not in _warnings(at)

    _select(at, demo=["age_band"], spend=["total_out"])
    at.run()
    assert numeric_warning not in _warnings(at)
    assert categorical_warning not in _warnings(at)


def test_group_dropdown_and_scoping_by_customer_segment(app_test):
    at = app_test
    at.selectbox(key="persona_level_select").set_value("By customer segment")
    at.run()
    _select(at, demo=["age_band"], spend=["total_out", "inflow_share_payroll"])
    _build(at)
    assert not at.exception
    assert not at.error

    dropdown = at.selectbox(key=GROUP_KEY)
    options = list(dropdown.options)
    assert options[-1] == persona_page.ALL_GROUPS_LABEL
    assert len(options) >= 3  # >= 2 segments + "All groups"

    # Default selection scopes to the first group only.
    assert set(_segment_markers(at)) == {f"**Segment: {options[0]}**"}

    at.selectbox(key=GROUP_KEY).select(persona_page.ALL_GROUPS_LABEL)
    at.run()
    all_markers = _segment_markers(at)
    assert len(set(all_markers)) >= len(options) - 1

    target = options[1]
    at.selectbox(key=GROUP_KEY).select(target)
    at.run()
    assert not at.exception
    scoped = _segment_markers(at)
    assert scoped
    assert set(scoped) == {f"**Segment: {target}**"}
    assert len(scoped) < len(all_markers)


def test_invalid_grouping_field_shows_actionable_error(app_test, monkeypatch):
    at = app_test
    monkeypatch.setattr(
        persona_page, "business_segment_field_for_level", lambda level: "segment_label"
    )
    at.selectbox(key="persona_level_select").set_value("By customer segment")
    at.run()
    _build(at)
    assert not at.exception
    expected = _segment_field_message("segment_label")
    assert [e.value for e in at.error] == [expected]
    assert "Personas" not in _subheaders(at)  # nothing was built


def test_no_new_promo_run_shows_info_and_no_old_mix_section(app_test):
    at = app_test
    _build(at)
    assert not at.exception
    assert "Decision Cards With Persona Mix" not in _subheaders(at)
    assert "Expected Joiners By Persona" in _subheaders(at)
    assert persona_page.NO_NEW_PROMO_MESSAGE in [i.value for i in at.info]


def test_expected_joiners_by_persona_renders_for_new_promo_run(app_test, sample):
    import pandas as pd

    from webapp_core.run_promo import RunResult

    at = app_test
    frame, _report = sample
    ids = frame["client_id"].tolist()
    sendable = pd.DataFrame(
        {"client_id": ids, "p_join": [0.30 if i % 2 == 0 else 0.05 for i in range(len(ids))]}
    )
    cards = [
        {
            "promo_id": "P900",
            "segment": "Ready Toppers",
            "action": "Send now",
            "dominant_channel": "In-app",
            "message_angle": "Reward",
            "expected_joiners": float(sendable["p_join"].sum()),
            "joiners_90_low": 1.0,
            "joiners_90_high": 2.0,
            "expected_value": 100.0,
            "top_drivers": ["tenure"],
            "excluded_by_reason": {},
        }
    ]
    run = RunResult(
        promo_spec=None,
        scored=pd.DataFrame(),
        segments_df=pd.DataFrame(),
        cards=cards,
        sendable_by_segment={"Ready Toppers": sendable},
    )
    at.session_state["run_result"] = run
    _build(at)
    assert not at.exception
    assert not at.error
    assert "Expected Joiners By Persona" in _subheaders(at)
    assert persona_page.NO_NEW_PROMO_MESSAGE not in [i.value for i in at.info]

    result = at.session_state[persona_page.PERSONA_RESULT_KEY]
    bd = core_personas.expected_joiners_by_persona(
        cards, run.sendable_by_segment, result.labels, result.persona_sets
    )[0]
    text = "\n".join(str(m.value) for m in at.markdown)
    assert "P900 -- Ready Toppers" in text
    assert "Expected joiners" in text
    assert html.escape(bd.takeaway) in text
    assert f"{bd.total_expected_joiners:,.1f}" in text