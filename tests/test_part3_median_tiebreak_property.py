"""Property-based test for ``part3_segments.segments.assign`` score-high.

Covers Property 3 of the part3-segments spec: within each promo, ``score_high``
is true exactly for the Leads whose ``p_join`` is greater than or equal to the
median ``p_join`` of that promo's Leads, so a Lead sitting exactly on its promo
median counts as score-high (the comparison is ``>=``).

The per-promo median is recomputed with an *independent* reference
(``statistics.median`` over each promo's Python-level ``p_join`` list) rather
than the implementation's ``groupby.transform("median")``, so the test does not
merely restate the implementation. The tie case is asserted explicitly: every
Lead whose ``p_join`` equals its promo median must be ``score_high``.
"""

from __future__ import annotations

import statistics

import pandas as pd
from hypothesis import given, settings

from part3_segments.segments import assign
from tests.strategies_part3 import segment_inputs


def _reference_promo_medians(scores) -> dict[str, float]:
    """Independently recompute each promo's median ``p_join``.

    Collects every Lead's ``p_join`` per promo into a plain Python list and
    takes ``statistics.median`` of each list. This is a deliberately simple,
    non-vectorized reference, distinct from the implementation's pandas
    ``groupby.transform("median")``.
    """
    per_promo: dict[str, list[float]] = {}
    for promo_id, p_join in zip(scores["promo_id"], scores["p_join"]):
        per_promo.setdefault(promo_id, []).append(float(p_join))
    return {promo_id: statistics.median(values) for promo_id, values in per_promo.items()}


# Feature: part3-segments, Property 3: For any scores frame, within each promo `score_high` is true exactly for the Leads whose `p_join` is greater than or equal to the median `p_join` of that promo's Leads; in particular every Lead whose `p_join` equals its promo median is `score_high`.
@settings(max_examples=200)
@given(segment_inputs())
def test_score_high_is_at_or_above_promo_median_with_ties_high(frames):
    """``score_high`` equals ``p_join >= promo median`` against a reference.

    For every Lead, the Segmenter's ``score_high`` must be true exactly when
    the Lead's ``p_join`` is at or above the median ``p_join`` of its promo,
    where the median is computed by an independent reference. Ties (a Lead at
    exactly its promo median) must be score-high.

    Validates: Requirements 2.3
    """
    leads = assign(frames)

    medians = _reference_promo_medians(frames["scores"])

    assert len(leads) == len(frames["scores"])

    for promo_id, p_join, score_high in zip(
        leads["promo_id"], leads["p_join"], leads["score_high"]
    ):
        median = medians[promo_id]
        expected = float(p_join) >= median
        assert bool(score_high) == expected, (
            f"promo {promo_id}: p_join={p_join} median={median} "
            f"score_high={bool(score_high)} expected {expected}"
        )

        # Explicit tie coverage: whenever a Lead sits *exactly* on its promo
        # median, it must be score-high because the comparison is `>=`
        # (Requirement 2.3). Ties are detected by exact float equality against
        # the independent reference median -- the same notion of "equal" the
        # `>=` test uses -- not a tolerance window, which could misclassify a
        # strictly-below Lead (e.g. 0.0 vs a subnormal median) as a tie.
        if float(p_join) == median:
            assert bool(score_high), (
                f"tie at promo {promo_id}: p_join={p_join} equals median "
                f"{median} but score_high is False"
            )


def test_lead_exactly_on_promo_median_is_score_high():
    """A Lead whose ``p_join`` equals its promo median is score-high.

    A deterministic tie case backing Property 3's "in particular every Lead
    whose ``p_join`` equals its promo median is score_high" clause. The promo
    has three Leads at 0.2, 0.5, 0.8, so the median is exactly 0.5 and the
    middle Lead sits on it; it must be score-high (the comparison is ``>=``).

    Validates: Requirements 2.3
    """
    scores = pd.DataFrame(
        {
            "promo_id": ["P001", "P001", "P001"],
            "client_id": ["C0001", "C0002", "C0003"],
            "p_join": [0.2, 0.5, 0.8],
            "top_driver_1": ["payroll", "payroll", "payroll"],
            "top_driver_2": ["payroll", "payroll", "payroll"],
            "top_driver_3": ["payroll", "payroll", "payroll"],
        }
    )
    empty_features = pd.DataFrame(columns=["client_id", "out_other_bank"])
    empty_adb = pd.DataFrame(columns=["client_id", "month", "adb_php"])
    empty_history = pd.DataFrame(columns=["promo_id", "threshold_php"])
    empty_leads = pd.DataFrame(
        columns=["promo_id", "client_id", "control_group", "joined"]
    )

    leads = assign(
        {
            "scores": scores,
            "features": empty_features,
            "adb": empty_adb,
            "promo_history": empty_history,
            "promo_leads": empty_leads,
        }
    )

    score_high = dict(zip(leads["client_id"], leads["score_high"]))
    # The median (0.5) Lead is a tie and must be high.
    assert bool(score_high["C0002"]) is True
    # The above-median Lead is high; the below-median Lead is not.
    assert bool(score_high["C0003"]) is True
    assert bool(score_high["C0001"]) is False
