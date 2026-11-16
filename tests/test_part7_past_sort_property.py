"""Property test for past campaign ordering (Part 7, Property 8).

**Property 8: Past campaign ordering is deterministic**

**Validates: Requirements 11.2, 11.12, 11.13**
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from tests.strategies_part7 import past_campaign_profiles
from webapp_core.past_campaigns import (
    SORT_MODES,
    SORT_MOST_SIMILAR,
    SORT_NEWEST,
    SORT_OLDEST,
    CampaignRow,
    sort_campaigns,
)
from webapp_core.similarity import CampaignProfile, SimilarityResult


def _to_row(p: dict) -> CampaignRow:
    profile = CampaignProfile(
        promo_id=p["promo_id"],
        name=p["promo_id"],
        product_type=p["product_type"] or "",
        mechanic=p["mechanic"] or "",
        threshold_php=p["threshold_php"],
        reward=p["reward"] or "",
        start=p["start_date"],
        end=p["end_date"],
        channels=tuple(p["channels"] or ()),
        audience_segments=(),
        opt_in_rate=None,
        treated_leads=0,
    )
    return CampaignRow(profile, SimilarityResult(components=(), score=p["score"]))


def _ids(rows) -> list[str]:
    return [r.profile.promo_id for r in rows]


def _expected(rows: list[CampaignRow], mode: str) -> list[str]:
    """Independent reference ordering built from the documented rules."""
    far = 10**9

    def newest(r):
        s = r.profile.start
        return -s.toordinal() if s else far

    def oldest(r):
        s = r.profile.start
        return s.toordinal() if s else far

    if mode == SORT_MOST_SIMILAR:
        def key(r):
            sc = r.similarity.score
            return (sc is None, -(sc or 0.0), newest(r), r.profile.promo_id)
    elif mode == SORT_OLDEST:
        def key(r):
            return (oldest(r), r.profile.promo_id)
    else:
        def key(r):
            return (newest(r), r.profile.promo_id)
    return _ids(sorted(rows, key=key))


@settings(max_examples=100, deadline=None)
@given(
    data=st.data(),
    profiles=st.lists(
        past_campaign_profiles(), min_size=0, max_size=12, unique_by=lambda p: p["promo_id"]
    ),
)
def test_sort_campaigns_is_deterministic(data, profiles):
    rows = [_to_row(p) for p in profiles]
    shuffled = data.draw(st.permutations(rows))

    for mode in SORT_MODES:
        a = sort_campaigns(rows, mode)
        b = sort_campaigns(shuffled, mode)
        # Independent of input order.
        assert _ids(a) == _ids(b)
        # Matches the documented rule (ties by promo_id ascending, unscored last).
        assert _ids(a) == _expected(rows, mode)
        assert sorted(_ids(a)) == sorted(_ids(rows))

    # Spot-check the Most Similar invariants explicitly.
    ms = sort_campaigns(shuffled, SORT_MOST_SIMILAR)
    scores = [r.similarity.score for r in ms]
    seen_none = False
    for s in scores:
        if s is None:
            seen_none = True
        else:
            assert not seen_none
    scored = [s for s in scores if s is not None]
    assert scored == sorted(scored, reverse=True)
    assert SORT_NEWEST in SORT_MODES and SORT_OLDEST in SORT_MODES
