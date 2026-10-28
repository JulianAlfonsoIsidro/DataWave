"""Model_Trainer and Calibrated_Model for the Part1_Optin_Pipeline.

The Model_Trainer fits an out-of-fold isotonic-calibrated XGBoost classifier
(Requirement 3) and bundles it with a separate full-data booster and the fitted
``FeatureSchema`` into a :class:`Calibrated_Model` wrapper.

Why two models (design "Why two models"):

- ``CalibratedClassifierCV(method="isotonic", cv=3)`` fits three internal
  booster clones and averages their isotonically-calibrated outputs, so there
  is no single booster inside it. This calibrated CV model is the source of the
  out-of-fold calibrated ``p_join`` used for prediction/validation/scoring
  (Requirement 3.3): no lead's calibrated score comes from a booster that saw
  that lead during fitting.
- A separate plain :class:`xgboost.XGBClassifier` is fit on **all** the given
  rows with the same seed; its :class:`xgboost.Booster` is what gets persisted
  as the valid JSON booster artifact (Requirement 6.1) and what SHAP's
  ``TreeExplainer`` runs on (Requirement 5.1).

A single :data:`~part1_optin.config.RANDOM_SEED` drives the ``XGBClassifier``
estimators and the seeded ``StratifiedKFold(n_splits=3, shuffle=True,
random_state=RANDOM_SEED)`` splitter so two runs on identical inputs produce
identical calibrated scores (Requirement 3.2).

The design mirrors ``part2_network`` conventions: absolute imports
(``from part1_optin...``), module-level helpers, and ``Config`` as the single
source of configuration.

The :class:`Calibrated_Model` dataclass is defined here (fields ``calibrated``,
``booster``, ``schema``) so :meth:`Model_Trainer.fit` can construct and return a
populated instance; its ``predict_proba`` and ``save`` are fleshed out in a
later task.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold

from part1_optin.config import Config, RANDOM_SEED
from part1_optin.features import FeatureSchema

# Number of internal calibration folds for CalibratedClassifierCV (design:
# out-of-fold isotonic calibration, Requirement 3.3). The production default is
# 3; each fold needs both classes, so callers provide at least three
# minority-class examples.
CALIBRATION_CV_FOLDS = 3


def _make_xgb_classifier() -> xgboost.XGBClassifier:
    """Return a seeded binary :class:`xgboost.XGBClassifier`.

    Both the calibrated CV estimator and the separate full-data booster are
    built from this one factory so they share identical hyperparameters and the
    fixed :data:`~part1_optin.config.RANDOM_SEED`, keeping scores deterministic
    across runs (Requirement 3.2). ``eval_metric="logloss"`` selects the
    log-loss objective's evaluation metric for binary classification; no
    ``use_label_encoder`` argument is passed because it was removed in modern
    XGBoost.
    """
    return xgboost.XGBClassifier(
        random_state=RANDOM_SEED,
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        eval_metric="logloss",
    )


@dataclass
class Calibrated_Model:
    """The fitted calibrated predictor bundled with its booster and schema.

    Holds two fitted models plus the feature contract:

    - ``calibrated``: the out-of-fold ``CalibratedClassifierCV(method="isotonic",
      cv=3)`` used for all calibrated ``p_join`` prediction/validation/scoring.
    - ``booster``: the single :class:`xgboost.Booster` fit on all given rows,
      used for the valid JSON booster artifact (Requirement 6.1) and SHAP
      driver attribution (Requirement 5.1).
    - ``schema``: the fitted :class:`FeatureSchema`, the transform-at-score-time
      contract.

    ``save`` persists the booster as the requirement-named artifact and the
    calibrated predictor + schema to sidecars for out-of-process reuse.
    """

    calibrated: CalibratedClassifierCV
    booster: xgboost.Booster
    schema: FeatureSchema

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated positive-class probabilities in ``[0, 1]``.

        Delegates to the out-of-fold ``CalibratedClassifierCV``, takes the
        positive-class column, and clips to the inclusive range ``[0, 1]``
        (Requirement 3.5).
        """
        proba = self.calibrated.predict_proba(X)[:, 1]
        return np.clip(proba, 0.0, 1.0)

    def save(self, model_path: Path) -> None:
        """Persist the booster artifact plus a schema + calibration sidecar.

        Writes three files, all in ``model_path``'s parent directory (created
        if absent, Requirement 6.7):

        - ``model_path`` (e.g. ``outputs/model_part1.json``): the single
          full-data booster written via ``booster.save_model`` so the file is a
          **valid JSON XGBoost booster document** that reloads with
          ``xgboost.Booster().load_model`` (Requirement 6.1). The
          ``CalibratedClassifierCV`` and ``FeatureSchema`` are not pure-booster
          artifacts, so they are deliberately kept out of this file to leave it
          an uncorrupted, reloadable booster.
        - ``<stem>.calibrated.pkl``: the pickled ``CalibratedClassifierCV``,
          the calibration representation (per-fold calibrated classifiers /
          isotonic breakpoints) needed to reconstruct the calibrated predictor
          out of process.
        - ``<stem>.sidecar.json``: a self-describing JSON document carrying
          ``schema.to_dict()`` under ``"schema"`` and the pickle's filename
          under ``"calibrated_path"`` so a loader can find and restore the
          calibrated predictor alongside the booster.

        ``save`` is called only after the final fit succeeds, so a failed run
        writes nothing (Requirement 6.2).

        Args:
            model_path: Destination for the valid JSON booster artifact; its
                parent directory is created if missing and its stem names the
                adjacent sidecar files.
        """
        model_path = Path(model_path)
        output_dir = model_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # The requirement-named artifact: a pure, valid JSON booster document
        # (Requirement 6.1). XGBoost infers the JSON format from the .json
        # extension and this reloads with Booster().load_model(model_path).
        self.booster.save_model(str(model_path))

        # Calibration representation persisted next to the booster. Pickling the
        # fitted CalibratedClassifierCV captures the per-fold calibrated
        # classifiers / isotonic maps needed to reconstruct the calibrated
        # predictor out of process, keeping model_path a pure booster.
        calibrated_path = model_path.with_suffix(".calibrated.pkl")
        with open(calibrated_path, "wb") as handle:
            pickle.dump(self.calibrated, handle)

        # Sidecar: schema contract + a reference to the calibration pickle by
        # filename (not full path) so the pair stays relocatable together.
        sidecar_path = model_path.with_suffix(".sidecar.json")
        sidecar = {
            "schema": self.schema.to_dict(),
            "calibrated_path": calibrated_path.name,
        }
        with open(sidecar_path, "w", encoding="utf-8") as handle:
            json.dump(sidecar, handle, indent=2)


