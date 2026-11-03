"""Streamlit entry point for the Promo Audience Navigator (Part 5 webapp).

This file is the declarative composition layer: it sets the wide desktop
layout, injects the single stylesheet once, renders the BPI-website chrome (top
utility bar, main nav bar with a red text brand, a breadcrumb row, and a hero
with a red-gradient KPI panel), then the Title Case tabs (New Promo, Results,
What-If, Ask Assistant, Past Promos), and routes to each tab body. All real
logic lives in ``src/webapp_core`` (model reload, eligibility, promo-id, run
orchestration) and ``app/theme`` (styling) -- this module only wires them to
Streamlit widgets and session state. Functionality is unchanged from the prior
version; only the presentation was restyled.

RUN flow (Requirement 3): build a :class:`PromoSpec` from the form, reload the
fitted Part 1 model with :func:`webapp_core.model_io.load_model` (catching the
missing-artifact error and showing the run-pipeline message, Requirement 1.4),
load the ``data/`` bundle, call :func:`webapp_core.run_promo.run_promo`, and
stash the :class:`RunResult` in ``st.session_state`` so Results / What-If /
Download Leads operate on it (Requirement 3.5). The unseen-mechanic soft warning
``score_promo`` emits is captured and surfaced as an ``st.warning``
(Requirement 3.3/7.4); an empty eligible audience shows the empty-audience
message (Requirement 3.4). The app never retrains -- it only reloads the model.
"""

from __future__ import annotations

import dataclasses
import html
import json
import math
import warnings
from pathlib import Path

import pandas as pd
import streamlit as st

# Wide layout must be configured before any other Streamlit call.
st.set_page_config(
    page_title="Promo Audience Navigator",
    layout="wide",
)

import theme  # noqa: E402  (imported after set_page_config by design)

from part1_optin.config import Config as Part1Config  # noqa: E402
from webapp_core.model_io import load_model  # noqa: E402
from webapp_core.past_promos import (  # noqa: E402
    predicted_vs_actual,
    read_sendable_ids_by_cell,
)
from webapp_core.promo_id import next_promo_id  # noqa: E402
from webapp_core.run_promo import PromoSpec, run_promo  # noqa: E402

# --- project paths (resolved from this file so the app runs from any cwd) ---

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"

CUSTOMER_DNA_PATH = DATA_DIR / "customer_dna.csv"
ADB_MONTHLY_PATH = DATA_DIR / "adb_monthly.csv"
FEATURES_PART2_PATH = OUTPUTS_DIR / "features_part2.csv"

CARDS_JSON_PATH = OUTPUTS_DIR / "cards.json"
PROMO_LEADS_PATH = DATA_DIR / "promo_leads.csv"

# Session-state keys.
RUN_RESULT_KEY = "run_result"
SEEN_PROMO_IDS_KEY = "seen_promo_ids"

# Sensible defaults for the New Promo form selectors.
MECHANIC_OPTIONS = ["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE", "OTHER"]
PRODUCT_TYPE_OPTIONS = ["Savings", "Time Deposit", "Investment", "Credit Card"]
# These must match Part 4's channel labels exactly (part4_cards.config
# CHANNEL_PRIORITY). Any other spelling, e.g. lowercase "email", makes every
# lead "no reachable channel", so nothing is sendable and every segment shows
# 0 expected joiners.
CHANNEL_OPTIONS = ["In-app", "Email", "SMS"]

RUN_PIPELINE_MESSAGE = (
    "The fitted Part 1 model could not be found. Run "
    "`python src/run_pipeline.py` (with `PYTHONPATH=src`) to regenerate the "
    "model and the on-disk artifacts the app reads, then try again."
)


@st.cache_data(show_spinner=False)
def _load_eligible_segment_options() -> list[str]:
    """The distinct Customer_DNA segments offered as eligible-segment choices."""
    try:
        dna = pd.read_csv(CUSTOMER_DNA_PATH, usecols=["segment"])
        return sorted(dna["segment"].dropna().unique().tolist())
    except (FileNotFoundError, ValueError):
        return ["Affluent-Gold", "Affluent-Preferred", "Mass", "Mid-Market"]


def _load_data_bundle() -> dict[str, pd.DataFrame]:
    """Load the ``data/`` frames bundle ``run_promo`` consumes."""
    return {
        "customer_dna": pd.read_csv(CUSTOMER_DNA_PATH),
        "adb_monthly": pd.read_csv(ADB_MONTHLY_PATH),
        "features": pd.read_csv(FEATURES_PART2_PATH),
    }


