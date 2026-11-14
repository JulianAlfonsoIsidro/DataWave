"""Cleanup checks for task 3.7 (audit items 1.6 to 1.8).

Removed code stays removed, the kept fairness helpers give the same results,
and the Personas caption uses plain words (spec webapp-audit-fixes,
Requirements 2.6, 2.7, 2.8, 3.6, 3.7).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from webapp_core import fairness

ROOT = Path(__file__).resolve().parent.parent
REMOVED = (
    "group_shares", "past_join_rates", "GroupShare", "PastRate", "GROUP_COLUMNS",
    "FLAG_GAP_PTS", "status_chips_html", "user_marker_html", "recommended_caption",
    "_render_persona_comparison", "persona_comparison_frame",
)
REMOVED_CSS = (
    "st-key-pan_results_actions", "pan-ai-status", "pan-turn-dot", "pan-turn-marker",
)


def _sources(*patterns: str):
    for folder in ("app", "src"):
        for pattern in patterns:
            yield from (ROOT / folder).rglob(pattern)


def test_removed_names_are_not_referenced():
    for path in _sources("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in REMOVED:
            assert not re.search(rf"\b{name}\b", text), f"{name} in {path}"


def test_removed_css_is_gone():
    css = (ROOT / "app" / "styles.css").read_text(encoding="utf-8")
    for name in REMOVED_CSS:
        assert name not in css, name


@settings(deadline=None)
@given(
    forecast=st.floats(0, 2000, allow_nan=False),
    sendable=st.integers(0, 3000),
    historical=st.one_of(st.none(), st.floats(0, 1, allow_nan=False)),
)
def test_forecast_caution_unchanged(forecast, sendable, historical):
    got = fairness.forecast_caution(forecast, sendable, historical)
    if not sendable or historical is None or historical <= 0:
        assert got is None
    elif forecast / sendable < historical * fairness.CAUTION_FACTOR:
        assert got is None
    else:
        assert got and "Treat the forecast with care." in got


def test_caution_factor_and_historical_rate():
    assert fairness.CAUTION_FACTOR == 2.0
    leads = pd.DataFrame({"control_group": [0, 0, 0, 1], "joined": [1, 0, 0, 1]})
    assert abs(fairness.historical_join_rate(leads) - 1 / 3) < 1e-9
    assert fairness.historical_join_rate(pd.DataFrame({"x": [1]})) is None


def test_personas_caption_has_no_part_4():
    text = (ROOT / "app" / "persona_page.py").read_text(encoding="utf-8")
    assert "Each card keeps its usual guidance, with expected joiners" in text
    assert "keeps its Part 4 guidance" not in text
