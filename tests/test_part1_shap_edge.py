"""Edge unit test for fewer-than-three non-zero SHAP contributions.

A targeted (non-Hypothesis) test for
:meth:`part1_optin.explain.Explainer.top_drivers` covering Requirement 5.4:
when a scored lead has fewer than three predictors with a non-zero SHAP
contribution, the trailing driver positions are filled with the empty string
``""``.

The scenario is built so the fitted booster assigns exactly zero SHAP to some
predictors: constant columns never appear in any tree split, so a
``TreeExplainer`` attributes them exactly ``0`` for every row. The matrix here
carries a single informative column (``f0``, which determines the label) and
two constant columns (``f1``, ``f2``), so every row ends up with at most one
non-zero-|SHAP| predictor and the two trailing driver slots must be padded with
``""``.

Beyond that concrete padding assertion, the test also checks the general
invariant across every row: the number of non-empty drivers returned equals
``min(3, count of non-zero-|SHAP| predictors)`` and the empties only ever
appear trailing. That makes the test robust even if a particular booster fit
happens to distribute zeros differently than expected.

All data is in memory and no path references a ``*_answer_key*`` file
(Requirement 2.14).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from part1_optin.config import Config
from part1_optin.explain import Explainer
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer

# One informative predictor plus two constant predictors. The constant columns
# never enter a tree split, so TreeExplainer gives them exactly 0 SHAP.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Rows per class. CalibratedClassifierCV uses an internal 3-fold
# StratifiedKFold during the trainer's fit, so each class needs at least three
# examples; six gives a comfortable margin.
_PER_CLASS = 6


def _schema() -> FeatureSchema:
    """Return a minimal schema whose columns match the generated matrix.

    The trainer reads only ``X`` / ``y`` and bundles the schema through
    unchanged; the Explainer takes predictor names from ``X.columns``, so the
    schema content beyond ``columns`` does not affect this test.
    """
    return FeatureSchema(
        columns=list(_FEATURE_COLUMNS),
        categorical_maps={},
        product_type_columns=[],
        part2_columns=[],
    )


def _one_driver_frame() -> tuple[pd.DataFrame, pd.Series]:
    """Return ``(X, y)`` where only ``f0`` drives the label; ``f1``/``f2`` constant.

    ``f0`` is low for the negative class and high for the positive class so the
    booster splits on it; ``f1`` and ``f2`` are constant across all rows so they
    never appear in a split and earn exactly 0 SHAP from the TreeExplainer.
    """
    f0 = np.array([0.0] * _PER_CLASS + [1.0] * _PER_CLASS)
    frame = pd.DataFrame(
        {
            "f0": f0,
            "f1": np.full(2 * _PER_CLASS, 5.0),  # constant -> 0 SHAP
            "f2": np.full(2 * _PER_CLASS, 7.0),  # constant -> 0 SHAP
        },
        columns=_FEATURE_COLUMNS,
    )
    y = pd.Series([0] * _PER_CLASS + [1] * _PER_CLASS, name="Join_Label")
    return frame, y


def test_fewer_than_three_nonzero_shap_pads_trailing_with_empty():
    """<3 non-zero SHAP contributions pad trailing drivers with "" (Req 5.4).

    Only ``f0`` carries signal; ``f1`` and ``f2`` are constant and so get
    exactly 0 SHAP. Each row therefore has at most one non-zero-|SHAP|
    predictor, so ``top_drivers`` must return that predictor (when non-zero)
    followed by ``""`` padding in the two trailing slots, and never place an
    empty string before a non-empty driver.

    _Requirements: 5.4_
    """
    x, y = _one_driver_frame()

    model = Model_Trainer(Config()).fit(x, y, _schema())
    explainer = Explainer(model)

    values = explainer.shap_values(x)
    abs_values = np.abs(values)
    drivers = explainer.top_drivers(x, k=3)

    # One driver tuple per scored row, each of width 3.
    assert len(drivers) == len(x)
    assert all(len(row) == 3 for row in drivers)

    predictors = list(x.columns)

    for row_index, row_drivers in enumerate(drivers):
        nonzero_count = int(np.count_nonzero(abs_values[row_index] > 0))

        expected_nonempty = min(3, nonzero_count)
        nonempty = [name for name in row_drivers if name != ""]

        # The number of real drivers equals min(3, non-zero-|SHAP| predictors).
        assert len(nonempty) == expected_nonempty

        # Empties only ever appear trailing: once a "" appears, everything after
        # it is also "".
        empties_start = [i for i, name in enumerate(row_drivers) if name == ""]
        if empties_start:
            first_empty = empties_start[0]
            assert all(name == "" for name in row_drivers[first_empty:])
            assert all(name != "" for name in row_drivers[:first_empty])

        # Every non-empty driver names a real predictor with a non-zero
        # contribution for this row.
        for name in nonempty:
            assert name in predictors
            assert abs_values[row_index][predictors.index(name)] > 0

    # The constant columns earned exactly 0 SHAP, so they never appear as a
    # driver and the two trailing slots are always the empty string here.
    assert np.all(abs_values[:, predictors.index("f1")] == 0)
    assert np.all(abs_values[:, predictors.index("f2")] == 0)
    for row_drivers in drivers:
        assert row_drivers[1] == ""
        assert row_drivers[2] == ""
        assert "f1" not in row_drivers
        assert "f2" not in row_drivers
