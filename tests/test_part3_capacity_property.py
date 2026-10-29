"""Property-based test for ``part3_segments.segments.assign`` capacity.

Covers Property 1 of the part3-segments spec: each Lead's ``capacity_php``
equals the client's latest-month ADB plus the client's external outflow, with
missing ADB / features sources treated as 0. This is a *reduction* property, so
the assertion is made against an independent, straightforward non-vectorized
reference computation (a simple Python recompute per client) rather than a
restatement of the vectorized implementation.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings

from part3_segments.segments import assign
from tests.strategies_part3 import segment_inputs


def _reference_latest_adb(adb: pd.DataFrame) -> dict[str, float]:
    """Independently recompute each client's latest-month ``adb_php``.

    Walks the ADB rows one at a time (no pandas groupby) and keeps, per client,
    the ``adb_php`` at the lexicographically greatest ``month`` string seen so
    far. Clients with no ADB row are simply absent from the returned mapping
    (the caller treats a miss as 0). This is a deliberately plain, independent
    reference rather than a copy of the vectorized ``_latest_adb`` helper.
    """
    best_month: dict[str, str] = {}
    best_adb: dict[str, float] = {}
    for client_id, month, adb_php in zip(
        adb["client_id"], adb["month"], adb["adb_php"]
    ):
        if client_id not in best_month or month > best_month[client_id]:
            best_month[client_id] = month
            best_adb[client_id] = float(adb_php)
    return best_adb


def _reference_out_other_bank(features: pd.DataFrame) -> dict[str, float]:
    """Independently build each client's ``out_other_bank`` lookup.

    One entry per features row; clients absent from the features frame are not
    in the mapping (the caller treats a miss as 0).
    """
    return {
        str(client_id): float(value)
        for client_id, value in zip(
            features["client_id"], features["out_other_bank"]
        )
    }


# Feature: part3-segments, Property 1: For any scores frame, ADB-monthly frame, and features frame, each Lead's `capacity_php` equals that client's `adb_php` at the lexicographically greatest `month` present for the client (0 when the client has no ADB row) plus that client's `out_other_bank` (0 when the client has no features row).
@settings(max_examples=200)
@given(segment_inputs())
def test_capacity_equals_latest_adb_plus_out_other_bank(frames):
    """``capacity_php`` matches an independent per-client reference recompute.

    For every Lead, the Segmenter's ``capacity_php`` must equal the client's
    latest-month ``adb_php`` (0 when the client has no ADB row) plus the
    client's ``out_other_bank`` (0 when the client has no features row).

    Validates: Requirements 1.5, 2.1
    """
    leads = assign(frames)

    latest_adb = _reference_latest_adb(frames["adb"])
    out_other_bank = _reference_out_other_bank(frames["features"])

    # One capacity value per Lead, aligned to the scores rows.
    assert len(leads) == len(frames["scores"])

    tolerance = 1e-6
    for client_id, capacity in zip(leads["client_id"], leads["capacity_php"]):
        expected = latest_adb.get(client_id, 0.0) + out_other_bank.get(
            client_id, 0.0
        )
        assert capacity == expected or abs(capacity - expected) <= tolerance, (
            f"client {client_id}: capacity_php={capacity} "
            f"expected {expected} (adb={latest_adb.get(client_id, 0.0)}, "
            f"out_other_bank={out_other_bank.get(client_id, 0.0)})"
        )

    # Missing sources contribute 0, so capacity is non-negative given the
    # non-negative ADB and outflow inputs the strategy generates (Req 1.5).
    assert (leads["capacity_php"] >= -tolerance).all()
