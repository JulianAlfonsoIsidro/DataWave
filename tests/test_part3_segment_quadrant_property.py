"""Property-based test for ``part3_segments.segments.assign`` segmentation.

Covers Property 2 of the part3-segments spec: each Lead's ``segment`` is the
2x2 quadrant of ``(score_high, capacity_high)`` mapped onto the four SEGMENTS
labels, and ``capacity_high`` is exactly ``capacity_php >= threshold_php`` with
a missing threshold (promo absent from the promo history) forcing capacity-low.

The assertion is made against an independent, straightforward recompute of the
expected label from the quadrant rather than a restatement of the vectorized
``np.select`` implementation, and against an independent per-promo threshold
lookup rebuilt from the promo-history frame.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings

from part3_segments.config import SEGMENTS
from part3_segments.segments import assign
from tests.strategies_part3 import segment_inputs

# SEGMENTS is ordered by the (score_high, capacity_high) quadrant:
#   index 0 -> high / high  -> "Ready Toppers"
#   index 1 -> high / low   -> "Willing but Stretched"
#   index 2 -> low  / high  -> "Untapped Wealth"
#   index 3 -> low  / low   -> "Not Now"
READY_TOPPERS, WILLING_STRETCHED, UNTAPPED_WEALTH, NOT_NOW = SEGMENTS


def _expected_label(score_high: bool, capacity_high: bool) -> str:
    """Independently map a quadrant to its SEGMENTS label (no ``np.select``)."""
    if score_high and capacity_high:
        return READY_TOPPERS
    if score_high and not capacity_high:
        return WILLING_STRETCHED
    if not score_high and capacity_high:
        return UNTAPPED_WEALTH
    return NOT_NOW


def _reference_thresholds(promo_history: pd.DataFrame) -> dict[str, float]:
    """Independently build each promo's ``threshold_php`` lookup.

    Promos absent from the promo-history frame are simply not in the mapping,
    so the caller treats a miss as "no threshold" (capacity-low by Req 1.6).
    """
    return {
        str(promo_id): float(value)
        for promo_id, value in zip(
            promo_history["promo_id"], promo_history["threshold_php"]
        )
    }


# Feature: part3-segments, Property 2: For any assigned Leads frame, each Lead's `segment` equals 'Ready Toppers' when both `score_high` and `capacity_high` are true, 'Willing but Stretched' when only `score_high` is true, 'Untapped Wealth' when only `capacity_high` is true, and 'Not Now' when both are false; `capacity_high` is true exactly when `capacity_php >= threshold_php` and false whenever the Lead's promo has no threshold (absent from the promo history).
@settings(max_examples=200)
@given(segment_inputs())
def test_segment_matches_score_by_capacity_quadrant(frames):
    """``segment`` is the (score_high, capacity_high) quadrant label, and
    ``capacity_high`` is the ``>=`` threshold test with missing-promo -> False.

    Validates: Requirements 1.6, 2.2, 2.4
    """
    leads = assign(frames)
    thresholds = _reference_thresholds(frames["promo_history"])
    promos_with_threshold = set(thresholds)

    # Every assigned label is one of the four known SEGMENTS (no "" default).
    assert set(leads["segment"]).issubset(set(SEGMENTS))

    for row in leads.itertuples(index=False):
        promo_id = row.promo_id
        capacity_php = float(row.capacity_php)
        capacity_high = bool(row.capacity_high)
        score_high = bool(row.score_high)
        segment = row.segment

        # capacity_high is exactly capacity_php >= threshold_php, and a promo
        # absent from the promo history has no threshold -> capacity-low.
        if promo_id in promos_with_threshold:
            threshold = thresholds[promo_id]
            expected_capacity_high = capacity_php >= threshold
            assert capacity_high == expected_capacity_high, (
                f"promo {promo_id}: capacity_high={capacity_high} but "
                f"capacity_php={capacity_php} vs threshold={threshold}"
            )
        else:
            # Missing promo threshold forces capacity-low (Requirement 1.6).
            assert capacity_high is False, (
                f"promo {promo_id} absent from promo history must be "
                f"capacity-low, got capacity_high={capacity_high}"
            )

        # segment is the quadrant of (score_high, capacity_high).
        expected = _expected_label(score_high, capacity_high)
        assert segment == expected, (
            f"promo {promo_id}: score_high={score_high} "
            f"capacity_high={capacity_high} -> expected {expected!r} "
            f"got {segment!r}"
        )

    # Cross-check every lead of a promo missing its threshold is capacity-low
    # and therefore in a low-capacity segment (Untapped Wealth / Ready Toppers
    # are the high-capacity labels, so those must never appear for such leads).
    for promo_id in set(leads["promo_id"]) - promos_with_threshold:
        promo_leads = leads[leads["promo_id"] == promo_id]
        assert not promo_leads["capacity_high"].any(), (
            f"promo {promo_id} absent from promo history has a "
            f"capacity-high lead"
        )
        assert set(promo_leads["segment"]).issubset(
            {WILLING_STRETCHED, NOT_NOW}
        ), (
            f"promo {promo_id} absent from promo history produced a "
            f"high-capacity segment"
        )