def _metric_from_run() -> tuple[str, str]:
    """The headline number + caption for the hero KPI panel."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        return "--", "Expected Joiners"
    total = sum(float(card.get("expected_joiners", 0.0)) for card in result.cards)
    return f"{total:,.0f}", "Expected Joiners"


FLASH_KEY = "flash_messages"


def _show_messages(messages: list[tuple[str, str]]) -> None:
    """Display (level, text) messages as Streamlit alerts."""
    for level, text in messages:
        {"error": st.error, "warning": st.warning, "success": st.success}.get(
            level, st.info
        )(text)


def _execute_run(spec: PromoSpec) -> list[tuple[str, str]]:
    """Reload the model, run the promo, and stash the result in session state.

    Returns the (level, text) messages to show, so the caller decides whether
    to show them now (What-If) or after a page refresh (New Promo).
    """
    try:
        model = load_model(OUTPUTS_DIR)
        data = _load_data_bundle()
    except FileNotFoundError:
        return [("error", RUN_PIPELINE_MESSAGE)]

    config = Part1Config()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = run_promo(spec, model=model, config=config, data=data)

    messages: list[tuple[str, str]] = [
        ("warning", str(warning.message)) for warning in captured
    ]

    st.session_state[RUN_RESULT_KEY] = result
    seen = st.session_state.setdefault(SEEN_PROMO_IDS_KEY, [])
    if spec.promo_id not in seen:
        seen.append(spec.promo_id)

    if not result.cards:
        messages.append((
            "warning",
            "No clients satisfy the eligibility filters, so no audience was "
            "produced. Loosen the minimum ADB or broaden the eligible "
            "segments, then run again.",
        ))
    else:
        total = sum(
            float(card.get("expected_joiners", 0.0)) for card in result.cards
        )
        messages.append((
            "success",
            f"Ran {spec.promo_id}: {len(result.scored):,} eligible clients "
            f"across {len(result.cards)} segments, "
            f"about {total:,.0f} expected joiners. See the Results tab.",
        ))
    return messages


def _render_new_promo_tab() -> None:
    """Render the New Promo form and handle Run (Requirement 3.1-3.5)."""
    segment_options = _load_eligible_segment_options()

    seen_ids = st.session_state.get(SEEN_PROMO_IDS_KEY, [])
    auto_promo_id = next_promo_id(seen_ids)

    st.subheader("Design A Promo")

    # Messages from the last Run survive the page refresh below.
    _show_messages(st.session_state.pop(FLASH_KEY, []))

    with st.form("new_promo_form"):
        st.text_input("Promo ID (Auto-Generated)", value=auto_promo_id, disabled=True)

        col_left, col_right = st.columns(2)
        with col_left:
            product_type = st.selectbox("Product Type", PRODUCT_TYPE_OPTIONS, index=0)
            mechanic = st.selectbox("Mechanic", MECHANIC_OPTIONS, index=0)
            threshold_php = st.number_input(
                "Threshold (PHP)",
                min_value=0.0,
                value=100_000.0,
                step=10_000.0,
                format="%.2f",
            )
            min_adb = st.number_input(
                "Minimum ADB (PHP)",
                min_value=0.0,
                value=0.0,
                step=10_000.0,
                format="%.2f",
            )
        with col_right:
            reward = st.text_input("Reward", value="Bonus interest")
            eligible_segments = st.multiselect(
                "Eligible Segments",
                options=segment_options,
                default=segment_options,
                help="Customer_DNA segments. Clients outside these are excluded.",
            )
            channels = st.multiselect(
                "Channels",
                options=CHANNEL_OPTIONS,
                default=CHANNEL_OPTIONS,
            )

        submitted = st.form_submit_button("Run Analysis")

    if submitted:
        spec = PromoSpec(
            promo_id=auto_promo_id,
            product_type=product_type,
            mechanic=mechanic,
            threshold_php=float(threshold_php),
            reward=reward,
            eligible_segments=list(eligible_segments),
            min_adb=float(min_adb),
            channels=list(channels),
        )
        with st.spinner("Scoring and segmenting the audience..."):
            st.session_state[FLASH_KEY] = _execute_run(spec)
        # Refresh once so the hero KPI at the top shows the new run's number.
        st.rerun()


# The four Part 3 Segment_Labels laid out as the 2x2 Results grid:
# rows = score high/low, columns = capacity low/high ->
# (high, low)=Willing but Stretched, (high, high)=Ready Toppers,
# (low, low)=Not Now, (low, high)=Untapped Wealth.
RESULTS_GRID = [
    ("score high", [("capacity low", "Willing but Stretched"),
                    ("capacity high", "Ready Toppers")]),
    ("score low", [("capacity low", "Not Now"),
                   ("capacity high", "Untapped Wealth")]),
]

# Ready Toppers is the emphasized (red-gradient) tile; the rest are white.
EMPHASIS_SEGMENT = "Ready Toppers"


def _cards_by_segment() -> dict[str, dict]:
    """Index the current run's cards by their Segment_Label."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None:
        return {}
    return {str(card.get("segment")): card for card in result.cards}


