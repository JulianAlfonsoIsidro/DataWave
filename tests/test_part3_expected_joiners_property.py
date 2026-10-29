"""Property-based test for ``part3_segments.validation.build`` expected joiners.

Covers Property 4 of the part3-segments spec: each (promo, segment) cell's
``expected_joiners`` equals the sum of ``p_join`` over the Leads assigned to
that cell, and the four cells of any single promo have ``expected_joiners``
values summing to that promo's total ``p_join``. This is a *reduction*
property, so the assertion is made against an independent, straightforward
non-vectorized reference computation (a plain per-cell Python sum of
``p_join``) rather than a restatement of the vectorized implementation.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
from hypothesis import given, settings

from part3_segments.segments import assign
from part3_segments.validation import build
from tests.strategies_part3 import segment_inputs


def _reference_expected_joiners(
    leads: pd.DataFrame,
) -> dict[tuple[str, str], float]:
    """Independently sum ``p_join`` per (promo, segment) cell.

    Walks the assigned leads one row at a time (no pandas groupby) and
    accumulates ``p_join`` into a plain dict keyed by (``promo_id``,
    ``segment``). A cell with no assigned Leads is simply absent from the
    mapping (the caller treats a miss as 0). This is a deliberately plain,
    independent reference rather than a copy of the vectorized aggregation.
    """
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for promo_id, segment, p_join in zip(
        leads["promo_id"], leads["segment"], leads["p_join"]
    ):
        totals[(str(promo_id), str(segment))] += float(p_join)
    return dict(totals)


def _reference_promo_totals(leads: pd.DataFrame) -> dict[str, float]:
    """Independently sum ``p_join`` per promo over all its assigned Leads."""
    totals: dict[str, float] = defaultdict(float)
    for promo_id, p_join in zip(leads["promo_id"], leads["p_join"]):
        totals[str(promo_id)] += float(p_join)
    return dict(totals)


# Feature: part3-segments, Property 4: For any assigned Leads frame, each (promo, segment) cell's `expected_joiners` equals the sum of `p_join` over the Leads assigned to that cell, and the four cells of any single promo have `expected_joiners` values summing to that promo's total `p_join`.
@settings(max_examples=200)
@given(segment_inputs())
def test_expected_joiners_equals_sum_of_p_join(frames):
    """``expected_joiners`` matches an independent per-cell reference recompute.

    For every (promo, segment) cell the summary must carry an
    ``expected_joiners`` equal to the plain sum of ``p_join`` over that cell's
    assigned Leads (0 for empty cells), and the four cells of each promo must
    sum to that promo's total ``p_join``.

    Validates: Requirements 4.2
    """
    leads = assign(frames)
    summary = build(leads, frames["promo_leads"])

    reference_cells = _reference_expected_joiners(leads)
    reference_promos = _reference_promo_totals(leads)

    tolerance = 1e-6

    # Each cell's expected_joiners equals the independent per-cell sum of
    # p_join; a cell with no assigned Leads sums to 0.
    per_promo_sum: dict[str, float] = defaultdict(float)
    for promo_id, segment, expected in zip(
        summary["promo_id"], summary["segment"], summary["expected_joiners"]
    ):
        key = (str(promo_id), str(segment))
        reference = reference_cells.get(key, 0.0)
        assert abs(float(expected) - reference) <= tolerance, (
            f"cell {key}: expected_joiners={expected} "
            f"reference sum of p_join={reference}"
        )
        per_promo_sum[str(promo_id)] += float(expected)

    # The four cells of each promo sum to that promo's total p_join.
    for promo_id, promo_total in reference_promos.items():
        summed = per_promo_sum.get(promo_id, 0.0)
        assert abs(summed - promo_total) <= tolerance, (
            f"promo {promo_id}: sum of cell expected_joiners={summed} "
            f"total p_join={promo_total}"
        )
