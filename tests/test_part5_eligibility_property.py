"""Property-based test for the Part 5 eligible-audience filter.

# Feature: part5-webapp, Property 1: eligibility is exactly the ADB-and-segment predicate over select_eligible_clients

Covers Property 1 of the part5-webapp spec: for any ``customer_dna``,
``adb_monthly``, ``eligible_segments``, and ``min_adb``, every client returned
by :func:`webapp_core.audience.select_eligible_clients` has ``segment`` in
``eligible_segments`` and latest-month ADB ``>= min_adb``; every client present
in the inputs but not returned fails at least one of those two conditions; and
the returned ``client_id`` values are unique (Requirement 3.2).

This is a relationship property: the test asserts the function's output against
an *independent* reference. The reference recomputes each client's latest-month
ADB directly from the raw ``adb_monthly`` frame (greatest ``YYYY-MM`` month,
missing client -> 0) without reusing the production ``latest_adb`` helper, then
applies the two-condition predicate itself. A divergence therefore signals a
real bug in the filter rather than a shared mistake.
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings

from webapp_core.audience import select_eligible_clients

from tests.strategies_part5 import eligibility_inputs


def _reference_latest_adb(adb_monthly: pd.DataFrame) -> dict[str, float]:
    """Independently recompute latest-month ADB per client from the raw frame.

    For each ``client_id``, take the ``adb_php`` at the lexicographically
    greatest ``month`` (``YYYY-MM`` strings sort chronologically as plain text).
    Never reuses the production ``latest_adb`` helper. Clients absent from the
    frame are not represented here; the caller treats them as ``0``.
    """
    reference: dict[str, float] = {}
    if adb_monthly.empty:
        return reference

    work = adb_monthly.copy()
    work["adb_php"] = pd.to_numeric(work["adb_php"], errors="coerce")
    for client_id, group in work.groupby("client_id"):
        ordered = group.sort_values("month")
        reference[str(client_id)] = float(ordered["adb_php"].to_numpy()[-1])
    return reference


@settings(max_examples=200, deadline=None)
@given(eligibility_inputs())
def test_eligibility_is_exactly_the_adb_and_segment_predicate(inputs):
    """Returned clients are exactly those passing the segment and ADB predicate.

    **Validates: Requirements 3.2**
    """
    customer_dna, adb_monthly, eligible_segments, min_adb = inputs

    result = select_eligible_clients(
        customer_dna, adb_monthly, eligible_segments, min_adb
    )

    eligible = set(eligible_segments)
    latest_by_client = _reference_latest_adb(adb_monthly)

    # Independent reference: for every client in the inputs, decide eligibility
    # from the two conditions directly.
    expected_ids: set[str] = set()
    expected_latest: dict[str, float] = {}
    expected_segment: dict[str, str] = {}
    for _, row in customer_dna.iterrows():
        client_id = str(row["client_id"])
        segment = row["segment"]
        latest = latest_by_client.get(client_id, 0.0)
        expected_latest[client_id] = latest
        expected_segment[client_id] = segment
        if segment in eligible and latest >= min_adb:
            expected_ids.add(client_id)

    returned_ids = [str(c) for c in result["client_id"].tolist()]

    # client_ids are unique.
    assert len(returned_ids) == len(set(returned_ids))

    # The returned set is exactly the predicate-satisfying set.
    assert set(returned_ids) == expected_ids

    # Every returned client satisfies BOTH conditions; its latest_adb/segment
    # match the independent reference.
    for _, row in result.iterrows():
        client_id = str(row["client_id"])
        assert expected_segment[client_id] in eligible
        assert float(row["latest_adb"]) >= min_adb
        assert float(row["latest_adb"]) == pytest.approx(
            expected_latest[client_id], rel=1e-9, abs=1e-6
        )
        assert row["segment"] == expected_segment[client_id]

    # Every input client NOT returned fails at least one condition.
    for client_id in expected_segment:
        if client_id not in returned_ids:
            fails_segment = expected_segment[client_id] not in eligible
            fails_adb = expected_latest[client_id] < min_adb
            assert fails_segment or fails_adb

    # Stable ascending client_id order.
    assert returned_ids == sorted(returned_ids)
