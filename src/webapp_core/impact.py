"""Impact summary: Baseline_Plan versus Recommended_Plan (Requirement 8).

Pure Python arithmetic over the in-memory run result and
``data/channel_costs.csv``. No Streamlit and no Bedrock: every number comes
from the run (Requirement 8.9).

- Baseline_Plan: every eligible, non-excluded lead (control included) on its
  best channel, taken from ``RunResult.non_excluded`` (Requirement 8.1).
- Recommended_Plan: the sendable leads of segments whose card action is not
  ``Skip`` (Requirement 8.2).
- Expected joiners are the sum of ``p_join``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd

from webapp_core.card_view import round_half_up

DEFAULT_COSTS_PATH = Path(__file__).resolve().parents[2] / "data" / "channel_costs.csv"

SKIP_ACTION = "Skip"

NEUTRAL_MESSAGE = "No comparison is available for this run."
COST_UNAVAILABLE_MESSAGE = "Cost savings are unavailable."


@dataclass(frozen=True)
class PlanTotals:
    """Messages, expected joiners, and channel cost of one plan.

    ``channel_cost`` is NaN when costs are unavailable for the plan.
    """

    messages: int
    expected_joiners: float
    channel_cost: float


@dataclass(frozen=True)
class ImpactSummary:
    """Baseline vs Recommended comparison (Requirements 8.3 to 8.8)."""

    baseline: PlanTotals
    recommended: PlanTotals
    messages_saved: int
    joiners_kept_pct: int | None  # Y
    fewer_clients_pct: int | None  # X
    cost_saved: int | None  # Z, None when costs unavailable
    available: bool  # False when baseline has 0 messages or 0 joiners
    cost_available: bool
    banner: str | None
    neutral_message: str | None
    cost_message: str | None = None


def load_channel_costs(path: Path | str = DEFAULT_COSTS_PATH) -> dict[str, float] | None:
    """Read ``channel -> cost_php_per_message``; None if missing or unreadable."""
    try:
        df = pd.read_csv(path)
        channels = df["channel"].astype(str).str.strip()
        costs = pd.to_numeric(df["cost_php_per_message"], errors="raise")
    except Exception:
        return None
    out: dict[str, float] = {}
    for ch, c in zip(channels, costs):
        if not math.isfinite(float(c)) or float(c) < 0:
            return None
        out[ch] = float(c)
    return out or None


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["client_id", "best_channel", "p_join"])


def plan_totals(frame: pd.DataFrame | None, costs: Mapping[str, float] | None) -> PlanTotals:
    """Totals for a plan frame (``best_channel``, ``p_join``).

    Channel cost is NaN if ``costs`` is None or any used channel lacks a cost.
    """
    if frame is None or len(frame) == 0:
        return PlanTotals(0, 0.0, 0.0 if costs is not None else float("nan"))
    messages = int(len(frame))
    joiners = float(pd.to_numeric(frame["p_join"], errors="coerce").fillna(0.0).sum())
    if costs is None:
        return PlanTotals(messages, joiners, float("nan"))
    per_lead = frame["best_channel"].map(lambda c: costs.get(c))
    if per_lead.isna().any():
        return PlanTotals(messages, joiners, float("nan"))
    return PlanTotals(messages, joiners, float(per_lead.astype(float).sum()))


def _clamp_pct(value: float) -> int:
    return max(0, min(100, round_half_up(value)))


def _recommended_frame(run) -> pd.DataFrame:
    skipped = {
        str(c.get("segment")) for c in (run.cards or []) if c.get("action") == SKIP_ACTION
    }
    parts = [
        df
        for seg, df in (run.sendable_by_segment or {}).items()
        if seg not in skipped and df is not None and len(df) > 0
    ]
    if not parts:
        return _empty_frame()
    return pd.concat(parts, ignore_index=True)


def compute_impact(run, costs: Mapping[str, float] | None) -> ImpactSummary:
    """Compute the Impact_Summary from a run result (Requirements 8.1 to 8.10)."""
    baseline_frame = run.non_excluded if run.non_excluded is not None else _empty_frame()
    rec_frame = _recommended_frame(run)

    baseline = plan_totals(baseline_frame, costs)
    recommended = plan_totals(rec_frame, costs)

    # Guard the subset invariant (Requirement 8.10) against odd inputs.
    rec_msgs = min(recommended.messages, baseline.messages)
    messages_saved = baseline.messages - rec_msgs

    if baseline.messages == 0 or baseline.expected_joiners <= 0:
        return ImpactSummary(
            baseline=baseline,
            recommended=recommended,
            messages_saved=messages_saved,
            joiners_kept_pct=None,
            fewer_clients_pct=None,
            cost_saved=None,
            available=False,
            cost_available=False,
            banner=None,
            neutral_message=NEUTRAL_MESSAGE,
            cost_message=None,
        )

    x = _clamp_pct((baseline.messages - rec_msgs) / baseline.messages * 100)
    y = _clamp_pct(recommended.expected_joiners / baseline.expected_joiners * 100)

    cost_ok = not (math.isnan(baseline.channel_cost) or math.isnan(recommended.channel_cost))
    if cost_ok:
        z: int | None = int(round(baseline.channel_cost - recommended.channel_cost))
        banner: str | None = (
            f"Messaging {x}% fewer clients keeps {y}% of expected joiners "
            f"and saves ₱{z:,} in channel costs."
        )
        cost_message = None
    else:
        z = None
        banner = None
        cost_message = COST_UNAVAILABLE_MESSAGE

    return ImpactSummary(
        baseline=baseline,
        recommended=recommended,
        messages_saved=messages_saved,
        joiners_kept_pct=y,
        fewer_clients_pct=x,
        cost_saved=z,
        available=True,
        cost_available=cost_ok,
        banner=banner,
        neutral_message=None,
        cost_message=cost_message,
    )
