"""Streamlit entry point for the Promo Audience Navigator (Part 5 webapp).

This file is the declarative composition layer described in the design: it sets
the wide desktop layout, injects the Theme once, renders the red header bar, the
uppercase tabs (NEW PROMO, RESULTS, WHAT-IF, ASK ASSISTANT, PAST PROMOS), the
balance-style metric panel, and the red action band, then routes to each tab
body. All real logic
lives in ``src/webapp_core`` (model reload, eligibility, promo-id, run
orchestration) and ``app/theme`` (styling) -- this module only wires them to
Streamlit widgets and session state.

Only the NEW PROMO tab is implemented here (task 6.1). The RESULTS, WHAT-IF /
ASK ASSISTANT, and PAST PROMOS tab bodies are tasks 6.2-6.4 and are left as
clearly-marked placeholders so the app runs end to end.

RUN flow (Requirement 3): build a :class:`PromoSpec` from the form, reload the
fitted Part 1 model with :func:`webapp_core.model_io.load_model` (catching the
missing-artifact error and showing the run-pipeline message, Requirement 1.4),
load the ``data/`` bundle, call :func:`webapp_core.run_promo.run_promo`, and
stash the :class:`RunResult` in ``st.session_state`` so RESULTS / WHAT-IF /
DOWNLOAD LEADS operate on it (Requirement 3.5). The unseen-mechanic soft warning
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

# Wide layout must be configured before any other Streamlit call (per design).
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

# The data bundle run_promo needs, loaded from the exact paths the run_promo
# tests read (tests/test_part5_run_promo.py): customer_dna / adb_monthly from
# data/, features from outputs/features_part2.csv.
CUSTOMER_DNA_PATH = DATA_DIR / "customer_dna.csv"
ADB_MONTHLY_PATH = DATA_DIR / "adb_monthly.csv"
FEATURES_PART2_PATH = OUTPUTS_DIR / "features_part2.csv"

# The on-disk Cards_File and historical outcomes the PAST PROMOS tab reads
# (Requirement 5): the Part 4 cards and the raw promo lead outcomes.
CARDS_JSON_PATH = OUTPUTS_DIR / "cards.json"
PROMO_LEADS_PATH = DATA_DIR / "promo_leads.csv"

# Session-state keys.
RUN_RESULT_KEY = "run_result"
SEEN_PROMO_IDS_KEY = "seen_promo_ids"

# Sensible defaults for the NEW PROMO form selectors.
MECHANIC_OPTIONS = ["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE", "OTHER"]
PRODUCT_TYPE_OPTIONS = ["Savings", "Time Deposit", "Investment", "Credit Card"]
CHANNEL_OPTIONS = ["email", "sms", "app_push", "branch", "call"]

# The run-pipeline guidance shown when a required model artifact is missing
# (Requirement 1.4).
RUN_PIPELINE_MESSAGE = (
    "The fitted Part 1 model could not be found. Run "
    "`python src/run_pipeline.py` (with `PYTHONPATH=src`) to regenerate the "
    "model and the on-disk artifacts the app reads, then try again."
)


@st.cache_data(show_spinner=False)
def _load_eligible_segment_options() -> list[str]:
    """The distinct Customer_DNA segments offered as eligible-segment choices.

    Read once from ``data/customer_dna.csv`` (cached) so the multiselect lists
    the real segments (e.g. "Affluent-Gold"). Falls back to a small default
    list if the file is absent so the form still renders.
    """
    try:
        dna = pd.read_csv(CUSTOMER_DNA_PATH, usecols=["segment"])
        return sorted(dna["segment"].dropna().unique().tolist())
    except (FileNotFoundError, ValueError):
        return ["Affluent-Gold", "Affluent-Preferred", "Mass", "Mid-Market"]


def _load_data_bundle() -> dict[str, pd.DataFrame]:
    """Load the ``data/`` frames bundle ``run_promo`` consumes.

    Keys match the run_promo contract exactly (see
    ``src/webapp_core/run_promo.py``): ``customer_dna`` and ``adb_monthly`` come
    from ``data/``, ``features`` from ``outputs/features_part2.csv`` -- the same
    three paths ``tests/test_part5_run_promo.py`` reads.
    """
    return {
        "customer_dna": pd.read_csv(CUSTOMER_DNA_PATH),
        "adb_monthly": pd.read_csv(ADB_MONTHLY_PATH),
        "features": pd.read_csv(FEATURES_PART2_PATH),
    }


def _metric_from_run() -> tuple[str, str]:
    """The headline number + caption for the metric panel (Requirement 2.4).

    Before any run the number is a dash placeholder. After a run it is the total
    expected joiners summed over the current :class:`RunResult`'s cards, styled
    like the account balance in the reference image.
    """
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        return "--", "Expected Joiners"
    total = sum(float(card.get("expected_joiners", 0.0)) for card in result.cards)
    return f"{total:,.0f}", "Expected Joiners"


def _execute_run(spec: PromoSpec) -> None:
    """Reload the model, run the promo, and stash the result in session state.

    Implements the RUN half of Requirement 3. Reloads the fitted model
    (Requirement 1.3) inside a try/except for the missing-artifact error
    (Requirement 1.4), loads the data bundle, calls ``run_promo`` while
    capturing the unseen-mechanic warning (Requirement 3.3/7.4), stores the
    :class:`RunResult` (Requirement 3.5), and surfaces the empty-audience
    message (Requirement 3.4). The model is only reloaded -- never retrained.
    """
    # 1. Reload the fitted model; a missing artifact is a handled error, not an
    #    unhandled exception (Requirement 1.4).
    try:
        model = load_model(OUTPUTS_DIR)
    except FileNotFoundError:
        st.error(RUN_PIPELINE_MESSAGE)
        return

    # 2. Load the data bundle run_promo needs.
    try:
        data = _load_data_bundle()
    except FileNotFoundError:
        st.error(RUN_PIPELINE_MESSAGE)
        return

    config = Part1Config()

    # 3. Run the promo, capturing any soft warning score_promo emits (the
    #    unseen-mechanic warning) so it can be surfaced via st.warning.
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = run_promo(spec, model=model, config=config, data=data)

    for warning in captured:
        st.warning(str(warning.message))

    # 4. Persist the result and remember this promo id for id auto-generation.
    st.session_state[RUN_RESULT_KEY] = result
    seen = st.session_state.setdefault(SEEN_PROMO_IDS_KEY, [])
    if spec.promo_id not in seen:
        seen.append(spec.promo_id)

    # 5. Empty-audience message vs success confirmation (Requirement 3.4).
    if not result.cards:
        st.warning(
            "No clients satisfy the eligibility filters, so no audience was "
            "produced. Loosen the minimum ADB or broaden the eligible "
            "segments, then run again."
        )
    else:
        total = sum(
            float(card.get("expected_joiners", 0.0)) for card in result.cards
        )
        st.success(
            f"Ran {spec.promo_id}: {len(result.scored):,} eligible clients "
            f"across {len(result.cards)} segments, "
            f"~{total:,.0f} expected joiners. See the RESULTS tab."
        )


def _render_new_promo_tab() -> None:
    """Render the NEW PROMO form and handle RUN (Requirement 3.1-3.5)."""
    segment_options = _load_eligible_segment_options()

    # The promo id is auto-generated as NEW-001 from the ids seen this session
    # (Requirement 3.1); shown read-only in the form.
    seen_ids = st.session_state.get(SEEN_PROMO_IDS_KEY, [])
    auto_promo_id = next_promo_id(seen_ids)

    st.subheader("Design a promo")

    with st.form("new_promo_form"):
        st.text_input("Promo ID (auto-generated)", value=auto_promo_id, disabled=True)

        col_left, col_right = st.columns(2)
        with col_left:
            product_type = st.selectbox("Product type", PRODUCT_TYPE_OPTIONS, index=0)
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
                "Eligible segments",
                options=segment_options,
                default=segment_options,
                help="Customer_DNA segments. Clients outside these are excluded.",
            )
            channels = st.multiselect(
                "Channels",
                options=CHANNEL_OPTIONS,
                default=["email", "sms"],
            )

        submitted = st.form_submit_button("RUN")

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
        _execute_run(spec)


# The four Part 3 Segment_Labels laid out as the 2x2 Results_Grid
# (design.md Req 4.1): rows = score high/low, columns = capacity low/high ->
# (high, low)=Willing but Stretched, (high, high)=Ready Toppers,
# (low, low)=Not Now, (low, high)=Untapped Wealth.
RESULTS_GRID = [
    ("score high", [("capacity low", "Willing but Stretched"),
                    ("capacity high", "Ready Toppers")]),
    ("score low", [("capacity low", "Not Now"),
                   ("capacity high", "Untapped Wealth")]),
]


def _cards_by_segment() -> dict[str, dict]:
    """Index the current run's cards by their Segment_Label.

    One card dict per segment (``build_cards`` emits one Cell per segment), so a
    plain label->card map is enough for both the grid and the decision cards.
    """
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None:
        return {}
    return {str(card.get("segment")): card for card in result.cards}


def _grid_cell_html(card: dict | None) -> str:
    """The small body HTML for one Results_Grid cell (client count + joiners).

    ``card`` is ``None`` for a segment with no Cell (no eligible clients in that
    quadrant), which shows a graceful 0 / empty count. All interpolated values
    are numeric-formatted, so no untrusted text reaches the HTML.
    """
    if card is None:
        n_clients = 0
        joiners = 0.0
    else:
        n_clients = int(card.get("n_clients", 0) or 0)
        joiners = float(card.get("expected_joiners", 0.0) or 0.0)
    return (
        f'<div style="font-size:0.85rem;color:#666;">Clients</div>'
        f'<div style="font-size:1.5rem;font-weight:800;">{n_clients:,}</div>'
        f'<div style="font-size:0.85rem;color:#666;margin-top:6px;">'
        f"Expected joiners</div>"
        f'<div style="font-size:1.25rem;font-weight:700;color:var(--pan-red);">'
        f"{joiners:,.1f}</div>"
    )


def _decision_card_html(card: dict) -> str:
    """Build the (escaped) body HTML for one segment's decision card.

    Shows the action, dominant channel, message angle, expected joiners with
    their 90% range, expected value, top drivers, and exclusions by reason
    (Requirement 4.2). ``theme.card`` trusts the body HTML, so every text value
    pulled from the card is escaped here; numbers are formatted, not escaped.
    """
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

    rows = [
        ("Action", action),
        ("Dominant channel", channel),
        ("Message angle", angle),
        (
            "Expected joiners",
            f"{joiners:,.1f} (90% range {low:,.1f} to {high:,.1f})",
        ),
        ("Expected value", f"{exp_value:,.2f}"),
        ("Top drivers", drivers_html),
        ("Exclusions by reason", exclusions_html),
    ]
    items = "".join(
        f'<div style="margin-bottom:4px;">'
        f'<span style="color:#666;font-size:0.8rem;text-transform:uppercase;'
        f'letter-spacing:1px;">{label}</span><br/>'
        f'<span style="font-weight:600;">{value}</span></div>'
        for label, value in rows
    )
    return items


def _render_results_tab() -> None:
    """Render the RESULTS tab: Results_Grid, decision cards, DOWNLOAD LEADS.

    Implements Requirement 4. When no :class:`RunResult` exists (or it produced
    no cards) the run-first prompt is shown and the tab returns early
    (Requirement 4.4). Otherwise it renders the 2x2 Results_Grid
    (Requirement 4.1), one decision card per segment (Requirement 4.2), and a
    per-segment Sendable_Leads CSV download button (Requirement 4.3).

    Note: the DOWNLOAD LEADS button in the red action band (``theme.action_band``)
    is decorative; the functional per-segment download buttons live here in the
    RESULTS tab body, matching the design.
    """
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        st.info(
            "Run a promo first. Open the NEW PROMO tab, design a promo, and "
            "press RUN -- the Results_Grid, decision cards, and lead downloads "
            "appear here once a run exists."
        )
        return

    cards_by_segment = _cards_by_segment()

    # --- 2x2 Results_Grid (Requirement 4.1) ---
    st.subheader("Results grid")
    for _row_label, cols in RESULTS_GRID:
        grid_cols = st.columns(2)
        for grid_col, (_col_label, segment_label) in zip(grid_cols, cols):
            with grid_col:
                card = cards_by_segment.get(segment_label)
                theme.card(segment_label, _grid_cell_html(card))

    # --- decision cards, one per segment present (Requirement 4.2) ---
    st.subheader("Decision cards")
    # Render in the fixed Results_Grid order so the cards track the grid.
    ordered_segments = [
        segment_label
        for _row, cols in RESULTS_GRID
        for _col, segment_label in cols
        if segment_label in cards_by_segment
    ]
    for segment_label in ordered_segments:
        card = cards_by_segment[segment_label]
        theme.card(segment_label, _decision_card_html(card))

    # --- DOWNLOAD LEADS: one per-segment Sendable_Leads CSV (Requirement 4.3) ---
    st.subheader("Download leads")
    sendable = result.sendable_by_segment or {}
    if not sendable:
        st.caption("No sendable leads were produced for this run.")
    else:
        for segment_label, leads_df in sendable.items():
            csv_bytes = leads_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"Download {segment_label} leads ({len(leads_df):,})",
                data=csv_bytes,
                file_name=(
                    f"{result.promo_spec.promo_id}_"
                    f"{segment_label.replace(' ', '_').lower()}_leads.csv"
                ),
                mime="text/csv",
                key=f"download_leads_{segment_label}",
            )


# WHAT-IF slider range. The slider spans from 0 up to four times the current
# run's threshold (with a non-degenerate floor so a tiny or zero current
# threshold still yields a usable range), and steps in ~1% increments of that
# span rounded to whole PHP. This keeps the current value centred-low in a
# range wide enough to explore both relaxing and tightening the threshold,
# while never producing a zero-width or absurdly fine slider (Requirement 6.1).
_WHATIF_RANGE_FLOOR = 200_000.0


def _whatif_slider_bounds(current: float) -> tuple[float, float, float]:
    """Return ``(min_value, max_value, step)`` for the WHAT-IF slider.

    ``min_value`` is always 0. ``max_value`` is four times the current
    threshold, floored at :data:`_WHATIF_RANGE_FLOOR` so a zero/near-zero
    current threshold still gives a meaningful span. ``step`` is 1% of the span
    rounded to a whole PHP (at least 1.0) so the slider is responsive without
    jittering on sub-peso moves.
    """
    max_value = max(current * 4.0, _WHATIF_RANGE_FLOOR)
    step = max(round(max_value / 100.0), 1.0)
    return 0.0, float(max_value), float(step)


def _render_whatif_tab() -> None:
    """Render the WHAT-IF threshold slider and rescore on change (Req 6.1-6.3).

    When no :class:`RunResult` exists the run-first prompt is shown and the tab
    returns early (Requirement 6.3). Otherwise a threshold slider initialized to
    the current run's ``threshold_php`` is shown (Requirement 6.1); when its
    value differs from the current run's threshold the promo is re-run with only
    ``threshold_php`` replaced -- reloading (never retraining) the model,
    rescoring, reassigning segments, and rebuilding cards -- and the updated
    headline is shown (Requirement 6.2).
    """
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None:
        st.info(
            "Run a promo first. Open the NEW PROMO tab, design a promo, and "
            "press RUN -- the WHAT-IF threshold slider appears here once a run "
            "exists."
        )
        return

    current = float(result.promo_spec.threshold_php)
    min_value, max_value, step = _whatif_slider_bounds(current)

    st.subheader("What-if: vary the threshold")
    st.caption(
        "Drag the threshold to rescore the current eligible audience with the "
        "already-fitted model. No model is retrained -- only threshold_php "
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

    # Re-run only when the slider actually moved off the current run's
    # threshold, so a plain rerun (e.g. tab switch) does not loop (Req 6.2).
    if abs(float(new_threshold) - current) >= (step / 2.0):
        new_spec = dataclasses.replace(
            result.promo_spec, threshold_php=float(new_threshold)
        )
        _execute_run(new_spec)
        result = st.session_state.get(RUN_RESULT_KEY)

    # Show the updated headline so the threshold's effect is visible.
    number, caption = _metric_from_run()
    theme.metric_panel(number, caption)
    if result is not None and result.cards:
        st.caption(
            f"Threshold {float(result.promo_spec.threshold_php):,.0f} PHP -- "
            f"{len(result.scored):,} eligible clients across "
            f"{len(result.cards)} segments."
        )


def _render_ask_assistant_tab() -> None:
    """Render the ASK ASSISTANT placeholder panel (Requirement 6.4).

    A static panel reading that the assistant is coming in the next spec. It
    makes no LLM call and no network call -- it is purely informational.
    """
    theme.card(
        "Ask Assistant",
        '<p style="margin:0;">The conversational assistant is coming in the '
        "next spec. For now this panel is a placeholder and performs no "
        "lookup or model call.</p>",
    )


def _fmt_rate(value: float) -> str:
    """Format a join rate for display, or "N/A" when it is NA.

    A rate is NA (``math.isnan``) when the cell has no sendable leads to divide
    or compare across (Requirement 5.4); otherwise it is a probability in
    ``[0, 1]`` shown to three decimals.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{float(value):.3f}"


