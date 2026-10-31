"""Card_Builder for the Part4_Cards_Pipeline.

Aggregates the classified per-Lead frame into one Card per Cell
(``promo_id``, ``segment``). Each Card carries the Cell's client counts and
breakdowns, the top drivers and dominant channel, the expected joiners / cost /
value with a 90% range, a recommended action, and a fixed message angle.

This module never writes any output and never halts the run on input-shape
grounds; the Input_Loader has already guaranteed valid, coerced frames and the
Lead_Classifier has attached the exclusion, best_channel, and control columns.

The internal entry point is ``_build_cards_from_frames(frames, cfg)``, which
classifies the frames (if not already classified) and returns the list of
Cards. The Reporter in ``main`` uses this entry when it already holds the
loaded frames. The public ``build_cards(segments_df, promo_dict)`` convenience
wrapper loads the reference frames, synthesizes a promo_history frame from
``promo_dict``, runs the classifier, and returns the Cards in memory without
writing any file or printing (Requirement 5.8).

Card field schema (built incrementally across tasks 5.1, 5.3, 5.5):

- ``promo_id`` (str), ``segment`` (str), ``n_clients`` (int)
- ``excluded_by_reason`` (dict reason -> count), ``control_count`` (int),
  ``sendable_count`` (int)
- ``top_drivers`` (list[str]), ``dominant_channel`` (str)
- ``expected_joiners``, ``joiners_90_low``, ``joiners_90_high``,
  ``total_channel_cost``, ``expected_value``, ``action``, ``message_angle``

Task 5.1 implements the per-Cell counts and breakdowns, the top drivers, and
the dominant channel (Requirements 5.1, 5.2, 5.3). Task 5.3 adds the expected
joiners, total channel cost, expected value, and the 90% range over the Cell's
Sendable_Leads (Requirements 5.4, 5.5, 5.6). Task 5.5 adds the recommended
``action`` from the four-way rule (Requirement 5.7), the fixed per-segment
``message_angle`` (Requirement 5.8), and the public ``build_cards`` wrapper.
"""

from __future__ import annotations

import math
from collections import Counter

import pandas as pd

from . import loader
from .classify import classify
from .config import (
    CHANNEL_PRIORITY,
    MESSAGE_ANGLES,
    VALUE_PER_JOIN_PHP,
    Z_90,
    Config,
)

# The number of top_driver_1 values recorded per Cell (Requirement 5.2).
TOP_DRIVERS_N = 3

# Rank of each channel in the priority order, for breaking dominant_channel
# ties (Requirement 5.3). Lower rank wins.
_CHANNEL_RANK = {channel: i for i, channel in enumerate(CHANNEL_PRIORITY)}


def _top_drivers(cell: pd.DataFrame) -> list[str]:
    """The three most common ``top_driver_1`` values among the Cell's Leads.

    Ordered by descending count and then ascending value, recording fewer than
    three when the Cell has fewer than three distinct ``top_driver_1`` values
    (Requirement 5.2).
    """
    counts = Counter(cell["top_driver_1"])
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [value for value, _count in ordered[:TOP_DRIVERS_N]]


def _dominant_channel(sendable: pd.DataFrame) -> str:
    """The most common ``best_channel`` among the Cell's Sendable_Leads.

    Ties are broken by the priority order In-app, Email, SMS (Requirement 5.3).
    Empty when the Cell has no Sendable_Leads (Requirement 5.6).
    """
    if sendable.empty:
        return ""
    counts = Counter(sendable["best_channel"])
    # Most common first; break ties by the channel's priority rank (lower wins).
    best = min(
        counts.items(),
        key=lambda kv: (-kv[1], _CHANNEL_RANK.get(kv[0], len(CHANNEL_PRIORITY))),
    )
    return best[0]


