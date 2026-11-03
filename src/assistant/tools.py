"""The four tools that wrap existing webapp_core functions.

This module exposes the campaign tools the assistant can call and the Bedrock
Converse ``toolSpec`` JSON schemas that advertise them. The two current-run
card tools (:func:`get_card`, :func:`compare_segments`) read straight from the
in-memory ``RunResult.cards`` built by Part 4's ``build_cards`` -- they compute
no campaign number themselves, so the assistant always mirrors the webapp's own
numbers (Requirements 2.2, 2.3). Both return a :class:`~assistant.models.ToolResult`
tagged with the tool name and an ``ok`` flag, carrying segment-level data only
and never a ``client_id`` (Requirement 2.6).

The remaining tools ``what_if`` and ``past_promo_accuracy`` are implemented in a
later task; here only their :data:`TOOL_SPECS` schema entries are defined so the
Bedrock driver can advertise all four tools.
"""

from __future__ import annotations

from typing import Any

from assistant.models import ToolResult

# The four Part 3 Segment_Labels, in priority order. Used both as the enum for
# the ``get_card`` tool schema and as the keys :func:`compare_segments` returns.
SEGMENT_LABELS = [
    "Ready Toppers",
    "Willing but Stretched",
    "Untapped Wealth",
    "Not Now",
]

# The card dict fields surfaced by the card tools. These are a subset of the
# keys Part 4's ``build_cards`` writes per Cell; ``segment`` identifies the card
# within ``RunResult.cards`` and is used to locate it, not surfaced as data.
_CARD_FIELDS = (
    "action",
    "dominant_channel",
    "message_angle",
    "expected_joiners",
    "joiners_90_low",
    "joiners_90_high",
    "expected_value",
    "top_drivers",
    "excluded_by_reason",
)

# Fixed notes for the not-ok branches, kept here so both tools and their tests
# share one spelling.
_NEEDS_A_RUN = "run a promo first"
_NO_CARD = "no card for that segment"


def _card_data(card: dict[str, Any]) -> dict[str, Any]:
    """Project one card dict down to the surfaced, segment-level fields.

    Keeps only :data:`_CARD_FIELDS`; never copies ``client_id`` or any other
    key, so no individual client data crosses the tool boundary
    (Requirement 2.6).
    """
    return {field: card.get(field) for field in _CARD_FIELDS}


def _find_card(segment: str, cards: list[dict]) -> dict | None:
    """The card for ``segment`` within ``cards``, or ``None`` when absent.

    A card is identified by its ``segment`` key (the Part 3 Segment_Label).
    """
    for card in cards:
        if card.get("segment") == segment:
            return card
    return None


def get_card(segment: str, run_result) -> ToolResult:
    """Return one segment's current-run card fields (Requirement 2.2).

    When no promo has been run yet (``run_result is None``) returns
    ``ok=False`` with a needs-a-run note. When a run exists but has no card for
    ``segment`` returns ``ok=False`` with a not-available note. Otherwise
    returns ``ok=True`` with that card's surfaced fields (``action``,
    ``dominant_channel``, ``message_angle``, ``expected_joiners``,
    ``joiners_90_low``/``joiners_90_high``, ``expected_value``, ``top_drivers``,
    ``excluded_by_reason``). Never includes a ``client_id`` (Requirement 2.6).
    """
    if run_result is None:
        return ToolResult("get_card", False, {}, note=_NEEDS_A_RUN)

    card = _find_card(segment, run_result.cards)
    if card is None:
        return ToolResult("get_card", False, {}, note=_NO_CARD)

    return ToolResult("get_card", True, _card_data(card))


def compare_segments(run_result) -> ToolResult:
    """Return all four segments' current-run cards together (Requirement 2.3).

    When no promo has been run yet (``run_result is None``) returns
    ``ok=False`` with a needs-a-run note. Otherwise returns ``ok=True`` with the
    surfaced fields of every card present in the run, keyed by Segment_Label.
    Segments without a card are simply absent from the mapping. Never includes a
    ``client_id`` (Requirement 2.6).
    """
    if run_result is None:
        return ToolResult("compare_segments", False, {}, note=_NEEDS_A_RUN)

    by_segment: dict[str, dict[str, Any]] = {}
    for card in run_result.cards:
        segment = card.get("segment")
        if segment in SEGMENT_LABELS:
            by_segment[str(segment)] = _card_data(card)

    return ToolResult("compare_segments", True, by_segment)


