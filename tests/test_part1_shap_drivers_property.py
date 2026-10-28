"""Property-based test for top-3 SHAP driver selection, tie-break, and padding.

# Feature: part1-optin, Property 17: Top-3 SHAP drivers are the largest-by-absolute, name-tie-broken, empty-padded

Covers Property 17 of the part1-optin spec: for every scored lead,
:meth:`part1_optin.explain.Explainer.top_drivers` returns the three predictors
with the largest absolute SHAP contribution ordered largest-to-smallest, breaks
ties on ``|SHAP|`` by ascending predictor name, and fills any position beyond the
count of non-zero-contribution predictors with the empty string ``""``
(Requirements 5.2, 5.3, 5.4, 7.5).

Why this is deterministic without a mocked model: the property is about the
``top_drivers`` *selection logic*, not about any particular SHAP numbers. We fit
a small real model to obtain a genuine :class:`~part1_optin.explain.Explainer`,
then read the SAME SHAP matrix the explainer uses via ``explainer.shap_values(X)``
and derive the expected top-3 independently from it. Comparing
``top_drivers(X)`` against that independent recompute of the identical matrix
isolates the selection/tie-break/padding rule from any run-to-run variation in
the SHAP values themselves.

This test fits a real model per example, so it keeps ``max_examples`` modest and
sets ``deadline=None``: each Hypothesis example fits a ``CalibratedClassifierCV``
(three internal XGBoost folds) plus a full-data booster, which is far slower than
a pure-function property, and a per-example deadline would flake on that cost.

A simple :class:`part1_optin.features.FeatureSchema` whose ``columns`` match the
generated matrix is built directly -- the full Feature_Assembler is not needed to
exercise the driver-selection guarantee. No path in this test references a
``*_answer_key*`` file; the matrices are generated in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import Config
from part1_optin.explain import Explainer
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer

# Predictor names chosen so the ascending-name tie-break is observable: they are
# NOT in sorted order as listed, so any correct tie-break must reorder by name
# rather than by column position. A small set keeps each fit cheap.
_FEATURE_COLUMNS = ["zeta", "alpha", "mu", "beta"]

# Minimum examples per class. CalibratedClassifierCV uses a 3-fold
# StratifiedKFold internally, so each class needs at least three examples for
# every inner fold to see both classes.
_MIN_PER_CLASS = 3

# How many driver positions top_drivers must return per row (Requirement 5.2).
_K = 3


def _expected_top_drivers(
    shap_row: np.ndarray, predictors: list[str], k: int
) -> tuple[str, ...]:
    """Independently derive the expected ``k`` drivers for one SHAP row.

    Mirrors the specified rule exactly (Requirements 5.2, 5.3, 5.4): rank
    predictors by descending ``|SHAP|`` with ties broken by ascending predictor
    name, take the top ``k`` names, and pad any position beyond the count of
    predictors with a strictly non-zero ``|SHAP|`` with ``""``.

    This is a straightforward reference recompute against the SAME SHAP values
    the explainer uses, so comparing it to ``top_drivers`` tests the selection
    logic and not the SHAP numbers themselves.
    """
    abs_row = np.abs(shap_row)
    # Descending magnitude, ascending name on ties: negate magnitude so larger
    # sorts first, keep name ascending within equal magnitude.
    order = sorted(
        range(len(predictors)),
        key=lambda i: (-abs_row[i], predictors[i]),
    )
    selected: list[str] = []
    for position in range(k):
        if position < len(order) and abs_row[order[position]] > 0:
            selected.append(predictors[order[position]])
        else:
            # Fewer than k non-zero-contribution predictors -> pad with "".
            selected.append("")
    return tuple(selected)


@st.composite
def _feature_matrix(draw, n_rows: int) -> pd.DataFrame:
    """Draw an ``n_rows`` x len(_FEATURE_COLUMNS) float feature matrix.

    Values are finite floats in a bounded range so XGBoost fits without NaNs or
    infinities derailing the trees; the columns are exactly ``_FEATURE_COLUMNS``
    so the fitted schema applies to both the fit matrix and the scored matrix.
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
    """Draw a fit matrix, two-class labels, and a separate matrix to score.

    Builds a label vector with at least :data:`_MIN_PER_CLASS` zeros and
    :data:`_MIN_PER_CLASS` ones (so the internal ``cv=3`` calibration folds each
    see both classes) and a matching feature matrix with one row per label. A
    second, independently drawn matrix shares the same columns so the fitted
    schema applies to it unchanged. Returns ``(X, y, X_score)``.
    """
    n_zero = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 3))
    n_one = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 3))
    labels = [0] * n_zero + [1] * n_one
    y = pd.Series(labels, name="Join_Label")
    x = draw(_feature_matrix(len(labels)))

    score_rows = draw(st.integers(min_value=1, max_value=6))
    x_score = draw(_feature_matrix(score_rows))
    return x, y, x_score


@settings(
    max_examples=10,
    deadline=None,  # each example fits a real calibrated model + booster; a
    # per-example deadline would flake on that cost, not on correctness.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_labeled_training_data())
def test_top_drivers_match_independent_selection(data):
    """Top-3 SHAP drivers are the largest-by-absolute, name-tie-broken, empty-padded.

    **Validates: Requirements 5.2, 5.3, 5.4, 7.5**

    Fit a real model to obtain a genuine ``Explainer``, read the SHAP matrix it
    uses via ``shap_values(X)``, and derive the expected top-3 drivers per row
    independently from that matrix. Assert ``top_drivers(X, k=3)`` equals the
    independent reference for every row, which pins the largest-by-absolute
    ordering (5.2), the ascending-name tie-break (5.3), and the empty-string
    padding for rows with fewer than three non-zero contributions (5.4, 7.5).
    """
    x, y, x_score = data

    # A minimal schema whose columns match the generated matrix. The full
    # Feature_Assembler is not needed to exercise driver selection; the trainer
    # only reads X / y and bundles the schema through.
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    model = Model_Trainer(Config()).fit(x, y, schema)
    explainer = Explainer(model)

    predictors = list(x_score.columns)

    # Read the SAME SHAP matrix the explainer uses, then derive expected drivers
    # independently from it so the comparison tests selection, not SHAP numbers.
    shap_matrix = explainer.shap_values(x_score)
    expected = [
        _expected_top_drivers(shap_matrix[row], predictors, _K)
        for row in range(len(x_score))
    ]

    actual = explainer.top_drivers(x_score, k=_K)

    # One k-tuple per scored row, matching the independent reference exactly.
    assert len(actual) == len(x_score)
    assert actual == expected

    # Structural guarantees of the contract, asserted directly for clarity:
    for drivers in actual:
        # Exactly k positions per row (Requirement 5.2).
        assert len(drivers) == _K
        # Every non-empty driver names a real predictor; empties are "".
        for name in drivers:
            assert name == "" or name in predictors
        # Padding is trailing only: no non-empty driver follows an empty one
        # (Requirement 5.4 fills *remaining* positions).
        seen_empty = False
        for name in drivers:
            if name == "":
                seen_empty = True
            elif seen_empty:
                raise AssertionError(
                    f"non-empty driver {name!r} follows an empty position in {drivers!r}"
                )
