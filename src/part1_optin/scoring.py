"""Scorer for the Part1_Optin_Pipeline.

The Scorer turns a fitted :class:`~part1_optin.model.Calibrated_Model` into the
per-lead Scores_File: it calibrated-scores every treated lead, attaches each
lead's top-3 SHAP drivers, and writes ``outputs/scores.csv`` in the fixed
six-column layout (Requirement 6). A separate :func:`score_promo` scores a new,
previously unseen promo (Requirement 7); it is implemented in a later task and
left as a stub here.

The design mirrors ``part2_network`` conventions: absolute imports
(``from part1_optin...``), module-level constants, ``Config`` as the single
source of configuration, and CSV output via ``to_csv(index=False)`` after
creating the parent directory (mirrors ``part2_network.features.write``).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from part1_optin.config import (
    Config,
    KNOWN_MECHANICS,
    PROMO_MECHANIC_COLUMN,
)
from part1_optin.explain import Explainer
from part1_optin.features import Feature_Assembler, PROMO_THRESHOLD_COLUMN
from part1_optin.model import Calibrated_Model

# The fixed Scores_File column order (Requirement 6.3). score_leads builds a
# frame with exactly these columns and write_scores emits them as the single
# header row with no index column.
SCORE_COLUMNS = [
    "promo_id",
    "client_id",
    "p_join",
    "top_driver_1",
    "top_driver_2",
    "top_driver_3",
]

# Decimal places each p_join is rounded to before writing (Requirement 6.4).
P_JOIN_DECIMALS = 6


class Scorer:
    """Produce calibrated per-lead scores with top SHAP drivers.

    Bundles the fitted :class:`Calibrated_Model` and the :class:`Config`.
    :meth:`score_leads` calibrated-scores the treated leads and attaches their
    top-3 drivers; :meth:`write_scores` persists the result as the fixed
    six-column ``outputs/scores.csv`` (Requirement 6).
    """

    def __init__(self, model: Calibrated_Model, config: Config) -> None:
        """Store the fitted model and config; no scoring happens here.

        Args:
            model: The bundled :class:`Calibrated_Model` whose calibrated
                predictor emits ``p_join`` and whose full-data booster SHAP
                explains.
            config: The pipeline :class:`Config` (output paths, constants).
        """
        self.model = model
        self.config = config

    def score_leads(self, leads: pd.DataFrame, X: pd.DataFrame) -> pd.DataFrame:
        """Calibrated-score every treated lead and attach its top-3 drivers.

        Scores every row of ``X`` with the calibrated predictor
        (``model.predict_proba``), clipped into ``[0, 1]`` by the model
        (Requirement 3.5), and attaches each lead's three largest-absolute SHAP
        drivers via ``Explainer(model).top_drivers(X, k=3)`` (Requirements 5.2,
        5.4). ``leads`` and ``X`` share row order and index (``X`` is the
        aligned feature matrix built from ``leads``), so the ``promo_id`` /
        ``client_id`` identity columns are taken from ``leads`` positionally and
        paired with the scored rows without a join.

        The returned frame carries exactly one row per scored lead with the
        fixed six columns in order (Requirement 6.6, 6.3); it is unsorted and
        unrounded here -- :meth:`write_scores` applies the rounding and ordering
        at persist time.

        Args:
            leads: The treated leads, carrying at least ``promo_id`` and
                ``client_id`` (plus other columns, ignored).
            X: The assembled feature matrix, one Feature_Row per lead, columns
                exactly ``model.schema.columns`` and the same row order/index
                as ``leads``.

        Returns:
            A :class:`pandas.DataFrame` with columns ``promo_id``,
            ``client_id``, ``p_join``, ``top_driver_1``, ``top_driver_2``,
            ``top_driver_3``, one row per scored lead.
        """
        # Calibrated positive-class probabilities, already clipped to [0, 1] by
        # the model (Requirement 3.5). predict_proba preserves X's row order.
        p_join = self.model.predict_proba(X)

        # Top-3 SHAP drivers per row: a list of 3-tuples of predictor-name
        # strings with "" padding beyond the non-zero-contribution count
        # (Requirements 5.2, 5.4).
        drivers = Explainer(self.model).top_drivers(X, k=3)

        # Pair identity columns from leads positionally with the scored rows;
        # leads and X are row-aligned, so reset_index drops any index mismatch
        # before constructing the output frame.
        promo_id = leads["promo_id"].reset_index(drop=True)
        client_id = leads["client_id"].reset_index(drop=True)

        scored = pd.DataFrame(
            {
                "promo_id": promo_id,
                "client_id": client_id,
                "p_join": p_join,
                "top_driver_1": [row[0] for row in drivers],
                "top_driver_2": [row[1] for row in drivers],
                "top_driver_3": [row[2] for row in drivers],
            }
        )

        # Enforce the fixed six-column order (Requirement 6.3).
        return scored[SCORE_COLUMNS]

    def write_scores(self, scored: pd.DataFrame, path: Path) -> None:
        """Write the Scores_File as the fixed six-column CSV (Requirement 6).

        Persists ``scored`` to ``path`` as a comma-separated file with a single
        header row, the fixed column order ``promo_id``, ``client_id``,
        ``p_join``, ``top_driver_1``, ``top_driver_2``, ``top_driver_3``, and no
        index column (Requirement 6.3). Before writing it:

        - creates ``path``'s parent directory (e.g. ``outputs/``) if absent
          (Requirement 6.7);
        - clips ``p_join`` into ``[0, 1]`` and rounds it to 6 decimal places
          (Requirement 6.4);
        - sorts the rows by ascending ``promo_id`` then ascending ``client_id``
          (Requirement 6.5).

        ``scored`` already carries exactly one row per treated lead
        (Requirement 6.6); this method preserves that one-row-per-lead cardinality.

        Args:
            scored: The frame returned by :meth:`score_leads`, carrying the six
                fixed columns.
            path: Destination CSV path; its parent directory is created if
                missing.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Operate on a copy so the caller's frame is untouched; select the fixed
        # column order up front (Requirement 6.3).
        out = scored[SCORE_COLUMNS].copy()

        # Bound p_join into [0, 1] and round to 6 dp (Requirement 6.4).
        out["p_join"] = out["p_join"].clip(0.0, 1.0).round(P_JOIN_DECIMALS)

        # Order by ascending promo_id then client_id (Requirement 6.5).
        out = out.sort_values(["promo_id", "client_id"]).reset_index(drop=True)

        # Single header row, fixed column order, no index column (Requirement 6.3).
        out.to_csv(path, index=False)


