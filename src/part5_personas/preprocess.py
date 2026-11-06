"""Preprocessing for the Persona_Pipeline.

Turns the selected columns of the Joined_Attribute_Set into a numeric/categorical
clustering input ready for k-prototypes. Pure functions over pandas/numpy with no
Streamlit imports.

The stage performs four responsibilities, in a deterministic order:

- **Type classification** (:func:`classify_types`): each selected column is
  categorical when it is a binary flag (``owns_*``, a name in
  :data:`KNOWN_FLAG_COLUMNS`, boolean dtype, or an integer dtype with all
  non-missing values in {0, 1}; floats are never reclassified from their values;
  see :func:`is_binary_flag`, Requirements 1.3, 2.2), numeric
  for any other integer/float column, categorical otherwise (Requirement 2.2); a user ``type_overrides`` entry wins over auto-detection
  (Requirement 2.3).
- **Imputation** (:func:`impute`): every missing numeric value becomes the column
  mean of the non-missing values and every missing categorical value becomes the
  column mode (the most frequent non-missing value, ties broken by sort order),
  so the clustered input contains zero missing values (Requirement 2.5). If, after
  imputation, a selected column still has zero non-missing values (it was entirely
  missing), the run is rejected naming that column and no assignments are produced
  (Requirement 2.6).
- **Scaling** (:func:`scale_numeric`): each numeric feature is standardized to zero
  mean and unit variance across the clustered leads before clustering
  (Requirement 2.4). A constant column (zero variance) is left centered at 0 — all
  zeros — rather than dividing by zero.
- **Categorical indices** (:func:`categorical_indices`): the positional indices of
  the categorical columns within the ordered selection are returned so k-prototypes
  matches categorical columns by the categorical dissimilarity (Requirement 2.7).

Ordering note: imputation runs *before* scaling so the scaler never sees a NaN and
the "zero missing values" guarantee holds for the returned frame. The
:func:`preprocess` orchestrator wires these together and returns the preprocessed
frame (restricted to the selection, in order) together with the categorical
positional indices.
"""

from __future__ import annotations

import pandas as pd

# Canonical names for the two allowed ``type_overrides`` values (Requirement 2.3).
NUMERIC = "numeric"
CATEGORICAL = "categorical"

# Known binary flags, categorical regardless of dtype/values (Requirement 2.2).
KNOWN_FLAG_COLUMNS = ("digital_app_user", "frugal_flag", "email_valid", "mobile_valid")


def is_binary_flag(series: pd.Series, name: str) -> bool:
    """Whether a column is a binary flag, hence categorical (Requirements 1.3, 2.2).

    True when ``name`` starts with ``owns_``, ``name`` is in
    :data:`KNOWN_FLAG_COLUMNS` (both regardless of dtype/values, so a known flag
    stored as float because of missing values is still a flag), the dtype is
    boolean, or the dtype is INTEGER (kind ``i``/``u``) with at least one
    non-missing value and every non-missing value within ``{0, 1}``. Floating-point
    columns are never reclassified from their values, so a float share that happens
    to hold only 0.0/1.0 (e.g. ``inflow_share_business_receipts``) stays numeric;
    the documented limit is that an unnamed float 0/1 flag is not detected. A
    column with zero non-missing values is not a flag by value (it keeps the
    dtype-based answer so :func:`impute` still rejects it). Non-numeric dtypes are
    never flagged here (they are categorical anyway).
    """
    if name.startswith("owns_") or name in KNOWN_FLAG_COLUMNS:
        return True
    if series.dtype.kind == "b":
        return True
    if series.dtype.kind not in "iu":
        return False
    non_missing = series.dropna()
    if non_missing.empty:
        return False
    return bool(non_missing.isin([0, 1]).all())


