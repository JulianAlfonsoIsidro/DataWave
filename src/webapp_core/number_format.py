"""How Expected Joiners and shares are written on the page (Part 9 round 2).

Pure helpers, no Streamlit (spec ``part9-layout-fixes``, Requirements 20
and 21). Expected Joiners is a forecast (the sum of each sendable lead's
chance of joining), so it has decimals. The page shows it as a whole number
of people with the forecast beside it: ``87 (Forecasted: 87.3)``.

- :func:`shown_joiners` rounds with halves up, the same rule the decision
  cards use (:func:`webapp_core.card_view.round_half_up`).
- :func:`forecast_text` writes the forecast to one decimal.
- :func:`share_pct` writes a share with one decimal, or ``None`` when the
  whole is 0, so nothing ever divides by zero.

A total is rounded from the unrounded sum, so rounded rows can differ from
the rounded total by 1 (Requirement 20.6).
"""

from __future__ import annotations

import math

from webapp_core.card_view import round_half_up

FORECAST_LABEL = "Forecasted"


def _finite(x: object) -> float:
    try:
        value = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def shown_joiners(forecast: object) -> int:
    """The forecast as a whole number of people, halves rounded up."""
    return round_half_up(_finite(forecast))


def forecast_number(forecast: object) -> str:
    """The forecast to one decimal, with thousands separators: ``1,204.4``."""
    return f"{_finite(forecast):,.1f}"


def forecast_text(forecast: object, *, short: bool = False) -> str:
    """``Forecasted: 87.3`` (or just ``87.3`` with ``short=True``, for tables)."""
    number = forecast_number(forecast)
    return number if short else f"{FORECAST_LABEL}: {number}"


def share_pct(part: object, whole: object) -> str | None:
    """``part / whole`` as a percentage with one decimal (``12.8%``).

    ``None`` when ``whole`` is 0 or not a positive number.
    """
    w = _finite(whole)
    if w <= 0:
        return None
    return f"{_finite(part) / w * 100:.1f}%"


def of_sendable_text(forecast: object, sendable: object) -> str:
    """``out of 1,595 sendable leads (12.8%)``; no percentage when 0 sendable."""
    n = int(_finite(sendable))
    noun = "lead" if n == 1 else "leads"
    pct = share_pct(forecast, n)
    return f"out of {n:,} sendable {noun}" + (f" ({pct})" if pct else "")
