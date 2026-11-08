"""Property test for the Balance Increase threshold (Part 7, Property 4)."""
from __future__ import annotations

import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.strategies_part7 import adb_series, all_missing_adb_series, pct_grid
from webapp_core.threshold import (
    THRESHOLD_SPECS,
    ThresholdType,
    effective_threshold,
)

_PESO_TYPES = [
    ThresholdType.TOP_UP,
    ThresholdType.MIN_BALANCE,
    ThresholdType.OPENING_AMOUNT,
]


@st.composite
def _peso_selection(draw):
    t = draw(st.sampled_from(_PESO_TYPES))
    spec = THRESHOLD_SPECS[t]
    n_steps = (spec.maximum - spec.minimum) // spec.step
    return t, spec.minimum + draw(st.integers(0, n_steps)) * spec.step


@settings(max_examples=100, deadline=None)
@given(
    pct=pct_grid,
    series=st.one_of(adb_series(), all_missing_adb_series()),
    peso=_peso_selection(),
)
def test_balance_increase_threshold_is_median_of_amounts(pct, series, peso):
    """**Property 4: Balance Increase threshold equals the median of per-client amounts**

    **Validates: Requirements 5.4, 5.5, 5.6, 5.10, 5.11**
    """
    res = effective_threshold(ThresholdType.BALANCE_INCREASE, pct, series)
    usable_mask = series.notna()

    if not usable_mask.any():
        # 5.11: error, no threshold, nothing to analyse.
        assert res.error
        assert res.threshold_php is None
    else:
        assert res.error is None
        amounts = res.per_client
        # 5.5: amounts equal pct / 100 * latest_adb for usable clients.
        expected = pct / 100.0 * series[usable_mask]
        assert np.allclose(amounts[usable_mask].to_numpy(), expected.to_numpy())
        # 5.6: missing ADB yields no amount, so the capacity check fails.
        assert amounts[~usable_mask].isna().all()
        # 5.4/5.10: threshold is the median over usable amounts.
        assert math.isclose(
            res.threshold_php, float(np.median(expected.to_numpy())), rel_tol=1e-9, abs_tol=1e-9
        )
        assert res.note is not None and len(res.note) <= 200

    # Peso types return the selected value unchanged.
    t, value = peso
    peso_res = effective_threshold(t, value, None)
    assert peso_res.threshold_php == float(value)
    assert peso_res.error is None