def classify_types(
    frame: pd.DataFrame,
    selected: list[str],
    type_overrides: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Split the selected columns into numeric and categorical lists.

    A column is categorical when it is a binary flag (:func:`is_binary_flag`:
    ``owns_*`` or known flag name, boolean dtype, or an integer dtype with all
    non-missing values within ``{0, 1}``; float values never make a flag)
    or has a non-numeric dtype; every other integer/unsigned/float column is
    numeric (Requirement 2.2). A column with zero non-missing values keeps the
    dtype-based answer. A ``type_overrides`` entry for a column wins over the
    auto-detected type (Requirement 2.3); it maps an attribute name onto either
    ``"numeric"`` or ``"categorical"``.

    Order within ``selected`` is preserved in each returned list, so the two lists
    together partition ``selected`` in its original order.

    Args:
        frame: The Joined_Attribute_Set carrying (at least) the ``selected`` columns.
        selected: The ordered clustering columns to classify.
        type_overrides: Optional per-column type override; values must be
            ``"numeric"`` or ``"categorical"``.

    Returns:
        A ``(numeric_cols, categorical_cols)`` tuple preserving ``selected`` order.
    """
    overrides = type_overrides or {}
    numeric_cols: list[str] = []
    categorical_cols: list[str] = []

    for col in selected:
        override = overrides.get(col)
        if override == NUMERIC:
            numeric_cols.append(col)
        elif override == CATEGORICAL:
            categorical_cols.append(col)
        elif is_binary_flag(frame[col], col):
            categorical_cols.append(col)
        elif frame[col].dtype.kind in "iuf":
            numeric_cols.append(col)
        else:
            categorical_cols.append(col)

    return numeric_cols, categorical_cols


def impute(
    frame: pd.DataFrame,
    numeric_cols: list[str],
    categorical_cols: list[str],
) -> pd.DataFrame:
    """Fill missing values so the result has zero missing values.

    Every missing numeric value is replaced by the mean of that column's
    non-missing values, and every missing categorical value by the column mode —
    the most frequent non-missing value, with ties broken deterministically by
    ascending sort order (Requirement 2.5).

    If, after this, a selected column still has zero non-missing values (it was
    entirely missing, so its mean/mode is undefined), the run is rejected naming
    that column so no cluster assignments are produced (Requirement 2.6).

    Args:
        frame: The frame carrying the ``numeric_cols`` and ``categorical_cols``.
        numeric_cols: Columns to impute with the column mean.
        categorical_cols: Columns to impute with the column mode.

    Returns:
        A copy of ``frame`` with the listed columns imputed to zero missing values.

    Raises:
        ValueError: If a listed column has zero non-missing values.
    """
    out = frame.copy()

    for col in numeric_cols:
        non_missing = out[col].dropna()
        if non_missing.empty:
            raise ValueError(
                f"column {col!r} has zero non-missing values after imputation"
            )
        out[col] = out[col].fillna(non_missing.mean())

    for col in categorical_cols:
        non_missing = out[col].dropna()
        if non_missing.empty:
            raise ValueError(
                f"column {col!r} has zero non-missing values after imputation"
            )
        # value_counts orders by descending count; sort the index first so ties
        # resolve to the smallest value by sort order for a reproducible mode.
        counts = non_missing.value_counts()
        mode = counts.sort_index().sort_values(ascending=False, kind="stable").index[0]
        out[col] = out[col].fillna(mode)

    return out


def scale_numeric(frame: pd.DataFrame, numeric_cols: list[str]) -> pd.DataFrame:
    """Standardize each numeric column to zero mean and unit variance.

    Each numeric feature is centered on its mean and divided by its population
    standard deviation across the clustered leads (``ddof=0``), so the scaled
    column has ~0 mean and ~1 population variance (Requirement 2.4), matching the
    "Property 5: scaling yields ~0 mean / unit variance" correctness property.

    A constant column has zero variance; dividing by its standard deviation would
    produce NaN/inf, so it is instead left centered at 0 (all zeros). Imputation is
    expected to have run first, so no NaN reaches this function.

    Args:
        frame: The (already imputed) frame carrying the numeric columns.
        numeric_cols: Columns to standardize in place on a copy.

    Returns:
        A copy of ``frame`` with the numeric columns standardized.
    """
    out = frame.copy()

    for col in numeric_cols:
        values = out[col].astype(float)
        mean = values.mean()
        std = values.std(ddof=0)
        if std == 0:
            # Constant column: center at 0 without dividing by zero.
            out[col] = 0.0
        else:
            out[col] = (values - mean) / std

    return out


def categorical_indices(
    selected_order: list[str],
    categorical_cols: list[str],
) -> list[int]:
    """Positional indices of the categorical columns within the selection.

    Returns the 0-based positions of ``categorical_cols`` inside
    ``selected_order``, the ordered list of clustering columns, so k-prototypes
    can match those columns by the categorical dissimilarity (Requirement 2.7).
    The indices follow ``selected_order`` (ascending), independent of the order of
    ``categorical_cols``.

    Args:
        selected_order: The ordered clustering columns as they appear in the frame.
        categorical_cols: The columns classified categorical.

    Returns:
        The ascending list of categorical column positions.
    """
    categorical_set = set(categorical_cols)
    return [i for i, col in enumerate(selected_order) if col in categorical_set]


def preprocess(
    frame: pd.DataFrame,
    selected: list[str],
    type_overrides: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[int]]:
    """Classify, impute, and scale the selected columns for k-prototypes.

    Orchestrates the preprocessing stage (Requirements 2.2-2.7):

    1. Classify each selected column as numeric or categorical, honoring
       ``type_overrides`` (Requirements 2.2, 2.3).
    2. Impute missing values *before* scaling so the scaler sees no NaN and the
       returned frame has zero missing values (Requirements 2.5, 2.6).
    3. Standardize the numeric columns to zero mean / unit variance, safe for
       constant columns (Requirement 2.4).
    4. Compute the categorical positional indices (Requirement 2.7).

    Args:
        frame: The Joined_Attribute_Set carrying the ``selected`` columns.
        selected: The ordered clustering columns to preprocess.
        type_overrides: Optional per-column type override (``"numeric"`` /
            ``"categorical"``).

    Returns:
        A ``(preprocessed, cat_indices)`` tuple: the preprocessed frame restricted
        to ``selected`` in order with zero missing values, and the ascending
        positional indices of its categorical columns.

    Raises:
        ValueError: If a selected column is entirely missing (Requirement 2.6).
    """
    numeric_cols, categorical_cols = classify_types(frame, selected, type_overrides)

    # Restrict to the selection in order, then impute before scaling.
    restricted = frame[selected].copy()
    imputed = impute(restricted, numeric_cols, categorical_cols)
    scaled = scale_numeric(imputed, numeric_cols)

    cat_indices = categorical_indices(selected, categorical_cols)
    return scaled, cat_indices