# The Scores_File column order used by score_promo for an unseen promo
# (Requirement 7). It mirrors SCORE_COLUMNS minus the promo_id identity column,
# since an unseen promo scores one row per eligible client (Requirement 7.5).
SCORE_PROMO_COLUMNS = [
    "client_id",
    "p_join",
    "top_driver_1",
    "top_driver_2",
    "top_driver_3",
]


def score_promo(
    promo_dict: dict,
    clients_df: pd.DataFrame,
    model: Calibrated_Model,
    config: Config,
) -> pd.DataFrame:
    """Score a new, previously unseen promo for its eligible clients (Requirement 7).

    Estimates a calibrated join probability for every eligible client in
    ``clients_df`` under the Unseen_Promo described by ``promo_dict``, reusing
    the already-fitted :class:`Calibrated_Model` without any retraining or
    recalibration (Requirement 7.3). The returned frame carries one row per
    client with its ``p_join`` in ``[0, 1]`` and its three top SHAP drivers
    (Requirements 7.1, 7.5).

    How the feature matrix is built (Requirement 7.2):

    1. A "leads"-shaped frame is constructed from ``clients_df`` -- one row per
       ``client_id`` with ``promo_id`` set to ``promo_dict["promo_id"]`` -- so
       the client-keyed feature blocks (DNA, product counts, ADB, contacts, NDB,
       part2) join exactly as they do for a treated lead.
    2. :meth:`Feature_Assembler.transform` reapplies the model's *frozen*
       ``schema`` so the matrix's column set, order, and categorical encoding
       match the trained matrix exactly.
    3. The Promo_Attributes block would normally look the promo's ``mechanic`` /
       ``threshold_php`` up from the Promo_History_File by ``promo_id`` -- but an
       Unseen_Promo is absent from that file, so that lookup would yield the
       reserved missing code and a ``0`` threshold. Instead, the ``mechanic``
       code and ``threshold_php`` columns are *overridden* from ``promo_dict``:
       ``mechanic`` is encoded through the frozen
       ``schema.categorical_maps[mechanic]`` (an unseen mechanic -> the reserved
       ``0``), and ``threshold_php`` is taken numerically from the dict. This
       guarantees the promo attributes come from the supplied dict, not from a
       promo-history lookup that would miss (Requirement 7.2).

    Unseen-mechanic handling (Requirement 7.4): if ``promo_dict["mechanic"]`` is
    not one of :data:`~part1_optin.config.KNOWN_MECHANICS`, every client is still
    scored, but a :func:`warnings.warn` is emitted that predictions are less
    reliable for an unseen promo mechanic.

    Args:
        promo_dict: The Unseen_Promo, carrying at least ``promo_id``,
            ``mechanic``, and ``threshold_php``.
        clients_df: The eligible clients, carrying a ``client_id`` column.
        model: The fitted :class:`Calibrated_Model`; applied as-is, never
            retrained or recalibrated (Requirement 7.3).
        config: The pipeline :class:`Config` holding the approved input paths
            the Feature_Assembler reads the client sources from.

    Returns:
        A :class:`pandas.DataFrame` with columns ``client_id``, ``p_join``,
        ``top_driver_1``, ``top_driver_2``, ``top_driver_3`` -- one row per
        eligible client, in ``clients_df`` order.
    """
    mechanic = promo_dict["mechanic"]
    threshold = promo_dict[PROMO_THRESHOLD_COLUMN]

    # Unseen-mechanic soft warning (Requirement 7.4): still score every client,
    # but flag that an unseen mechanic makes the predictions less reliable. The
    # mechanic still encodes to the reserved 0 below, so scoring proceeds.
    if mechanic not in KNOWN_MECHANICS:
        warnings.warn(
            f"promo mechanic {mechanic!r} was not among the training leads; "
            f"join-probability predictions are less reliable for unseen promo "
            f"mechanics (Requirement 7.4)",
            stacklevel=2,
        )

    # Build a "leads"-shaped frame: one row per eligible client, tagged with the
    # unseen promo's id so the client-keyed feature blocks join as usual. Order
    # and index are preserved so the scored rows line up with clients_df.
    leads = pd.DataFrame(
        {
            "client_id": clients_df["client_id"].to_numpy(),
            "promo_id": promo_dict["promo_id"],
        }
    )

    # Reapply the frozen schema so columns/order/encoding match the trained
    # matrix exactly (Requirement 7.2). The promo block inside transform looks
    # the mechanic/threshold up from the Promo_History_File by promo_id, which
    # misses for an unseen promo -- so both columns are overridden next.
    assembler = Feature_Assembler(config)
    X = assembler.transform(leads, model.schema)

    # Override the promo-attribute columns from promo_dict (Requirement 7.2):
    # the mechanic code via the frozen value->code map (unseen -> reserved 0),
    # and threshold_php as the supplied numeric value. This guarantees the
    # unseen promo's attributes come from the dict, not a history lookup.
    mechanic_map = model.schema.categorical_maps.get(PROMO_MECHANIC_COLUMN, {})
    X[PROMO_MECHANIC_COLUMN] = int(mechanic_map.get(mechanic, 0))
    X[PROMO_THRESHOLD_COLUMN] = pd.to_numeric(threshold, errors="coerce")
    X[PROMO_THRESHOLD_COLUMN] = X[PROMO_THRESHOLD_COLUMN].fillna(0)

    # Keep the exact trained column order after the overrides (Requirement 7.2);
    # the overrides reassigned existing columns, so this is an ordering no-op
    # that also guards against any accidental column drift.
    X = X.reindex(columns=model.schema.columns, fill_value=0)

    # Apply the existing Calibrated_Model without retraining; p_join is already
    # clipped to [0, 1] by the model (Requirements 7.3, 3.5).
    p_join = model.predict_proba(X)

    # Top-3 SHAP drivers per client, largest-to-smallest |SHAP| with "" padding
    # beyond the non-zero-contribution count (Requirement 7.5).
    drivers = Explainer(model).top_drivers(X, k=3)

    scored = pd.DataFrame(
        {
            "client_id": clients_df["client_id"].reset_index(drop=True),
            "p_join": p_join,
            "top_driver_1": [row[0] for row in drivers],
            "top_driver_2": [row[1] for row in drivers],
            "top_driver_3": [row[2] for row in drivers],
        }
    )

    return scored[SCORE_PROMO_COLUMNS]
