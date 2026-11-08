"""Unit tests for Part 7 threshold types (Requirements 5.1, 5.2, 5.3, 5.7, 10.3)."""
from __future__ import annotations

import pandas as pd
import pytest

from webapp_core.threshold import (
    BALANCE_INCREASE_NOTE,
    THRESHOLD_SPECS,
    ThresholdType,
    default_value,
    effective_threshold,
    format_value,
)

# Requirement 5.1: (min, max, step) per type.
EXPECTED = {
    ThresholdType.TOP_UP: (50_000, 2_000_000, 10_000),
    ThresholdType.MIN_BALANCE: (10_000, 5_000_000, 10_000),
    ThresholdType.BALANCE_INCREASE: (5, 100, 5),
    ThresholdType.OPENING_AMOUNT: (1_000, 100_000, 1_000),
}


def test_exactly_four_types() -> None:
    assert set(THRESHOLD_SPECS) == set(ThresholdType) == set(EXPECTED)


@pytest.mark.parametrize("t", list(ThresholdType))
def test_min_max_step(t: ThresholdType) -> None:
    spec = THRESHOLD_SPECS[t]
    assert (spec.minimum, spec.maximum, spec.step) == EXPECTED[t]


@pytest.mark.parametrize("t", list(ThresholdType))
def test_default_inside_range_and_on_grid(t: ThresholdType) -> None:
    spec = THRESHOLD_SPECS[t]
    d = default_value(t)
    assert spec.minimum <= d <= spec.maximum
    assert (d - spec.minimum) % spec.step == 0


@pytest.mark.parametrize(
    "t,expected",
    [
        (ThresholdType.TOP_UP, 530_000),  # 50k + floor(487.5k/10k)*10k
        (ThresholdType.MIN_BALANCE, 1_250_000),  # 10k + 1,240k
        (ThresholdType.BALANCE_INCREASE, 25),  # 5 + floor(23.75/5)*5
        (ThresholdType.OPENING_AMOUNT, 25_000),
    ],
)
def test_default_is_min_plus_quarter_width_rounded_down(t, expected) -> None:
    # Requirement 5.3
    assert default_value(t) == expected


@pytest.mark.parametrize(
    "t,value,text",
    [
        (ThresholdType.TOP_UP, 50_000, "₱50,000"),
        (ThresholdType.TOP_UP, 2_000_000, "₱2,000,000"),
        (ThresholdType.MIN_BALANCE, 5_000_000, "₱5,000,000"),
        (ThresholdType.OPENING_AMOUNT, 1_000, "₱1,000"),
        (ThresholdType.BALANCE_INCREASE, 5, "5%"),
        (ThresholdType.BALANCE_INCREASE, 100, "100%"),
        (ThresholdType.BALANCE_INCREASE, 25.0, "25%"),
    ],
)
def test_format_value(t, value, text) -> None:
    assert format_value(t, value) == text


def test_labels_carry_units() -> None:
    for spec in THRESHOLD_SPECS.values():
        if spec.is_percent:
            assert "%" in spec.label
        else:
            assert spec.label.endswith("(₱)")


def test_balance_increase_note_length_and_presence() -> None:
    assert 0 < len(BALANCE_INCREASE_NOTE) <= 200
    res = effective_threshold(
        ThresholdType.BALANCE_INCREASE, 10, pd.Series([100_000.0, 200_000.0])
    )
    assert res.note is not None and len(res.note) <= 200
    assert res.threshold_php == pytest.approx(15_000.0)


@pytest.mark.parametrize(
    "t", [ThresholdType.TOP_UP, ThresholdType.MIN_BALANCE, ThresholdType.OPENING_AMOUNT]
)
def test_peso_types_have_no_note(t: ThresholdType) -> None:
    res = effective_threshold(t, 60_000, None)
    assert res.note is None and res.threshold_php == 60_000.0
