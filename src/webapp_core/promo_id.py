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


# Matches past-campaign ids of the form P### (P001, P002, ...).
_PAST_ID_PATTERN = re.compile(r"^P(\d+)$")


def next_past_promo_ids(existing: Iterable[str], count: int) -> list[str]:
    """Return ``count`` new past-campaign ids after the highest ``P###`` seen.

    Used by the Past Promos import placeholder: with P001-P003 on file, two
    imported files become ``["P004", "P005"]``. Other ids are ignored.
    """
    numbers = [
        int(m.group(1))
        for m in (_PAST_ID_PATTERN.match(str(item)) for item in existing if item is not None)
        if m is not None
    ]
    start = max(numbers, default=0) + 1
    return [f"P{n:03d}" for n in range(start, start + max(count, 0))]