# The Bedrock Converse toolSpec schemas advertising the four tools. Each entry
# follows the Converse shape ``{"name", "description", "inputSchema": {"json":
# {...}}}``. ``what_if`` and ``past_promo_accuracy`` are implemented in a later
# task; their schemas are defined here so the driver can advertise them now.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_card",
        "description": (
            "Return the current run's recommendation card for one segment: its "
            "action, dominant channel, message angle, expected joiners with a "
            "90% range, expected value, top drivers, and exclusion breakdown."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "segment": {
                        "type": "string",
                        "enum": list(SEGMENT_LABELS),
                        "description": "The segment label to look up.",
                    }
                },
                "required": ["segment"],
            }
        },
    },
    {
        "name": "compare_segments",
        "description": (
            "Return the current run's recommendation cards for all four "
            "segments together, for comparing or prioritizing across segments."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {},
            }
        },
    },
    {
        "name": "what_if",
        "description": (
            "Re-run the current promo with a different top-up threshold (in "
            "PHP) and report the per-segment totals and the delta versus the "
            "current run."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "threshold_php": {
                        "type": "number",
                        "description": "The new top-up threshold in PHP.",
                    }
                },
                "required": ["threshold_php"],
            }
        },
    },
    {
        "name": "past_promo_accuracy",
        "description": (
            "Compare the predicted and actual joiners for a past promo by its "
            "promo id, per segment."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "promo_id": {
                        "type": "string",
                        "description": "The past promo id, e.g. PROMO-2024-03.",
                    }
                },
                "required": ["promo_id"],
            }
        },
    },
]


# ---------------------------------------------------------------------------
# what_if and past_promo_accuracy (Requirements 2.1, 2.4, 2.5, 2.6)
# ---------------------------------------------------------------------------

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from part1_optin.config import Config as Part1Config
from webapp_core.model_io import load_model
from webapp_core.past_promos import predicted_vs_actual, read_sendable_ids_by_cell
from webapp_core.run_promo import run_promo

# Project paths resolved from this file so the tools work from any cwd, exactly
# as app/main.py resolves them from __file__ (not from the process cwd).
_ROOT = Path(__file__).resolve().parents[2]
_OUTPUTS_DIR = _ROOT / "outputs"
_DATA_DIR = _ROOT / "data"

_CUSTOMER_DNA_PATH = _DATA_DIR / "customer_dna.csv"
_ADB_MONTHLY_PATH = _DATA_DIR / "adb_monthly.csv"
_FEATURES_PART2_PATH = _OUTPUTS_DIR / "features_part2.csv"
_CARDS_JSON_PATH = _OUTPUTS_DIR / "cards.json"
_PROMO_LEADS_PATH = _DATA_DIR / "promo_leads.csv"
_LEADS_DIR = _OUTPUTS_DIR / "leads"

# The run-pipeline note, matching app/main.py.RUN_PIPELINE_MESSAGE so the chat
# relays the same guidance the New Promo / Past Promos tabs show on a missing
# artifact.
RUN_PIPELINE_MESSAGE = (
    "The fitted Part 1 model could not be found. Run "
    "`python src/run_pipeline.py` (with `PYTHONPATH=src`) to regenerate the "
    "model and the on-disk artifacts the app reads, then try again."
)

# The not-available note for a past promo whose on-disk artifacts are missing.
_NOT_AVAILABLE = "past-promo data not available"

# The per-card totals surfaced by what_if, keyed by Segment_Label. These are a
# subset of the keys Part 4's build_cards writes; none is a client_id.
_TOTAL_FIELDS = (
    "expected_joiners",
    "joiners_90_low",
    "joiners_90_high",
    "expected_value",
    "sendable_count",
)


@dataclass(frozen=True)
class RunContext:
    """The reusable pieces a re-run needs, assembled once like ``_execute_run``.

    Holds the reloaded fitted Part 1 model, the Part 1 ``Config`` ``score_promo``
    reads its client source paths from, and the ``data/`` frames bundle
    ``run_promo`` consumes (``customer_dna``, ``adb_monthly``, ``features``).
    :func:`build_run_context` builds one the same way ``app/main.py._execute_run``
    does, so ``what_if`` re-runs over the exact same inputs the webapp uses.
    """

    model: Any
    config: Any
    data: dict[str, pd.DataFrame]


def _load_data_bundle() -> dict[str, pd.DataFrame]:
    """Load the ``data/`` frames bundle ``run_promo`` consumes.

    Mirrors ``app/main.py._load_data_bundle`` but resolves its paths from this
    file's location so the tool works regardless of the process cwd.
    """
    return {
        "customer_dna": pd.read_csv(_CUSTOMER_DNA_PATH),
        "adb_monthly": pd.read_csv(_ADB_MONTHLY_PATH),
        "features": pd.read_csv(_FEATURES_PART2_PATH),
    }


def build_run_context() -> RunContext:
    """Assemble a :class:`RunContext` the same way ``_execute_run`` does.

    Reloads the fitted model via ``webapp_core.model_io.load_model`` from
    ``outputs/``, constructs a Part 1 ``Config``, and loads the ``data/`` bundle,
    resolving every path relative to the project root (not the cwd).

    Raises:
        FileNotFoundError: If the model artifact (or a required ``data/`` frame)
            is missing, so the caller (the engine or ``what_if``) can fall back
            to the run-pipeline note rather than surfacing a partial context.
    """
    model = load_model(_OUTPUTS_DIR)
    data = _load_data_bundle()
    config = Part1Config()
    return RunContext(model=model, config=config, data=data)


