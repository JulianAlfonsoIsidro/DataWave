"""Threshold types, fixed ranges, and conversion to ``Threshold_Php``.

Pure logic with no Streamlit imports (Requirements 5.1 to 5.7, 5.10, 5.11).

Four threshold types are offered. Three are plain peso values used directly
as ``threshold_php``. Balance Increase is a percentage of each client's
``latest_adb``: the per-client amounts drive the capacity check, and their
median becomes ``threshold_php`` for model scoring.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

__all__ = [
    "ThresholdType",
    "ThresholdSpec",
    "THRESHOLD_SPECS",
    "ThresholdResolution",
    "BALANCE_INCREASE_NOTE",
    "NO_USABLE_ADB_ERROR",
    "default_value",
    "format_value",
    "per_client_amounts",
    "effective_threshold",
]


class ThresholdType(str, Enum):
    """The four selectable threshold types (Requirement 5.1)."""

    TOP_UP = "Top-Up Amount"
    MIN_BALANCE = "Minimum Balance To Maintain"
    BALANCE_INCREASE = "Balance Increase"
    OPENING_AMOUNT = "Opening Amount For A New Account"


@dataclass(frozen=True)
class ThresholdSpec:
    """Fixed slider range and step for one threshold type."""

    type: ThresholdType
    label: str
    minimum: int
    maximum: int
    step: int
    is_percent: bool


THRESHOLD_SPECS: dict[ThresholdType, ThresholdSpec] = {
    ThresholdType.TOP_UP: ThresholdSpec(
        ThresholdType.TOP_UP, "Top-Up Amount (₱)", 50_000, 2_000_000, 10_000, False
    ),
    ThresholdType.MIN_BALANCE: ThresholdSpec(
        ThresholdType.MIN_BALANCE,
        "Minimum Balance To Maintain (₱)",
        10_000,
        5_000_000,
        10_000,
        False,
    ),
    ThresholdType.BALANCE_INCREASE: ThresholdSpec(
        ThresholdType.BALANCE_INCREASE,
        "Balance Increase (% Of Current ADB)",
        5,
        100,
        5,
        True,
    ),
    ThresholdType.OPENING_AMOUNT: ThresholdSpec(
        ThresholdType.OPENING_AMOUNT,
        "Opening Amount For A New Account (₱)",
        1_000,
        100_000,
        1_000,
        False,
    ),
}

BALANCE_INCREASE_NOTE = (
    "Each client's threshold is this percentage of their current ADB. "
    "The median of those amounts is used for scoring."
)
NO_USABLE_ADB_ERROR = "The percentage threshold cannot be applied: no client has a usable ADB."


@dataclass(frozen=True)
class ThresholdResolution:
    """Result of resolving a threshold selection (Requirements 5.4 to 5.7, 5.11)."""

    threshold_php: float | None
    per_client: pd.Series | None
    error: str | None
    note: str | None


def default_value(t: ThresholdType) -> int:
    """Minimum plus 25% of the range width, rounded down to the step (Req 5.3)."""
    spec = THRESHOLD_SPECS[ThresholdType(t)]
    width = spec.maximum - spec.minimum
    steps = int(math.floor((0.25 * width) / spec.step))
    return spec.minimum + steps * spec.step


def format_value(t: ThresholdType, v: float) -> str:
    """Format a value with a peso sign and separators, or as a whole percent (Req 5.2)."""
    spec = THRESHOLD_SPECS[ThresholdType(t)]
    if spec.is_percent:
        return f"{int(round(float(v)))}%"
    return f"₱{int(round(float(v))):,}"


def per_client_amounts(pct: float, latest_adb: pd.Series) -> pd.Series:
    """Per-client amounts: ``pct / 100 * latest_adb`` (Req 5.5).

    Missing or non-finite ADB yields NaN, which fails the capacity check.
    """
    adb = pd.to_numeric(latest_adb, errors="coerce").astype(float)
    adb = adb.where(np.isfinite(adb))
    return (float(pct) / 100.0) * adb


def effective_threshold(
    t: ThresholdType, value: float, latest_adb: pd.Series | None
) -> ThresholdResolution:
    """Resolve a selection into ``threshold_php`` and optional per-client amounts."""
    t = ThresholdType(t)
    if t is not ThresholdType.BALANCE_INCREASE:
        return ThresholdResolution(float(value), None, None, None)

    if latest_adb is None:
        return ThresholdResolution(None, None, NO_USABLE_ADB_ERROR, None)
    amounts = per_client_amounts(value, latest_adb)
    usable = amounts.dropna()
    if usable.empty:
        return ThresholdResolution(None, amounts, NO_USABLE_ADB_ERROR, None)
    return ThresholdResolution(
        float(usable.median()), amounts, None, BALANCE_INCREASE_NOTE[:200]
    )