def _tile_body_html(card: dict | None, *, emphasis: bool) -> str:
    """The body HTML for one 2x2 grid tile (client count + expected joiners).

    ``card`` is ``None`` for a segment with no Cell (no eligible clients in that
    quadrant), shown as a graceful 0. On the emphasized (red) tile the accent
    text is white; on white tiles it is red -- both handled by CSS via the tile
    kind, so only numeric values are interpolated here.
    """
    if card is None:
        n_clients = 0
        joiners = 0.0
    else:
        n_clients = int(card.get("n_clients", 0) or 0)
        joiners = float(card.get("expected_joiners", 0.0) or 0.0)
    return (
        '<div class="pan-tile-k">Clients</div>'
        f'<div class="pan-tile-v">{n_clients:,}</div>'
        '<div class="pan-tile-k" style="margin-top:10px;">Expected Joiners</div>'
        f'<div class="pan-tile-accent">{joiners:,.1f}</div>'
    )


def _decision_card_html(card: dict) -> str:
    """Build the (escaped) body HTML for one segment's decision card."""
    action = html.escape(str(card.get("action", "--")))
    channel = html.escape(str(card.get("dominant_channel", "--")))
    angle = html.escape(str(card.get("message_angle", "--")))

    joiners = float(card.get("expected_joiners", 0.0) or 0.0)
    low = float(card.get("joiners_90_low", 0.0) or 0.0)
    high = float(card.get("joiners_90_high", 0.0) or 0.0)
    exp_value = float(card.get("expected_value", 0.0) or 0.0)

    drivers = card.get("top_drivers") or []
    drivers_html = ", ".join(html.escape(str(d)) for d in drivers) or "--"

    excluded = card.get("excluded_by_reason") or {}
    if excluded:
        exclusions_html = ", ".join(
            f"{html.escape(str(reason))}: {int(count):,}"
            for reason, count in excluded.items()
        )
    else:
        exclusions_html = "none"

    # Stat chips for the headline numbers.
    chips = (
        theme.chip(f"Joiners {joiners:,.1f}")
        + theme.chip(f"90% {low:,.1f}-{high:,.1f}")
        + theme.chip(f"Value {exp_value:,.0f}")
    )

    rows = [
        ("Action", action),
        ("Dominant Channel", channel),
        ("Message Angle", angle),
        ("Top Drivers", drivers_html),
        ("Exclusions By Reason", exclusions_html),
    ]
    items = "".join(
        f'<div style="margin-bottom:8px;">'
        f'<span style="color:var(--pan-gray);font-size:0.78rem;'
        f'letter-spacing:0.2px;">{label}</span><br/>'
        f'<span style="font-weight:600;color:var(--pan-charcoal);">{value}</span>'
        "</div>"
        for label, value in rows
    )
    return f'<div style="margin-bottom:12px;">{chips}</div>{items}'


