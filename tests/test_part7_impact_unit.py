"""Unit tests for the Part 7 impact summary (Requirements 8.3, 8.6, 8.7, 8.8, 10.7)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from webapp_core.impact import (
    COST_UNAVAILABLE_MESSAGE,
    NEUTRAL_MESSAGE,
    compute_impact,
    load_channel_costs,
)

COSTS = {"In-app": 1.0, "Email": 2.0, "SMS": 5.0}


def _frame(rows: list[tuple[str, float, int]], start: int = 0) -> pd.DataFrame:
    """Build a plan frame from (channel, p_join, count) groups."""
    data = []
    i = start
    for channel, p, n in rows:
        for _ in range(n):
            data.append({"client_id": f"C{i}", "best_channel": channel, "p_join": p})
            i += 1
    return pd.DataFrame(data, columns=["client_id", "best_channel", "p_join"])


def _run(sendable: dict[str, pd.DataFrame], actions: dict[str, str], baseline: pd.DataFrame):
    return SimpleNamespace(
        non_excluded=baseline,
        sendable_by_segment=sendable,
        cards=[{"segment": s, "action": a} for s, a in actions.items()],
    )


def _hand_run():
    """Baseline: 4 In-app @0.5, 3 Email @0.2, 3 SMS @0.1. Segment B is skipped."""
    a = _frame([("In-app", 0.5, 4)])
    b = _frame([("Email", 0.2, 3), ("SMS", 0.1, 3)], start=4)
    baseline = pd.concat([a, b], ignore_index=True)
    return _run({"A": a, "B": b}, {"A": "Send", "B": "Skip"}, baseline)


def test_hand_computed_x_y_z():
    s = compute_impact(_hand_run(), COSTS)
    # Messages: 10 -> 4, X = 6/10 = 60%
    assert s.baseline.messages == 10 and s.recommended.messages == 4
    assert s.messages_saved == 6
    assert s.fewer_clients_pct == 60
    # Joiners: 2.0 / 2.9 = 68.97 -> 69%
    assert s.joiners_kept_pct == 69
    # Cost: baseline 4 + 6 + 15 = 25, recommended 4, Z = 21
    assert s.cost_saved == 21
    assert s.available and s.cost_available
    assert s.banner == (
        "Messaging 60% fewer clients keeps 69% of expected joiners "
        "and saves ₱21 in channel costs."
    )


def test_zero_baseline_messages_gives_neutral_message():
    empty = _frame([])
    s = compute_impact(_run({}, {}, empty), COSTS)
    assert not s.available
    assert s.neutral_message == NEUTRAL_MESSAGE
    assert s.banner is None
    assert s.fewer_clients_pct is None and s.joiners_kept_pct is None
    assert s.cost_saved is None


def test_zero_baseline_joiners_gives_neutral_message():
    a = _frame([("Email", 0.0, 3)])
    s = compute_impact(_run({"A": a}, {"A": "Send"}, a), COSTS)
    assert s.baseline.messages == 3
    assert not s.available
    assert s.neutral_message == NEUTRAL_MESSAGE
    assert s.banner is None


def test_missing_cost_file_keeps_two_tiles(tmp_path):
    costs = load_channel_costs(tmp_path / "does_not_exist.csv")
    assert costs is None
    s = compute_impact(_hand_run(), costs)
    assert s.available and not s.cost_available
    assert s.fewer_clients_pct == 60
    assert s.joiners_kept_pct == 69
    assert s.messages_saved == 6
    assert s.cost_saved is None
    assert s.banner is None
    assert s.cost_message == COST_UNAVAILABLE_MESSAGE


def test_what_if_rescore_recomputes():
    first = compute_impact(_hand_run(), COSTS)

    # A second run where segment B's Email leads are now sendable (B no longer skipped
    # for them): recommended = 4 In-app + 3 Email.
    a = _frame([("In-app", 0.5, 4)])
    b = _frame([("Email", 0.2, 3)], start=4)
    c = _frame([("SMS", 0.1, 3)], start=7)
    baseline = pd.concat([a, b, c], ignore_index=True)
    second_run = _run({"A": a, "B": b, "C": c}, {"A": "Send", "B": "Send", "C": "Skip"}, baseline)
    second = compute_impact(second_run, COSTS)

    assert second.fewer_clients_pct == 30
    assert second.joiners_kept_pct == 90  # 2.6 / 2.9 = 89.66
    assert second.cost_saved == 15  # 25 - (4 + 6)
    assert second.messages_saved == 3
    assert (second.fewer_clients_pct, second.joiners_kept_pct, second.cost_saved) != (
        first.fewer_clients_pct,
        first.joiners_kept_pct,
        first.cost_saved,
    )
