"""Past Promos tab body (Part 7, task 16.6; Requirement 11).

Presentation and session-state wiring only. The logic lives in
``webapp_core.past_campaigns`` (loading, sort, filter, paging, detail) and
``webapp_core.similarity`` (the eight-component Similarity_Score).

- Sort: Newest (default), Oldest, Most Similar. Most Similar is offered only
  when a New Promo profile can be built, from the last run result or from the
  New Promo form keys in ``app/upload_panel.py`` (Requirements 11.2, 11.3).
- Filters: Product Type and Target Audience (11.4).
- Five campaigns at a time with a View More button (+5, hidden when all are
  shown). The visible count resets to 5 on any sort or filter change
  (11.5, 11.6, 11.7).
- Each campaign shows dates, inclusive duration, opt-in rate on treated leads
  or "Not Available", per-segment responses, the similarity breakdown bar
  chart, and the existing predicted-vs-actual table (11.12, 11.14, 11.15, 11.17).
- A missing data file shows the error naming the file and nothing else (11.18).
- Completed campaigns only (11.20).
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

import streamlit as st

import theme
import upload_panel
from webapp_core import number_help
from webapp_core import past_campaigns as pc
from webapp_core.similarity import (
    COMPONENT_KEYS,
    NewPromoProfile,
    SimilarityResult,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = ROOT / "outputs"
CARDS_JSON_PATH = OUTPUTS_DIR / "cards.json"

RUN_RESULT_KEY = "run_result"  # same key as app/main.py

SORT_KEY = "past_sort"
PRODUCT_FILTER_KEY = "past_filter_product"
AUDIENCE_FILTER_KEY = "past_filter_audience"
VISIBLE_KEY = "past_visible"
_SIGNATURE_KEY = "past_view_signature"

COMPONENT_LABELS: dict[str, str] = {
    "audience": "Audience",
    "need": "Customer Need",
    "product_mechanic": "Product And Mechanic",
    "economics": "Economics",
    "duration": "Duration",
    "channels": "Channels",
    "objective": "Objective",
    "name_summary": "Name And Summary",
}

SEGMENT_ORDER = ["Ready Toppers", "Untapped Wealth", "Willing but Stretched", "Not Now"]


# --------------------------------------------------------------------------
# Predicted vs actual (moved here from app/main.py, same output)
# --------------------------------------------------------------------------

def fmt_rate(value) -> str:
    """Format a join rate as a percentage (39.6%), or "No Leads" when NA."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "No Leads"
    return f"{float(value) * 100:.1f}%"


def gap_text(predicted, actual) -> str:
    """Actual minus predicted, in percentage points (round 3)."""
    def ok(v):
        return v is not None and not (isinstance(v, float) and math.isnan(v))
    if not (ok(predicted) and ok(actual)):
        return "No Leads"
    gap = (float(actual) - float(predicted)) * 100
    if abs(gap) < 0.05:
        return "0.0 pts"
    return f"{'+' if gap > 0 else '−'}{abs(gap):.1f} pts"


def _segment_sort_key(row: dict) -> tuple[int, str]:
    segment = str(row.get("segment"))
    rank = SEGMENT_ORDER.index(segment) if segment in SEGMENT_ORDER else len(SEGMENT_ORDER)
    return rank, segment


def predicted_actual_html(rows: list[dict]) -> str:
    """Escaped table HTML for one campaign's predicted-vs-actual rows."""
    header = (
        "<tr>"
        '<th class="pan-th">Segment</th>'
        # Part 9 round 2 (Requirement 22): plain meanings as hover texts.
        f'<th class="pan-th pan-num">{theme.tooltip_html("Predicted", number_help.predicted_actual_help())}</th>'
        f'<th class="pan-th pan-num">{theme.tooltip_html("Actual", number_help.predicted_actual_help())}</th>'
        f'<th class="pan-th pan-num">{theme.tooltip_html("Gap", number_help.gap_help())}</th>'
        "</tr>"
    )
    body = []
    for row in sorted(rows, key=_segment_sort_key):
        body.append(
            "<tr>"
            f'<td class="pan-td pan-strong">{html.escape(str(row.get("segment", "N/A")))}</td>'
            f'<td class="pan-td pan-num">{fmt_rate(row.get("predicted"))}</td>'
            f'<td class="pan-td pan-num pan-accent">{fmt_rate(row.get("actual"))}</td>'
            f'<td class="pan-td pan-num">{gap_text(row.get("predicted"), row.get("actual"))}</td></tr>'
        )
    return f'<table class="pan-table">{header}{"".join(body)}</table>'


# --------------------------------------------------------------------------
# New Promo profile
# --------------------------------------------------------------------------

