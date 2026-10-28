"""Property-based test for the SHAP matrix shape.

# Feature: part1-optin, Property 16: SHAP matrix has one contribution per predictor per scored row

Covers Property 16 of the part1-optin spec: :meth:`part1_optin.explain.Explainer.shap_values`
builds a ``shap.TreeExplainer`` on the Calibrated_Model's single full-data
booster and returns one contribution per predictor per scored row, so the
returned array is exactly ``(n_rows, n_predictors)`` -- matching the number of
rows scored and the number of columns in the feature matrix (Requirement 5.1).

This property is about the SHAP matrix *shape*, not feature assembly, so the
test feeds the trainer a small numeric feature matrix ``X`` built directly (no
Feature_Assembler) paired with a trivially constructed
:class:`part1_optin.features.FeatureSchema` whose ``columns`` match
``X.columns``. The two-class label vector ``y`` is constructed with at least
three examples per class so the internal ``cv=3`` calibration folds each see
both classes.

The test scores two different matrices (the training matrix and a second,
smaller matrix with the same columns) and asserts each SHAP result's shape
tracks the rows actually scored while the predictor count stays fixed at the
number of columns.

No path in this test references a ``*_answer_key*`` file; nothing is read from
disk at all.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import Config
from part1_optin.explain import Explainer
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer

# Minimum per-class examples so each of the cv=3 calibration folds can contain
# both classes (design: "callers provide at least three minority-class
# examples").
_MIN_PER_CLASS = 3

# A modest fixed number of feature columns. The shape property does not depend
# on the feature content, only on the counts of rows and columns, so a small
# numeric matrix is enough and keeps model fitting fast.
_N_FEATURES = 4


@st.composite
def matrices_and_labels(draw):
    """Draw a training ``X``/``y`` and a second same-column scoring matrix.

    Rows are kept modest because each generated example fits XGBoost models,
    which is slow. ``y`` is built by drawing a positive count and a negative
    count, each at least :data:`_MIN_PER_CLASS`, so both classes are guaranteed
    present with enough minority-class examples for the internal ``cv=3``
    stratified calibration folds. ``X`` is a dense numeric matrix whose columns
    are named ``f0..f{n-1}``.

    A second matrix ``X2`` is drawn with an independent row count (and the same
    columns) so the test can confirm the SHAP result's row dimension tracks the
    rows actually scored rather than the training row count.
    """
    n_pos = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=17 - _MIN_PER_CLASS))
    n_neg = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=20 - n_pos))
    n_rows = n_pos + n_neg

    y_values = [1] * n_pos + [0] * n_neg

    cell = st.floats(
        min_value=-1000.0,
        max_value=1000.0,
        allow_nan=False,
        allow_infinity=False,
    )
    rows = draw(
        st.lists(
            st.lists(cell, min_size=_N_FEATURES, max_size=_N_FEATURES),
            min_size=n_rows,
            max_size=n_rows,
        )
    )

    # A second matrix with the same columns but an independently chosen number
    # of rows, so the scored-row count differs from the training-row count.
    n_rows2 = draw(st.integers(min_value=1, max_value=8))
    rows2 = draw(
        st.lists(
            st.lists(cell, min_size=_N_FEATURES, max_size=_N_FEATURES),
            min_size=n_rows2,
            max_size=n_rows2,
        )
    )

    columns = [f"f{i}" for i in range(_N_FEATURES)]
    X = pd.DataFrame(rows, columns=columns, dtype=float)
    y = pd.Series(y_values, name="Join_Label")
    X2 = pd.DataFrame(rows2, columns=columns, dtype=float)
    return X, y, X2


# max_examples is kept modest because EACH example fits the calibrated model
# (three internal cv folds) plus a full-data booster, then builds a SHAP
# TreeExplainer -- model fitting is slow, so a large example budget would make
# the suite impractically long. deadline=None because a single fit easily
# exceeds Hypothesis's default per-example deadline.
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(matrices_and_labels())
def test_shap_matrix_has_one_contribution_per_predictor_per_row(data):
    """SHAP matrix has one contribution per predictor per scored row.

    **Validates: Requirements 5.1**

    After fitting :class:`part1_optin.model.Model_Trainer`, building an
    :class:`part1_optin.explain.Explainer`, and calling ``shap_values`` on a
    matrix, the returned array must be exactly ``(n_rows, n_predictors)`` where
    ``n_rows`` is the number of rows scored and ``n_predictors`` is the number
    of feature columns. Scoring a second, same-column matrix must yield a shape
    that tracks *its* row count, confirming the row dimension follows the rows
    scored rather than any fixed training size.
    """
    X, y, X2 = data

    schema = FeatureSchema(columns=list(X.columns))
    config = Config()

    model = Model_Trainer(config).fit(X, y, schema)
    explainer = Explainer(model)

    # One contribution per predictor per scored row for the training matrix
    # (Requirement 5.1).
    values = explainer.shap_values(X)
    assert values.shape == (len(X), len(X.columns))

    # The same contract on a second matrix with the same columns but a different
    # row count: the row dimension tracks the rows scored, the predictor count
    # stays the column count.
    values2 = explainer.shap_values(X2)
    assert values2.shape == (len(X2), len(X2.columns))
