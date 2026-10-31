"""Property-based test for the Part 5 segment-quadrant assignment.

# Feature: part5-webapp, Property 2: assign_segments is exactly the score-vs-capacity quadrant in the fixed label order

Covers Property 2 of the part5-webapp spec: for any scored frame and
``threshold_php``, each lead's ``segment`` produced by
:func:`part3_segments.segments.assign_segments` equals the 2x2 of
(``p_join >=`` that promo's median ``p_join``) and (``capacity_php >=
threshold_php``) mapped onto the fixed label order Ready Toppers / Willing but
Stretched / Untapped Wealth / Not Now, and every lead receives exactly one of
the four labels (Requirements 3.3, 4.1).

This is a relationship property: the test asserts ``assign_segments`` output
against an *independent* reference that recomputes capacity (latest-month ADB +
out_other_bank, each missing -> 0) and the median split directly from the raw
inputs, never reusing the production capacity or quadrant code. A divergence
therefore signals a real bug rather than a shared mistake.
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings

from part3_segments.config import SEGMENTS
from part3_segments.segments import assign_segments

from tests.strategies_part5 import scored_audience


def _reference_latest_adb(adb: pd.DataFrame) -> dict[str, float]:
    """Latest-month ADB per client, recomputed independently from the raw frame."""
    reference: dict[str, float] = {}
    if adb.empty:
        return reference
    work = adb.copy()
    work["adb_php"] = pd.to_numeric(work["adb_php"], errors="coerce")
    for client_id, group in work.groupby("client_id"):
        ordered = group.sort_values("month")
        reference[str(client_id)] = float(ordered["adb_php"].to_numpy()[-1])
    return reference


def _reference_out_other_bank(features: pd.DataFrame) -> dict[str, float]:
    """out_other_bank per client, recomputed independently from the raw frame."""
    reference: dict[str, float] = {}
    if features.empty:
        return reference
    for _, row in features.iterrows():
        reference[str(row["client_id"])] = float(row["out_other_bank"])
    return reference


def _reference_label(score_high: bool, capacity_high: bool) -> str:
    """Map the (score_high, capacity_high) quadrant onto the fixed label order.

    SEGMENTS order is high/high, high/low, low/high, low/low -- Ready Toppers,
    Willing but Stretched, Untapped Wealth, Not Now (Requirement 4.1). This is
    written out explicitly rather than reusing the production ``np.select``.
    """
    if score_high and capacity_high:
        return SEGMENTS[0]  # Ready Toppers
    if score_high and not capacity_high:
        return SEGMENTS[1]  # Willing but Stretched
    if not score_high and capacity_high:
        return SEGMENTS[2]  # Untapped Wealth
    return SEGMENTS[3]  # Not Now


@settings(max_examples=200, deadline=None)
@given(scored_audience())
def test_assign_segments_is_exactly_the_score_vs_capacity_quadrant(inputs):
    """Each segment equals the independent score-vs-capacity quadrant.

    **Validates: Requirements 3.3, 4.1**
    """
    scored, promo_dict, frames = inputs

    result = assign_segments(scored, promo_dict, frames)

    threshold = float(promo_dict["threshold_php"])
    latest_by_client = _reference_latest_adb(frames["adb"])
    out_by_client = _reference_out_other_bank(frames["features"])

    # Independent capacity per client and the independent promo-median split.
    p_join_values = pd.to_numeric(scored["p_join"], errors="coerce")
    promo_median = float(p_join_values.median())

    capacity_by_client: dict[str, float] = {}
    for _, row in scored.iterrows():
        client_id = str(row["client_id"])
        capacity = latest_by_client.get(client_id, 0.0) + out_by_client.get(
            client_id, 0.0
        )
        capacity_by_client[client_id] = capacity

    # Every lead gets exactly one of the four labels, and it matches the
    # independent quadrant.
    assert len(result) == len(scored)
    assert set(result["segment"]).issubset(set(SEGMENTS))

    result_by_client = {
        str(row["client_id"]): row for _, row in result.iterrows()
    }
    for _, row in scored.iterrows():
        client_id = str(row["client_id"])
        p_join = float(row["p_join"])
        capacity = capacity_by_client[client_id]

        score_high = p_join >= promo_median
        capacity_high = capacity >= threshold
        expected = _reference_label(score_high, capacity_high)

        out_row = result_by_client[client_id]
        assert out_row["segment"] == expected
        # capacity_php the function reports also matches the independent sum.
        assert float(out_row["capacity_php"]) == pytest.approx(
            capacity, rel=1e-9, abs=1e-6
        )

    # Every segment label is one of the four (exactly-one-of-four).
    assert result["segment"].isin(SEGMENTS).all()
