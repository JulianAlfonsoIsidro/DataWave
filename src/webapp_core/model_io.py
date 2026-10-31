"""Reload a persisted :class:`Calibrated_Model` for the Part 5 webapp.

The Part 1 pipeline trains and persists a :class:`Calibrated_Model` via
:meth:`Calibrated_Model.save`, which writes three artifacts into an outputs
directory (Requirement 6.1 of Part 1):

- ``model_part1.json`` -- the full-data :class:`xgboost.Booster`, a valid JSON
  booster document reloadable with ``xgboost.Booster().load_model``,
- ``model_part1.sidecar.json`` -- a self-describing document carrying the
  fitted :class:`FeatureSchema` under ``"schema"`` and the calibration pickle's
  filename under ``"calibrated_path"``, and
- ``model_part1.calibrated.pkl`` -- the pickled ``CalibratedClassifierCV``.

The webapp is a presentation/orchestration layer: it never retrains. Instead it
reloads these artifacts out of process to reconstruct the exact calibrated
predictor the pipeline produced (Requirements 1.3, 1.4). :func:`load_model`
mirrors the save contract field-for-field and fails loudly, naming the first
missing artifact, so a half-populated outputs directory produces a clear error
rather than a partial or wrong model.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import xgboost

from part1_optin.features import FeatureSchema
from part1_optin.model import Calibrated_Model

# The booster artifact name written by Calibrated_Model.save; its stem drives
# the adjacent sidecar/calibration filenames (Part 1 Requirement 6.1).
BOOSTER_FILENAME = "model_part1.json"

# The sidecar document name, model_path.with_suffix(".sidecar.json").
SIDECAR_FILENAME = "model_part1.sidecar.json"


def load_model(outputs_dir) -> Calibrated_Model:
    """Reconstruct the persisted :class:`Calibrated_Model` from ``outputs_dir``.

    Inverts :meth:`Calibrated_Model.save`: reloads the full-data booster from
    ``model_part1.json``, the :class:`FeatureSchema` and calibration-pickle
    reference from ``model_part1.sidecar.json``, and the
    ``CalibratedClassifierCV`` from the pickle named by the sidecar's
    ``"calibrated_path"`` (resolved relative to ``outputs_dir``), then bundles
    them into a :class:`Calibrated_Model` (Requirements 1.3, 1.4).

    Artifacts are checked in dependency order -- booster, then sidecar, then the
    calibration pickle the sidecar points at -- and the **first** missing one
    raises ``FileNotFoundError`` naming that artifact, so a partially populated
    outputs directory fails loudly instead of yielding a half-built model
    (Requirement 1.4).

    Args:
        outputs_dir: Directory holding the three saved artifacts (a
            :class:`~pathlib.Path` or ``str``), e.g. ``outputs/``.

    Returns:
        A :class:`Calibrated_Model` whose ``booster``, ``schema``, and
        ``calibrated`` are the reloaded artifacts.

    Raises:
        FileNotFoundError: If the booster, the sidecar, or the calibration
            pickle is absent; the message names the first missing artifact.
    """
    outputs_dir = Path(outputs_dir)

    # 1. Booster artifact (model_part1.json). Checked first because it is the
    # requirement-named artifact and the anchor for the save contract.
    booster_path = outputs_dir / BOOSTER_FILENAME
    if not booster_path.exists():
        raise FileNotFoundError(
            f"missing model artifact: {booster_path}"
        )

    # 2. Sidecar (model_part1.sidecar.json). Read second because it names the
    # calibration pickle we check third; without it we cannot locate the pickle.
    sidecar_path = outputs_dir / SIDECAR_FILENAME
    if not sidecar_path.exists():
        raise FileNotFoundError(
            f"missing model artifact: {sidecar_path}"
        )
    with open(sidecar_path, "r", encoding="utf-8") as handle:
        sidecar = json.load(handle)

    # 3. Calibration pickle, named by the sidecar's calibrated_path (a bare
    # filename, resolved relative to outputs_dir so the pair stays relocatable).
    calibrated_path = outputs_dir / sidecar["calibrated_path"]
    if not calibrated_path.exists():
        raise FileNotFoundError(
            f"missing model artifact: {calibrated_path}"
        )

    # All three artifacts present: reconstruct each piece and rebundle.
    booster = xgboost.Booster()
    booster.load_model(str(booster_path))

    schema = FeatureSchema.from_dict(sidecar["schema"])

    with open(calibrated_path, "rb") as handle:
        calibrated = pickle.load(handle)

    return Calibrated_Model(
        calibrated=calibrated,
        booster=booster,
        schema=schema,
    )
