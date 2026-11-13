"""Streamlit entry point for the Promo Audience Manager (Part 5 webapp).

This file is the declarative composition layer: it sets the wide desktop
layout, injects the single stylesheet once, renders the page chrome (a
current-run context banner, then a hero with a red-gradient KPI panel; the
former utility bar and brand bar were removed in Part 8, Requirement 6), then the Title Case tabs (New Promo, Results,
What-If, Personas, Past Promos, Ask Assistant), and routes to each tab body. All real
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
import re
import warnings
from pathlib import Path

import pandas as pd
import streamlit as st

# Wide layout must be configured before any other Streamlit call.
st.set_page_config(
    page_title="Promo Audience Manager",
    layout="wide",
)

import theme  # noqa: E402  (imported after set_page_config by design)
import ui_effects  # noqa: E402  (Part 8 effects: job ring state)
import persona_page  # noqa: E402  (Persona_Page tab body; imported like theme)
import upload_panel  # noqa: E402  (Upload Campaign File tab body)
import assistant_page  # noqa: E402  (Ask Assistant tab body)
import past_promos_page  # noqa: E402  (Past Promos tab body)

from part1_optin.config import Config as Part1Config  # noqa: E402
from webapp_core.card_view import build_card_view  # noqa: E402
from webapp_core.persona_view import build_persona_section  # noqa: E402
from webapp_core.personas import expected_joiners_by_persona  # noqa: E402
from webapp_core.model_io import load_model  # noqa: E402
from webapp_core.past_promos import (  # noqa: E402
    predicted_vs_actual,
    read_sendable_ids_by_cell,
)
from webapp_core.audience import latest_adb  # noqa: E402
from webapp_core.promo_id import next_promo_id  # noqa: E402
from webapp_core import toast_queue  # noqa: E402  (Part 8 loader stage texts)
from webapp_core import number_help  # noqa: E402  (Part 9 round 2 plain descriptions)
from webapp_core.number_format import shown_joiners  # noqa: E402
from webapp_core.segment_flow import display_rank, flow_rows, flow_total  # noqa: E402
import help_page  # noqa: E402  (Part 9 round 2 Help And FAQs dialog)
from webapp_core.run_promo import PromoSpec, run_promo  # noqa: E402
from webapp_core.threshold import (  # noqa: E402
    THRESHOLD_SPECS,
    ThresholdType,
    default_value,
    effective_threshold,
    format_value,
)

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
MECHANIC_DISPLAY = {
    "TOP_UP": "Top Up",
    "NEW_ACCOUNT": "New Account",
    "ADB_INCREASE": "ADB Increase",
    "OTHER": "Other",
}
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


@st.cache_data(show_spinner=False)
def _load_latest_adb_series() -> pd.Series | None:
    """Latest ADB per client for the Balance Increase threshold, or `None`."""
    try:
        adb = pd.read_csv(ADB_MONTHLY_PATH)
    except (FileNotFoundError, ValueError):
        return None
    return latest_adb(adb)["latest_adb"]


def _slider_format(spec) -> str:
    """The Streamlit format for a threshold slider.

    Peso amounts use Streamlit's "localized" preset so the handle and the
    min/max labels show thousands separators (512,500); the peso sign is in
    the slider's label ("Top-Up Amount (₱)"). Percentages stay "50%".
    """
    return "%d%%" if spec.is_percent else "localized"


def _threshold_readout(threshold_type: ThresholdType, value: float, key: str) -> None:
    """The "Selected: ₱512,500" line under a threshold slider.

    When the value changes, its digits roll from the previous amount to the
    new one (the same digit columns as the other animated numbers); the peso
    sign, commas and percent stay put. The first render and unchanged
    reruns are static. The plain value stays readable for screen readers.
    """
    text = format_value(threshold_type, value)
    prev = ui_effects.number_prev(f"{key}:{threshold_type.name}", text)
    st.markdown(theme.selected_readout_html(text, prev), unsafe_allow_html=True)


def _threshold_kwargs(
    threshold_type: ThresholdType, value: float
) -> tuple[dict | None, str | None, str | None]:
    """Resolve a selection into PromoSpec threshold fields.

    Returns ``(fields, error, note)``; ``fields`` is `None` when the threshold
    cannot be applied (Balance Increase with no usable ADB, Requirement 5.11).
    """
    resolution = effective_threshold(threshold_type, value, _load_latest_adb_series())
    if resolution.error is not None or resolution.threshold_php is None:
        return None, resolution.error, None
    fields = {
        "threshold_type": threshold_type.value,
        "threshold_pct": (
            float(value) if threshold_type is ThresholdType.BALANCE_INCREASE else None
        ),
        "threshold_php": float(resolution.threshold_php),
    }
    return fields, None, resolution.note


def _load_data_bundle() -> dict[str, pd.DataFrame]:
    """Load the ``data/`` frames bundle ``run_promo`` consumes."""
    return {
        "customer_dna": pd.read_csv(CUSTOMER_DNA_PATH),
        "adb_monthly": pd.read_csv(ADB_MONTHLY_PATH),
        "features": pd.read_csv(FEATURES_PART2_PATH),
    }


def _segment_figures(result) -> dict[str, tuple[int, float, int]]:
    """{segment: (clients, expected joiners, sendable)} for a run."""
    if result is None or not result.cards:
        return {}
    sendable = result.sendable_by_segment or {}
    out = {}
    for card in result.cards:
        seg = str(card.get("segment"))
        leads = sendable.get(seg)
        out[seg] = (
            int(card.get("n_clients", 0) or 0),
            float(card.get("expected_joiners", 0.0) or 0.0),
            0 if leads is None else len(leads),
        )
    return out


def _run_forecast(result=None) -> tuple[float, int]:
    """(unrounded Expected Joiners, sendable leads) over the Run's segments.

    Part 9 round 2 (Requirements 20, 21): the header shows the forecast
    rounded, the forecast in brackets, and the share of sendable leads.
    """
    result = st.session_state.get(RUN_RESULT_KEY) if result is None else result
    if result is None or not result.cards:
        return 0.0, 0
    forecast = sum(float(card.get("expected_joiners", 0.0) or 0.0) for card in result.cards)
    sendable = sum(len(df) for df in (result.sendable_by_segment or {}).values())
    return forecast, sendable


def _metric_from_run() -> tuple[str, str]:
    """The headline number + caption for the header.

    Round 2 (Requirement 20): the whole number is the forecast rounded with
    halves up (the cards' rule), not Python's round-half-even format.
    """
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        return "--", "Expected Joiners"
    forecast, _sendable = _run_forecast(result)
    return f"{shown_joiners(forecast):,}", "Expected Joiners"


def _run_context_items() -> list[str] | None:
    """The current run as short display items, or `None` before any run."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None:
        return None
    spec = result.promo_spec
    return [
        str(spec.promo_id),
        str(spec.product_type),
        str(spec.mechanic).replace("_", " ").title(),
        f"Threshold ₱{float(spec.threshold_php):,.0f}",
        f"{len(result.scored):,} eligible clients",
        f"{len(result.cards)} segments",
    ]


# --- navigation (Part 9): the six sections stay st.tabs; a key lets code
# switch them (View Results, landing on Results after a run). ---
NAV_KEY = "main_nav"
NAV_PENDING_KEY = "main_nav_pending"


def go_to(label: str) -> None:
    """Open a section on the next render (safe to call after the tabs exist)."""
    st.session_state[NAV_PENDING_KEY] = label


def _go_to_now(label: str) -> None:
    """Button callback: switch section before the next render draws the tabs."""
    st.session_state[NAV_KEY] = label


FLASH_KEY = "flash_messages"
# (expected joiners, threshold label, threshold type name, threshold value,
# unrounded forecast) as run; the fifth element is Part 9 round 2
WHATIF_BASELINE_KEY = "whatif_baseline"
# {segment: (clients, expected joiners, sendable)} as run (round 3 table)
WHATIF_SEGMENTS_KEY = "whatif_baseline_segments"
WHATIF_RESET_KEY = "whatif_reset_pending"   # a Reset button asked for the as-run threshold
WHATIF_RESET_COUNT_KEY = "whatif_reset_count"  # resets so far (gives the slider a fresh key)
WHATIF_FLASH_KEY = "whatif_flash_messages"   # rescore messages survive its rerun


def _show_messages(messages: list[tuple[str, str]]) -> None:
    """Display (level, text) messages as Streamlit alerts."""
    for level, text in messages:
        show = {"error": st.error, "warning": st.warning, "success": st.success}.get(
            level, st.info
        )
        if level in ("success", "warning"):
            # Quiet style so the flash reads below the Completion_Toast (Req 8.14).
            with ui_effects.quiet_container(level):
                show(text)
        else:
            show(text)


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

    # Messages from the last Run survive the page refresh below.
    _show_messages(st.session_state.pop(FLASH_KEY, []))

    # Round 3: after a What-If change the form below still holds the threshold
    # you ran, so say which one the current results use.
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is not None and result.cards:
        label, base_label, changed = _threshold_context(result)
        if changed:
            st.markdown(
                theme.banner_html(
                    f"Active results use a threshold of {label}, set in What-If. "
                    f"The form below still shows {base_label}; Run Analysis "
                    "uses the form.",
                    "info",
                ),
                unsafe_allow_html=True,
            )

    # Fill In Details is shown first (most planners type a promo in); Upload
    # is the second option (Part 9).
    form_tab, upload_tab = st.tabs(
        [upload_panel.FORM_TAB_LABEL, upload_panel.UPLOAD_TAB_LABEL],
        key="new_promo_mode",
    )

    # The upload tab still runs first, so its prefill reaches session state
    # before the Fill In Details widgets below are created (Requirement 2.9).
    with upload_tab:
        upload_panel.render_upload_panel(
            segment_options=segment_options,
            product_options=PRODUCT_TYPE_OPTIONS,
            mechanic_options=MECHANIC_OPTIONS,
            channel_options=CHANNEL_OPTIONS,
        )

    with form_tab:
        _render_fill_in_details(
            segment_options=segment_options, auto_promo_id=auto_promo_id
        )


def _render_fill_in_details(*, segment_options: list[str], auto_promo_id: str) -> None:
    """The Fill In Details tab: threshold controls, the form, and Run."""
    upload_panel.ensure_form_defaults(
        segment_options, PRODUCT_TYPE_OPTIONS, MECHANIC_OPTIONS, CHANNEL_OPTIONS
    )

    st.subheader("Design A Promo")

    # Threshold controls live above the form so a type change reruns the page
    # and the slider (keyed by type) resets to its default (Requirements 5.1-5.3).
    theme.section_label("Threshold", "The amount that qualifies a client.")
    st.session_state.setdefault(upload_panel.THRESHOLD_TYPE_KEY, list(ThresholdType)[0])
    type_col, slider_col = st.columns([1, 2])
    with type_col:
        threshold_type = st.selectbox(
            "Threshold Type",
            list(ThresholdType),
            format_func=lambda t: t.value,
            key=upload_panel.THRESHOLD_TYPE_KEY,
        )
        upload_panel.field_tag("threshold_type")
    t_spec = THRESHOLD_SPECS[threshold_type]
    slider_key = upload_panel.threshold_value_key(threshold_type)
    st.session_state.setdefault(slider_key, default_value(threshold_type))
    with slider_col:
        threshold_value = st.slider(
            t_spec.label,
            min_value=t_spec.minimum,
            max_value=t_spec.maximum,
            step=t_spec.step,
            format=_slider_format(t_spec),
            key=slider_key,
        )
        upload_panel.field_tag("threshold_value")
    _threshold_readout(threshold_type, threshold_value, "new_promo_threshold")
    threshold_fields, threshold_error, threshold_note = _threshold_kwargs(
        threshold_type, threshold_value
    )
    if threshold_note:
        st.info(threshold_note)
    if threshold_error:
        st.error(threshold_error)

    with st.form("new_promo_form"):
        # Part 9: with no box round the form, the Promo ID belongs under the
        # Promo Basics heading (it read as part of Threshold above it).
        theme.section_label("Promo Basics", "What you are offering.")
        id_col, _id_spacer = st.columns([1, 2])
        with id_col:
            st.text_input("Promo ID (Auto-Generated)", value=auto_promo_id, disabled=True)

        basics_a, basics_b, basics_c = st.columns(3)
        with basics_a:
            product_type = st.selectbox(
                "Product Type", PRODUCT_TYPE_OPTIONS, key=upload_panel.PRODUCT_TYPE_KEY
            )
            upload_panel.field_tag("product_type")
        with basics_b:
            mechanic = st.selectbox(
                "Mechanic",
                MECHANIC_OPTIONS,
                # Part 9: shown as words; the value stays the code (TOP_UP).
                format_func=lambda m: MECHANIC_DISPLAY.get(m, m),
                key=upload_panel.MECHANIC_KEY,
            )
            upload_panel.field_tag("mechanic")
        with basics_c:
            reward = st.text_input("Reward", key=upload_panel.REWARD_KEY)
            upload_panel.field_tag("reward")

        theme.section_label("Offer Terms", "The amounts that qualify a client.")
        terms_a, _terms_spacer = st.columns(2)
        with terms_a:
            min_adb = st.number_input(
                "Minimum ADB (PHP)",
                min_value=0.0,
                step=10_000.0,
                format="%.2f",
                key=upload_panel.MIN_ADB_KEY,
                help=number_help.adb_help(),
            )
            upload_panel.field_tag("min_adb")

        theme.section_label("Audience", "Who can receive the promo.")
        aud_a, aud_b = st.columns(2)
        with aud_a:
            eligible_segments = st.multiselect(
                "Eligible Segments",
                options=segment_options,
                help="Customer_DNA segments. Clients outside these are excluded.",
                key=upload_panel.SEGMENTS_KEY,
            )
            upload_panel.field_tag("eligible_segments")
        with aud_b:
            channels = st.multiselect(
                "Channels",
                options=CHANNEL_OPTIONS,
                key=upload_panel.CHANNELS_KEY,
            )
            upload_panel.field_tag("channels")

        with st.container(key=ui_effects.P8_BTN_RUN_ANALYSIS):
            # Ring slot sits before the button, inside the form (Requirement 7).
            ring_slot = ui_effects.ring_slot("analysis")
            submitted = st.form_submit_button("Run Analysis")

    # With no usable ADB the error is shown above and the run is blocked
    # (Requirement 5.11).
    if submitted and threshold_fields is not None:
        spec = PromoSpec(
            promo_id=auto_promo_id,
            product_type=product_type,
            mechanic=mechanic,
            **threshold_fields,
            reward=reward,
            eligible_segments=list(eligible_segments),
            min_adb=float(min_adb),
            channels=list(channels),
        )
        # Keyboard guard (Requirements 7.11, 7.12): the same inputs re-submitted
        # within the window of the previous Job's end start no second Job.
        # promo_id is excluded because it is auto-generated per run.
        signature = repr(sorted(
            (k, v) for k, v in dataclasses.asdict(spec).items() if k != "promo_id"
        ))
        if not ui_effects.is_duplicate("analysis", signature):
            # One loading screen only: the former toast wording is its live
            # status line, streamed before the blocking call.
            ui_effects.start_job("analysis", ring_slot)
            with theme.loading(
                "analysis",
                "Scoring and segmenting your audience...",
                status=toast_queue.start_text("analysis", spec.promo_id),
            ) as loader:
                messages = _execute_run(spec)
                # Saved inside the loader block, before its cleanup makes the
                # next Streamlit call. A keypress queued during the Job
                # interrupts the run at that call; with the flash and job-end
                # record already stored, the guard above skips the repeat on
                # the next run (Requirements 7.11, 7.12).
                st.session_state[FLASH_KEY] = messages
                # Empty audience and missing model end with the error ring (D3).
                ok = any(level == "success" for level, _ in messages)
                ui_effects.end_job("analysis", ok, signature)
                if ok:
                    loader.status(toast_queue.DONE_TEXT["analysis"])
                    # The overlay stays through the rerun; the completion render
                    # fades it out (design section l). Errors clear it as before.
                    loader.keep()
                    # Land on the answer, not back on the form (Part 9).
                    go_to("Results")
                    # What-If compares later thresholds with this run.
                    base_number, _caption = _metric_from_run()
                    st.session_state[WHATIF_BASELINE_KEY] = (
                        base_number,
                        format_value(threshold_type, threshold_value),
                        threshold_type.name,
                        float(threshold_value),
                        _run_forecast()[0],
                    )
                    st.session_state[WHATIF_SEGMENTS_KEY] = _segment_figures(
                        st.session_state.get(RUN_RESULT_KEY)
                    )
                    st.session_state.pop(WHATIF_RESET_KEY, None)
            # Refresh once so the hero KPI at the top shows the new run's number.
            st.rerun()

    # Back on the form after a run: one step to the answer (Part 9).
    if st.session_state.get(RUN_RESULT_KEY) is not None:
        _nav_button("View Results", "Results", key="nav_newpromo_results")


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

# Part 9: no tile is drawn as a red slab any more. The segment whose card
# action is "Prioritize" is the recommended one ("Act first" tag), and the
# decision cards run in action order, best action first.
RECOMMENDED_ACTION = "Prioritize"
ACTION_ORDER = ["Prioritize", "Offer lower tier", "Include", "Skip"]


def _action_rank(card: dict) -> tuple[int, float]:
    action = str(card.get("action", ""))
    rank = ACTION_ORDER.index(action) if action in ACTION_ORDER else len(ACTION_ORDER)
    return rank, -float(card.get("expected_joiners", 0.0) or 0.0)


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
        sendable = 0
    else:
        n_clients = int(card.get("n_clients", 0) or 0)
        joiners = float(card.get("expected_joiners", 0.0) or 0.0)
        sendable = int(card.get("sendable_count", 0) or 0)
    # Numbers count up from 0 after a run (theme.counting, Part 8 polish).
    # Round 2 (Requirements 20, 22): the whole number counts up; the forecast
    # bracket and the "out of N sendable leads" line are plain.
    main = theme.count_text_html(f"{shown_joiners(joiners):,}")
    return (
        '<div class="pan-tile-k">Clients</div>'
        f'<div class="pan-tile-v">{theme.count_text_html(f"{n_clients:,}")}</div>'
        '<div class="pan-tile-k pan-tile-k--spaced">Expected Joiners</div>'
        f'<div class="pan-tile-accent">{theme.joiners_pair_html(joiners, main_html=main)}</div>'
        f'<div class="pan-tile-sub">{html.escape(number_help.joiners_of_sendable(joiners, sendable))}</div>'
    )


def _results_persona_section(result, card: dict, segment_label: str):
    """Persona section for one Results card (Requirements 7.1, 7.4, 7.5, 7.10).

    Without a persona run the card shows the "personas not generated" line. A
    run with several groups is detailed in the Personas tab, so no section is
    shown here (group names are never printed on these cards).
    """
    persona_result = st.session_state.get(persona_page.PERSONA_RESULT_KEY)
    if persona_result is None:
        # Part 9: said once above the cards (with a Build Personas action),
        # not repeated on every card.
        return None
    if persona_page.group_options(persona_result):
        return None
    items = expected_joiners_by_persona(
        [card],
        result.sendable_by_segment or {},
        persona_result.labels,
        persona_result.persona_sets,
        drop_empty=True,
    )
    breakdown = items[0] if items else None
    return persona_page.persona_section_for(breakdown, segment_label)


_TIP_MESSAGES_SAVED = (
    "Baseline messages minus Recommended messages. Baseline is every eligible "
    "lead; Recommended skips segments whose action is Skip."
)
_TIP_JOINERS_KEPT = (
    "Recommended expected joiners divided by Baseline expected joiners, as a "
    "percent. Expected joiners are the sum of each lead's p_join."
)
_TIP_COST_SAVED = (
    "Baseline channel cost minus Recommended channel cost, using the per "
    "message cost of each lead's best channel."
)


def _render_impact_summary(result) -> None:
    """Show the Impact Summary banner and tiles for a run (Req 8.3, 8.5-8.8).

    Shared by the Results and What-If tabs.
    """
    from webapp_core.impact import compute_impact, load_channel_costs

    try:
        impact = compute_impact(result, load_channel_costs())
    except Exception:
        st.markdown(
            theme.banner_html("No comparison is available for this run.", "info"),
            unsafe_allow_html=True,
        )
        return
    if not impact.available:
        st.markdown(
            theme.banner_html(
                impact.neutral_message or "No comparison is available for this run.",
                "info",
            ),
            unsafe_allow_html=True,
        )
        return
    if impact.cost_available and impact.banner:
        st.markdown(theme.banner_html(impact.banner, "info"), unsafe_allow_html=True)
    else:
        st.markdown(
            theme.banner_html(
                impact.cost_message or "Cost savings are unavailable.", "info"
            ),
            unsafe_allow_html=True,
        )
    cost_value = (
        f"₱{impact.cost_saved:,}" if impact.cost_saved is not None else "Unavailable"
    )
    tiles = [
        theme.stat_tile_html(
            f"Messages Saved: {impact.messages_saved:,}", _TIP_MESSAGES_SAVED
        ),
        theme.stat_tile_html(
            f"Joiners Kept (%): {impact.joiners_kept_pct}%", _TIP_JOINERS_KEPT
        ),
        theme.stat_tile_html(f"Cost Saved (₱): {cost_value}", _TIP_COST_SAVED),
    ]
    st.markdown(theme.stat_tiles_html(tiles), unsafe_allow_html=True)
    st.caption(number_help.impact_help())


def _render_results_tab() -> None:
    """Render the Results tab: 2x2 grid, decision cards, Download Leads."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        st.info(
            "Run a promo first. Open the New Promo tab, design a promo, and "
            "press Run Analysis. The results grid, decision cards, and lead "
            "downloads appear here once a run exists."
        )
        _nav_button("Go To New Promo", "New Promo", key="nav_results_empty")
        return

    cards_by_segment = _cards_by_segment()

    # After a run, the headline numbers fade in and count up once (keyed to
    # the analysis generation; plain and static on every later rerun).
    run_el = ui_effects.reveal("analysis")

    recommended = {
        seg for seg, card in cards_by_segment.items()
        if str(card.get("action", "")) == RECOMMENDED_ACTION
    }

    # --- which threshold these results use, then the action bar (Part 9) ---
    _render_threshold_context(result)
    _render_results_actions(result, recommended)

    # --- 2x2 Results grid: score (rows) by capacity (columns), axes labelled ---
    st.subheader("Results Grid")
    with theme.counting(*run_el):
        grid_rows = [
            (
                row_label,
                [
                    (
                        col_label,
                        segment_label,
                        _tile_body_html(cards_by_segment.get(segment_label), emphasis=False),
                    )
                    for col_label, segment_label in cols
                ],
            )
            for row_label, cols in RESULTS_GRID
        ]
        st.markdown(theme.results_grid_html(grid_rows, recommended), unsafe_allow_html=True)

    # --- Impact Summary banner and tiles (Req 8.3, 8.5-8.8) ---
    # Part 9: only the headline figures count up (header and grid tiles). The
    # impact boxes and decision cards arrive with their final numbers: 70-odd
    # rolling digit columns at once made the reveal skip on slower machines.
    _render_impact_summary(result)

    # --- where each segment's clients go (Part 9 round 2, Requirement 27) ---
    _render_segment_flow(result, reveal=run_el[0] is not None)

    # --- decision cards, two per row on wide screens ---
    st.subheader("Decision Cards")
    has_personas = st.session_state.get(persona_page.PERSONA_RESULT_KEY) is not None
    if not has_personas:
        st.caption(
            "Personas were not generated for this run. Build them to see "
            "expected joiners by persona on each card."
        )
    # Best action first (Prioritize, Offer lower tier, Include, Skip), then
    # more expected joiners first within an action.
    ordered_segments = sorted(
        (
            segment_label
            for _row, cols in RESULTS_GRID
            for _col, segment_label in cols
            if segment_label in cards_by_segment
        ),
        key=lambda s: _action_rank(cards_by_segment[s]),
    )
    for i in range(0, len(ordered_segments), 2):
        pair = ordered_segments[i : i + 2]
        card_cols = st.columns(2)
        for card_col, segment_label in zip(card_cols, pair):
            with card_col:
                card = cards_by_segment[segment_label]
                view = build_card_view(
                    card, persona=_results_persona_section(result, card, segment_label)
                )
                theme.card(
                    view.title,
                    theme.decision_card_body_html(view),
                    recommended=segment_label in recommended,
                )

    # --- Download Leads: one row per segment, in action order (Part 9) ---
    # Each row reconciles the grid: clients = not contacted + control group +
    # sendable, so the CSV count never looks unexplained.
    # Round 2 (Requirement 25): one closed dropdown holding the same rows;
    # every download key is unchanged.
    sendable = result.sendable_by_segment or {}
    n_files = len(sendable)
    with st.expander(
        f"Download Leads ({n_files} {'file' if n_files == 1 else 'files'})",
        expanded=False,
        key="pan_download_leads",
    ):
        if not sendable:
            st.caption("No sendable leads were produced for this run.")
        else:
            rows = [s for s in ordered_segments if s in sendable] + [
                s for s in sendable if s not in ordered_segments
            ]
            for i, segment_label in enumerate(rows):
                _render_download_row(
                    i, result, segment_label, sendable[segment_label],
                    cards_by_segment.get(segment_label, {}),
                    recommended=segment_label in recommended,
                )
            st.caption(DOWNLOAD_NOTE)

    # --- where to go next: real actions instead of a "Next:" sentence ---
    with st.container(key="pan_next_actions", horizontal=True):
        _nav_button(
            "View Personas" if has_personas else "Build Personas",
            "Personas", key="nav_results_personas", primary=not has_personas,
        )
        _nav_button("Try Another Threshold", "What-If", key="nav_results_whatif")


FLOW_SEGMENT_KEY = "pan_flow_segment"
FLOW_ALL = "All Segments"


def _render_segment_flow(result, *, reveal: bool) -> None:
    """Results: "Where Each Segment's Clients Go" (Part 9 round 2, Req 27).

    Stacked bars and the table, read straight from the Run's cards.
    """
    rows = flow_rows(result.cards)
    if not rows:
        return
    st.subheader("Where Each Segment's Clients Go")
    st.caption(number_help.flow_help())
    # Owner follow-up: one segment at a time, picked from a dropdown, in the
    # display order, with "All Segments" (the Total) last. No separate table.
    by_name = {r.segment: r for r in rows}
    options = [r.segment for r in rows] + [FLOW_ALL]
    if st.session_state.get(FLOW_SEGMENT_KEY) not in options:
        st.session_state[FLOW_SEGMENT_KEY] = options[0]
    col, _rest = st.columns([1, 1])
    with col:
        choice = st.selectbox("Segment", options, key=FLOW_SEGMENT_KEY)
    row = flow_total(rows) if choice == FLOW_ALL else by_name[choice]
    st.markdown(
        theme.segment_flow_html(row, reveal=reveal, title=choice),
        unsafe_allow_html=True,
    )


def _nav_button(label: str, section: str, *, key: str, primary: bool = False) -> None:
    """A button that opens another section (Part 9 signposts)."""
    st.button(
        label,
        key=key,
        type="primary" if primary else "secondary",
        on_click=_go_to_now,
        args=(section,),
    )


EXPORT_CACHE_KEY = "export_summary_cache"
EXPORT_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _export_workbook_bytes(result) -> bytes:
    """Build the Export_Workbook bytes, cached per run and persona result.

    The cache key uses object identity, so a new run or a new persona
    generation rebuilds the workbook once and reruns reuse the bytes.
    """
    from datetime import date

    from webapp_core.export_workbook import build_workbook
    from webapp_core.impact import compute_impact, load_channel_costs

    persona_result = st.session_state.get(persona_page.PERSONA_RESULT_KEY)
    source = (
        getattr(persona_result, "narration_source", "Demo")
        if persona_result is not None
        else "Demo"
    )
    key = (id(result), id(persona_result), source, date.today())
    cached = st.session_state.get(EXPORT_CACHE_KEY)
    if cached is not None and cached[0] == key:
        return cached[1]
    impact = compute_impact(result, load_channel_costs())
    data = build_workbook(result, impact, persona_result, source, run_date=date.today())
    st.session_state[EXPORT_CACHE_KEY] = (key, data)
    return data


DOWNLOAD_NOTE = (
    "Lead files leave out clients on the do not bother list, clients contacted "
    "too often, clients with no reachable channel, and the control group held "
    "back to measure the promo."
)


def _current_threshold(result) -> tuple[ThresholdType, float]:
    """The threshold the current run (or What-If rescore) was scored at."""
    t_type = _spec_threshold_type(result.promo_spec)
    if t_type is ThresholdType.BALANCE_INCREASE and result.promo_spec.threshold_pct is not None:
        return t_type, float(result.promo_spec.threshold_pct)
    return t_type, float(result.promo_spec.threshold_php)


def _as_run_threshold(t_type: ThresholdType) -> tuple[str, float] | None:
    """(label, value) of the threshold New Promo ran, if it has this type."""
    base = st.session_state.get(WHATIF_BASELINE_KEY)
    if not base or len(base) < 4 or base[2] != t_type.name:
        return None
    return str(base[1]), float(base[3])


def _threshold_context(result) -> tuple[str, str | None, bool]:
    """(current threshold label, as-run label or None, changed in What-If)."""
    t_type, value = _current_threshold(result)
    label = format_value(t_type, value)
    as_run = _as_run_threshold(t_type)
    if as_run is None:
        return label, None, False
    changed = abs(as_run[1] - value) >= THRESHOLD_SPECS[t_type].step / 2.0
    return label, as_run[0], changed


def _request_threshold_reset() -> None:
    """Button callback: What-If rescores back to the as-run threshold."""
    st.session_state[WHATIF_RESET_KEY] = True


def _threshold_slug(result) -> str:
    """The current threshold for file names: 600000, or 15pct."""
    label, _base, _changed = _threshold_context(result)
    digits = re.sub(r"[^0-9]", "", label)
    return f"{digits}pct" if "%" in label else digits


def _leads_file_name(result, segment_label: str) -> str:
    # Part 9: the threshold is in the name, so a saved file says what it was cut at.
    return (
        f"{result.promo_spec.promo_id}_{_threshold_slug(result)}_"
        f"{segment_label.replace(' ', '_').lower()}_leads.csv"
    )


def _render_threshold_context(result) -> None:
    """Top of Results: the threshold these results use (Part 9).

    After a What-If change it says so plainly and offers the way back, since
    Results and every lead file follow the threshold last scored.
    """
    label, base_label, changed = _threshold_context(result)
    if changed:
        st.markdown(
            theme.banner_html(
                f"These results and lead files use a threshold of {label}, set "
                f"in What-If. You ran {base_label}.",
                "info",
            ),
            unsafe_allow_html=True,
        )
        st.button(
            f"Reset To {base_label}", key="whatif_reset_results",
            on_click=_request_threshold_reset,
        )
    else:
        st.caption(
            f"Threshold {label}" + (", as run. " if base_label else ". ")
            + number_help.threshold_help()
        )


def _render_results_actions(result, recommended: set[str]) -> None:
    """Top of Results: Download Recommended Leads (primary) and Export Summary."""
    sendable = result.sendable_by_segment or {}
    frames = [sendable[s] for s in sorted(recommended) if s in sendable]
    with st.container(key="pan_results_actions", horizontal=True):
        if frames:
            leads = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
            st.download_button(
                f"Download Recommended Leads ({len(leads):,})",
                data=leads.to_csv(index=False).encode("utf-8"),
                file_name=(
                    f"{result.promo_spec.promo_id}_{_threshold_slug(result)}"
                    "_recommended_leads.csv"
                ),
                mime="text/csv",
                type="primary",
                key="download_leads_recommended",
                help=(
                    "The sendable leads of the segment marked Act first, at a "
                    f"threshold of {_threshold_context(result)[0]}."
                ),
            )
        _render_export_summary(result)
    if frames:
        cards = _cards_by_segment()
        forecast = sum(
            float(cards.get(s, {}).get("expected_joiners", 0.0) or 0.0)
            for s in recommended if s in sendable
        )
        st.caption(number_help.recommended_caption(forecast, len(leads)))


def _download_cell(label: str, value: str, notes: tuple[str, ...] = (), tip: str = "") -> str:
    note_html = "".join(f'<span class="pan-dl-note">{html.escape(n)}</span>' for n in notes)
    # Round 2 (Requirement 22): the plain meaning is the label's hover text,
    # so the closed dropdown stays clean.
    key_html = theme.tooltip_html(label, tip) if tip else html.escape(label)
    return (
        f'<div class="pan-dl-cell"><span class="pan-dl-k">{key_html}</span>'
        f'<span class="pan-dl-v">{html.escape(value)}</span>{note_html}</div>'
    )


def _render_download_row(i: int, result, segment_label: str, leads_df, card: dict,
                         *, recommended: bool) -> None:
    """One Download Leads row: who is in the file, who is left out, the file."""
    excluded = {str(k): int(v) for k, v in (card.get("excluded_by_reason") or {}).items()}
    n_excluded = sum(excluded.values())
    # Same plain reason labels as the decision card ("Contacted Too Often: 26"),
    # one per line.
    reasons = tuple(build_card_view(card).exclusions) if card else ()
    control = int(card.get("control_count", 0) or 0)
    marker, seg_class = theme.segment_marker_html(segment_label)
    tag = theme.act_first_tag_html() if recommended else ""
    action = str(card.get("action", "")) or "Not set"
    with st.container(key=f"pan_dl_row_{i}"):
        name_col, clients_col, out_col, control_col, send_col, file_col = st.columns(
            [2.6, 1, 2.6, 1.2, 1, 2], vertical_alignment="center"
        )
        with name_col:
            st.markdown(
                f'<div class="pan-dl-name {seg_class}">{marker}'
                f"<span>{html.escape(segment_label)}</span>{tag}</div>"
                f'<div class="pan-dl-action">{html.escape(action)}</div>',
                unsafe_allow_html=True,
            )
        with clients_col:
            st.markdown(_download_cell("Clients", f"{int(card.get('n_clients', 0) or 0):,}"),
                        unsafe_allow_html=True)
        with out_col:
            st.markdown(_download_cell("Not Contacted", f"{n_excluded:,}", reasons,
                                       number_help.not_contacted_help()),
                        unsafe_allow_html=True)
        with control_col:
            st.markdown(_download_cell("Control Group", f"{control:,}", (),
                                       number_help.control_help()),
                        unsafe_allow_html=True)
        with send_col:
            st.markdown(_download_cell("Sendable", f"{len(leads_df):,}", (),
                                       number_help.sendable_help()),
                        unsafe_allow_html=True)
        with file_col:
            # The row already names the segment, so the label stays short
            # enough not to truncate; the file name still carries it.
            st.download_button(
                label=f"Download {len(leads_df):,} Leads",
                data=leads_df.to_csv(index=False).encode("utf-8"),
                file_name=_leads_file_name(result, segment_label),
                mime="text/csv",
                key=f"download_leads_{segment_label}",
                width="stretch",
            )


def _render_export_summary(result) -> None:
    """Export Summary download for the current run (Requirements 9.1, 9.2, 9.12).

    Part 9: drawn in the Results action bar, so it has no heading of its own.
    """
    from webapp_core.export_workbook import workbook_filename

    if result is None:
        st.caption("Run an analysis first to export a summary.")
        st.download_button(
            "Export Summary",
            data=b"",
            disabled=True,
            key="export_summary_disabled",
        )
        return
    try:
        data = _export_workbook_bytes(result)
    except Exception:
        st.error(
            "The summary could not be built for this run. Run the analysis "
            "again, then try the export once more."
        )
        return
    st.download_button(
        "Export Summary",
        data=data,
        file_name=workbook_filename(result.promo_spec.promo_id),
        mime=EXPORT_MIME,
        key="export_summary",
    )


def _spec_threshold_type(spec: PromoSpec) -> ThresholdType:
    """The run's threshold type; legacy specs without one are Top-Up."""
    try:
        return ThresholdType(spec.threshold_type)
    except ValueError:
        return ThresholdType.TOP_UP


def _render_whatif_tab() -> None:
    """Render the What-If threshold slider and rescore on change (Req 6.1-6.3)."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None:
        st.info(
            "Run a promo first. Open the New Promo tab, design a promo, and "
            "press Run Analysis. The What-If threshold slider appears here "
            "once a run exists."
        )
        _nav_button("Go To New Promo", "New Promo", key="nav_whatif_empty")
        return

    t_type = _spec_threshold_type(result.promo_spec)
    t_spec = THRESHOLD_SPECS[t_type]
    min_value, max_value, step = t_spec.minimum, t_spec.maximum, t_spec.step
    if t_type is ThresholdType.BALANCE_INCREASE and result.promo_spec.threshold_pct is not None:
        current = float(result.promo_spec.threshold_pct)
    else:
        current = float(result.promo_spec.threshold_php)

    # The browser keeps a slider's last value, so after a reset the slider
    # gets a fresh key (a new widget that starts at the result's threshold).
    # Until the first reset the key is the original one.
    reset_n = int(st.session_state.get(WHATIF_RESET_COUNT_KEY, 0))
    slider_key = f"whatif_threshold_{t_type.name}" + (f"_r{reset_n}" if reset_n else "")
    as_run = _as_run_threshold(t_type)
    # A Reset button (here or on Results) asked for the as-run threshold:
    # rescore there, then let the slider start again from the result.
    if st.session_state.pop(WHATIF_RESET_KEY, False) and as_run is not None:
        r_fields, _r_error, _r_note = _threshold_kwargs(t_type, as_run[1])
        if r_fields is not None and abs(as_run[1] - current) >= (step / 2.0):
            if _run_rescore(result, t_type, as_run[1], r_fields):
                st.session_state.pop(slider_key, None)
                st.session_state[WHATIF_RESET_COUNT_KEY] = reset_n + 1
                st.rerun()

    st.subheader("What-If: Vary The Threshold")
    st.caption(
        "Drag the threshold to rescore the current eligible audience with the "
        "already-fitted model. No model is retrained; only the threshold "
        "changes, so the audience is rescored, resegmented, and recarded."
    )

    new_threshold = st.slider(
        t_spec.label,
        min_value=min_value,
        max_value=max_value,
        value=int(min(max(current, min_value), max_value)),
        step=step,
        format=_slider_format(t_spec),
        key=slider_key,
    )
    # Part 9: a plain readout (no digit roll, which showed wrong amounts
    # mid-roll) in a slot the rescore reuses for "Rescoring at ...", so
    # nothing below moves while it works.
    readout = st.empty()
    readout.markdown(
        theme.selected_readout_html(format_value(t_type, new_threshold)),
        unsafe_allow_html=True,
    )

    fields, error, note = _threshold_kwargs(t_type, new_threshold)
    if note:
        st.info(note)
    # Messages from the rescore that just finished (it reruns, like a run).
    _show_messages(st.session_state.pop(WHATIF_FLASH_KEY, []))
    if error:
        st.error(error)
    elif fields is not None and abs(float(new_threshold) - current) >= (step / 2.0):
        if _run_rescore(result, t_type, float(new_threshold), fields, status_slot=readout):
            st.rerun()
        # A failed rescore leaves the result unchanged; rerunning would retry
        # forever, so its messages show here and the page carries on.
        _show_messages(st.session_state.pop(WHATIF_FLASH_KEY, []))

    number, caption = _metric_from_run()
    # Part 9: the number as it changed from the run you made, not a second
    # red panel repeating the header. Counts up once after a run; later
    # slider changes roll from the last shown value (Part 8, F5).
    now_label = format_value(t_type, current)
    base = st.session_state.get(WHATIF_BASELINE_KEY)
    with theme.counting(*ui_effects.reveal("analysis")):
        st.markdown(
            theme.whatif_change_html(
                caption,
                number,
                now_label,
                base_number=base[0] if base else None,
                base_label=base[1] if base else None,
                prev=ui_effects.number_prev("whatif", number),
                forecast=_run_forecast(result)[0],
                base_forecast=base[4] if base and len(base) > 4 else None,
            ),
            unsafe_allow_html=True,
        )
    _render_whatif_segments(result)
    with theme.counting(*ui_effects.reveal("analysis")):
        if result is not None:
            _render_impact_summary(result)
    if result is not None and result.cards:
        st.caption(
            f"Threshold ₱{float(result.promo_spec.threshold_php):,.0f}: "
            f"{len(result.scored):,} eligible clients across "
            f"{len(result.cards)} segments."
        )
    with st.container(key="pan_whatif_actions", horizontal=True):
        _nav_button("View Results", "Results", key="nav_whatif_results")
        _label, base_label, changed = _threshold_context(result)
        if changed:
            st.button(
                f"Reset To {base_label}", key="whatif_reset_whatif",
                on_click=_request_threshold_reset,
            )


def _render_whatif_segments(result) -> None:
    """Round 3: each segment at this threshold, with its change from the run."""
    now = _segment_figures(result)
    if not now:
        return
    # The changes show only once the threshold differs from the run;
    # at the as-run threshold every one would read "No change".
    _label, _base_label, changed = _threshold_context(result)
    base = (st.session_state.get(WHATIF_SEGMENTS_KEY) or {}) if changed else {}
    # Round 2 (Requirement 24): best first, the one display order.
    segments = sorted(set(now) | set(base), key=display_rank)
    rows = []
    for seg in segments:
        n = now.get(seg, (0, 0.0, 0))
        b = base.get(seg) if base else None
        rows.append((seg, [
            (n[0], None if b is None else b[0], "count"),
            (n[1], None if b is None else b[1], "joiners"),
            (n[2], None if b is None else b[2], "count"),
        ]))
    st.markdown(theme.whatif_segments_html(rows), unsafe_allow_html=True)
    st.caption(number_help.whatif_table_help())


def _run_rescore(result, t_type: ThresholdType, value: float, fields: dict,
                 *, status_slot=None) -> bool:
    """Rescore the current run at ``value``; the caller reruns on success.

    Part 9: no page lock, loader overlay or finish animation for a slider
    move. The page stays as it is (Streamlit dims it slightly while the run
    works), ``status_slot`` says "Rescoring at ...", and on the rerun the
    numbers roll to their new values. Moving the slider again while it works
    simply starts the next rescore. Returns whether it succeeded; a failed
    rescore leaves the result unchanged.
    """
    if status_slot is not None:
        status_slot.markdown(
            '<div class="pan-selected">'
            + theme.thinking_html(f"Rescoring at {format_value(t_type, value)}")
            + "</div>",
            unsafe_allow_html=True,
        )
    new_spec = dataclasses.replace(result.promo_spec, **fields)
    messages = _execute_run(new_spec)
    # The run's success line belongs to New Promo ("See the Results tab");
    # What-If keeps only real warnings and errors.
    st.session_state[WHATIF_FLASH_KEY] = [m for m in messages if m[0] != "success"]
    return any(level == "success" for level, _ in messages) or bool(
        (st.session_state.get(RUN_RESULT_KEY) or result).cards
    )


def _render_ask_assistant_tab() -> None:
    """Render the Ask Assistant tab (Part 7, Requirements 3.8-3.12)."""
    assistant_page.render_assistant_page()


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

    Rates are right-aligned numbers; the Segment column stays left-aligned so
    the names read cleanly. Rates are shown as percentages with one decimal.
    """
    header = (
        "<tr>"
        '<th class="pan-th">Segment</th>'
        '<th class="pan-th pan-num">Predicted</th>'
        '<th class="pan-th pan-num">Actual</th>'
        "</tr>"
    )
    body_rows = []
    for row in sorted(rows, key=_segment_sort_key):
        segment = html.escape(str(row.get("segment", "N/A")))
        predicted = _fmt_rate(row.get("predicted"))
        actual = _fmt_rate(row.get("actual"))
        body_rows.append(
            "<tr>"
            f'<td class="pan-td pan-strong">{segment}</td>'
            f'<td class="pan-td pan-num">{predicted}</td>'
            f'<td class="pan-td pan-num pan-accent">{actual}</td></tr>'
        )
    return f'<table class="pan-table">{header}{"".join(body_rows)}</table>'


def _render_past_promos_tab() -> None:
    """Render the Past Promos tab (Part 7, Requirement 11)."""
    past_promos_page.render_past_promos_tab()


def main() -> None:
    """Compose the BPI-web app shell and route to the tabs."""
    theme.inject_css()

    # Effects slot lives outside the tabs (inactive panels are display:none).
    ui_effects.fx_container()
    # Locks the page while a job loader is shown (decision A7).
    ui_effects.install_page_lock()

    # --- header (Part 9): wordmark, the current run and its one number. The
    # hero is gone; theme.hero_kpi_html/hero_text_html remain available. ---
    number, caption = _metric_from_run()
    with theme.counting(*ui_effects.reveal("analysis")):
        st.markdown(
            theme.run_header_html(
                number,
                caption,
                has_run=st.session_state.get(RUN_RESULT_KEY) is not None,
                forecast=_run_forecast()[0],
                sendable_total=_run_forecast()[1],
                # Counts up once after a run; rolls from the last shown value
                # on later changes (Part 8, F5).
                prev=ui_effects.number_prev("hero", number),
            ),
            unsafe_allow_html=True,
        )
    st.markdown(
        theme.nav_state_html(
            has_run=st.session_state.get(RUN_RESULT_KEY) is not None,
            has_personas=st.session_state.get(persona_page.PERSONA_RESULT_KEY) is not None,
        ),
        unsafe_allow_html=True,
    )

    # Help And FAQs (Part 9 round 2, Requirement 28): a round "?" fixed at
    # the top right, outside the tab bar; it opens a dialog over the page so
    # no tab (and no widget state) is unmounted.
    with st.container(key="pan_help"):
        if st.button("?", key="help_open", help="Help And FAQs"):
            help_page.open_help(_go_to_now)

    # A section asked for during the last render (after its tabs existed).
    pending = st.session_state.pop(NAV_PENDING_KEY, None)
    if pending in theme.TAB_LABELS:
        st.session_state[NAV_KEY] = pending

    (
        new_promo_tab,
        results_tab,
        whatif_tab,
        personas_tab,
        past_promos_tab,
        ask_assistant_tab,
    ) = st.tabs(theme.TAB_LABELS, key=NAV_KEY, on_change="rerun")

    # Each tab staggers its own card entrances (theme.card_group).
    with new_promo_tab, theme.card_group("new_promo"):
        _render_new_promo_tab()
    with results_tab, theme.card_group("results"):
        _render_results_tab()
    with whatif_tab, theme.card_group("whatif"):
        _render_whatif_tab()
    with personas_tab, theme.card_group("personas"):
        persona_page.render_persona_tab(run_result_key=RUN_RESULT_KEY)
    with past_promos_tab, theme.card_group("past_promos"):
        _render_past_promos_tab()
    with ask_assistant_tab, theme.card_group("assistant"):
        _render_ask_assistant_tab()


main()