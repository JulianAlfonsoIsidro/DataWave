"""Property-based test for calibrated-probability bounds.

# Feature: part1-optin, Property 12: Calibrated probabilities are bounded in [0, 1]

Covers Property 12 of the part1-optin spec: the calibrated predictor produced by
:meth:`part1_optin.model.Model_Trainer.fit` only ever emits positive-class
probabilities inside the inclusive range ``[0, 1]`` -- both on the data it was
fit on and on a separately generated held-out matrix carrying the same columns
(Requirements 3.5, 7.3).

The ``Calibrated_Model.predict_proba`` contract is an out-of-fold isotonic
``CalibratedClassifierCV`` whose positive-class column is clipped to ``[0, 1]``,
so every element of its output must satisfy ``0.0 <= p <= 1.0`` regardless of
the inputs it scores.

This test fits a real model per example, so it keeps ``max_examples`` modest and
sets ``deadline=None``: each Hypothesis example fits a ``CalibratedClassifierCV``
(three internal XGBoost folds) plus a full-data booster, which is far slower than
a pure-function property, and a per-example deadline would flake on that cost.

A simple :class:`part1_optin.features.FeatureSchema` whose ``columns`` match the
generated matrix is built directly -- the full Feature_Assembler is not needed to
exercise the trainer's probability-bound guarantee. No path in this test
references a ``*_answer_key*`` file; the matrices are generated in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import Config
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer

# Feature column names for the generated matrices. A small fixed set keeps each
# fit cheap while still exercising a multi-feature calibrated model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Minimum examples per class. CalibratedClassifierCV uses a 3-fold
# StratifiedKFold internally, so each class needs at least three examples for
# every inner fold to see both classes.
_MIN_PER_CLASS = 3


@st.composite
def _feature_matrix(draw, n_rows: int) -> pd.DataFrame:
    """Draw an ``n_rows`` x len(_FEATURE_COLUMNS) float feature matrix.

    Values are finite floats in a bounded range so XGBoost fits without NaNs or
    infinities derailing the trees; the columns are exactly ``_FEATURE_COLUMNS``
    so the same schema applies to both the fit and the held-out matrix.
    """
    rows = draw(
        st.lists(
            st.lists(
                st.floats(
                    min_value=-100.0,
                    max_value=100.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                min_size=len(_FEATURE_COLUMNS),
                max_size=len(_FEATURE_COLUMNS),
            ),
            min_size=n_rows,
            max_size=n_rows,
        )
    )
    return pd.DataFrame(rows, columns=_FEATURE_COLUMNS)


@st.composite
def _labeled_training_data(draw):
    """Draw a fit matrix, labels, and a separate held-out matrix.

    Builds a label vector with at least :data:`_MIN_PER_CLASS` zeros and
    :data:`_MIN_PER_CLASS` ones (so the internal ``cv=3`` calibration folds each
    see both classes) and a matching feature matrix with one row per label. A
    second, independently drawn held-out matrix shares the same columns so the
    fitted schema applies to it unchanged. Returns ``(X, y, X_heldout)``.
    """
    n_zero = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 3))
    n_one = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 3))
    labels = [0] * n_zero + [1] * n_one
    y = pd.Series(labels, name="Join_Label")
    x = draw(_feature_matrix(len(labels)))

    heldout_rows = draw(st.integers(min_value=1, max_value=6))
    x_heldout = draw(_feature_matrix(heldout_rows))
    return x, y, x_heldout


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_labeled_training_data())
def test_calibrated_probabilities_are_bounded(data):
    """Calibrated probabilities are bounded in [0, 1].

    **Validates: Requirements 3.5, 7.3**

    Fit a ``Model_Trainer`` on a small two-class matrix and assert every
    ``predict_proba`` value on the training matrix lies in the inclusive range
    ``[0, 1]``. Then score a separately generated held-out matrix with the same
    columns and assert those probabilities are in ``[0, 1]`` too.
    """
    x, y, x_heldout = data

    # A minimal schema whose columns match the generated matrix. The full
    # Feature_Assembler is not needed to exercise the probability-bound
    # guarantee; the trainer only reads X / y and bundles the schema through.
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    model = Model_Trainer(Config()).fit(x, y, schema)

    # --- Probabilities on the fit data are all within [0, 1]. ---
    train_proba = model.predict_proba(x)
    assert np.all(train_proba >= 0.0)
    assert np.all(train_proba <= 1.0)

    # --- Probabilities on a separate held-out matrix are also within [0, 1]. ---
    heldout_proba = model.predict_proba(x_heldout)
    assert np.all(heldout_proba >= 0.0)
    assert np.all(heldout_proba <= 1.0)
