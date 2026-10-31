"""Property-based test for the Part 5 predicted-vs-actual join rates.

# Feature: part5-webapp, Property 4: predicted_vs_actual rates are in [0,1] or NA, NA exactly when a cell has no sendable leads

Covers Property 4 of the part5-webapp spec: for any cards and ``promo_leads``,
:func:`webapp_core.past_promos.predicted_vs_actual` yields, per
``(promo_id, segment)`` cell, ``predicted = expected_joiners / sendable_count``
and ``actual = mean(joined)`` over the cell's Sendable_Leads; each rate is
either in ``[0, 1]`` or NA, and a rate is NA exactly when its cell has no
Sendable_Leads -- for ``predicted`` that means ``sendable_count == 0``, for
``actual`` it means the cell's sendable id set is empty (Requirements 5.2, 5.4).

This is a relationship property: the test asserts the function output against an
*independent* reference that recomputes each rate directly from the card and the
raw ``promo_leads`` rows, never reusing the production arithmetic. A divergence
therefore signals a real bug rather than a shared mistake.
"""

from __future__ import annotations

import math

from hypothesis import given, settings

from webapp_core.past_promos import predicted_vs_actual

from tests.strategies_part5 import predicted_actual_inputs


def _is_na(value) -> bool:
    """True when ``value`` is a float NaN (the module's NA sentinel)."""
    return isinstance(value, float) and math.isnan(value)


@settings(max_examples=200, deadline=None)
@given(predicted_actual_inputs())
def test_predicted_vs_actual_rates_are_bounded_or_na(inputs):
    """Each rate is in [0, 1] or NA, NA exactly when the cell has no sendable leads.

    **Validates: Requirements 5.2, 5.4**
    """
    cards, promo_leads, sendable_ids_by_cell = inputs

    rows = predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell)

    # One output row per input card, in order, carrying the cell key through.
    assert len(rows) == len(cards)

    for card, row in zip(cards, rows):
        promo_id = str(card["promo_id"])
        segment = str(card["segment"])
        sendable_count = int(card["sendable_count"])
        expected_joiners = float(card["expected_joiners"])

        assert row["promo_id"] == promo_id
        assert row["segment"] == segment
        assert row["sendable_count"] == sendable_count

        predicted = row["predicted"]
        actual = row["actual"]

        # --- predicted: NA iff sendable_count == 0, else in [0, 1] ---
        if sendable_count == 0:
            assert _is_na(predicted)
        else:
            assert not _is_na(predicted)
            expected_predicted = expected_joiners / sendable_count
            assert predicted == expected_predicted
            assert 0.0 <= predicted <= 1.0

        # --- actual: NA iff the cell's sendable id set is empty, else in [0, 1] ---
        sendable_ids = {
            str(cid)
            for cid in sendable_ids_by_cell.get((promo_id, segment), ())
        }
        if not sendable_ids:
            assert _is_na(actual)
        else:
            # Independent reference: mean of joined over this cell's sendable
            # leads, recomputed straight from the raw promo_leads rows.
            matched = [
                int(lead_row["joined"])
                for _, lead_row in promo_leads.iterrows()
                if str(lead_row["promo_id"]) == promo_id
                and str(lead_row["client_id"]) in sendable_ids
            ]
            if not matched:
                # Sendable ids exist but none appear in promo_leads for this
                # promo: the function reports NA (no rows to average).
                assert _is_na(actual)
            else:
                expected_actual = sum(matched) / len(matched)
                assert not _is_na(actual)
                assert actual == expected_actual
                assert 0.0 <= actual <= 1.0