class Model_Trainer:
    """Fit the out-of-fold calibrated model and a separate full-data booster.

    :meth:`fit` builds a ``CalibratedClassifierCV(method="isotonic",
    cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_SEED))``
    around a seeded :class:`xgboost.XGBClassifier` and fits it on the given
    leads (Requirements 3.1, 3.3); separately it fits one plain
    :class:`xgboost.XGBClassifier` on all given rows and extracts its
    :class:`xgboost.Booster` for the artifact and SHAP (Requirement 6.1, 5.1).
    """

    def __init__(self, config: Config) -> None:
        """Store the ``Config``. No fitting happens here; see :meth:`fit`."""
        self.config = config

    def fit(
        self, X: pd.DataFrame, y: pd.Series, schema: FeatureSchema
    ) -> Calibrated_Model:
        """Fit the calibrated model and full-data booster; return the bundle.

        Steps, in order:

        1. **Single-class guard (Requirement 3.6).** If the labels for this fit
           have only one unique class, raise ``ValueError`` indicating that
           calibration requires both opt-in and non-opt-in examples, halting
           before any fit so no ``Calibrated_Model`` is produced. Neither the
           calibrated CV model nor a single-class booster can be calibrated.
        2. **Out-of-fold calibrated predictor (Requirements 3.1, 3.3).** Build
           ``CalibratedClassifierCV(estimator=XGBClassifier(...),
           method="isotonic", cv=StratifiedKFold(n_splits=3, shuffle=True,
           random_state=RANDOM_SEED))`` and fit it on ``X`` / ``y``. The
           internal 3-fold CV produces the out-of-fold predictions the isotonic
           maps are fit on, so calibration is never in-sample.
        3. **Full-data booster (Requirements 6.1, 5.1).** Separately fit one
           plain seeded ``XGBClassifier`` on all of ``X`` / ``y`` and extract
           its ``Booster``.
        4. Bundle ``calibrated``, ``booster``, and ``schema`` into a
           :class:`Calibrated_Model` and return it.

        The fixed :data:`~part1_optin.config.RANDOM_SEED` drives both
        classifiers and the seeded splitter, so repeated runs yield identical
        scores (Requirement 3.2). When this trainer is used inside a
        leave-one-promo-out fold, ``X`` / ``y`` carry only the two training
        promos' leads, so the held-out promo enters neither the outer fit nor
        the inner calibration CV (Requirements 3.3, 3.4).

        Args:
            X: The assembled feature matrix, one Feature_Row per lead, columns
                exactly ``schema.columns``.
            y: The Join_Label target aligned to ``X``.
            schema: The fitted :class:`FeatureSchema` to bundle into the result.

        Returns:
            A populated :class:`Calibrated_Model`.

        Raises:
            ValueError: If ``y`` contains only a single class (Requirement 3.6).
        """
        y = pd.Series(y)

        # Single-class guard (Requirement 3.6): both opt-in and non-opt-in
        # examples are required to fit the classifier and the isotonic
        # calibrator. Halt before any fit so no Calibrated_Model is produced.
        if y.nunique(dropna=False) < 2:
            raise ValueError(
                "calibration requires both opt-in and non-opt-in examples; "
                "the labels for this fit have only one unique class "
                "(Requirement 3.6)"
            )

        # Out-of-fold isotonic calibration (Requirements 3.1, 3.3). The seeded
        # StratifiedKFold spreads the minority class across folds so each inner
        # fold sees both classes; its out-of-fold predictions feed the isotonic
        # maps, so no lead is calibrated by a booster that saw it.
        cv = StratifiedKFold(
            n_splits=CALIBRATION_CV_FOLDS,
            shuffle=True,
            random_state=RANDOM_SEED,
        )
        calibrated = CalibratedClassifierCV(
            estimator=_make_xgb_classifier(),
            method="isotonic",
            cv=cv,
        )
        calibrated.fit(X, y)

        # Separate full-data booster (Requirements 6.1, 5.1): one plain seeded
        # XGBClassifier fit on ALL given rows; its Booster is the artifact and
        # the tree model SHAP explains. This is a distinct fit from the
        # calibrated CV model, which has no single booster to persist.
        full_classifier = _make_xgb_classifier()
        full_classifier.fit(X, y)
        booster = full_classifier.get_booster()

        return Calibrated_Model(
            calibrated=calibrated,
            booster=booster,
            schema=schema,
        )