def _render_results_tab() -> None:
    """Render the Results tab: 2x2 grid, decision cards, Download Leads."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        st.info(
            "Run a promo first. Open the New Promo tab, design a promo, and "
            "press Run Analysis. The results grid, decision cards, and lead "
            "downloads appear here once a run exists."
        )
        return

    cards_by_segment = _cards_by_segment()

    # --- 2x2 Results grid (four rounded tiles) ---
    st.subheader("Results Grid")
    for _row_label, cols in RESULTS_GRID:
        grid_cols = st.columns(2)
        for grid_col, (_col_label, segment_label) in zip(grid_cols, cols):
            with grid_col:
                card = cards_by_segment.get(segment_label)
                emphasis = segment_label == EMPHASIS_SEGMENT
                theme.tile(
                    segment_label,
                    _tile_body_html(card, emphasis=emphasis),
                    emphasis=emphasis,
                )

    # --- decision cards, two per row on wide screens ---
    st.subheader("Decision Cards")
    ordered_segments = [
        segment_label
        for _row, cols in RESULTS_GRID
        for _col, segment_label in cols
        if segment_label in cards_by_segment
    ]
    for i in range(0, len(ordered_segments), 2):
        pair = ordered_segments[i : i + 2]
        card_cols = st.columns(2)
        for card_col, segment_label in zip(card_cols, pair):
            with card_col:
                theme.card(
                    segment_label, _decision_card_html(cards_by_segment[segment_label])
                )

    # --- Download Leads: one per-segment Sendable_Leads CSV ---
    st.subheader("Download Leads")
    sendable = result.sendable_by_segment or {}
    if not sendable:
        st.caption("No sendable leads were produced for this run.")
    else:
        dl_cols = st.columns(2)
        for i, (segment_label, leads_df) in enumerate(sendable.items()):
            csv_bytes = leads_df.to_csv(index=False).encode("utf-8")
            with dl_cols[i % 2]:
                st.download_button(
                    label=f"Download {segment_label} Leads ({len(leads_df):,})",
                    data=csv_bytes,
                    file_name=(
                        f"{result.promo_spec.promo_id}_"
                        f"{segment_label.replace(' ', '_').lower()}_leads.csv"
                    ),
                    mime="text/csv",
                    key=f"download_leads_{segment_label}",
                )


_WHATIF_RANGE_FLOOR = 200_000.0


def _whatif_slider_bounds(current: float) -> tuple[float, float, float]:
    """Return ``(min_value, max_value, step)`` for the What-If slider."""
    max_value = max(current * 4.0, _WHATIF_RANGE_FLOOR)
    step = max(round(max_value / 100.0), 1.0)
    return 0.0, float(max_value), float(step)


def _render_whatif_tab() -> None:
    """Render the What-If threshold slider and rescore on change (Req 6.1-6.3)."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None:
        st.info(
            "Run a promo first. Open the New Promo tab, design a promo, and "
            "press Run Analysis. The What-If threshold slider appears here "
            "once a run exists."
        )
        return

    current = float(result.promo_spec.threshold_php)
    min_value, max_value, step = _whatif_slider_bounds(current)

    st.subheader("What-If: Vary The Threshold")
    st.caption(
        "Drag the threshold to rescore the current eligible audience with the "
        "already-fitted model. No model is retrained; only the threshold "
        "changes, so the audience is rescored, resegmented, and recarded."
    )

    new_threshold = st.slider(
        "Threshold (PHP)",
        min_value=min_value,
        max_value=max_value,
        value=min(max(current, min_value), max_value),
        step=step,
        format="%.0f",
    )

    if abs(float(new_threshold) - current) >= (step / 2.0):
        new_spec = dataclasses.replace(
            result.promo_spec, threshold_php=float(new_threshold)
        )
        _show_messages(_execute_run(new_spec))
        result = st.session_state.get(RUN_RESULT_KEY)

    number, caption = _metric_from_run()
    theme.metric_panel(number, caption)
    if result is not None and result.cards:
        st.caption(
            f"Threshold ₱{float(result.promo_spec.threshold_php):,.0f}: "
            f"{len(result.scored):,} eligible clients across "
            f"{len(result.cards)} segments."
        )


def _render_ask_assistant_tab() -> None:
    """Render the Ask Assistant placeholder panel (Requirement 6.4)."""
    theme.card(
        "Ask Assistant",
        '<p style="margin:0;">The conversational assistant is coming in the '
        "next spec. For now this panel is a placeholder and performs no "
        "lookup or model call.</p>",
    )


