"""Example/edge unit tests for the Part1_Optin trainer and model artifact.

Targeted (non-Hypothesis) tests for :class:`part1_optin.model.Model_Trainer`
and :class:`part1_optin.model.Calibrated_Model`, covering:

- Fitting on a small two-class matrix and predicting probabilities
  (Requirement 3.1).
- The single-class guard raising the both-classes ``ValueError`` and writing
  no artifact (Requirement 3.6).
- The saved ``model_part1.json`` reloading as a valid XGBoost booster that
  predicts, with the sidecar carrying the calibration representation + schema
  (Requirement 6.1).
- A missing ``outputs/`` directory being created on save (Requirement 6.7).

These are small, fixed-fixture example tests (the property-based coverage of
bounds/determinism lives in the ``*_property.py`` suites). Each class needs at
least three examples for the internal ``cv=3`` ``StratifiedKFold`` to see both
classes in every fold, so the fixtures build six rows per class. No path in
this module references a ``*_answer_key*`` file; all matrices are in memory and
all save targets are under pytest's ``tmp_path`` (Requirement 2.14).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import xgboost

from part1_optin.config import Config
from part1_optin.features import FeatureSchema
from part1_optin.model import Calibrated_Model, Model_Trainer

# Feature columns for the generated matrices; a small fixed set keeps each fit
# cheap while exercising a multi-feature model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Rows per class. CalibratedClassifierCV uses an internal 3-fold
# StratifiedKFold, so each class needs at least three examples; six gives a
# comfortable margin and a separable-ish signal.
_PER_CLASS = 6


def _two_class_frame() -> tuple[pd.DataFrame, pd.Series]:
    """Return a small, deterministic two-class ``(X, y)`` for fitting.

    Builds ``_PER_CLASS`` rows of each label. The two classes are given
    slightly offset feature values so the booster has a signal to learn, but
    the test only asserts shape/bounds, not accuracy.
    """
    rng = np.random.RandomState(0)
    zeros = rng.normal(loc=-1.0, scale=1.0, size=(_PER_CLASS, len(_FEATURE_COLUMNS)))
    ones = rng.normal(loc=1.0, scale=1.0, size=(_PER_CLASS, len(_FEATURE_COLUMNS)))
    x = pd.DataFrame(np.vstack([zeros, ones]), columns=_FEATURE_COLUMNS)
    y = pd.Series([0] * _PER_CLASS + [1] * _PER_CLASS, name="Join_Label")
    return x, y


def _schema() -> FeatureSchema:
    """Return a minimal schema whose columns match the generated matrix.

    The full Feature_Assembler is not needed here: the trainer reads only
    ``X`` / ``y`` and bundles the schema through unchanged, and ``save``
    serializes ``schema.to_dict()`` into the sidecar. A non-trivial
    categorical map is included so the round-trip through the sidecar is
    exercised on more than an empty schema.
    """
    return FeatureSchema(
        columns=list(_FEATURE_COLUMNS),
        categorical_maps={"mechanic": {"TOP_UP": 1, "NEW_ACCOUNT": 2}},
        product_type_columns=["active_count_savings"],
        part2_columns=["join_rate"],
    )


def test_fit_two_class_predicts_probabilities():
    """Fitting on a two-class set yields probabilities in [0, 1] (Req 3.1).

    _Requirements: 3.1_
    """
    x, y = _two_class_frame()

    model = Model_Trainer(Config()).fit(x, y, _schema())

    assert isinstance(model, Calibrated_Model)
    # A full-data booster was fit and bundled (Requirement 6.1 / 5.1 source).
    assert isinstance(model.booster, xgboost.Booster)

    proba = model.predict_proba(x)
    # One probability per scored row, all within the inclusive unit interval.
    assert proba.shape == (len(x),)
    assert np.all(proba >= 0.0)
    assert np.all(proba <= 1.0)


def test_single_class_fit_raises_and_writes_no_artifact(tmp_path):
    """Single-class data raises the both-classes error and writes nothing.

    The single-class guard must fire before any fit so no ``Calibrated_Model``
    (and therefore no artifact) is produced; the error message must mention
    both opt-in and non-opt-in examples.

    _Requirements: 3.6_
    """
    x, _ = _two_class_frame()
    # All-one labels: only a single unique class.
    y_single = pd.Series([1] * len(x), name="Join_Label")

    model_path = tmp_path / "model_part1.json"

    with pytest.raises(ValueError) as excinfo:
        Model_Trainer(Config()).fit(x, y_single, _schema())

    message = str(excinfo.value).lower()
    assert "opt-in" in message
    assert "non-opt-in" in message

    # The guard halts before fitting, so nothing can have been saved. Confirm
    # no booster artifact or sidecar exists on disk.
    assert not model_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_saved_artifact_reloads_as_booster_and_sidecar_has_schema(tmp_path):
    """Saved JSON reloads as a booster; sidecar carries calibration + schema.

    ``save`` writes the full-data booster to ``model_part1.json`` as a valid
    JSON XGBoost booster document, a ``.calibrated.pkl`` calibration
    representation, and a ``.sidecar.json`` naming that pickle and carrying the
    schema. Reloading the booster with a fresh ``xgboost.Booster`` and
    predicting on a ``DMatrix`` confirms the artifact is a usable booster, and
    the sidecar schema reconstructs via ``FeatureSchema.from_dict``.

    _Requirements: 6.1_
    """
    x, y = _two_class_frame()
    schema = _schema()
    model = Model_Trainer(Config()).fit(x, y, schema)

    model_path = tmp_path / "model_part1.json"
    model.save(model_path)

    sidecar_path = model_path.with_suffix(".sidecar.json")
    calibrated_path = model_path.with_suffix(".calibrated.pkl")

    # All three artifacts exist next to each other.
    assert model_path.exists()
    assert sidecar_path.exists()
    assert calibrated_path.exists()

    # The JSON booster artifact reloads with a fresh Booster and predicts.
    reloaded = xgboost.Booster()
    reloaded.load_model(str(model_path))
    preds = reloaded.predict(xgboost.DMatrix(x))
    assert preds.shape == (len(x),)
    assert np.all(np.isfinite(preds))

    # The sidecar is a self-describing JSON document carrying the schema and a
    # reference (by filename) to the calibration representation.
    with open(sidecar_path, encoding="utf-8") as handle:
        sidecar = json.load(handle)

    assert sidecar["calibrated_path"] == calibrated_path.name
    reconstructed = FeatureSchema.from_dict(sidecar["schema"])
    assert reconstructed.columns == schema.columns
    assert reconstructed.categorical_maps == schema.categorical_maps
    assert reconstructed.product_type_columns == schema.product_type_columns
    assert reconstructed.part2_columns == schema.part2_columns


def test_save_creates_missing_output_directory(tmp_path):
    """A missing output directory is created on save (Requirement 6.7).

    Point ``model_path`` at a nested, not-yet-existing subdirectory and confirm
    ``save`` creates the parent directory and writes the artifact there.

    _Requirements: 6.7_
    """
    x, y = _two_class_frame()
    model = Model_Trainer(Config()).fit(x, y, _schema())

    missing_dir = tmp_path / "outputs" / "nested"
    assert not missing_dir.exists()

    model_path = missing_dir / "model_part1.json"
    model.save(model_path)

    assert missing_dir.is_dir()
    assert model_path.exists()
    assert model_path.with_suffix(".sidecar.json").exists()
    assert model_path.with_suffix(".calibrated.pkl").exists()
