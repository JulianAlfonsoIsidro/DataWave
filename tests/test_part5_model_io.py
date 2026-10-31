"""Example/edge unit tests for :func:`webapp_core.model_io.load_model`.

These cover the two behaviors of the model reloader (Requirements 1.3, 1.4):

- a full round-trip: a :class:`Calibrated_Model` saved by
  :meth:`Calibrated_Model.save` into a temporary directory reloads into an
  equivalent model (a booster, a calibrated predictor, and a schema whose
  columns match), and
- the missing-artifact guard: ``load_model`` raises ``FileNotFoundError``
  naming the *first* missing artifact, checked in the order booster ->
  sidecar -> calibration pickle.

These are concrete example/edge tests, not Hypothesis properties. Any artifact
the tests write lands in pytest's ``tmp_path`` (cleaned up automatically),
never the repo root.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import xgboost
from sklearn.calibration import CalibratedClassifierCV

from part1_optin.model import Calibrated_Model
from webapp_core.model_io import (
    BOOSTER_FILENAME,
    SIDECAR_FILENAME,
    load_model,
)

# The real trained artifacts shipped in outputs/ are the simplest reliable
# source of a genuine Calibrated_Model to round-trip.
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def test_load_model_round_trips_a_saved_model(tmp_path):
    """A model saved into a temp dir reloads into an equivalent model.

    Loads the real trained model from ``outputs/``, re-saves it into a fresh
    temporary directory via ``Calibrated_Model.save``, then reloads *that*
    directory. The reloaded bundle must carry a booster, a calibrated
    predictor, and a schema whose column list matches the original
    (Requirement 1.3).
    """
    original = load_model(OUTPUTS_DIR)

    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()
    original.save(scratch_dir / BOOSTER_FILENAME)

    reloaded = load_model(scratch_dir)

    assert isinstance(reloaded, Calibrated_Model)
    assert isinstance(reloaded.booster, xgboost.Booster)
    assert isinstance(reloaded.calibrated, CalibratedClassifierCV)
    assert reloaded.schema.columns == original.schema.columns
    # The whole schema survives the round-trip, not just the columns.
    assert reloaded.schema.to_dict() == original.schema.to_dict()


def test_load_model_names_missing_booster_first(tmp_path):
    """An empty directory fails naming the booster artifact first."""
    with pytest.raises(FileNotFoundError, match=BOOSTER_FILENAME):
        load_model(tmp_path)


def test_load_model_names_missing_sidecar_when_only_booster_present(tmp_path):
    """With only the booster present, the sidecar is the first missing one."""
    original = load_model(OUTPUTS_DIR)
    # Save a full set elsewhere, then copy only the booster into tmp_path so the
    # sidecar and calibration pickle are absent.
    original.booster.save_model(str(tmp_path / BOOSTER_FILENAME))

    with pytest.raises(FileNotFoundError, match=SIDECAR_FILENAME):
        load_model(tmp_path)


def test_load_model_names_missing_calibration_pickle_last(tmp_path):
    """With booster + sidecar present, the pickle is the first missing one."""
    original = load_model(OUTPUTS_DIR)
    original.booster.save_model(str(tmp_path / BOOSTER_FILENAME))

    # Write a sidecar pointing at a calibration pickle that does not exist.
    calibrated_name = "model_part1.calibrated.pkl"
    sidecar = {
        "schema": original.schema.to_dict(),
        "calibrated_path": calibrated_name,
    }
    with open(tmp_path / SIDECAR_FILENAME, "w", encoding="utf-8") as handle:
        json.dump(sidecar, handle)

    with pytest.raises(FileNotFoundError, match=calibrated_name):
        load_model(tmp_path)