def _fmt_rate(value: float) -> str:
    """Format a join rate as a percentage (39.6%), or "No Leads" when NA."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "No Leads"
    return f"{float(value) * 100:.1f}%"


# Segments always appear in this order, best to worst.
SEGMENT_ORDER = ["Ready Toppers", "Untapped Wealth", "Willing but Stretched", "Not Now"]


def _segment_sort_key(row: dict) -> tuple[int, str]:
    segment = str(row.get("segment"))
    rank = SEGMENT_ORDER.index(segment) if segment in SEGMENT_ORDER else len(SEGMENT_ORDER)
    return rank, segment


def _past_promo_card_html(rows: list[dict]) -> str:
    """Build the (escaped) body HTML for one Past_Promo predicted-vs-actual card.

    Values are centered; the Segment column stays left-aligned so the names
    read cleanly. Rates are shown as percentages with one decimal.
    """
    th = (
        "padding:10px 12px;font-size:0.8rem;font-weight:600;"
        "color:#6B7280;border-bottom:1.5px solid #E6E6E6;"
    )
    td = "padding:10px 12px;border-bottom:1px solid #F0F0F0;"
    header = (
        "<tr>"
        f'<th style="{th}text-align:left;">Segment</th>'
        f'<th style="{th}text-align:center;">Predicted</th>'
        f'<th style="{th}text-align:center;">Actual</th>'
        "</tr>"
    )
    body_rows = []
    for row in sorted(rows, key=_segment_sort_key):
        segment = html.escape(str(row.get("segment", "N/A")))
        predicted = _fmt_rate(row.get("predicted"))
        actual = _fmt_rate(row.get("actual"))
        body_rows.append(
            "<tr>"
            f'<td style="{td}text-align:left;font-weight:600;">{segment}</td>'
            f'<td style="{td}text-align:center;color:#2B2B2B;">{predicted}</td>'
            f'<td style="{td}text-align:center;color:#AE1319;font-weight:700;">'
            f"{actual}</td></tr>"
        )
    return (
        '<table style="border-collapse:collapse;width:100%;font-size:0.95rem;'
        'border:none;">'
        f"{header}{''.join(body_rows)}</table>"
    )


def _render_past_promos_tab() -> None:
    """Render the Past Promos tab: predicted vs actual join rate per promo."""
    try:
        with open(CARDS_JSON_PATH, encoding="utf-8") as fh:
            cards = json.load(fh)
    except FileNotFoundError:
        st.info(RUN_PIPELINE_MESSAGE)
        return

    if not cards:
        st.info(
            "No past promos were found in the Cards_File. Run "
            "`python src/run_pipeline.py` to regenerate the promo cards."
        )
        return

    try:
        promo_leads = pd.read_csv(PROMO_LEADS_PATH)
    except FileNotFoundError:
        st.info(RUN_PIPELINE_MESSAGE)
        return

    sendable_ids_by_cell = read_sendable_ids_by_cell(
        cards, leads_dir=OUTPUTS_DIR / "leads"
    )
    rows = predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell)

    rows_by_promo: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_promo.setdefault(str(row.get("promo_id")), []).append(row)

    st.subheader("Past Promos: Predicted Vs Actual Join Rate")
    st.caption(
        "For each past promo, the model's predicted join rate next to the "
        "actual join rate that happened, per segment. No Leads means the "
        "segment had no sendable leads."
    )
    promo_ids = sorted(rows_by_promo)
    for i in range(0, len(promo_ids), 2):
        pair = promo_ids[i : i + 2]
        card_cols = st.columns(2)
        for card_col, promo_id in zip(card_cols, pair):
            with card_col:
                theme.card(
                    heading=promo_id,
                    body_html=_past_promo_card_html(rows_by_promo[promo_id]),
                )


def main() -> None:
    """Compose the BPI-web app shell and route to the tabs."""
    theme.inject_css()

    # --- page chrome: utility bar, nav, breadcrumb ---
    theme.utility_bar()
    theme.nav_bar(active="New Promo")
    theme.breadcrumb("Home", "Results")

    # --- hero: title + subtitle on the left, red-gradient KPI panel right ---
    number, caption = _metric_from_run()
    hero_left, hero_right = st.columns([1.4, 1])
    with hero_left:
        st.markdown(
            theme.hero_text_html(
                "Promo Audience Navigator",
                "Design, score and segment a promo audience, then act on the "
                "recommendation.",
            ),
            unsafe_allow_html=True,
        )
    with hero_right:
        st.markdown(
            theme.hero_kpi_html(number, caption, foot="Across all segments"),
            unsafe_allow_html=True,
        )

    st.write("")

    (
        new_promo_tab,
        results_tab,
        whatif_tab,
        ask_assistant_tab,
        past_promos_tab,
    ) = st.tabs(
        ["New Promo", "Results", "What-If", "Ask Assistant", "Past Promos"]
    )

    with new_promo_tab:
        _render_new_promo_tab()
    with results_tab:
        _render_results_tab()
    with whatif_tab:
        _render_whatif_tab()
    with ask_assistant_tab:
        _render_ask_assistant_tab()
    with past_promos_tab:
        _render_past_promos_tab()


main()