def current_profile(state=None) -> NewPromoProfile | None:
    """Build the New Promo profile from the last run or the form keys, else None."""
    state = st.session_state if state is None else state
    result = state.get(RUN_RESULT_KEY)
    spec = getattr(result, "promo_spec", None)
    if spec is not None:
        return NewPromoProfile(
            name=str(spec.promo_id),
            summary=str(spec.reward or ""),
            product_type=str(spec.product_type),
            mechanic=str(spec.mechanic),
            threshold_php=float(spec.threshold_php),
            eligible_segments=tuple(spec.eligible_segments),
            channels=tuple(spec.channels),
        )
    product = state.get(upload_panel.PRODUCT_TYPE_KEY)
    if not product:
        return None
    return NewPromoProfile(
        summary=str(state.get(upload_panel.REWARD_KEY) or ""),
        product_type=str(product),
        mechanic=str(state.get(upload_panel.MECHANIC_KEY) or ""),
        eligible_segments=tuple(state.get(upload_panel.SEGMENTS_KEY) or ()),
        channels=tuple(state.get(upload_panel.CHANNELS_KEY) or ()),
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def similarity_chart_html(result: SimilarityResult) -> str:
    """Eight horizontal bars; Unavailable components are labeled as such."""
    by_key = {c.key: c for c in result.components}
    parts = []
    for key in COMPONENT_KEYS:
        comp = by_key.get(key)
        name = COMPONENT_LABELS[key]
        if comp is None or comp.fraction is None:
            # Round 3: no empty bar, so Unavailable never reads as a 0 score.
            parts.append(theme.unavailable_line_html(f"{name}: Unavailable"))
        else:
            parts.append(
                theme.bar_html(f"{name}: {comp.points:.0f} of {comp.max_points:.0f}", comp.fraction)
            )
    return "".join(parts)


def _segment_table_html(detail: pc.CampaignDetail) -> str:
    if not detail.segment_responses:
        return ""
    header = (
        "<tr>"
        '<th class="pan-th">Segment</th>'
        '<th class="pan-th pan-num">Treated</th>'
        '<th class="pan-th pan-num">Joined</th>'
        '<th class="pan-th pan-num">Response</th></tr>'
    )
    body = "".join(
        "<tr>"
        f'<td class="pan-td pan-strong">{html.escape(r.segment)}</td>'
        f'<td class="pan-td pan-num">{r.treated:,}</td>'
        f'<td class="pan-td pan-num">{r.joined:,}</td>'
        f'<td class="pan-td pan-num pan-accent">{pc.format_opt_in(r.rate)}</td></tr>'
        for r in detail.segment_responses
    )
    return f'<table class="pan-table">{header}{body}</table>'


def _campaign_body_html(
    detail: pc.CampaignDetail, prediction_rows: list[dict], similarity_on: bool
) -> str:
    p = detail.profile
    days = f"{detail.duration_days} Days" if detail.duration_days else pc.NOT_AVAILABLE
    fields = [
        ("Start Date", html.escape(detail.start.isoformat() if detail.start else pc.NOT_AVAILABLE)),
        ("End Date", html.escape(detail.end.isoformat() if detail.end else pc.NOT_AVAILABLE)),
        ("Duration", html.escape(days)),
        ("Product Type", html.escape(p.product_type or pc.NOT_AVAILABLE)),
        ("Opt-In Rate", html.escape(detail.opt_in_display)),
    ]
    out = [theme.fields_row_html(fields)]
    if detail.segment_responses:
        out.append(theme.section_label_html("Responses By Segment"))
        out.append(_segment_table_html(detail))
    if similarity_on and detail.similarity is not None:
        out.append(theme.section_label_html("Similarity To Your New Promo"))
        if detail.similarity.score is None:
            out.append(theme.banner_html(pc.NOT_ENOUGH_DATA, "info"))
        else:
            out.append(
                theme.badge_html(f"Similarity Score: {pc.display_score(detail.similarity)}", "info")
            )
            out.append(f'<div class="pan-help-line">{html.escape(number_help.similarity_help())}</div>')
            out.append(similarity_chart_html(detail.similarity))
    if prediction_rows:
        out.append(theme.section_label_html("Predicted Vs Actual Join Rate"))
        out.append(predicted_actual_html(prediction_rows))
    return "".join(out)


def _load_cards() -> list[dict]:
    try:
        with open(CARDS_JSON_PATH, encoding="utf-8") as fh:
            return json.load(fh) or []
    except (FileNotFoundError, ValueError):
        return []


def _row_label(row: pc.CampaignRow, similarity_on: bool) -> str:
    p = row.profile
    label = f"{p.promo_id}: {p.name}" if p.name else p.promo_id
    if similarity_on and row.similarity is not None:
        # Part 9: the bare "(64)" is named, as in the badge inside.
        label += f" (Similarity Score: {pc.display_score(row.similarity)})"
    return label


_PAST_FILES = ("promo_history.csv", "promo_leads.csv", "customer_dna.csv")


def _load_past_data():
    """The past-campaign frames and profiles, cached until a data file changes.

    Part 9: these were re-read and rebuilt on every rerun (about 0.5 s), and
    every tab switch reruns the app now, so the reveal after Run Analysis and
    each tab switch paid for it. The data is read-only here.
    """
    stamps = tuple(
        (name, (DATA_DIR / name).stat().st_mtime_ns if (DATA_DIR / name).exists() else 0)
        for name in _PAST_FILES
    )
    return _cached_past_data(stamps)


@st.cache_data(show_spinner=False)
def _cached_past_data(stamps: tuple):
    history, leads, dna = pc.load_all(*(DATA_DIR / name for name in _PAST_FILES))
    return history, leads, dna, pc.build_profiles(history, leads, dna)


def render_past_promos_tab() -> None:
    """Render the Past Promos tab."""
    try:
        history, leads, dna, profiles = _load_past_data()
    except pc.PastCampaignsDataError as exc:
        theme.st_markdown(theme.banner_html(str(exc), "error"))
        return

    current = current_profile()
    rows = pc.build_rows(profiles, current)
    has_similarity = pc.similarity_available(rows)

    st.subheader("Past Promos")
    st.caption(
        "Completed campaigns only. Open a campaign to see how it ran and how "
        "close the model's prediction came."
    )
    if has_similarity:
        # Part 9: the score is relative to the current run, so it moves when
        # the run moves; say so, or the change looks like an error.
        run = st.session_state.get(RUN_RESULT_KEY)
        threshold = getattr(getattr(run, "promo_spec", None), "threshold_php", None)
        if run is None:
            # Round 3: before a run the score uses the New Promo form as it
            # is filled in now; say so rather than imply a run exists.
            st.caption(
                "Similarity Score compares each past promo with the New Promo "
                "form as filled in now. After Run Analysis it compares with the run."
            )
        else:
            at = f" at ₱{float(threshold):,.0f}" if threshold is not None else ""
            st.caption(
                f"Similarity Score compares each past promo with your current run{at}, "
                "so it changes when you rescore in What-If or run a new promo."
            )

    product_opts, audience_opts = pc.filter_options(rows)
    sort_modes = list(pc.SORT_MODES) if has_similarity else [pc.SORT_NEWEST, pc.SORT_OLDEST]
    if st.session_state.get(SORT_KEY) not in sort_modes:
        st.session_state[SORT_KEY] = pc.SORT_NEWEST
    for key, opts in ((PRODUCT_FILTER_KEY, product_opts), (AUDIENCE_FILTER_KEY, audience_opts)):
        if st.session_state.get(key) not in opts:
            st.session_state[key] = pc.FILTER_ALL

    c1, c2, c3 = st.columns(3)
    with c1:
        sort_mode = st.selectbox("Sort By", sort_modes, key=SORT_KEY)
        if not has_similarity:
            st.caption("Most Similar needs a New Promo with product details.")
    with c2:
        product = st.selectbox("Product Type", product_opts, key=PRODUCT_FILTER_KEY)
    with c3:
        audience = st.selectbox("Target Audience", audience_opts, key=AUDIENCE_FILTER_KEY)

    signature = (sort_mode, product, audience)
    if st.session_state.get(_SIGNATURE_KEY) != signature:
        st.session_state[_SIGNATURE_KEY] = signature
        st.session_state[VISIBLE_KEY] = pc.INITIAL_VISIBLE

    ordered = pc.sort_campaigns(pc.filter_campaigns(rows, product, audience), sort_mode)
    if not ordered:
        theme.st_markdown(theme.banner_html("No past campaigns match these filters.", "info"))
        return

    visible = int(st.session_state.get(VISIBLE_KEY, pc.INITIAL_VISIBLE))
    shown, more = pc.page(ordered, visible)
    cards = _load_cards()

    for row in shown:
        detail = pc.campaign_detail(row, leads, dna)
        prediction = pc.prediction_comparison(
            row.profile.promo_id, cards, leads, OUTPUTS_DIR / "leads"
        )
        with st.expander(_row_label(row, has_similarity)):
            theme.st_markdown(_campaign_body_html(detail, prediction, has_similarity))

    st.caption(f"Showing {len(shown)} of {len(ordered)} campaigns.")
    if more and st.button("View More", key="past_view_more"):
        st.session_state[VISIBLE_KEY] = pc.next_visible(visible)
        st.rerun()
