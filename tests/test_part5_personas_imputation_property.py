"""Property-based tests for Persona_Pipeline missing-value imputation.

Covers Property 6 (imputation leaves zero missing values) of the
persona-segmentation spec, exercising
``part5_personas.preprocess.impute`` and the ``preprocess`` orchestrator
against Requirement 2.5.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part5_personas.preprocess import classify_types, impute, preprocess


# A small alphabet of categorical labels. Kept short so ties and repeated
# values (which exercise the deterministic mode path) actually arise.
_CATEGORIES = ["a", "b", "c", "d"]

# Finite numeric values: no NaN/inf from the float strategy itself -- missing
# numeric cells are injected explicitly below so the generator stays in control
# of the "at least one non-missing per column" precondition.
_NUMERIC_VALUE = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
)


def _inject_missing(draw, values: list, sentinel) -> list:
    """Return a copy of ``values`` with a random subset set to ``sentinel``.

    Never masks every position: at least one original (non-missing) value is
    always retained so the column satisfies the property's precondition that
    every selected column has at least one non-missing value.
    """
    n = len(values)
    # A mask of booleans, one per row; True means "make this cell missing".
    mask = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    # Guarantee at least one surviving (non-missing) cell.
    if all(mask):
        keep = draw(st.integers(min_value=0, max_value=n - 1))
        mask[keep] = False
    return [sentinel if m else v for v, m in zip(values, mask)]


@st.composite
def _frame_with_missing(draw) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Generate a frame with >=1 numeric and >=1 categorical column.

    Every column carries some missing values but at least one non-missing value,
    honoring the Property 6 precondition. Returns the frame together with the
    numeric and categorical column name lists.
    """
    n_rows = draw(st.integers(min_value=2, max_value=100))
    n_numeric = draw(st.integers(min_value=1, max_value=3))
    n_categorical = draw(st.integers(min_value=1, max_value=3))

    data: dict[str, list] = {}
    numeric_cols: list[str] = []
    categorical_cols: list[str] = []

    for i in range(n_numeric):
        col = f"num_{i}"
        numeric_cols.append(col)
        values = draw(
            st.lists(_NUMERIC_VALUE, min_size=n_rows, max_size=n_rows)
        )
        data[col] = _inject_missing(draw, values, np.nan)

    for i in range(n_categorical):
        col = f"cat_{i}"
        categorical_cols.append(col)
        values = draw(
            st.lists(
                st.sampled_from(_CATEGORIES), min_size=n_rows, max_size=n_rows
            )
        )
        data[col] = _inject_missing(draw, values, None)

    # Build with object dtype preserved for categoricals; numeric columns carry
    # np.nan so pandas infers float.
    frame = pd.DataFrame(data)
    return frame, numeric_cols, categorical_cols


def _expected_mode(series: pd.Series):
    """The deterministic mode: most frequent non-missing value, ties -> smallest
    by ascending sort order (mirrors ``preprocess.impute``)."""
    non_missing = series.dropna()
    counts = non_missing.value_counts()
    return counts.sort_index().sort_values(ascending=False, kind="stable").index[0]


# Feature: persona-segmentation, Property 6: Imputation leaves zero missing values
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(_frame_with_missing())
def test_impute_leaves_zero_missing_values(
    generated: tuple[pd.DataFrame, list[str], list[str]],
) -> None:
    frame, numeric_cols, categorical_cols = generated

    # Precondition sanity: every column has at least one non-missing value.
    for col in numeric_cols + categorical_cols:
        assert frame[col].notna().any()

    # Record the original non-missing fill values and which cells were missing.
    numeric_means = {c: frame[c].dropna().mean() for c in numeric_cols}
    categorical_modes = {c: _expected_mode(frame[c]) for c in categorical_cols}
    missing_mask = {c: frame[c].isna() for c in numeric_cols + categorical_cols}

    result = impute(frame, numeric_cols, categorical_cols)

    # Core invariant: zero missing values anywhere in the imputed frame.
    assert result.isna().sum().sum() == 0

    # Numeric columns: previously-missing cells equal the original-column mean,
    # and originally-non-missing cells are unchanged (vectorized; empty masks
    # make np.allclose return True).
    for col in numeric_cols:
        expected_mean = numeric_means[col]
        mask = missing_mask[col]
        assert np.allclose(
            result.loc[mask, col].to_numpy(), expected_mean
        )
        assert np.allclose(
            result.loc[~mask, col].to_numpy(),
            frame.loc[~mask, col].to_numpy(),
        )

    # Categorical columns: previously-missing cells equal the deterministic
    # mode, and originally-non-missing cells are unchanged (vectorized).
    for col in categorical_cols:
        expected_mode = categorical_modes[col]
        mask = missing_mask[col]
        assert (result.loc[mask, col] == expected_mode).all()
        assert (
            result.loc[~mask, col].to_numpy()
            == frame.loc[~mask, col].to_numpy()
        ).all()


# Feature: persona-segmentation, Property 6: Imputation leaves zero missing values
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(_frame_with_missing())
def test_preprocess_path_leaves_zero_missing_values(
    generated: tuple[pd.DataFrame, list[str], list[str]],
) -> None:
    frame, numeric_cols, categorical_cols = generated
    selected = numeric_cols + categorical_cols

    # classify_types sees np.nan float columns as numeric and object columns as
    # categorical, matching how we built the frame; confirm the orchestrator
    # end-to-end yields zero missing values.
    detected_numeric, detected_categorical = classify_types(frame, selected)
    assert set(detected_numeric) == set(numeric_cols)
    assert set(detected_categorical) == set(categorical_cols)

    preprocessed, _cat_indices = preprocess(frame, selected)

    assert preprocessed.isna().sum().sum() == 0
    # The preprocessed frame is restricted to the selection, in order.
    assert list(preprocessed.columns) == selected


def test_impute_rejects_entirely_missing_column() -> None:
    """Req 2.6 guard: an entirely-missing selected column is rejected by name.

    This is an explicit example (not the property) documenting the boundary the
    Property 6 precondition excludes.
    """
    frame = pd.DataFrame(
        {
            "num_0": [1.0, 2.0, 3.0],
            "num_all_missing": [np.nan, np.nan, np.nan],
            "cat_0": ["a", "b", "a"],
        }
    )
    with pytest.raises(ValueError, match="num_all_missing"):
        impute(frame, ["num_0", "num_all_missing"], ["cat_0"])