def _past_promo_card_html(rows: list[dict]) -> str:
    """Build the (escaped) body HTML for one Past_Promo's predicted-vs-actual card.

    ``rows`` are the :func:`predicted_vs_actual` Row dicts for a single
    ``promo_id`` (one per segment). Renders a small table showing, per segment,
    the Predicted_Join_Rate next to the Actual_Join_Rate, with NA cells shown as
    "N/A" (Requirements 5.2, 5.4). ``theme.card`` trusts the body HTML, so the
    segment label is escaped; the rates are formatted numbers.
    """
    header = (
        '<tr style="text-align:left;color:#666;font-size:0.8rem;'
        'text-transform:uppercase;letter-spacing:1px;">'
        "<th>Segment</th><th>Predicted</th><th>Actual</th></tr>"
    )
    body_rows = []
    for row in sorted(rows, key=lambda r: str(r.get("segment"))):
        segment = html.escape(str(row.get("segment", "--")))
        predicted = _fmt_rate(row.get("predicted"))
        actual = _fmt_rate(row.get("actual"))
        body_rows.append(
            f'<tr style="border-top:1px solid #eee;">'
            f'<td style="padding:4px 12px 4px 0;font-weight:600;">{segment}</td>'
            f'<td style="padding:4px 12px 4px 0;">{predicted}</td>'
            f'<td style="padding:4px 0;color:var(--pan-red);font-weight:600;">'
            f"{actual}</td></tr>"
        )
    return (
        '<table style="border-collapse:collapse;width:100%;font-size:0.95rem;">'
        f"{header}{''.join(body_rows)}</table>"
    )


