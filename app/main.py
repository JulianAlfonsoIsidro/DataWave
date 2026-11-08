"""Streamlit entry point for the Promo Audience Navigator (Part 5 webapp).

This file is the declarative composition layer: it sets the wide desktop
layout, injects the single stylesheet once, renders the page chrome (slim top
bar, a text brand, a current-run context banner, and a hero with a
red-gradient KPI panel), then the Title Case tabs (New Promo, Results,
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
    """The Streamlit printf format for a threshold slider (peso or percent)."""
    return "%d%%" if spec.is_percent else "₱%d"


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


def _metric_from_run() -> tuple[str, str]:
    """The headline number + caption for the hero KPI panel."""
    result = st.session_state.get(RUN_RESULT_KEY)
    if result is None or not result.cards:
        return "--", "Expected Joiners"
    total = sum(float(card.get("expected_joiners", 0.0)) for card in result.cards)
    return f"{total:,.0f}", "Expected Joiners"


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

    # Messages from the last Run survive the page refresh below.
    _show_messages(st.session_state.pop(FLASH_KEY, []))

    upload_tab, form_tab = st.tabs([
        upload_panel.UPLOAD_TAB_LABEL,
        upload_panel.FORM_TAB_LABEL,
    ])

    # The upload tab runs first, so its prefill reaches session state before
    # the Fill In Details widgets below are created (Requirement 2.9).
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
    st.caption(f"Selected: {format_value(threshold_type, threshold_value)}")
    threshold_fields, threshold_error, threshold_note = _threshold_kwargs(
        threshold_type, threshold_value
    )
    if threshold_note:
        st.info(threshold_note)
    if threshold_error:
        st.error(threshold_error)

    with st.form("new_promo_form"):
        id_col, _id_spacer = st.columns([1, 2])
        with id_col:
            st.text_input("Promo ID (Auto-Generated)", value=auto_promo_id, disabled=True)

        theme.section_label("Promo Basics", "What you are offering.")
        basics_a, basics_b, basics_c = st.columns(3)
        with basics_a:
            product_type = st.selectbox(
                "Product Type", PRODUCT_TYPE_OPTIONS, key=upload_panel.PRODUCT_TYPE_KEY
            )
            upload_panel.field_tag("product_type")
        with basics_b:
            mechanic = st.selectbox(
                "Mechanic", MECHANIC_OPTIONS, key=upload_panel.MECHANIC_KEY
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
        with theme.loading("analysis", "Scoring and segmenting your audience..."):
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
        '<div class="pan-tile-k pan-tile-k--spaced">Expected Joiners</div>'
        f'<div class="pan-tile-accent">{joiners:,.1f}</div>'
    )


def _results_persona_section(result, card: dict, segment_label: str):
    """Persona section for one Results card (Requirements 7.1, 7.4, 7.5, 7.10).

    Without a persona run the card shows the "personas not generated" line. A
    run with several groups is detailed in the Personas tab, so no section is
    shown here (group names are never printed on these cards).
    """
    persona_result = st.session_state.get(persona_page.PERSONA_RESULT_KEY)
    if persona_result is None:
        return build_persona_section(None, 0.0, segment_label)
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

    # --- Impact Summary banner and tiles (Req 8.3, 8.5-8.8) ---
    _render_impact_summary(result)

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
                card = cards_by_segment[segment_label]
                view = build_card_view(
                    card, persona=_results_persona_section(result, card, segment_label)
                )
                theme.card(view.title, theme.decision_card_body_html(view))

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

    _render_export_summary(result)

    theme.next_step(
        "Test a different threshold in What-If, or group these clients into "
        "personas in Personas."
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


def _render_export_summary(result) -> None:
    """Export Summary download for the current run (Requirements 9.1, 9.2, 9.12)."""
    from webapp_core.export_workbook import workbook_filename

    st.subheader("Export Summary")
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
        return

    t_type = _spec_threshold_type(result.promo_spec)
    t_spec = THRESHOLD_SPECS[t_type]
    min_value, max_value, step = t_spec.minimum, t_spec.maximum, t_spec.step
    if t_type is ThresholdType.BALANCE_INCREASE and result.promo_spec.threshold_pct is not None:
        current = float(result.promo_spec.threshold_pct)
    else:
        current = float(result.promo_spec.threshold_php)

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
        key=f"whatif_threshold_{t_type.name}",
    )

    fields, error, note = _threshold_kwargs(t_type, new_threshold)
    if note:
        st.info(note)
    if error:
        st.error(error)
    elif fields is not None and abs(float(new_threshold) - current) >= (step / 2.0):
        new_spec = dataclasses.replace(result.promo_spec, **fields)
        with theme.loading("rescore", "Rescoring at the new threshold...", slow=True):
            messages = _execute_run(new_spec)
        _show_messages(messages)
        result = st.session_state.get(RUN_RESULT_KEY)

    number, caption = _metric_from_run()
    theme.metric_panel(number, caption)
    if result is not None:
        _render_impact_summary(result)
    if result is not None and result.cards:
        st.caption(
            f"Threshold ₱{float(result.promo_spec.threshold_php):,.0f}: "
            f"{len(result.scored):,} eligible clients across "
            f"{len(result.cards)} segments."
        )
    theme.next_step("Open Results to see the decision cards at this threshold.")


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

    # --- page chrome: slim bar, brand, current-run context banner ---
    theme.utility_bar()
    theme.nav_bar()
    theme.context_banner(_run_context_items())

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
            theme.hero_kpi_html(
                number,
                caption,
                foot=(
                    "Across all segments"
                    if st.session_state.get(RUN_RESULT_KEY) is not None
                    else "Run a promo to see expected joiners"
                ),
            ),
            unsafe_allow_html=True,
        )

    st.write("")

    (
        new_promo_tab,
        results_tab,
        whatif_tab,
        personas_tab,
        past_promos_tab,
        ask_assistant_tab,
    ) = st.tabs(theme.TAB_LABELS)

    with new_promo_tab:
        _render_new_promo_tab()
    with results_tab:
        _render_results_tab()
    with whatif_tab:
        _render_whatif_tab()
    with personas_tab:
        persona_page.render_persona_tab(run_result_key=RUN_RESULT_KEY)
    with past_promos_tab:
        _render_past_promos_tab()
    with ask_assistant_tab:
        _render_ask_assistant_tab()


main()