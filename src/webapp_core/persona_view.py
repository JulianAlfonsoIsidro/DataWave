"""Pure "Expected Joiners By Persona" view-model (no Streamlit imports).

A new presentation over the existing ``CardPersonaBreakdown`` /
``GroupCardBreakdown`` rows in ``webapp_core.personas``. It adds no modelling:
the joiner numbers come straight from those rows, and the "Other Personas"
amount is defined as the remainder of the card's expected joiners.

Governing spec: Part 7 Requirements 7.1 to 7.12 (design section 8).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from webapp_core.card_view import round_half_up

OTHER_PERSONAS_NAME = "Other Personas"
UNAVAILABLE_TEXT = "Personas were not generated for this run."
NO_STAND_OUT_TAKEAWAY = "No persona stands out; one message fits this card."
_TIE_TOLERANCE = 1e-9

_KIND_PERSONA = "persona"


@dataclass(frozen=True)
class PersonaLine:
    """One persona row: sentence text, bar fill (0 to 100) and raw joiners."""

    text: str
    bar_pct: float
    joiners: float


@dataclass(frozen=True)
class PersonaSection:
    """The display-ready persona section of one decision card."""

    lines: tuple[PersonaLine, ...]
    total_line: str
    note: str
    takeaway: str
    unavailable_text: str | None
    # Extras for the renderer; defaults keep the design's constructor valid.
    total_joiners: int = 0
    total_leads: int = 0


def _finite(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _percent(joiners: float, leads: int) -> int:
    """Whole percent of ``joiners`` over ``leads`` clamped to 0..100 (7.2)."""
    if leads <= 0:
        return 0
    return int(min(100, max(0, round_half_up(joiners / leads * 100.0))))


def _line(name: str, joiners: float, leads: int) -> PersonaLine:
    joiners = max(0.0, _finite(joiners))
    if leads <= 0:
        return PersonaLine(f"{name}: no leads in this group", 0.0, joiners)
    pct = _percent(joiners, leads)
    n = round_half_up(joiners)
    return PersonaLine(
        f"{name}: about {n:,} of {leads:,} likely to join ({pct}%)", float(pct), joiners
    )


def _unavailable(segment: str) -> PersonaSection:
    return PersonaSection((), f"Total For {segment}", "", "", UNAVAILABLE_TEXT)


def build_persona_section(
    breakdown: Any | None, card_expected_joiners: float, segment: str
) -> PersonaSection:
    """Build the persona section for one card (Requirements 7.1 to 7.12).

    Args:
        breakdown: A ``CardPersonaBreakdown`` or ``GroupCardBreakdown`` (or any
            object with ``rows`` of ``PersonaJoinerRow``), or ``None``.
        card_expected_joiners: The card's expected joiners (Other Personas is
            the remainder after the listed personas).
        segment: The segment display name used in the total row and note.
    """
    rows = tuple(getattr(breakdown, "rows", ()) or ()) if breakdown is not None else ()
    if not rows:
        return _unavailable(segment)

    listed = [r for r in rows if getattr(r, "kind", _KIND_PERSONA) == _KIND_PERSONA]
    folded_leads = sum(
        max(0, int(r.leads)) for r in rows
        if getattr(r, "kind", _KIND_PERSONA) != _KIND_PERSONA
    )

    lines: list[PersonaLine] = []
    names: list[str] = []
    for r in listed:
        lines.append(_line(str(r.name), _finite(r.expected_joiners), max(0, int(r.leads))))
        names.append(str(r.name))

    card_total = max(0.0, _finite(card_expected_joiners))
    remainder = card_total - sum(l.joiners for l in lines)
    if remainder > _TIE_TOLERANCE:  # ignore float noise (7.6)
        lines.append(_line(OTHER_PERSONAS_NAME, remainder, folded_leads))
        names.append(OTHER_PERSONAS_NAME)

    # Takeaway: highest joiners, first in displayed order wins ties (7.7, 7.8).
    best_idx = -1
    best = 0.0
    for i, l in enumerate(lines):
        if l.joiners > best + _TIE_TOLERANCE:
            best, best_idx = l.joiners, i

    if best_idx < 0:
        takeaway, note = NO_STAND_OUT_TAKEAWAY, ""
    else:
        top = names[best_idx]
        takeaway = f"Most likely joiners are in {top}; lead the message with them."
        note = f"{top} is {round_half_up(best):,} of the {segment} total"

    return PersonaSection(
        lines=tuple(lines),
        total_line=f"Total For {segment}",
        note=note,
        takeaway=takeaway,
        unavailable_text=None,
        total_joiners=round_half_up(card_total),
        total_leads=sum(max(0, int(r.leads)) for r in rows),
    )
