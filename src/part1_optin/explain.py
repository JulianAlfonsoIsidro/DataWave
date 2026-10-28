"""Explainer for the Part1_Optin_Pipeline.

The Explainer computes SHAP feature attributions for scored leads and derives
each lead's top drivers (Requirement 5). It runs on the
:class:`~part1_optin.model.Calibrated_Model`'s single full-data XGBoost booster
rather than on the calibrated CV model, which has no single booster for SHAP
(design "explain.py"); because isotonic calibration is monotonic and does not
reorder scores, the booster's driver ranking is the intended explanation of the
calibrated ranking (Requirement 5.1).

The design mirrors ``part2_network`` conventions: absolute imports
(``from part1_optin...``), module-level helpers, and the ``Calibrated_Model``
as the single source of the explainable model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from part1_optin.model import Calibrated_Model


class Explainer:
    """Compute SHAP values and per-lead top drivers for a Calibrated_Model.

    Holds a reference to the fitted :class:`Calibrated_Model`; a fresh
    :class:`shap.TreeExplainer` is built over its full-data booster on each
    :meth:`shap_values` call so the explainer reflects the model handed in.
    """

    def __init__(self, model: Calibrated_Model) -> None:
        """Store the fitted :class:`Calibrated_Model` to explain.

        Args:
            model: The bundled calibrated model whose single full-data
                ``booster`` SHAP runs on (Requirement 5.1).
        """
        self.model = model

    def shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """Return one SHAP contribution per predictor per scored row.

        Builds a :class:`shap.TreeExplainer` on the Calibrated_Model's single
        full-data XGBoost booster and evaluates it on ``X`` (Requirement 5.1).
        For binary classification ``shap`` may return either a 2D array of shape
        ``(rows, predictors)`` or a list/3D array carrying a matrix per output
        class; in the list/3D case the positive-class matrix is selected so the
        result is always ``(rows, predictors)``.

        Args:
            X: The assembled feature matrix, one Feature_Row per scored lead,
                columns exactly ``schema.columns``.

        Returns:
            A ``numpy.ndarray`` of shape ``(len(X), X.shape[1])`` holding the
            SHAP contribution of each predictor for each row.
        """
        explainer = shap.TreeExplainer(self.model.booster)
        values = explainer.shap_values(X)

        # Binary classification can yield a per-class list (older shap) or a 3D
        # array (rows, predictors, classes). Reduce to the positive-class
        # (rows, predictors) matrix so the shape contract always holds.
        if isinstance(values, list):
            values = values[-1]
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, -1]

        return values

    def top_drivers(self, X: pd.DataFrame, k: int = 3) -> list[tuple[str, ...]]:
        """Return each row's ``k`` top SHAP drivers as predictor-name tuples.

        For each scored row, ranks predictors by absolute SHAP contribution
        from largest to smallest and takes the top ``k`` names (Requirement
        5.2). Ties on ``|SHAP|`` break by ascending predictor name so the
        ordering is deterministic across repeated runs on identical inputs
        (Requirement 5.3). When a row has fewer than ``k`` predictors with a
        non-zero SHAP contribution, the trailing positions are filled with the
        empty string ``""`` (Requirement 5.4).

        Args:
            X: The assembled feature matrix; its columns name the predictors.
            k: The number of driver positions per row (default 3).

        Returns:
            A list with one ``k``-tuple of predictor-name strings per row of
            ``X``, ordered largest-to-smallest absolute contribution with empty
            positions padded by ``""``.
        """
        predictors = list(X.columns)
        values = self.shap_values(X)
        abs_values = np.abs(values)

        drivers: list[tuple[str, ...]] = []
        for row in abs_values:
            # Sort predictor indices by descending |SHAP|, breaking ties by
            # ascending predictor name for determinism (Requirement 5.3). The
            # key negates the magnitude so larger contributions sort first while
            # the name sorts ascending within an equal magnitude.
            order = sorted(
                range(len(predictors)),
                key=lambda i: (-row[i], predictors[i]),
            )

            selected: list[str] = []
            for position in range(k):
                if position < len(order) and row[order[position]] > 0:
                    # Only non-zero-contribution predictors earn a driver slot
                    # (Requirement 5.4); the ordered list front-loads the
                    # non-zero contributions since zeros sort last.
                    selected.append(predictors[order[position]])
                else:
                    selected.append("")

            drivers.append(tuple(selected))

        return drivers