def _render_past_promos_tab() -> None:
    """Render the PAST PROMOS tab: predicted vs actual join rate per promo.

    Implements Requirement 5. Reads the on-disk Cards_File
    (``outputs/cards.json``); when it is absent the run-pipeline message is
    shown and the tab returns -- not an unhandled exception (Requirement 5.3).
    Otherwise it loads the historical outcomes, computes each Past_Promo cell's
    Predicted_Join_Rate and Actual_Join_Rate via
    :func:`webapp_core.past_promos.predicted_vs_actual`, groups the rows by
    ``promo_id`` (Requirement 5.1), and renders one card per promo in sorted id
    order showing both rates per segment, with NA cells shown as "N/A"
    (Requirements 5.2, 5.4).
    """
    # 1. Read the Cards_File; a missing file is a handled error (Requirement 5.3).
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

    # 2. Load the historical outcomes and compute predicted vs actual per cell.
    try:
        promo_leads = pd.read_csv(PROMO_LEADS_PATH)
    except FileNotFoundError:
        st.info(RUN_PIPELINE_MESSAGE)
        return

    sendable_ids_by_cell = read_sendable_ids_by_cell(
        cards, leads_dir=OUTPUTS_DIR / "leads"
    )
    rows = predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell)

    # 3. Group rows by promo_id and render one card per promo (Requirement 5.1).
    rows_by_promo: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_promo.setdefault(str(row.get("promo_id")), []).append(row)

    st.subheader("Past promos: predicted vs actual join rate")
    st.caption(
        "For each past promo, the model's predicted join rate next to the "
        "actual join rate that happened, per segment. N/A means the cell had "
        "no sendable leads."
    )
    for promo_id in sorted(rows_by_promo):
        theme.card(
            heading=promo_id,
            body_html=_past_promo_card_html(rows_by_promo[promo_id]),
        )


def main() -> None:
    """Compose the app shell and route to the three tabs."""
    theme.inject_css()
    theme.header()

    number, caption = _metric_from_run()
    theme.metric_panel(number, caption)
    theme.action_band()

    (
        new_promo_tab,
        results_tab,
        whatif_tab,
        ask_assistant_tab,
        past_promos_tab,
    ) = st.tabs(
        ["NEW PROMO", "RESULTS", "WHAT-IF", "ASK ASSISTANT", "PAST PROMOS"]
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
