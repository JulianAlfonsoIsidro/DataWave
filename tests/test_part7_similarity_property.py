"""Property test for the deterministic Similarity_Score (Part 7).

**Property 7: Similarity score bounds, determinism, and renormalization**
"""
from __future__ import annotations

import math

from hypothesis import given, settings, strategies as st

from tests.strategies_part7 import campaign_profiles
from webapp_core.similarity import (
    COMPONENT_KEYS,
    CampaignProfile,
    NewPromoProfile,
    similarity,
)

_SEGMENTS = ["Ready Toppers", "Untapped Wealth", "Willing but Stretched", "Not Now"]
_segments = st.lists(st.sampled_from(_SEGMENTS), max_size=4, unique=True).map(tuple)


def _new_promo(d: dict, segments: tuple[str, ...]) -> NewPromoProfile:
    return NewPromoProfile(
        name=d["reward"],
        summary=d["reward"],
        objective=d["mechanic"],
        product_type=d["product_type"],
        mechanic=d["mechanic"],
        threshold_php=d["threshold_php"],
        eligible_segments=segments,
        channels=tuple(d["channels"] or ()),
        start=d["start_date"],
        end=d["end_date"],
    )


def _past(d: dict, segments: tuple[str, ...]) -> CampaignProfile:
    return CampaignProfile(
        promo_id=d["promo_id"],
        name=d["reward"] or "",
        product_type=d["product_type"] or "",
        mechanic=d["mechanic"] or "",
        threshold_php=d["threshold_php"],
        reward=d["reward"] or "",
        start=d["start_date"],
        end=d["end_date"],
        channels=tuple(d["channels"] or ()),
        audience_segments=segments,
        opt_in_rate=None,
        treated_leads=0,
    )


@settings(max_examples=100, deadline=None)
@given(
    cur=campaign_profiles(),
    past=campaign_profiles(),
    cur_segs=_segments,
    past_segs=_segments,
)
def test_similarity_bounds_determinism_renormalization(cur, past, cur_segs, past_segs):
    """**Validates: Requirements 11.8, 11.9, 11.10, 11.11, 11.12**"""
    current = _new_promo(cur, cur_segs)
    campaign = _past(past, past_segs)

    result = similarity(current, campaign)

    # Determinism.
    assert similarity(current, campaign) == result

    assert tuple(c.key for c in result.components) == COMPONENT_KEYS
    available = [c for c in result.components if c.fraction is not None]
    unavailable = [c for c in result.components if c.fraction is None]

    # Unavailable components are excluded from scoring.
    for c in unavailable:
        assert c.points is None and c.max_points is None

    if not available:
        assert result.score is None
        return

    for c in available:
        assert 0.0 <= c.fraction <= 1.0
        assert c.max_points is not None and c.points is not None
        assert math.isclose(c.points, c.fraction * c.max_points, abs_tol=1e-9)

    assert math.isclose(sum(c.max_points for c in available), 100.0, abs_tol=1e-6)
    assert result.score is not None
    assert 0.0 <= result.score <= 100.0
    assert math.isclose(result.score, sum(c.points for c in available), abs_tol=1e-6)
