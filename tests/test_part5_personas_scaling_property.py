"""Property-based test for numeric-feature scaling.

# Feature: persona-segmentation, Property 5: Scaling yields zero mean and unit variance

Covers Property 5 of the persona-segmentation spec: for any set of numeric
clustering attributes with at least one non-missing value and non-zero variance,
:func:`part5_personas.preprocess.scale_numeric` standardizes each numeric feature
to ~0 mean and ~1 population variance across the clustered leads (Requirement
2.4).

``scale_numeric`` centers each numeric column on its mean and divides by its
population standard deviation (``ddof=0``), so a non-constant column has mean ~0
and population variance ~1. A constant (zero-variance) column is mapped to all
zeros rather than NaN/inf; that behavior is covered by an explicit, non-property
sanity check below while the core property targets non-constant columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from part5_personas.preprocess import scale_numeric

# Non-constant columns are required for the property. Bounding the magnitude to
# a moderate range keeps the standardization arithmetic well-conditioned so the
# tolerance below is not dominated by float round-off on extreme values.
_VALUE = st.floats(
    min_value=-1e3,
    max_value=1e3,
    allow_nan=False,
    allow_infinity=False,
)

# At least two rows so a column can carry two distinct values (non-zero
# variance); capped so each example stays cheap.
_MIN_ROWS = 2
_MAX_ROWS = 200

# Tolerance for the mean/variance assertions. 1e-6 comfortably absorbs the
# float round-off of centering and dividing a bounded (-1e3..1e3) column.
_TOL = 1e-6


@st.composite
def _numeric_frame(draw) -> tuple[pd.DataFrame, list[str]]:
    """Draw a DataFrame of 1..4 numeric columns, each with non-zero variance.

    Each column is a list of finite bounded floats; ``assume`` discards any draw
    whose column is (near-)constant so the generated matrix always exercises the
    non-constant branch the property targets. Returns ``(frame, numeric_cols)``.
    """
    n_rows = draw(st.integers(min_value=_MIN_ROWS, max_value=_MAX_ROWS))
    n_cols = draw(st.integers(min_value=1, max_value=4))

    columns = [f"num{i}" for i in range(n_cols)]
    data: dict[str, list[float]] = {}
    for col in columns:
        values = draw(
            st.lists(_VALUE, min_size=n_rows, max_size=n_rows)
        )
        # Non-zero population variance: at least two distinct values, and the
        # spread is comfortably above the round-off floor so division by std is
        # well-conditioned.
        assume(np.std(np.asarray(values, dtype=float), ddof=0) > 1e-3)
        data[col] = values

    return pd.DataFrame(data, columns=columns), columns


@settings(max_examples=100)
@given(frame_cols=_numeric_frame())
def test_scaling_yields_zero_mean_and_unit_variance(frame_cols):
    """Scaling yields zero mean and unit variance.

    **Validates: Requirements 2.4**

    For every generated non-constant numeric column, the scaled column has mean
    within ``_TOL`` of 0 and population variance within ``_TOL`` of 1, and the
    scaled output contains no NaN or infinity.
    """
    frame, numeric_cols = frame_cols

    scaled = scale_numeric(frame, numeric_cols)

    for col in numeric_cols:
        values = scaled[col].to_numpy(dtype=float)

        # No NaN / inf leaked into the scaled output.
        assert np.all(np.isfinite(values)), col

        mean = float(values.mean())
        variance = float(np.var(values, ddof=0))

        assert abs(mean) <= _TOL, (col, mean)
        assert abs(variance - 1.0) <= _TOL, (col, variance)


def test_constant_column_scales_to_all_zeros() -> None:
    """A zero-variance column is mapped to all zeros, never NaN/inf.

    Explicit sanity check (not the property) for the constant-column branch:
    ``scale_numeric`` centers a constant column at 0 instead of dividing by a
    zero standard deviation.
    """
    frame = pd.DataFrame({"c": [5.0, 5.0, 5.0, 5.0]})

    scaled = scale_numeric(frame, ["c"])
    values = scaled["c"].to_numpy(dtype=float)

    assert np.all(np.isfinite(values))
    assert np.all(values == 0.0)
