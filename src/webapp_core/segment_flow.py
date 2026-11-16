"""Where each segment's clients go (Part 9 round 2, Requirements 24 and 27).

Pure, no Streamlit. Every client in a segment ends up in exactly one of:

- **Not Contacted**: left out by the contact rules (the sum of the card's
  ``excluded_by_reason``),
- **Control Group**: held back to measure the promo (``control_count``),
- **Sendable**: the leads in the download file (``sendable_count``).

So Clients = Not Contacted + Control Group + Sendable. These rows feed the
Results "Where Each Segment's Clients Go" chart and table. Nothing is
recomputed: every value is read from the Run's cards. When a card does not
add up, :func:`reconciles` says so and the values are shown as given.

``SEGMENT_DISPLAY_ORDER`` is the one fixed segment order for tables that
list segments best first (the What-If table and this chart).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

SEGMENT_DISPLAY_ORDER: tuple[str, ...] = (
    "Ready Toppers",
    "Willing but Stretched",
    "Untapped Wealth",
    "Not Now",
)


def display_rank(segment: str) -> tuple[int, str]:
    """Sort key: the display order first, any other name after, by name."""
    name = str(segment)
    if name in SEGMENT_DISPLAY_ORDER:
        return SEGMENT_DISPLAY_ORDER.index(name), ""
    return len(SEGMENT_DISPLAY_ORDER), name


def in_display_order(segments: Iterable[str]) -> list[str]:
    """The segment names sorted by :func:`display_rank` (stable, no repeats)."""
    return sorted(dict.fromkeys(str(s) for s in segments), key=display_rank)


@dataclass(frozen=True)
class FlowRow:
    """One segment's split (or the Total)."""

    segment: str
    clients: int
    not_contacted: int
    control: int
    sendable: int
    forecast: float

    @property
    def parts_sum(self) -> int:
        return self.not_contacted + self.control + self.sendable


def _int(card: Mapping[str, Any], key: str) -> int:
    try:
        return int(card.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _float(card: Mapping[str, Any], key: str) -> float:
    try:
        return float(card.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def flow_row(card: Mapping[str, Any]) -> FlowRow:
    """Read one card into a :class:`FlowRow` (no calculation beyond a sum)."""
    excluded = card.get("excluded_by_reason") or {}
    try:
        not_contacted = sum(int(v or 0) for v in dict(excluded).values())
    except (TypeError, ValueError):
        not_contacted = 0
    return FlowRow(
        segment=str(card.get("segment", "")),
        clients=_int(card, "n_clients"),
        not_contacted=not_contacted,
        control=_int(card, "control_count"),
        sendable=_int(card, "sendable_count"),
        forecast=_float(card, "expected_joiners"),
    )


def flow_rows(cards: Sequence[Mapping[str, Any]]) -> list[FlowRow]:
    """One row per card, in the display order."""
    rows = [flow_row(c) for c in cards]
    return sorted(rows, key=lambda r: display_rank(r.segment))


def flow_total(rows: Sequence[FlowRow]) -> FlowRow:
    """The Total row: each column summed (the forecast unrounded)."""
    return FlowRow(
        segment="Total",
        clients=sum(r.clients for r in rows),
        not_contacted=sum(r.not_contacted for r in rows),
        control=sum(r.control for r in rows),
        sendable=sum(r.sendable for r in rows),
        forecast=sum(r.forecast for r in rows),
    )


def reconciles(row: FlowRow) -> bool:
    """True when Clients = Not Contacted + Control Group + Sendable."""
    return row.clients == row.parts_sum