def _totals_by_segment(cards: list[dict]) -> dict[str, dict[str, Any]]:
    """Project each card down to its surfaced per-segment totals.

    Keeps only :data:`_TOTAL_FIELDS`, keyed by Segment_Label; never copies a
    ``client_id`` or any other key, so no individual client data crosses the
    tool boundary (Requirement 2.6).
    """
    totals: dict[str, dict[str, Any]] = {}
    for card in cards:
        segment = card.get("segment")
        if segment in SEGMENT_LABELS:
            totals[str(segment)] = {
                field: card.get(field) for field in _TOTAL_FIELDS
            }
    return totals


def _delta_by_segment(
    new_totals: dict[str, dict[str, Any]],
    old_totals: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Per-segment change in each numeric total (new minus current run).

    Covers every segment present in either run; a total missing on one side is
    treated as 0 so a segment that appears or disappears still shows a delta.
    """
    deltas: dict[str, dict[str, float]] = {}
    for segment in set(new_totals) | set(old_totals):
        new_card = new_totals.get(segment, {})
        old_card = old_totals.get(segment, {})
        deltas[segment] = {
            field: float(new_card.get(field) or 0.0)
            - float(old_card.get(field) or 0.0)
            for field in _TOTAL_FIELDS
        }
    return deltas


def what_if(threshold_php, run_result, run_context) -> ToolResult:
    """Re-run the current promo with only ``threshold_php`` changed (Req 2.4).

    Rebuilds the :class:`~webapp_core.run_promo.PromoSpec` from
    ``run_result.promo_spec`` via ``dataclasses.replace`` with the new threshold,
    re-runs ``webapp_core.run_promo.run_promo`` over the current eligible
    audience using the model/config/data in ``run_context`` (no retraining), and
    returns the resulting per-segment totals plus the delta versus the current
    run. Returns ``ok=False`` with a needs-a-run note when no promo has been run
    yet (``run_result is None``), and ``ok=False`` with the run-pipeline note on
    a missing model artifact (``FileNotFoundError``). Never includes a
    ``client_id`` (Requirement 2.6).
    """
    if run_result is None:
        return ToolResult("what_if", False, {}, note=_NEEDS_A_RUN)

    spec = replace(run_result.promo_spec, threshold_php=float(threshold_php))

    try:
        new_result = run_promo(
            spec,
            model=run_context.model,
            config=run_context.config,
            data=run_context.data,
        )
    except FileNotFoundError:
        return ToolResult("what_if", False, {}, note=RUN_PIPELINE_MESSAGE)

    new_totals = _totals_by_segment(new_result.cards)
    old_totals = _totals_by_segment(run_result.cards)

    data = {
        "threshold_php": float(threshold_php),
        "totals_by_segment": new_totals,
        "delta_by_segment": _delta_by_segment(new_totals, old_totals),
    }
    return ToolResult("what_if", True, data)


def past_promo_accuracy(promo_id) -> ToolResult:
    """Predicted vs actual join rate per segment for a past promo (Req 2.5).

    Loads ``outputs/cards.json``, reads ``data/promo_leads.csv``, then calls
    ``read_sendable_ids_by_cell`` and ``predicted_vs_actual`` exactly as the Past
    Promos tab does, and keeps only ``(segment, predicted, actual)`` per row for
    the requested ``promo_id``. Returns ``ok=False`` with a not-available note
    when ``outputs/cards.json`` or ``data/promo_leads.csv`` is missing
    (``FileNotFoundError``). Never includes a ``client_id`` (Requirement 2.6).
    """
    try:
        with open(_CARDS_JSON_PATH, encoding="utf-8") as fh:
            cards = json.load(fh)
        promo_leads = pd.read_csv(_PROMO_LEADS_PATH)
    except FileNotFoundError:
        return ToolResult("past_promo_accuracy", False, {}, note=_NOT_AVAILABLE)

    sendable_ids_by_cell = read_sendable_ids_by_cell(cards, leads_dir=_LEADS_DIR)
    rows = predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell)

    wanted = str(promo_id)
    segments = [
        {
            "segment": str(row.get("segment")),
            "predicted": row.get("predicted"),
            "actual": row.get("actual"),
        }
        for row in rows
        if str(row.get("promo_id")) == wanted
    ]

    if not segments:
        return ToolResult(
            "past_promo_accuracy", False, {}, note=_NOT_AVAILABLE
        )

    data = {"promo_id": wanted, "segments": segments}
    return ToolResult("past_promo_accuracy", True, data)
