"""Promo id generation for the Part 5 webapp."""

from __future__ import annotations

import re
from typing import Iterable

# Matches ids of the form NEW-### where ### is one or more digits.
_NEW_ID_PATTERN = re.compile(r"^NEW-(\d+)$")


def next_promo_id(existing: Iterable[str]) -> str:
    """Return the next promo id in the ``NEW-###`` sequence.

    Only ids matching ``NEW-\\d+`` count toward the max; any other id
    (e.g. ``"P001"``) is ignored. When no matching id exists the result is
    ``"NEW-001"``; otherwise it is ``NEW-`` followed by one past the max
    numeric part, zero-padded to three digits. The result always matches
    the pattern ``NEW-\\d{3}`` (for numbers up to 999; larger numbers are
    not padded further).
    """
    max_seen: int | None = None
    for item in existing:
        if item is None:
            continue
        match = _NEW_ID_PATTERN.match(str(item))
        if match is None:
            continue
        value = int(match.group(1))
        if max_seen is None or value > max_seen:
            max_seen = value

    next_value = 1 if max_seen is None else max_seen + 1
    return f"NEW-{next_value:03d}"
