"""How sure the forecast looks (Part 9 round 3).

Pure, read-only, no Streamlit (spec part9-layout-fixes, Requirement 38). It
changes no model, score or segment; it only compares counts that exist.

- :func:`historical_join_rate` gives the join rate of treated past leads.
- :func:`forecast_caution` returns a short note when a run's expected join
  rate is at least :data:`CAUTION_FACTOR` times the historical rate.
"""

from __future__ import annotations

import pandas as pd

CAUTION_FACTOR = 2.0

def historical_join_rate(promo_leads: pd.DataFrame) -> float | None:
    """Join rate of treated past leads, as a fraction (None when unknown)."""
    if not {"control_group", "joined"} <= set(promo_leads.columns):
        return None
    treated = promo_leads[promo_leads["control_group"] == 0]
    return float(treated["joined"].mean()) if len(treated) else None


def forecast_caution(forecast: float, sendable: int, historical: float | None,
                     factor: float = CAUTION_FACTOR) -> str | None:
    """A plain caution when the run's expected join rate looks far above history."""
    if not sendable or historical is None or historical <= 0:
        return None
    rate = forecast / sendable
    if rate < historical * factor:
        return None
    return (
        f"This run expects {rate * 100:.1f}% of sendable leads to join, more than "
        f"{factor:g} times the {historical * 100:.1f}% that joined past promos. "
        "Treat the forecast with care."
    )
