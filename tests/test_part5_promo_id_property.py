"""Property-based test for the Part 5 promo-id generator.

# Feature: part5-webapp, Property 3: next_promo_id is the successor of the max NEW-id and always matches NEW-\\d{3}

Covers Property 3 of the part5-webapp spec: for any iterable of existing ids,
:func:`webapp_core.promo_id.next_promo_id` returns ``NEW-001`` when none match
``NEW-###``, otherwise ``NEW-`` + (max matched number + 1) zero-padded to three
digits; the result always matches ``NEW-\\d{3}`` (Requirement 3.1).

This is a relationship property: the test asserts the function's output against
an *independent* reference that re-scans the id list for the max ``NEW-###``
number itself (not reusing the production regex object) and formats the
successor directly. A divergence therefore signals a real bug rather than a
shared mistake.
"""

from __future__ import annotations

import re

from hypothesis import given, settings

from webapp_core.promo_id import next_promo_id

from tests.strategies_part5 import existing_promo_ids

# The result must always match NEW-### with at least three digits.
_RESULT_PATTERN = re.compile(r"^NEW-\d{3,}$")

# Independent id matcher (a separately compiled pattern, not the production one).
_REFERENCE_MATCHER = re.compile(r"^NEW-(\d+)$")


def _reference_next_id(existing) -> str:
    """Independently compute the expected next id from the id list.

    Scans for the max numeric part among ids matching ``NEW-\\d+`` (ignoring
    ``None`` and non-matching ids), then formats ``NEW-001`` when none matched
    or ``NEW-<max+1>`` zero-padded to three digits otherwise.
    """
    max_seen = None
    for item in existing:
        if item is None:
            continue
        match = _REFERENCE_MATCHER.match(str(item))
        if match is None:
            continue
        value = int(match.group(1))
        if max_seen is None or value > max_seen:
            max_seen = value
    next_value = 1 if max_seen is None else max_seen + 1
    return f"NEW-{next_value:03d}"


@settings(max_examples=300, deadline=None)
@given(existing_promo_ids())
def test_next_promo_id_is_successor_of_max_new_id(existing):
    """``next_promo_id`` is the successor of the max NEW-id and well-formed.

    **Validates: Requirements 3.1**
    """
    result = next_promo_id(existing)

    # Always a well-formed NEW-### id (at least three digits, zero-padded).
    assert _RESULT_PATTERN.match(result), result

    # Matches the independent successor-of-max computation.
    assert result == _reference_next_id(existing)


@settings(max_examples=50, deadline=None)
@given(existing_promo_ids())
def test_next_promo_id_is_unused_and_above_all_existing(existing):
    """The generated id is not already present and exceeds every existing NEW-id.

    **Validates: Requirements 3.1**
    """
    result = next_promo_id(existing)
    result_value = int(_REFERENCE_MATCHER.match(result).group(1))

    for item in existing:
        if item is None:
            continue
        match = _REFERENCE_MATCHER.match(str(item))
        if match is not None:
            # The new id's number strictly exceeds every existing NEW-### number.
            assert result_value > int(match.group(1))
