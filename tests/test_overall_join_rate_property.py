"""Property-based test for the overall inner-join rate.

# Feature: part2-network, Property: overall inner-join rate

Covers Property 18 of the part2-network spec: the overall inner-join rate
reported by :func:`part2_network.validation.compute_report` is a bounded
fraction equal to matched / total_treated (Requirement 9.8).

The overall inner-join rate is defined (Requirement 9.8) as the count of P001
Treated_Leads that inner-join to the Features_File divided by the total count of
selected P001 Treated_Leads, producing a value in the inclusive range 0 to 1.

Strategy shape:
- A set of P001 Treated_Leads -- every row has ``promo_id`` "P001" and
  ``control_group`` 0 (so they are exactly the selected population), with
  ``joined`` drawn from {0, 1} and a *unique* ``client_id`` drawn from a pool.
  Unique lead client_ids keep the inner join one-to-one, so the matched count
  equals the size of the intersection of lead and feature client_ids -- a clean
  independent reference for matched / total_treated.
- A Features_File frame whose ``client_id`` set partially overlaps the leads'
  client_ids, carrying the ``ext_outflow_ratio`` column the report needs. Sizes
  vary, including empty leads, so matched ranges over 0..total_treated.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from part2_network.config import P001_PROMO_ID, TREATED_CONTROL_GROUP
from part2_network.validation import compute_report


# A pool of candidate client ids shared by leads and features so the two frames
# can partially overlap. Zero-padded so lexicographic order is stable/obvious.
_CLIENT_POOL = [f"C{n:04d}" for n in range(12)]


@st.composite
def _leads_and_features(draw: st.DrawFn) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Draw (treated_leads, features) with partially overlapping client ids.

    All leads are P001 / control_group 0 (the selected population) with unique
    client ids; features draw a (possibly disjoint, possibly overlapping,
    possibly empty) subset-plus-extras of the pool. Empty leads are allowed.
    """
    # Unique lead client ids (0..len(pool)); min_size 0 covers empty leads.
    lead_clients = draw(
        st.lists(
            st.sampled_from(_CLIENT_POOL),
            min_size=0,
            max_size=len(_CLIENT_POOL),
            unique=True,
        )
    )
    joined_flags = draw(
        st.lists(
            st.sampled_from([0, 1]),
            min_size=len(lead_clients),
            max_size=len(lead_clients),
        )
    )
    treated_leads = pd.DataFrame(
        {
            "promo_id": [P001_PROMO_ID] * len(lead_clients),
            "client_id": lead_clients,
            "control_group": [TREATED_CONTROL_GROUP] * len(lead_clients),
            "joined": joined_flags,
        }
    )

    # Feature client ids: an independent unique subset of the pool so the
    # overlap with the leads varies from none to full.
    feature_clients = draw(
        st.lists(
            st.sampled_from(_CLIENT_POOL),
            min_size=0,
            max_size=len(_CLIENT_POOL),
            unique=True,
        )
    )
    ratios = draw(
        st.lists(
            st.floats(
                min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
            ),
            min_size=len(feature_clients),
            max_size=len(feature_clients),
        )
    )
    features = pd.DataFrame(
        {
            "client_id": feature_clients,
            "ext_outflow_ratio": ratios,
        }
    )

    return treated_leads, features


@settings(max_examples=200)
@given(_leads_and_features())
def test_overall_join_rate_is_bounded_matched_over_total(data) -> None:
    """overall_join_rate == matched/total_treated and lies in [0, 1].

    **Validates: Requirements 9.8**
    """
    treated_leads, features = data
    report = compute_report(treated_leads, features)

    total_treated = report["total_treated"]
    matched = report["matched"]
    rate = report["overall_join_rate"]

    # Independent reference: with unique lead client ids the inner join is
    # one-to-one, so the matched count is exactly the size of the intersection
    # of the lead and feature client-id sets.
    lead_client_set = set(treated_leads["client_id"])
    feature_client_set = set(features["client_id"])
    expected_matched = len(lead_client_set & feature_client_set)

    assert total_treated == len(treated_leads)
    assert matched == expected_matched
    assert matched <= total_treated

    # The rate is a bounded fraction (Requirement 9.8).
    assert 0.0 <= rate <= 1.0

    if total_treated == 0:
        # No division by zero; rate is 0.0 and no quartiles are produced
        # (aligns with Requirement 9.9).
        assert rate == 0.0
        assert report["quartiles"] == []
    else:
        assert rate == matched / total_treated
