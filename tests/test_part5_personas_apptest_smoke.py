"""Streamlit AppTest smoke test of the Personas tab (spec part6 task 14.15).

Renders ``app.persona_page.render_persona_tab`` headlessly on a small sampled
Joined_Attribute_Set (~300 rows, k=2) and checks, end to end through the real
widgets: personas render with the default attributes at "All leads"; the
single-type warning appears for numeric-only and categorical-only selections and
not for a mix (Requirements 6.11); the group dropdown appears for a split run and
scoping a group scopes the output (Requirements 3.16, 3.17); the level selector
offers only "All leads" and "By campaign", and "By campaign" with a split renders
(task 14.17, Requirements 3.4, 3.8, 3.23). Task 14.16:
"Expected Joiners By Persona" shows an info message without a New Promo run and
renders the per-card persona table when one is in session state (Requirement 7).
"""

from __future__ import annotations

import re

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
    # Part 9: the "How the Personas Differ" table was removed from the page.
    assert "How the Personas Differ" not in _subheaders(at)
    assert len(at.dataframe) == 0
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


def _split_by(at: AppTest, *columns: str) -> None:
    at.checkbox(key="persona_two_step").set_value(True)
    at.run()
    at.multiselect(key="persona_grouping_attrs").set_value(list(columns))
    at.run()


def test_group_dropdown_and_scoping_by_customer_segment(app_test):
    at = app_test
    _split_by(at, "segment")
    # "segment" is used for the split, so it is not offered in the picker.
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


def test_level_selector_offers_only_all_leads_and_by_campaign(app_test):
    at = app_test
    assert list(at.selectbox(key="persona_level_select").options) == [
        "All leads",
        "By campaign",
    ]


def test_by_campaign_with_split_by_age_band_renders(app_test):
    at = app_test
    at.selectbox(key="persona_level_select").set_value("By campaign")
    at.run()  # no live run -> past promo P001 pool
    _split_by(at, "age_band")
    _build(at)
    assert not at.exception
    assert not at.error
    assert "Personas" in _subheaders(at)
    assert at.selectbox(key=GROUP_KEY).options  # group dropdown present
    # The split column is not offered in the picker.
    assert "age_band" not in at.multiselect(key="persona_attr_Demographics").options


def test_no_new_promo_run_shows_info_and_no_old_mix_section(app_test):
    at = app_test
    _build(at)
    assert not at.exception
    assert "Decision Cards With Persona Mix" not in _subheaders(at)
    assert "Expected Joiners By Persona" in _subheaders(at)
    assert persona_page.NO_NEW_PROMO_MESSAGE in [i.value for i in at.info]


def _new_promo_run(frame):
    """A New Promo RunResult whose single card covers every sampled client."""
    import pandas as pd

    from webapp_core.run_promo import RunResult

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
    return run, cards


def _markdown_text(at: AppTest) -> str:
    return "\n".join(str(m.value) for m in at.markdown)


def test_expected_joiners_by_persona_renders_for_new_promo_run(app_test, sample):
    at = app_test
    frame, _report = sample
    run, cards = _new_promo_run(frame)
    at.session_state["run_result"] = run
    _build(at)
    assert not at.exception
    assert not at.error
    assert "Expected Joiners By Persona" in _subheaders(at)
    assert persona_page.NO_NEW_PROMO_MESSAGE not in [i.value for i in at.info]

    result = at.session_state[persona_page.PERSONA_RESULT_KEY]
    bd = core_personas.expected_joiners_by_persona(
        cards, run.sendable_by_segment, result.labels, result.persona_sets, drop_empty=True
    )[0]
    text = _markdown_text(at)
    # Part 9 round 3: the promo id is wrapped in a muted span; compare the visible text.
    assert "P900 · Ready Toppers" in re.sub(r"<[^>]+>", "", text)
    # Part 7 wording: sentence rows, "Total For <Segment>" line, no old table headers.
    assert "likely to join" in text
    assert "Total For Ready Toppers" in text
    assert "Leads (share)" not in text and ">Rate<" not in text
    # Single group: no group instruction, collapsed expanders present.
    assert persona_page.ALL_GROUPS_INSTRUCTION not in text
    labels = [e.label for e in at.expander]
    assert "How to message this" in labels and "Details" in labels
    assert all(not e.proto.expanded for e in at.expander if e.label in ("How to message this", "Details"))


def test_split_by_age_band_single_group_and_all_groups(app_test, sample):
    at = app_test
    frame, _report = sample
    run, cards = _new_promo_run(frame)
    at.session_state["run_result"] = run
    _split_by(at, "age_band")
    _build(at)
    assert not at.exception
    assert not at.error
    options = list(at.selectbox(key=GROUP_KEY).options)
    group = options[0]
    result = at.session_state[persona_page.PERSONA_RESULT_KEY]

    # One group selected: note + that group's personas only.
    text = _markdown_text(at)
    # Part 7 (7.9): no group index or old group note in any persona string.
    assert "across all groups" not in text
    assert "Total For Ready Toppers" in text
    assert f"Total for {group}" not in text
    assert persona_page.ALL_GROUPS_INSTRUCTION not in text
    names_here = {p.name for ps in result.persona_sets if ps.group_key == group for p in ps.personas}
    names_else = {p.name for ps in result.persona_sets if ps.group_key != group for p in ps.personas}
    for name in names_else - names_here:
        assert html.escape(name) not in text

    # All groups: instruction as visible markdown (not a caption) + group summary.
    at.selectbox(key=GROUP_KEY).select(persona_page.ALL_GROUPS_LABEL)
    at.run()
    assert not at.exception
    assert persona_page.ALL_GROUPS_INSTRUCTION in [m.value for m in at.markdown]
    assert persona_page.ALL_GROUPS_INSTRUCTION not in [c.value for c in at.caption]
    text = _markdown_text(at)
    assert "<th" in text and ">Group<" in text
    assert html.escape(group) in text
    assert "across all groups" not in text
    assert "Details" not in [e.label for e in at.expander]