"""Pure digit-diff plan for the CSS number roll (Part 8, F5, Requirement 11).

No Streamlit import. ``app/theme.py`` turns the plan into markup: each
``roll`` cell becomes a clipped 0-9 strip that slides from the previous digit
to the current one, ``enter`` cells fade in, ``static`` cells are plain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

DEFAULT_PLACEHOLDERS: tuple[str, ...] = ("--",)
_DIGITS = "0123456789"


@dataclass(frozen=True)
class RollCell:
    """One character of the current value.

    ``prev`` is the character at the same right-aligned position in the
    previous value (``None`` when there is none). ``kind`` is ``"roll"`` (both
    are digits and differ), ``"enter"`` (no counterpart) or ``"static"``.
    """

    char: str
    prev: str | None
    kind: Literal["static", "roll", "enter"]


def plan_roll(
    prev: str | None,
    cur: str,
    placeholders: Sequence[str] = DEFAULT_PLACEHOLDERS,
) -> tuple[RollCell, ...]:
    """Plan the roll from ``prev`` to ``cur`` (Requirements 11.2, 11.3, 11.5, 11.8).

    The strings are right-aligned (so units line up with units). With no
    previous value, a placeholder such as ``"--"``, or identical text, every
    cell is static. The cells always spell exactly ``cur``.
    """
    cur = str(cur)
    if prev is None or str(prev) in placeholders or str(prev) == cur:
        return tuple(RollCell(c, None, "static") for c in cur)
    prev = str(prev)
    offset = len(cur) - len(prev)
    cells: list[RollCell] = []
    for i, c in enumerate(cur):
        j = i - offset
        p = prev[j] if 0 <= j < len(prev) else None
        if p is None:
            kind = "enter"
        elif c in _DIGITS and p in _DIGITS and c != p:
            kind = "roll"
        else:
            kind = "static"
        cells.append(RollCell(c, p, kind))
    return tuple(cells)
