"""Property-based tests for the per-quartile Join_Rate.

Covers Property 17 (per-quartile join rate is a bounded mean of the joined
flag) of the part2-network spec, which validates Requirement 9.6: for each
non-empty Ext_Outflow_Quartile the Validation_Reporter computes the Join_Rate
as the count of joined P001 Treated_Leads with ``joined`` equal to 1 divided by
the count of joined leads in that quartile, producing a value in [0, 1].

The strategy builds P001 Treated_Leads (``promo_id`` "P001", ``control_group``
0, a ``client_id``, and a 0/1 ``joined`` flag) alongside a Features_File frame
carrying ``client_id`` and ``ext_outflow_ratio``, arranged so that a subset of
the leads match a client in the features frame. The test then re-derives the
join, the quartile binning, and each per-quartile rate independently from the
joined+binned data and asserts :func:`compute_report` agrees.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from part2_network.config import P001_PROMO_ID, TREATED_CONTROL_GROUP
from part2_network.validation import (
    assign_quartiles,
    compute_report,
    join_rate,
    join_to_features,
)


def _client_id(n: int) -> str:
    """Zero-padded client id whose lexicographic order matches numeric order."""
    return f"C{n:04d}"


@st.composite
def treated_leads_and_features(draw: st.DrawFn) -> tuple:
    """Build P001 Treated_Leads and a Features_File frame with partial overlap.

    A universe of distinct client ids is split into two disjoint pools: a
    ``feature`` pool that appears in the features frame (each with an
    ``ext_outflow_ratio`` in [0, 1]) and a ``lead_only`` pool that does not.
    Each generated P001 Treated_Lead draws its ``client_id`` from the union, so
    some leads inner-join to features and some do not. Every lead is a genuine
    P001 Treated_Lead (``promo_id`` "P001", ``control_group`` 0) carrying a 0/1
    ``joined`` flag, so the selection is already the treated population and the
    test can focus on the join-rate arithmetic (Requirement 9.6).

    Returns:
        A ``(treated_leads, features)`` pair of DataFrames.
    """
    n_feature_clients = draw(st.integers(min_value=1, max_value=8))
    n_lead_only_clients = draw(st.integers(min_value=0, max_value=4))

    total_clients = n_feature_clients + n_lead_only_clients
    # Distinct ids for the whole universe, then partitioned into the two pools.
    universe = draw(
        st.lists(
            st.integers(min_value=0, max_value=9999).map(_client_id),
            min_size=total_clients,
            max_size=total_clients,
            unique=True,
        )
    )
    feature_clients = universe[:n_feature_clients]
    lead_only_clients = universe[n_feature_clients:]

    ratios = draw(
        st.lists(
            st.floats(
                min_value=0.0,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=n_feature_clients,
            max_size=n_feature_clients,
        )
    )
    features = pd.DataFrame(
        {
            "client_id": feature_clients,
            "ext_outflow_ratio": ratios,
        }
    )

    lead_client_pool = feature_clients + lead_only_clients
    lead_client_ids = draw(
        st.lists(
            st.sampled_from(lead_client_pool),
            min_size=1,
            max_size=20,
        )
    )
    joined_flags = draw(
        st.lists(
            st.sampled_from([0, 1]),
            min_size=len(lead_client_ids),
            max_size=len(lead_client_ids),
        )
    )
    treated_leads = pd.DataFrame(
        {
            "promo_id": [P001_PROMO_ID] * len(lead_client_ids),
            "client_id": lead_client_ids,
            "control_group": [TREATED_CONTROL_GROUP] * len(lead_client_ids),
            "joined": joined_flags,
        }
    )

    return treated_leads, features


# Feature: part2-network, Property: per-quartile join rate
@settings(max_examples=200)
@given(treated_leads_and_features())
def test_per_quartile_join_rate_is_bounded_mean_of_joined_flag(payload):
    """Each quartile's Join_Rate is a bounded mean of the ``joined`` flag,
    independently recomputed from the joined and binned data.

    Validates: Requirements 9.6
    """
    treated_leads, features = payload
    report = compute_report(treated_leads, features)

    # Independently reproduce the inner join and the binning the report uses.
    joined = join_to_features(treated_leads, features)
    assert report["matched"] == len(joined)

    quartiles = report["quartiles"]

    # Every reported quartile is non-empty and the counts sum to the matched
    # (inner-joined) lead total (Requirement 9.6: only non-empty bins reported).
    for quartile in quartiles:
        assert quartile["count"] >= 1
    assert sum(q["count"] for q in quartiles) == report["matched"]

    if report["matched"] == 0:
        # No joined leads: no quartile entries exist.
        assert quartiles == []
        return

    labels = assign_quartiles(joined)

    for quartile in quartiles:
        group = joined[labels == quartile["label"]]

        # The reported count matches the independently binned group size.
        assert len(group) == quartile["count"]

        # Each join_rate lies in the inclusive range [0, 1] (Requirement 9.6).
        assert 0.0 <= quartile["join_rate"] <= 1.0

        # Independently recompute: count(joined == 1) / count(group).
        expected = (group["joined"] == 1).sum() / len(group)
        assert quartile["join_rate"] == expected
        # ...and it equals the mean of the joined flag over that group.
        assert quartile["join_rate"] == group["joined"].mean()


# Feature: part2-network, Property: per-quartile join rate
@settings(max_examples=200)
@given(
    flags=st.lists(st.sampled_from([0, 1]), min_size=1, max_size=30),
)
def test_join_rate_equals_mean_of_joined_flag(flags):
    """``join_rate`` of a hand-built group equals the mean of its 0/1 ``joined``
    flag and stays within [0, 1].

    Validates: Requirements 9.6
    """
    group = pd.DataFrame({"joined": flags})

    rate = join_rate(group)

    assert 0.0 <= rate <= 1.0
    assert rate == sum(flags) / len(flags)
    assert rate == group["joined"].mean()
