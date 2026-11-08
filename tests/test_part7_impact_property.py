"""Property test for the impact summary invariants (Part 7, Property 5).

Feature: part7-AI-and-finishing, Property 5: Impact summary invariants.

**Validates: Requirements 8.3, 8.4, 8.7, 8.10**
"""
from __future__ import annotations

from types import SimpleNamespace

from hypothesis import given, settings

from tests.strategies_part7 import frame_and_subset
from webapp_core.impact import compute_impact

COSTS = {"In-app": 0.05, "Email": 0.25, "SMS": 1.5}


@settings(max_examples=100, deadline=None)
@given(frame_and_subset())
def test_impact_summary_invariants(pair):
    baseline, recommended = pair
    run = SimpleNamespace(
        non_excluded=baseline,
        sendable_by_segment={"Ready Toppers": recommended},
        cards=[{"segment": "Ready Toppers", "action": "Send"}],
    )

    s = compute_impact(run, COSTS)  # must never raise, even for empty baselines

    # Requirement 8.10: Recommended never exceeds Baseline.
    assert s.recommended.messages <= s.baseline.messages
    assert s.recommended.expected_joiners <= s.baseline.expected_joiners + 1e-9
    assert s.messages_saved == s.baseline.messages - s.recommended.messages

    if s.baseline.messages == 0 or s.baseline.expected_joiners <= 0:
        # Requirement 8.7: neutral message, no percentages, no banner.
        assert not s.available
        assert s.banner is None
        assert s.neutral_message
        assert s.fewer_clients_pct is None and s.joiners_kept_pct is None
        assert s.cost_saved is None
    else:
        # Requirements 8.3, 8.4: whole percents within 0..100.
        assert s.available
        for pct in (s.fewer_clients_pct, s.joiners_kept_pct):
            assert isinstance(pct, int) and 0 <= pct <= 100
        assert s.cost_available
        expected_z = round(s.baseline.channel_cost - s.recommended.channel_cost)
        assert s.cost_saved == expected_z
        assert s.cost_saved >= 0
        assert s.banner
