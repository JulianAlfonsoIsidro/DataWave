"""Pure decision-card view-model (no Streamlit imports).

Turns a read-only Part 4 card dict into plain-language display values. The
input dict is never mutated and ``outputs/cards.json`` is never rewritten
(Requirement 4.11); all relabeling and filtering happens here.

Governing spec: Part 7 Requirements 4.4 to 4.12 (design section 6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from labels import HIDDEN_DRIVER_CODES, plain_driver_phrase, plain_label

MAX_DRIVERS = 3
MAX_TOOLTIP_CHARS = 120
WHY_HEADING = "Why This Group:"
NOT_CONTACTED_HEADING = "Not Contacted:"
# One fixed choice for every card with no exclusions (Requirement 4.7).
NO_EXCLUSIONS_TEXT = "None"

LIKELY_TOOLTIP = "Our best estimate of how many people in this group will join the promo."
RANGE_TOOLTIP = "We are 90% sure the number who join will land between these two values."
VALUE_TOOLTIP = "Estimated peso value of the joiners, after the cost of contacting them."


@dataclass(frozen=True)
class StatView:
    """One stat tile: display label plus a plain-language tooltip (<= 120 chars)."""

    label: str
    tooltip: str


@dataclass(frozen=True)
class CardView:
    """Display-ready decision card (Requirements 4.4 to 4.10)."""

    title: str
    action: str
    channel: str
    angle: str
    why_heading: str
    drivers: tuple[str, ...]
    not_contacted_heading: str
    exclusions: tuple[str, ...]
    stats: tuple[StatView, StatView, StatView]
    # A ``webapp_core.persona_view.PersonaSection`` (task 12.1); typed loosely
    # so card_view does not depend on persona_view.
    persona_lines: Any | None = None


def round_half_up(x: float) -> int:
    """Round to the nearest integer, halves rounded up (Requirement 4.8)."""
    try:
        value = float(x)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(value):
        return 0
    return int(math.floor(value + 0.5))


def _num(card: Mapping[str, Any], key: str) -> float:
    try:
        value = float(card.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _drivers(card: Mapping[str, Any]) -> tuple[str, ...]:
    codes = [c for c in (card.get("top_drivers") or []) if c not in HIDDEN_DRIVER_CODES]
    return tuple(plain_driver_phrase(str(c)) for c in codes[:MAX_DRIVERS])


def _exclusions(card: Mapping[str, Any]) -> tuple[str, ...]:
    pairs: list[tuple[str, int]] = []
    for code, count in (card.get("excluded_by_reason") or {}).items():
        n = round_half_up(count)
        if n >= 1:
            pairs.append((plain_label(str(code)), n))
    pairs.sort(key=lambda p: (-p[1], p[0]))
    return tuple(f"{reason}: {n}" for reason, n in pairs)


def _tip(text: str) -> str:
    return text if len(text) <= MAX_TOOLTIP_CHARS else text[: MAX_TOOLTIP_CHARS - 3] + "..."


def build_card_view(card: Mapping[str, Any], *, persona: Any | None = None) -> CardView:
    """Build a :class:`CardView` from a Part 4 card dict without mutating it."""
    n = round_half_up(_num(card, "expected_joiners"))
    low = min(round_half_up(_num(card, "joiners_90_low")), n)
    high = max(round_half_up(_num(card, "joiners_90_high")), n)
    value = round_half_up(_num(card, "expected_value"))

    stats = (
        StatView(f"About {n:,} Likely To Join", _tip(LIKELY_TOOLTIP)),
        StatView(f"Likely Range: {low:,} To {high:,}", _tip(RANGE_TOOLTIP)),
        StatView(f"Expected Value: ₱{value:,}", _tip(VALUE_TOOLTIP)),
    )
    return CardView(
        title=f"{card.get('promo_id', '')} · {card.get('segment', '')}",
        action=str(card.get("action", "")),
        channel=str(card.get("dominant_channel", "")),
        angle=str(card.get("message_angle", "")),
        why_heading=WHY_HEADING,
        drivers=_drivers(card),
        not_contacted_heading=NOT_CONTACTED_HEADING,
        exclusions=_exclusions(card),
        stats=stats,
        persona_lines=persona,
    )
