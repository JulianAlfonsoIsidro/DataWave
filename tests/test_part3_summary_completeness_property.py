"""Property-based test for ``part3_segments.validation.build`` completeness.

Covers Property 5 of the part3-segments spec: the Segment_Summary contains
exactly one row for every distinct scores ``promo_id`` crossed with each of the
four segment labels (so the row count equals four times the number of distinct
promos), and every (promo, segment) cell to which no Lead is assigned is
zero-filled for the numeric aggregates and blank-filled for the text, with an
empty ``actual_join_rate``; any cell with no treated leads likewise has an
empty ``actual_join_rate``.

The empty-cell expectations are asserted against an independent reference: the
set of (promo, segment) cells that actually receive an assigned Lead and the
set of cells that receive a treated lead are recomputed by plain Python walks
over the assigned leads and the promo-leads frame, not by restating the
vectorized reindex.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings

from part3_segments.config import SEGMENTS, TREATED_CONTROL_GROUP
from part3_segments.segments import assign
from part3_segments.validation import build
from tests.strategies_part3 import segment_inputs


def _assigned_cells(leads: pd.DataFrame) -> set[tuple[str, str]]:
    """The (promo, segment) cells that receive at least one assigned Lead.

    A plain per-row walk over the assigned leads, independent of the vectorized
    groupby/reindex used by ``build``.
    """
    return {
        (str(promo_id), str(segment))
        for promo_id, segment in zip(leads["promo_id"], leads["segment"])
    }


def _treated_cells(
    leads: pd.DataFrame, promo_leads: pd.DataFrame
) -> set[tuple[str, str]]:
    """The (promo, segment) cells that receive at least one treated lead.

    Independently maps each Treated_Lead (``control_group`` 0) to its Lead's
    segment by a plain lookup on (``promo_id``, ``client_id``), so cells with
    no treated lead can be checked for an empty Actual_Join_Rate.
    """
    segment_by_key = {
        (str(promo_id), str(client_id)): str(segment)
        for promo_id, client_id, segment in zip(
            leads["promo_id"], leads["client_id"], leads["segment"]
        )
    }
    treated_cells: set[tuple[str, str]] = set()
    treated_marker = str(TREATED_CONTROL_GROUP)
    for promo_id, client_id, control_group in zip(
        promo_leads["promo_id"],
        promo_leads["client_id"],
        promo_leads["control_group"],
    ):
        control = str(control_group).strip()
        if control != treated_marker and control != f"{treated_marker}.0":
            continue
        key = (str(promo_id), str(client_id))
        if key in segment_by_key:
            treated_cells.add((key[0], segment_by_key[key]))
    return treated_cells


# Feature: part3-segments, Property 5: For any scores frame, the Segment_Summary_File contains exactly one row for every combination of a distinct scores `promo_id` with each of the four segment labels (so the row count equals four times the number of distinct promos), and every (promo, segment) cell to which no Lead is assigned has `n_clients` equal to 0, `mean_p_join` equal to 0, `expected_joiners` equal to 0, an empty `actual_join_rate`, and an empty `top_driver_1`; any cell with no treated leads likewise has an empty `actual_join_rate`.
@settings(max_examples=200)
@given(segment_inputs())
def test_summary_completeness_and_empty_cell_filling(frames):
    """Full promo x four-segment cross product with zero/empty-filled cells.

    The summary must carry exactly one row per (distinct scores ``promo_id`` x
    each of the four ``SEGMENTS``), its row count must equal four times the
    number of distinct promos, the set of (promo, segment) pairs must match the
    full cross product, and every empty cell (no assigned Lead) must be
    zero-filled for ``n_clients`` / ``mean_p_join`` / ``expected_joiners`` and
    blank-filled for ``top_driver_1`` with an empty ``actual_join_rate``. Any
    cell with no treated leads must also carry an empty ``actual_join_rate``.

    Validates: Requirements 4.1, 4.4, 4.5
    """
    leads = assign(frames)
    summary = build(leads, frames["promo_leads"])

    distinct_promos = list(pd.unique(leads["promo_id"]))
    expected_pairs = {
        (str(promo_id), str(segment))
        for promo_id in distinct_promos
        for segment in SEGMENTS
    }

    # Row count equals four times the number of distinct promos (Req 4.1).
    assert len(summary) == 4 * len(distinct_promos), (
        f"summary has {len(summary)} rows; expected "
        f"{4 * len(distinct_promos)} (4 x {len(distinct_promos)} promos)"
    )

    # Exactly one row per (promo, segment) pair: no duplicates, and the set of
    # pairs matches the full cross product (Req 4.1).
    summary_pairs = [
        (str(promo_id), str(segment))
        for promo_id, segment in zip(summary["promo_id"], summary["segment"])
    ]
    assert len(summary_pairs) == len(set(summary_pairs)), (
        "summary contains duplicate (promo, segment) rows"
    )
    assert set(summary_pairs) == expected_pairs, (
        "summary (promo, segment) pairs do not match the full cross product"
    )

    assigned = _assigned_cells(leads)
    treated = _treated_cells(leads, frames["promo_leads"])

    for row in summary.itertuples(index=False):
        key = (str(row.promo_id), str(row.segment))

        # Empty cells (no assigned Lead) are zero/blank filled (Req 4.5).
        if key not in assigned:
            assert row.n_clients == 0, (
                f"empty cell {key}: n_clients={row.n_clients}, expected 0"
            )
            assert float(row.mean_p_join) == 0.0, (
                f"empty cell {key}: mean_p_join={row.mean_p_join}, expected 0"
            )
            assert float(row.expected_joiners) == 0.0, (
                f"empty cell {key}: expected_joiners={row.expected_joiners}, "
                f"expected 0"
            )
            assert row.top_driver_1 == "", (
                f"empty cell {key}: top_driver_1={row.top_driver_1!r}, "
                f"expected ''"
            )
            assert pd.isna(row.actual_join_rate), (
                f"empty cell {key}: actual_join_rate={row.actual_join_rate}, "
                f"expected empty"
            )

        # Any cell with no treated leads has an empty actual_join_rate (Req 4.4).
        if key not in treated:
            assert pd.isna(row.actual_join_rate), (
                f"cell {key} has no treated leads but "
                f"actual_join_rate={row.actual_join_rate}, expected empty"
            )
