"""Property-based test for the Part 5 WHAT-IF threshold monotonicity.

# Feature: part5-webapp, Property 5: capacity-high count (Ready Toppers + Untapped Wealth) is non-increasing as threshold_php rises for a fixed scored audience

Covers Property 5 of the part5-webapp spec: for a fixed eligible audience and
fixed scored ``p_join`` / ``capacity_php``, raising ``threshold_php`` never
increases the number of capacity-high leads, so the combined Ready Toppers +
Untapped Wealth count (the two capacity-high labels) is non-increasing as the
WHAT-IF threshold rises (Requirement 6.2).

The property is exercised through :func:`part3_segments.segments.assign_segments`
-- the exact entry point the WHAT-IF slider re-runs -- on one fixed scored frame
and ``frames`` across an ascending sequence of thresholds. Capacity depends only
on the client (latest-month ADB + out_other_bank), so a higher threshold can
only ever flip a lead from capacity-high to capacity-low, never the reverse;
this test pins that monotonicity against the two capacity-high labels in
:data:`part3_segments.config.SEGMENTS` (index 0 Ready Toppers, index 2 Untapped
Wealth).
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

# Each example runs assign_segments once per threshold (a pandas merge/groupby
# per call), so a single case can exceed Hypothesis's default per-example
# deadline on a cold run; the deadline is disabled since wall-clock time is not
# what this property asserts.

from part3_segments.config import SEGMENTS
from part3_segments.segments import assign_segments

from tests.strategies_part5 import scored_audience

# The two capacity-high Segment_Labels: Ready Toppers (score-high/capacity-high)
# and Untapped Wealth (score-low/capacity-high).
CAPACITY_HIGH_LABELS = {SEGMENTS[0], SEGMENTS[2]}


def _capacity_high_count(segments: pd.Series) -> int:
    """Number of leads whose assigned segment is one of the capacity-high labels."""
    return int(segments.isin(CAPACITY_HIGH_LABELS).sum())


@st.composite
def _audience_with_thresholds(draw):
    """A fixed scored audience plus an ascending sequence of thresholds."""
    scored, promo_dict, frames = draw(scored_audience())
    thresholds = draw(
        st.lists(
            st.floats(
                min_value=0.0,
                max_value=1_000_000.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=2,
            max_size=6,
        )
    )
    thresholds = sorted(thresholds)
    return scored, promo_dict, frames, thresholds


@settings(max_examples=150, deadline=None)
@given(_audience_with_thresholds())
def test_capacity_high_count_is_non_increasing_in_threshold(inputs):
    """Raising threshold_php never increases the capacity-high lead count.

    **Validates: Requirement 6.2**
    """
    scored, promo_dict, frames, thresholds = inputs

    counts: list[int] = []
    for threshold in thresholds:
        promo_at_threshold = dict(promo_dict)
        promo_at_threshold["threshold_php"] = threshold
        result = assign_segments(scored, promo_at_threshold, frames)
        counts.append(_capacity_high_count(result["segment"]))

    # Thresholds are ascending; the capacity-high count must be non-increasing
    # across every consecutive pair on the same scored frame + frames.
    for lower_count, higher_count in zip(counts, counts[1:]):
        assert higher_count <= lower_count
