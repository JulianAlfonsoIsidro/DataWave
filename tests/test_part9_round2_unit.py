"""Part 9 round 2: rounded joiners, shares, segment flow, descriptions, help.

Spec ``part9-layout-fixes``, Requirements 20 to 28 (tasks 17.1 and 17.2).
Property tests cover the pure helpers in ``webapp_core``; unit tests cover the
HTML builders in ``app/theme.py`` and the help content.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import theme  # noqa: E402
from part4_cards.config import CONTROL_FRACTION, VALUE_PER_JOIN_PHP, Z_90  # noqa: E402
from webapp_core import help_content, number_help  # noqa: E402
from webapp_core.number_format import (  # noqa: E402
    forecast_text,
    of_sendable_text,
    share_pct,
    shown_joiners,
)
from webapp_core.segment_flow import (  # noqa: E402
    SEGMENT_DISPLAY_ORDER,
    FlowRow,
    display_rank,
    flow_rows,
    flow_total,
    in_display_order,
    reconciles,
)

forecasts = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)


# --- number_format (Requirements 20, 21) --------------------------------------

@settings(deadline=None)
@given(forecasts)
def test_shown_joiners_is_a_whole_number_within_half(x):
    n = shown_joiners(x)
    assert isinstance(n, int)
    assert abs(n - x) <= 0.5 + 1e-9


def test_shown_joiners_rounds_halves_up_and_handles_bad_input():
    assert shown_joiners(2.5) == 3
    assert shown_joiners(87.3) == 87
    assert shown_joiners(0.4) == 0
    assert shown_joiners(None) == 0
    assert shown_joiners(float("nan")) == 0


@settings(deadline=None)
@given(forecasts)
def test_forecast_text_has_one_decimal(x):
    text = forecast_text(x)
    assert text.startswith("Forecasted: ")
    assert re.fullmatch(r"[\d,]+\.\d", forecast_text(x, short=True))


@settings(deadline=None)
@given(forecasts, st.integers(min_value=-5, max_value=10**6))
def test_share_pct_never_divides_by_zero(part, whole):
    pct = share_pct(part, whole)
    if whole <= 0:
        assert pct is None
    else:
        assert pct is not None and re.fullmatch(r"-?[\d.]+%", pct)


def test_of_sendable_text_cases():
    assert of_sendable_text(204.4, 1595) == "out of 1,595 sendable leads (12.8%)"
    assert of_sendable_text(3.0, 0) == "out of 0 sendable leads"
    assert of_sendable_text(0.2, 1) == "out of 1 sendable lead (20.0%)"


# --- segment_flow (Requirements 24, 27) ---------------------------------------

def _card(segment, clients, excluded, control, sendable, forecast=1.0):
    return {
        "segment": segment, "n_clients": clients, "excluded_by_reason": excluded,
        "control_count": control, "sendable_count": sendable, "expected_joiners": forecast,
    }


@settings(deadline=None)
@given(st.lists(st.tuples(st.integers(0, 500), st.integers(0, 500), st.integers(0, 500)),
                min_size=1, max_size=4))
def test_flow_rows_parts_add_to_clients(parts):
    cards = [
        _card(seg, a + b + c, {"Contacted Too Often": a}, b, c)
        for seg, (a, b, c) in zip(SEGMENT_DISPLAY_ORDER, parts)
    ]
    rows = flow_rows(cards)
    assert all(reconciles(r) for r in rows)
    total = flow_total(rows)
    assert total.clients == total.parts_sum == sum(a + b + c for a, b, c in parts)


@settings(deadline=None)
@given(st.permutations(list(SEGMENT_DISPLAY_ORDER) + ["Zeta", "Alpha"]))
def test_display_order_is_stable_and_total(names):
    ordered = in_display_order(names)
    assert ordered[:4] == list(SEGMENT_DISPLAY_ORDER)
    assert ordered[4:] == ["Alpha", "Zeta"]
    assert in_display_order(ordered) == ordered


def test_display_order_is_the_owner_order():
    assert SEGMENT_DISPLAY_ORDER == (
        "Ready Toppers", "Willing but Stretched", "Untapped Wealth", "Not Now",
    )
    assert display_rank("Ready Toppers") < display_rank("Not Now") < display_rank("Other")


def test_reconciles_flags_a_mismatch():
    assert not reconciles(FlowRow("X", 10, 2, 2, 2, 1.0))


# --- theme HTML builders (Requirements 20, 21, 24, 27) ------------------------

def test_joiners_pair_shows_whole_number_with_exact_forecast_in_tip():
    full = theme.joiners_pair_html(87.3)
    # Critique: no bracket beside the number; the exact forecast is its tip
    # (visible on hover/focus and in the accessible label).
    assert ">87<" in full and "(Forecasted" not in full
    assert "Exact forecast: 87.3" in full
    assert theme.joiners_pair_html(87.3, full=False) == full
    zero = theme.joiners_pair_html(0.3)
    assert ">0<" in zero and "Exact forecast: 0.3" in zero


def test_run_kpi_sub_line_and_brand():
    out = theme.run_kpi_html("204", "Expected Joiners", forecast=204.4, sendable_total=1595)
    # Owner follow-up: the number is the whole number only, no bracket.
    assert "Forecasted" not in out
    assert "out of 1,595 sendable leads (12.8%)" in out
    assert number_help.header_help() in out
    zero = theme.run_kpi_html("0", "Expected Joiners", forecast=0.0, sendable_total=0)
    assert "out of 0 sendable leads" in zero and "%)" not in zero
    brand = theme.brand_html()
    assert "Promo Audience Manager" in brand and all(f"pan-logo-{k}" in brand for k in ("tile", "p", "ring", "dot"))


def test_whatif_segments_cells_and_heading():
    rows = [
        ("Ready Toppers", [(347, 340, "count"), (87.3, 85.6, "joiners"), (282, 280, "count")]),
        ("Not Now", [(947, None, "count"), (38.8, None, "joiners"), (717, None, "count")]),
    ]
    out = theme.whatif_segments_html(rows)
    assert "Expected Joiners (Forecast)" in out
    assert "Exact forecast: 87.3" in out and "(87.3)" not in out
    # The joiners change is the difference of the shown whole numbers: 87 - 86.
    assert "+1</span>" in out
    assert out.index("Ready Toppers") < out.index("Not Now")


def test_whatif_change_uses_whole_numbers():
    out = theme.whatif_change_html("Expected Joiners", "203", "₱560,000",
                                   base_number="204", base_label="₱530,000",
                                   forecast=203.4, base_forecast=204.4)
    assert "Exact forecast: 203.4" in out and "Exact forecast: 204.4" in out
    assert "(Forecasted" not in out
    assert "−1" in out


def test_segment_flow_html_one_segment_with_counts_and_shares():
    cards = [
        _card("Not Now", 947, {"a": 151}, 79, 717, 38.8),
        _card("Ready Toppers", 347, {"a": 34}, 31, 282, 87.3),
    ]
    rows = flow_rows(cards)
    assert [r.segment for r in rows] == ["Ready Toppers", "Not Now"]   # display order
    out = theme.segment_flow_html(rows[0])
    for name in ("Not Contacted", "Control Group", "Sendable"):
        assert name in out
    assert out.count('class="pan-flow-part') == 3
    assert ">282<" in out and "81.3%" in out and "9.8%" in out and "8.9%" in out
    assert "<strong>347</strong> clients" in out
    assert 'role="img"' in out
    assert "Ready Toppers: 34 not contacted, 31 control group, 282 sendable, of 347 clients" in out
    assert "<table" not in out
    assert "do not add up" not in out
    total = theme.segment_flow_html(flow_total(rows), title="All Segments")
    assert "All Segments" in total and "<strong>1,294</strong> clients" in total
    bad = theme.segment_flow_html(FlowRow("X", 10, 1, 1, 1, 1.0))
    assert "These figures do not add up for this run." in bad


def test_help_marks_render_bold_and_quoted():
    import importlib
    import streamlit  # noqa: F401  (help_page imports streamlit)

    sys.path.insert(0, str(REPO_ROOT / "app"))
    help_page = importlib.import_module("help_page")
    assert help_page.marked_html("See [[Results]] tab") == 'See <strong>&quot;Results&quot;</strong> tab'
    assert help_page.marked_md("On the [[Results]] tab?") == 'On the **"Results"** tab?'
    for entry in help_content.ENTRIES:
        assert "[[" not in help_page.marked_html(entry.answer + entry.where)
        assert "[[" not in help_page.marked_md(entry.question)


# --- descriptions and help (Requirements 22, 28) ------------------------------

def test_descriptions_are_short_plain_and_read_the_config():
    for fn in number_help.ALL_STATIC:
        text = fn()
        assert 0 < len(text) <= number_help.MAX_CHARS, fn.__name__
        assert "p_join" not in text and "excluded_by_reason" not in text
    assert f"{CONTROL_FRACTION * 100:.0f}%" in number_help.control_help()
    assert f"₱{VALUE_PER_JOIN_PHP:,.0f}" in number_help.value_help()
    assert number_help.persona_group_caption("Luzon", 376, 1595, sendable=True) == (
        "Luzon · 376 of 1,595 sendable leads"
    )


def test_help_content_is_complete():
    ids = [e.id for e in help_content.ENTRIES]
    assert len(ids) == len(set(ids)) >= 16
    for entry in help_content.ENTRIES:
        assert entry.question.endswith("?")
        assert entry.answer and entry.where
        assert len(re.findall(r"[.!?](?:\s|$)", entry.answer)) <= 5, entry.id
    for f in help_content.FORMULAS:
        assert f.name and "=" in f.equation
    text = " ".join(f"{f.name} {f.equation}" for f in help_content.FORMULAS)
    assert f"{Z_90:g}" in text
    assert f"₱{VALUE_PER_JOIN_PHP:,.0f}" in text
    assert "Not Contacted + Control Group + Sendable" in text
    assert [s for s, _ in help_content.NEXT_STEPS] == ["Results", "What-If", "Personas"]
