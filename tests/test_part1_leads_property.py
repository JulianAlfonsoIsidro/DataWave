"""Property-based test for Lead_Loader treated-lead selection.

# Feature: part1-optin, Property 1: Treated-lead selection keeps exactly the valid treated P001/P002/P003 rows

Covers Property 1 of the part1-optin spec: given any Promo_Leads_File-shaped
frame, :meth:`part1_optin.leads.Lead_Loader.load` returns exactly the rows that
are treated (``control_group == 0``), carry a ``promo_id`` in P001/P002/P003,
have a ``joined`` value in ``{0, 1}``, and are deduplicated on
``(promo_id, client_id)`` keeping the first occurrence, with ``Join_Label``
equal to ``joined`` (Requirements 1.2, 1.3, 1.4, 1.5, 1.6).

The test exercises the real file-reading path: it writes the generated leads
frame to a temporary CSV, points a :class:`part1_optin.config.Config` at it,
runs the loader, and compares the result against an independent reference
recompute of the selection rules. The independent recompute never shares code
with the loader -- it re-derives the expected surviving rows directly from the
generated frame -- so a divergence signals a real selection bug.

No path in this test references a ``*_answer_key*`` file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import given, settings
from hypothesis import HealthCheck

from part1_optin.config import Config, PROMO_IDS, TREATED_CONTROL_GROUP
from part1_optin.leads import Lead_Loader

from tests.strategies_part1 import promo_leads_frames


def _reference_selection(frame: pd.DataFrame) -> pd.DataFrame:
    """Independently recompute the treated-lead population from a raw frame.

    Re-derives the exact rows the Lead_Loader should keep, without reusing the
    loader, following the selection rules in order:

    1. coerce ``control_group`` / ``joined`` with ``to_numeric(coerce)`` so
       typed/quoted/NaN values compare like the loader does (Requirements 1.2,
       1.6),
    2. keep ``control_group == 0`` (Requirement 1.2),
    3. keep ``promo_id in {P001, P002, P003}`` (Requirement 1.3),
    4. keep ``joined in {0, 1}`` (Requirement 1.6),
    5. dedup on ``(promo_id, client_id)`` keeping the first (Requirement 1.4).

    The first-occurrence semantics are anchored by comparing on the row's
    original position, so ties resolve to the same row the loader keeps.
    """
    work = frame.copy()
    work["_orig_pos"] = range(len(work))
    work["control_group"] = pd.to_numeric(work["control_group"], errors="coerce")
    work["joined"] = pd.to_numeric(work["joined"], errors="coerce")

    kept = work[work["control_group"] == TREATED_CONTROL_GROUP]
    kept = kept[kept["promo_id"].isin(PROMO_IDS)]
    kept = kept[kept["joined"].isin([0, 1])]

    # Keep the first occurrence of each (promo_id, client_id) by original order.
    kept = kept.sort_values("_orig_pos")
    kept = kept.drop_duplicates(subset=["promo_id", "client_id"], keep="first")

    return kept


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(promo_leads_frames())
def test_treated_lead_selection_keeps_exactly_valid_rows(frame):
    """The loader keeps exactly the valid treated P001/P002/P003 rows.

    **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**
    """
    expected = _reference_selection(frame)

    # Write the generated frame to a temp CSV and point a Config at it so the
    # real read_csv + coercion path runs (exercises Requirements 1.2, 1.6). A
    # self-managed temp dir keeps each Hypothesis example isolated without a
    # function-scoped pytest fixture (which Hypothesis cannot drive per example).
    with tempfile.TemporaryDirectory() as tmp_dir:
        leads_path = Path(tmp_dir) / "promo_leads.csv"
        frame.to_csv(leads_path, index=False)

        config = Config(promo_leads_path=leads_path)
        loader = Lead_Loader(config)

        if expected.empty:
            # Requirement 1.8: zero treated leads halts with an error, so there
            # is no result frame to compare against -- the empty case is covered
            # by the edge tests (task 2.3). Property 1 targets the non-empty
            # selection.
            return

        result = loader.load()

    # --- Membership: every returned row satisfies all selection rules. ---
    assert (result["control_group"] == TREATED_CONTROL_GROUP).all()  # 1.2
    assert result["promo_id"].isin(PROMO_IDS).all()                  # 1.3
    assert result["Join_Label"].isin([0, 1]).all()                   # 1.6

    # --- Label: Join_Label mirrors the (coerced) joined value. ---
    assert (result["Join_Label"] == result["joined"].astype(int)).all()  # 1.5

    # --- Dedup: each (promo_id, client_id) pair appears at most once. ---
    pair_counts = result.groupby(["promo_id", "client_id"]).size()  # 1.4
    assert (pair_counts == 1).all()

    # --- Exactness: the kept (promo_id, client_id) set equals the reference. ---
    result_pairs = set(
        zip(result["promo_id"], result["client_id"])
    )
    expected_pairs = set(
        zip(expected["promo_id"], expected["client_id"])
    )
    assert result_pairs == expected_pairs
    assert len(result) == len(expected_pairs)

    # --- First-occurrence: the kept row's joined matches the first valid
    #     occurrence of that pair in the reference recompute (Requirement 1.4
    #     keep="first" + 1.5 label). ---
    expected_label = {
        (row.promo_id, row.client_id): int(row.joined)
        for row in expected.itertuples(index=False)
    }
    for row in result.itertuples(index=False):
        assert expected_label[(row.promo_id, row.client_id)] == int(row.Join_Label)