def _join_estimates(sendable: pd.DataFrame, cost_map: dict[str, float]) -> dict:
    """The expected joiners, channel cost, expected value, and 90% range.

    Over the Cell's Sendable_Leads (Requirements 5.4, 5.5):

    - ``expected_joiners`` = Σ ``p_join``.
    - ``total_channel_cost`` = Σ ``cost_map[best_channel]``.
    - ``expected_value`` = ``expected_joiners × VALUE_PER_JOIN_PHP −
      total_channel_cost``.
    - ``joiners_90_low`` / ``joiners_90_high`` by binomial normal
      approximation treating each Sendable_Lead as an independent Bernoulli
      trial: ``mean = Σ p_join``, ``var = Σ p_join·(1−p_join)``, range
      ``mean ± Z_90·√var`` with ``low`` clamped to a lower bound of 0.

    A Cell with zero Sendable_Leads gets ``expected_joiners``, both range
    bounds, ``total_channel_cost``, and ``expected_value`` all 0
    (Requirement 5.6); the empty sums below already evaluate to 0.
    """
    p_join = sendable["p_join"]
    expected_joiners = float(p_join.sum())
    total_channel_cost = float(
        sendable["best_channel"].map(lambda ch: cost_map.get(ch, 0.0)).sum()
    )
    expected_value = expected_joiners * VALUE_PER_JOIN_PHP - total_channel_cost

    variance = float((p_join * (1.0 - p_join)).sum())
    spread = Z_90 * math.sqrt(variance)
    joiners_90_low = max(0.0, expected_joiners - spread)
    joiners_90_high = expected_joiners + spread

    return {
        "expected_joiners": expected_joiners,
        "joiners_90_low": joiners_90_low,
        "joiners_90_high": joiners_90_high,
        "total_channel_cost": total_channel_cost,
        "expected_value": expected_value,
    }


def _action(segment: str, expected_value: float, mechanic: str) -> str:
    """The recommended action from the four-way decision rule (Requirement 5.7).

    First match wins, in this fixed order:

    1. ``"Prioritize"`` when ``segment == "Ready Toppers"`` and ``EV > 0``.
    2. else ``"Offer lower tier"`` when the promo ``mechanic == "TOP_UP"`` and
       ``segment == "Willing but Stretched"`` and ``EV > 0``.
    3. else ``"Include"`` when ``EV > 0``.
    4. else ``"Skip"``.
    """
    if segment == "Ready Toppers" and expected_value > 0:
        return "Prioritize"
    if (
        mechanic == "TOP_UP"
        and segment == "Willing but Stretched"
        and expected_value > 0
    ):
        return "Offer lower tier"
    if expected_value > 0:
        return "Include"
    return "Skip"


def _build_card(
    promo_id: str,
    segment: str,
    cell: pd.DataFrame,
    cost_map: dict[str, float],
    mechanic_map: dict[str, str],
) -> dict:
    """Build one Card for a single Cell from its classified Leads.

    Records the segment, ``n_clients``, the ``excluded_by_reason`` breakdown,
    the control and sendable counts (Requirement 5.1), the ``top_drivers``
    (Requirement 5.2), the ``dominant_channel`` (Requirement 5.3), the expected
    joiners, total channel cost, expected value, and 90% range over the
    Sendable_Leads (Requirements 5.4, 5.5, 5.6), the recommended ``action`` from
    the four-way rule (Requirement 5.7), and the fixed ``message_angle`` for the
    segment (Requirement 5.8). ``mechanic_map`` resolves the promo's mechanic
    (``promo_id`` -> mechanic) for the action rule.
    """
    excluded = cell[cell["excluded"]]
    sendable = cell[(~cell["excluded"]) & (cell["control"] == 0)]
    control_count = int(((~cell["excluded"]) & (cell["control"] == 1)).sum())

    # excluded_by_reason: reason -> count, one entry per reason present.
    excluded_by_reason = {
        str(reason): int(count)
        for reason, count in excluded["exclusion_reason"].value_counts().items()
    }

    estimates = _join_estimates(sendable, cost_map)
    mechanic = str(mechanic_map.get(str(promo_id), ""))

    return {
        "promo_id": str(promo_id),
        "segment": str(segment),
        "n_clients": int(len(cell)),
        "excluded_by_reason": excluded_by_reason,
        "control_count": control_count,
        "sendable_count": int(len(sendable)),
        "top_drivers": _top_drivers(cell),
        "dominant_channel": _dominant_channel(sendable),
        **estimates,
        "action": _action(str(segment), estimates["expected_value"], mechanic),
        "message_angle": MESSAGE_ANGLES.get(str(segment), ""),
    }


