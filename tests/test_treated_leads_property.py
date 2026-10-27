"""Property-based test for ``part2_network.validation.select_treated_leads``.

Covers Property 15 (treated-lead selection) of the part2-network spec: the
selection keeps exactly the P001 control-group-0 rows and nothing else.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from part2_network.config import P001_PROMO_ID, TREATED_CONTROL_GROUP
from part2_network.validation import select_treated_leads

# The promo-id pool spans the treated promo plus two other promos, so a
# generated frame has a non-trivial mix of qualifying and non-qualifying promos.
PROMO_IDS = ["P001", "P002", "P003"]

# control_group is a 0/1 flag: 0 marks a Treated_Lead (kept), 1 a control row
# (dropped). Both values appear so the control-group predicate is exercised.
CONTROL_GROUPS = [0, 1]


@st.composite
def promo_leads_frames(draw: st.DrawFn) -> pd.DataFrame:
    """Draw a promo-leads DataFrame with a non-trivial mix of rows.

    Each row draws ``promo_id`` from {P001, P002, P003}, ``control_group`` from
    {0, 1}, a ``joined`` 0/1 flag, and ``join_date`` / ``channel_sent`` values,
    mirroring the real Promo_Leads_File columns. ``client_id`` values are drawn
    with repetition allowed from a small pool so duplicate client ids can occur
    across promos. The frame is built directly from generated column lists.
    """
    n_rows = draw(st.integers(min_value=0, max_value=40))

    promo_id = draw(
        st.lists(st.sampled_from(PROMO_IDS), min_size=n_rows, max_size=n_rows)
    )
    client_id = draw(
        st.lists(
            st.integers(min_value=0, max_value=50).map(lambda n: f"C{n:04d}"),
            min_size=n_rows,
            max_size=n_rows,
        )
    )
    control_group = draw(
        st.lists(
            st.sampled_from(CONTROL_GROUPS), min_size=n_rows, max_size=n_rows
        )
    )
    joined = draw(
        st.lists(
            st.sampled_from([0, 1]), min_size=n_rows, max_size=n_rows
        )
    )
    channel_sent = draw(
        st.lists(
            st.sampled_from(["Email", "SMS", "Push"]),
            min_size=n_rows,
            max_size=n_rows,
        )
    )
    join_date = draw(
        st.lists(
            st.sampled_from(["2026-07-10", "2026-08-05", "2026-09-20", ""]),
            min_size=n_rows,
            max_size=n_rows,
        )
    )

    return pd.DataFrame(
        {
            "promo_id": promo_id,
            "client_id": client_id,
            "control_group": control_group,
            "channel_sent": channel_sent,
            "joined": joined,
            "join_date": join_date,
        }
    )


# Feature: part2-network, Property: treated-lead selection
# Property 15: Treated-lead selection is exactly the P001 control-group-0 rows
@settings(max_examples=200)
@given(leads=promo_leads_frames())
def test_treated_lead_selection_is_exactly_p001_control_group_zero(leads):
    """``select_treated_leads`` keeps exactly the P001 control-group-0 rows.

    Soundness: every returned row satisfies the predicate
    (``promo_id == "P001"`` and ``control_group == 0``). Completeness: the
    output row count equals the number of input rows satisfying that same
    predicate, so no qualifying row is dropped and no P002/P003 or
    control_group==1 row leaks through.

    Validates: Requirements 9.2
    """
    selected = select_treated_leads(leads)

    # Soundness: every surviving row is a P001 Treated_Lead.
    assert (selected["promo_id"] == P001_PROMO_ID).all()
    assert (selected["control_group"] == TREATED_CONTROL_GROUP).all()

    # Completeness: the output count equals the number of qualifying input rows
    # computed independently from the raw columns.
    expected_mask = (leads["promo_id"] == P001_PROMO_ID) & (
        leads["control_group"] == TREATED_CONTROL_GROUP
    )
    assert len(selected) == int(expected_mask.sum())

    # Non-qualifying promos and control rows are excluded entirely.
    assert not (selected["promo_id"].isin(["P002", "P003"])).any()
    assert not (selected["control_group"] == 1).any()