def _cost_map(frames: dict[str, pd.DataFrame]) -> dict[str, float]:
    """The ``channel -> per-send cost`` map from the Channel_Costs_File.

    The Channel_Costs_File channel values match the best_channel labels
    exactly, so the cost lookup over Sendable_Leads is a direct map
    (Requirement 5.4). Falls back to an empty map if the frame is absent so
    callers that build frames without it (e.g. the partition tests) still work,
    with every cost treated as 0.
    """
    channel_costs = frames.get("channel_costs")
    if channel_costs is None:
        return {}
    return {
        str(channel): float(cost)
        for channel, cost in zip(
            channel_costs["channel"], channel_costs["cost_php_per_message"]
        )
    }


def _mechanic_map(frames: dict[str, pd.DataFrame]) -> dict[str, str]:
    """The ``promo_id -> mechanic`` map for the action rule (Requirement 5.7).

    Falls back to an empty map if the promo_history frame is absent so callers
    that build frames without it still work, with every mechanic treated as
    ``""`` (no promo-specific action branch).
    """
    promo_history = frames.get("promo_history")
    if promo_history is None or "mechanic" not in promo_history.columns:
        return {}
    return {
        str(promo_id): str(mechanic)
        for promo_id, mechanic in zip(
            promo_history["promo_id"], promo_history["mechanic"]
        )
    }


def build_cards_from_classified(
    leads: pd.DataFrame, frames: dict[str, pd.DataFrame]
) -> list[dict]:
    """Build one Card per Cell from an already-classified Leads frame.

    Groups the classified Leads by Cell (``promo_id``, ``segment``) and returns
    the list of Cards. This is the entry the Reporter uses when it has already
    run the Lead_Classifier once, avoiding a redundant second classification;
    ``frames`` supplies the ``channel_costs`` and ``promo_history`` reference
    frames for the cost and mechanic maps.
    """
    cost_map = _cost_map(frames)
    mechanic_map = _mechanic_map(frames)

    cards: list[dict] = []
    for (promo_id, segment), cell in leads.groupby(
        ["promo_id", "segment"], sort=False
    ):
        cards.append(_build_card(promo_id, segment, cell, cost_map, mechanic_map))
    return cards


def _build_cards_from_frames(
    frames: dict[str, pd.DataFrame], cfg: Config
) -> list[dict]:
    """Classify the frames and build one Card per Cell.

    The internal entry point used when holding the loaded (unclassified)
    frames. Runs the Lead_Classifier, then delegates to
    :func:`build_cards_from_classified`.
    """
    leads = classify(frames, cfg)
    return build_cards_from_classified(leads, frames)


def build_cards(
    segments_df: pd.DataFrame, promo_dict: dict[str, dict]
) -> list[dict]:
    """Public convenience wrapper: build the Cards for ``segments_df`` in memory.

    The public API named in Requirement 5.8. ``promo_dict`` maps
    ``promo_id -> {"mechanic": str, "channels": list[str] (Allowed_Channels),
    ...}``. The wrapper loads the reference frames (NDB, contact history,
    channel costs, customer DNA) via ``Config`` defaults, synthesizes a
    ``promo_history`` frame from ``promo_dict`` (so the classifier's channel
    gating and the action rule's mechanic lookup see the supplied promos),
    assembles a ``frames`` dict with the supplied ``segments_df``, runs the
    classifier internally, and returns the list of Cards **in memory without
    writing any file or printing** (Requirement 5.8).

    Side effects (writing ``cards.json`` / the per-Cell lead CSVs and printing
    the summary) live only in the Reporter / ``main``, so an application can
    embed card building by calling this wrapper without triggering output.
    """
    cfg = Config()
    frames = loader.load(cfg)

    # Synthesize a promo_history frame from promo_dict so the classifier sees
    # the supplied promos' Allowed_Channels and the action rule sees their
    # mechanic. The classifier parses the comma-separated ``channels`` string
    # back into the Allowed_Channels set, so join the supplied channel list.
    promo_rows = [
        {
            "promo_id": str(promo_id),
            "channels": ", ".join(info.get("channels", []) or []),
            "mechanic": str(info.get("mechanic", "")),
        }
        for promo_id, info in promo_dict.items()
    ]
    frames = {**frames, "segments": segments_df, "promo_history": pd.DataFrame(
        promo_rows, columns=["promo_id", "channels", "mechanic"]
    )}

    return _build_cards_from_frames(frames, cfg)
