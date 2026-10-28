"""Validator for the Part1_Optin_Pipeline.

Leave-one-promo-out (LOPO) cross-validation across P001/P002/P003
(Requirement 4). For each held-out promo the Validator fits a fresh
``Model_Trainer`` on only the *other two* promos' leads, predicts the held-out
leads, and reports three per-promo metrics:

- **ROC_AUC** -- only when the held-out set contains both a joiner and a
  non-joiner, otherwise ``None`` (Requirements 4.2, 4.5).
- **Capture_Rate_Top_Quintile** -- when the held-out set has at least one
  joiner: cutoff position ``ceil(TOP_QUINTILE * N)``; every lead whose predicted
  probability is ``>=`` the probability at the cutoff position is counted in the
  top quintile; the rate is joiners-in-top divided by total joiners, in
  ``[0, 1]`` (Requirements 4.3, 4.5).
- **Calibration_Table** -- the held-out leads binned into
  :data:`~part1_optin.config.N_CALIBRATION_BINS` equal-width bins over
  ``[0, 1]``; each non-empty bin reports mean predicted probability, observed
  join rate, and count; empty bins are omitted (Requirement 4.4).

LOPO leakage is enforced structurally: the held-out promo's leads enter neither
the outer fit nor the ``CalibratedClassifierCV`` inner calibration CV
(Requirements 3.3, 3.4, 4.1). A held-out promo with zero joiners reports
``None`` for ROC_AUC and capture without halting the remaining folds
(Requirement 4.5); a fold whose two-promo training subset is single-class
(``Model_Trainer.fit`` raises ``ValueError``) is likewise recorded with
undefined metrics rather than crashing the whole run.

The design mirrors ``part2_network`` conventions: absolute imports
(``from part1_optin...``), module-level helpers, and ``Config`` as the single
source of configuration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

from part1_optin.config import (
    Config,
    N_CALIBRATION_BINS,
    PROMO_IDS,
    RANDOM_SEED,
    TOP_QUINTILE,
)
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer


@dataclass
class PromoFoldResult:
    """Per-held-out-promo metrics from one LOPO fold (Requirement 4.6).

    Attributes:
        promo_id: The held-out promo (one of P001/P002/P003).
        roc_auc: ROC_AUC of predicted join probabilities against the
            Join_Label, in ``[0, 1]``; ``None`` when undefined because the
            held-out set lacks both classes, has no joiners, or the fold could
            not be trained (Requirements 4.2, 4.5).
        capture_rate_top_quintile: Fraction of actual joiners captured in the
            top predicted-probability quintile, in ``[0, 1]``; ``None`` when the
            held-out set has no joiners or the fold could not be trained
            (Requirements 4.3, 4.5).
        calibration_table: One dict per non-empty predicted-probability bin,
            each with ``bin_lo``, ``bin_hi``, ``mean_pred``, ``observed_rate``,
            and ``count`` (Requirement 4.4). Empty when the fold could not be
            trained.
        joiners: Count of actual joiners in the held-out promo.
        n: Count of held-out leads for the promo.
    """

    promo_id: str
    roc_auc: float | None
    capture_rate_top_quintile: float | None
    calibration_table: list[dict]
    joiners: int
    n: int


@dataclass
class StratifiedValidationResult:
    """Headline StratifiedGroupKFold cross-validation metrics (Requirement 8).

    All metrics derive from a single out-of-fold predicted-probability vector:
    every Treated_Lead held out exactly once across the five folds, with no
    client straddling a fold split (Requirements 8.1, 8.3).

    Attributes:
        overall_auc: Overall_Stratified_AUC -- ROC_AUC of the out-of-fold
            probabilities against the Join_Label pooled across all leads, in
            ``[0, 1]``; ``None`` when the pooled labels lack both classes
            (Requirements 8.4, 8.7).
        overall_capture_rate_top_quintile: Stratified_Capture_Rate_Top_Quintile
            over all leads, in ``[0, 1]``; ``None`` when there are no joiners
            overall (Requirements 8.5, 8.7).
        per_promo_auc: ``promo_id -> Per_Promo_Stratified_AUC`` for each promo in
            :data:`~part1_optin.config.PROMO_IDS`, slicing the out-of-fold vector
            to that promo's leads; ``None`` for a slice lacking both classes
            (Requirements 8.4, 8.7).
        per_promo_capture: ``promo_id -> Stratified_Capture_Rate_Top_Quintile``
            per promo; ``None`` for a promo with zero joiners
            (Requirements 8.5, 8.7).
        n: Total count of Treated_Leads scored out-of-fold.
        joiners: Total count of actual joiners across all leads.
    """

    overall_auc: float | None
    overall_capture_rate_top_quintile: float | None
    per_promo_auc: dict[str, float | None]
    per_promo_capture: dict[str, float | None]
    n: int
    joiners: int


@dataclass
class ValidationResult:
    """The validation result carrying both validation schemes.

    Attributes:
        folds: A :class:`PromoFoldResult` per held-out promo from the LOPO
            cold-start scheme, in :data:`~part1_optin.config.PROMO_IDS` order
            (Requirement 4.6).
        stratified: The headline :class:`StratifiedValidationResult` from the
            StratifiedGroupKFold scheme (Requirement 8), or ``None`` when only
            the LOPO scheme was run.
    """

    folds: list[PromoFoldResult] = field(default_factory=list)
    stratified: StratifiedValidationResult | None = None


def _capture_rate_top_quintile(probs: np.ndarray, labels: np.ndarray) -> float:
    """Capture rate of joiners in the top predicted-probability quintile.

    The cutoff position is ``ceil(TOP_QUINTILE * N)`` for ``N`` held-out leads
    (at least 1). After sorting the predicted probabilities in descending order,
    the probability at that cutoff position defines an inclusive threshold:
    every lead whose predicted probability is ``>=`` that threshold is counted
    as top-quintile, so ties at the boundary all count (Requirement 4.3). The
    rate is the number of actual joiners among those top-quintile leads divided
    by the total number of actual joiners, which lies in ``[0, 1]``.

    Callers guarantee at least one joiner before calling this.

    Args:
        probs: Predicted join probabilities for the held-out leads.
        labels: The Join_Label (0/1) aligned to ``probs``.

    Returns:
        The capture rate in ``[0, 1]``.
    """
    n = len(probs)
    total_joiners = int(labels.sum())

    # Cutoff position ceil(0.20 * N), clamped into [1, N]. The threshold prob is
    # the one at that 1-based rank in descending order.
    cutoff_pos = max(1, math.ceil(TOP_QUINTILE * n))
    cutoff_pos = min(cutoff_pos, n)

    sorted_probs = np.sort(probs)[::-1]
    threshold = sorted_probs[cutoff_pos - 1]

    in_top = probs >= threshold
    joiners_in_top = int(labels[in_top].sum())
    return joiners_in_top / total_joiners


def _roc_auc_guarded(probs: np.ndarray, labels: np.ndarray) -> float | None:
    """ROC_AUC of ``probs`` against ``labels``, or ``None`` when undefined.

    ROC_AUC is only defined when the label slice contains both a joiner and a
    non-joiner; a single-class (or empty) slice returns ``None`` rather than
    raising (Requirements 4.2, 4.5, 8.4, 8.7). This is the shared guard reused
    by both the LOPO folds and the stratified slices so the two schemes apply
    exactly the same rule.

    Args:
        probs: Predicted join probabilities.
        labels: The Join_Label (0/1) aligned to ``probs``.

    Returns:
        The ROC_AUC in ``[0, 1]`` when both classes are present, else ``None``.
    """
    n = len(labels)
    joiners = int(labels.sum())
    if 0 < joiners < n:
        return float(roc_auc_score(labels, probs))
    return None


def _calibration_table(probs: np.ndarray, labels: np.ndarray) -> list[dict]:
    """Build the calibration table of non-empty equal-width probability bins.

    The ``[0, 1]`` interval is split into
    :data:`~part1_optin.config.N_CALIBRATION_BINS` equal-width bins. Each
    held-out lead is assigned to the bin covering its predicted probability (the
    rightmost edge ``1.0`` falls in the last bin). For every bin that contains
    at least one lead, the table reports the bin edges, the mean predicted
    probability, the observed join rate, and the lead count; empty bins are
    omitted (Requirement 4.4).

    Args:
        probs: Predicted join probabilities for the held-out leads.
        labels: The Join_Label (0/1) aligned to ``probs``.

    Returns:
        A list of per-non-empty-bin dicts with keys ``bin_lo``, ``bin_hi``,
        ``mean_pred``, ``observed_rate``, ``count``, in ascending bin order.
    """
    n_bins = N_CALIBRATION_BINS
    edges = np.linspace(0.0, 1.0, n_bins + 1)

    # Clip guards against any stray out-of-range value; np.digitize places each
    # prob into bins 1..n_bins over the interior edges, so the rightmost edge
    # (1.0) lands in the last bin rather than spilling into an n_bins+1 bin.
    clipped = np.clip(probs, 0.0, 1.0)
    bin_index = np.digitize(clipped, edges[1:-1], right=False)

    table: list[dict] = []
    for b in range(n_bins):
        mask = bin_index == b
        count = int(mask.sum())
        if count == 0:
            continue
        table.append(
            {
                "bin_lo": float(edges[b]),
                "bin_hi": float(edges[b + 1]),
                "mean_pred": float(clipped[mask].mean()),
                "observed_rate": float(labels[mask].mean()),
                "count": count,
            }
        )
    return table


class Validator:
    """Leave-one-promo-out cross-validation over P001/P002/P003 (Requirement 4).

    :meth:`run` holds out each promo in turn, fits a fresh ``Model_Trainer`` on
    only the other two promos' leads, predicts the held-out leads, and reports
    ROC_AUC, Capture_Rate_Top_Quintile, and a Calibration_Table per held-out
    promo. :meth:`print_report` (a later task) presents them.
    """

    def __init__(self, config: Config) -> None:
        """Store the ``Config``. No work happens here; see :meth:`run`."""
        self.config = config

    def run(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        promo_ids: pd.Series,
        schema: FeatureSchema,
        client_ids: pd.Series | None = None,
    ) -> ValidationResult:
        """Run both validation schemes and return their combined result.

        The result carries two schemes (Requirements 4.6, 8.6):

        - the **headline** StratifiedGroupKFold metrics in
          :attr:`ValidationResult.stratified`, computed by
          :meth:`run_stratified` when ``client_ids`` is supplied; and
        - the LOPO cold-start ``folds`` described below.

        For each held-out promo in :data:`~part1_optin.config.PROMO_IDS`:

        1. Partition on ``promo_ids`` into the held-out promo's leads and the
           other two promos' leads. The held-out leads never enter the fit, so
           the ``CalibratedClassifierCV`` (classifier and its inner isotonic CV)
           sees only the two training promos (Requirements 3.3, 3.4, 4.1).
        2. Fit a fresh ``Model_Trainer`` on the two-promo training subset. If
           that subset is single-class, ``Model_Trainer.fit`` raises
           ``ValueError``; the fold is recorded with undefined metrics rather
           than halting the remaining folds.
        3. Predict calibrated probabilities for the held-out leads and compute
           ROC_AUC (only with both classes present), Capture_Rate_Top_Quintile
           (only with at least one joiner), and the Calibration_Table.

        Args:
            X: The assembled feature matrix, one Feature_Row per lead, columns
                exactly ``schema.columns``.
            y: The Join_Label (0/1) target aligned to ``X``.
            promo_ids: The per-row ``promo_id`` aligned to ``X``, giving each
                lead's promo.
            schema: The fitted :class:`FeatureSchema` passed through to each
                fold's ``Model_Trainer.fit``.
            client_ids: The per-row ``client_id`` aligned to ``X``. When
                supplied, the headline StratifiedGroupKFold scheme also runs via
                :meth:`run_stratified` and populates
                :attr:`ValidationResult.stratified`; when ``None`` only the LOPO
                scheme runs and ``stratified`` stays ``None``.

        Returns:
            A :class:`ValidationResult` carrying one :class:`PromoFoldResult`
            per held-out promo in ``PROMO_IDS`` order (``folds``) and, when
            ``client_ids`` is supplied, the headline
            :class:`StratifiedValidationResult` (``stratified``).
        """
        # Reset index alignment so positional masks line up across X/y/promo_ids
        # regardless of the caller's index.
        X = X.reset_index(drop=True)
        y = pd.Series(np.asarray(y)).reset_index(drop=True)
        promo_ids = pd.Series(np.asarray(promo_ids)).reset_index(drop=True)

        folds: list[PromoFoldResult] = []
        for held_out in PROMO_IDS:
            held_mask = (promo_ids == held_out).to_numpy()
            train_mask = ~held_mask

            X_held = X.loc[held_mask]
            y_held = y.loc[held_mask].to_numpy().astype(int)
            n = int(held_mask.sum())
            joiners = int(y_held.sum())

            X_train = X.loc[train_mask]
            y_train = y.loc[train_mask]

            # A fold with no held-out leads has nothing to evaluate; record an
            # empty fold so each promo still has an entry (Requirement 4.6).
            if n == 0:
                folds.append(
                    PromoFoldResult(
                        promo_id=held_out,
                        roc_auc=None,
                        capture_rate_top_quintile=None,
                        calibration_table=[],
                        joiners=0,
                        n=0,
                    )
                )
                continue

            # Fit on the two training promos only (Requirements 3.3, 3.4, 4.1).
            # A single-class training subset can't be calibrated: record the
            # fold with undefined metrics rather than halting the whole run.
            try:
                model = Model_Trainer(self.config).fit(X_train, y_train, schema)
                probs = model.predict_proba(X_held)
            except ValueError:
                folds.append(
                    PromoFoldResult(
                        promo_id=held_out,
                        roc_auc=None,
                        capture_rate_top_quintile=None,
                        calibration_table=[],
                        joiners=joiners,
                        n=n,
                    )
                )
                continue

            probs = np.asarray(probs, dtype=float)

            # ROC_AUC only when the held-out set has both a joiner and a
            # non-joiner (Requirements 4.2, 4.5).
            roc_auc = _roc_auc_guarded(probs, y_held)

            # Capture rate only when at least one joiner exists
            # (Requirements 4.3, 4.5).
            capture: float | None
            if joiners >= 1:
                capture = _capture_rate_top_quintile(probs, y_held)
            else:
                capture = None

            calibration_table = _calibration_table(probs, y_held)

            folds.append(
                PromoFoldResult(
                    promo_id=held_out,
                    roc_auc=roc_auc,
                    capture_rate_top_quintile=capture,
                    calibration_table=calibration_table,
                    joiners=joiners,
                    n=n,
                )
            )

        # Headline StratifiedGroupKFold scheme (Requirement 8) when the caller
        # supplies client groups; otherwise only the LOPO folds are returned.
        stratified: StratifiedValidationResult | None = None
        if client_ids is not None:
            stratified = self.run_stratified(X, y, promo_ids, client_ids, schema)

        return ValidationResult(folds=folds, stratified=stratified)

    def run_stratified(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        promo_ids: pd.Series,
        client_ids: pd.Series,
        schema: FeatureSchema,
    ) -> StratifiedValidationResult:
        """Run the headline StratifiedGroupKFold validation (Requirement 8).

        Uses :class:`sklearn.model_selection.StratifiedGroupKFold` with 5 folds,
        ``groups=client_ids`` and ``y=Join_Label`` so every lead of one client
        stays in a single fold and each fold preserves the opt-in rate
        (Requirements 8.1, 8.3). For each fold it fits a fresh ``Model_Trainer``
        on that fold's training leads only -- the held-out leads enter neither
        the outer fit nor the inner calibration CV (Requirement 8.2) -- and
        predicts the held-out leads, assembling one out-of-fold probability per
        lead (every lead held out exactly once, no client straddling a split).

        From that single out-of-fold vector it computes Overall_Stratified_AUC
        and the overall capture rate across all leads, plus
        Per_Promo_Stratified_AUC and per-promo capture by slicing the vector per
        ``promo_id``. ROC_AUC reuses :func:`_roc_auc_guarded` (defined only with
        both classes) and capture reuses the ``ceil(TOP_QUINTILE * N)``
        cutoff/tie helper :func:`_capture_rate_top_quintile`; any undefined
        slice yields ``None`` without halting the remaining reporting
        (Requirements 8.4, 8.5, 8.7).

        Args:
            X: The assembled feature matrix, one Feature_Row per lead, columns
                exactly ``schema.columns``.
            y: The Join_Label (0/1) target aligned to ``X``.
            promo_ids: The per-row ``promo_id`` aligned to ``X``.
            client_ids: The per-row ``client_id`` aligned to ``X``, used as the
                grouping key so no client straddles a fold split.
            schema: The fitted :class:`FeatureSchema` passed through to each
                fold's ``Model_Trainer.fit``.

        Returns:
            A :class:`StratifiedValidationResult` with the overall and per-promo
            AUC and capture metrics.
        """
        # Reset index alignment so positional masks line up across all inputs
        # regardless of the caller's index.
        X = X.reset_index(drop=True)
        y = pd.Series(np.asarray(y)).reset_index(drop=True)
        promo_ids = pd.Series(np.asarray(promo_ids)).reset_index(drop=True)
        client_ids = pd.Series(np.asarray(client_ids)).reset_index(drop=True)

        y_arr = y.to_numpy().astype(int)
        n = len(y_arr)
        total_joiners = int(y_arr.sum())

        # One out-of-fold probability per lead. NaN marks a lead not yet
        # predicted so we can assert full coverage after the fold loop.
        oof = np.full(n, np.nan, dtype=float)

        splitter = StratifiedGroupKFold(
            n_splits=5,
            shuffle=True,
            random_state=RANDOM_SEED,
        )
        for train_idx, held_idx in splitter.split(X, y_arr, groups=client_ids):
            X_train = X.iloc[train_idx]
            y_train = y.iloc[train_idx]
            X_held = X.iloc[held_idx]

            # Fit on this fold's training leads only; the held-out leads enter
            # neither the outer fit nor the inner calibration CV
            # (Requirement 8.2). A single-class training slice can't calibrate;
            # record the held-out leads with NaN rather than halting, so a
            # degenerate fold doesn't crash the headline scheme.
            try:
                model = Model_Trainer(self.config).fit(X_train, y_train, schema)
                probs = model.predict_proba(X_held)
            except ValueError:
                continue

            oof[held_idx] = np.asarray(probs, dtype=float)

        # Leads whose fold couldn't be trained stay NaN; exclude them from the
        # pooled and per-promo metrics so undefined slices don't poison AUC.
        scored_mask = ~np.isnan(oof)

        # Overall metrics across all scored leads (Requirements 8.4, 8.5).
        overall_probs = oof[scored_mask]
        overall_labels = y_arr[scored_mask]
        overall_auc = _roc_auc_guarded(overall_probs, overall_labels)
        if int(overall_labels.sum()) >= 1:
            overall_capture = _capture_rate_top_quintile(
                overall_probs, overall_labels
            )
        else:
            overall_capture = None

        # Per-promo metrics by slicing the out-of-fold vector per promo_id
        # (Requirements 8.4, 8.5, 8.7).
        per_promo_auc: dict[str, float | None] = {}
        per_promo_capture: dict[str, float | None] = {}
        promo_arr = promo_ids.to_numpy()
        for promo in PROMO_IDS:
            slice_mask = scored_mask & (promo_arr == promo)
            slice_probs = oof[slice_mask]
            slice_labels = y_arr[slice_mask]

            per_promo_auc[promo] = _roc_auc_guarded(slice_probs, slice_labels)
            if int(slice_labels.sum()) >= 1:
                per_promo_capture[promo] = _capture_rate_top_quintile(
                    slice_probs, slice_labels
                )
            else:
                per_promo_capture[promo] = None

        return StratifiedValidationResult(
            overall_auc=overall_auc,
            overall_capture_rate_top_quintile=overall_capture,
            per_promo_auc=per_promo_auc,
            per_promo_capture=per_promo_capture,
            n=n,
            joiners=total_joiners,
        )

    def print_report(self, result: ValidationResult) -> None:
        """Print the validation report, headline stratified first (Req 8.6).

        The report leads with the headline StratifiedGroupKFold block so the
        cold-start LOPO numbers are not mistaken for the model's primary quality
        (Requirement 8.6):

        1. **Headline: stratified group k-fold (known promos)** -- the overall
           AUC and overall Capture_Rate_Top_Quintile across all Treated_Leads,
           then the Per_Promo_Stratified_AUC and per-promo capture for each
           promo (Requirements 8.4, 8.5). Any ``None`` metric is marked
           ``undefined`` rather than halting the report (Requirement 8.7). When
           the result carries no ``stratified`` block (LOPO-only run), that is
           noted and the headline block is skipped.
        2. **Cold-start: unseen promo type** -- the LOPO folds, each held-out
           promo's ROC_AUC, Capture_Rate_Top_Quintile, and Calibration_Table
           printed separately (Requirements 4.5, 4.6). A ``None`` AUC or capture
           is marked ``undefined (no joiners)`` and a zero-joiner promo is still
           reported, so every fold appears without halting (Requirement 4.5).

        Args:
            result: The :class:`ValidationResult` from :meth:`run`.
        """
        undefined = "undefined"

        def _fmt(value: float | None) -> str:
            """Render a metric as 4-decimal text or ``undefined`` when None."""
            return undefined if value is None else f"{value:.4f}"

        # 1. Headline stratified group k-fold block, printed FIRST so it reads
        #    as the model's primary quality (Requirement 8.6).
        print("Headline: stratified group k-fold validation (known promos)")
        print("=" * 60)

        stratified = result.stratified
        if stratified is None:
            print("No stratified metrics to report.")
        else:
            print(
                f"Treated leads: {stratified.n}  "
                f"(joiners: {stratified.joiners})"
            )
            print(f"  Overall_Stratified_AUC: {_fmt(stratified.overall_auc)}")
            print(
                "  Stratified_Capture_Rate_Top_Quintile: "
                f"{_fmt(stratified.overall_capture_rate_top_quintile)}"
            )
            print("  Per-promo:")
            for promo in PROMO_IDS:
                auc = stratified.per_promo_auc.get(promo)
                capture = stratified.per_promo_capture.get(promo)
                print(
                    f"    {promo}: AUC {_fmt(auc)}  "
                    f"Capture_Rate_Top_Quintile {_fmt(capture)}"
                )

        # 2. LOPO cold-start block, under its own heading so the two schemes are
        #    not conflated (Requirements 4.6, 8.6).
        print()
        print("Cold-start: unseen promo type (leave-one-promo-out)")
        print("=" * 60)

        if not result.folds:
            print("No folds to report.")
            return

        lopo_undefined = "undefined (no joiners)"
        for fold in result.folds:
            print()
            print(f"Held-out promo: {fold.promo_id}")
            print(f"  Held-out leads: {fold.n}  (joiners: {fold.joiners})")

            if fold.roc_auc is None:
                print(f"  ROC_AUC: {lopo_undefined}")
            else:
                print(f"  ROC_AUC: {fold.roc_auc:.4f}")

            if fold.capture_rate_top_quintile is None:
                print(f"  Capture_Rate_Top_Quintile: {lopo_undefined}")
            else:
                print(
                    "  Capture_Rate_Top_Quintile: "
                    f"{fold.capture_rate_top_quintile:.4f}"
                )

            print("  Calibration_Table:")
            if not fold.calibration_table:
                print("    (no calibration bins)")
            else:
                print(
                    f"    {'bin':>13}  {'mean_pred':>9}  "
                    f"{'observed':>9}  {'count':>6}"
                )
                for row in fold.calibration_table:
                    bin_label = f"[{row['bin_lo']:.2f}, {row['bin_hi']:.2f}]"
                    print(
                        f"    {bin_label:>13}  {row['mean_pred']:>9.4f}  "
                        f"{row['observed_rate']:>9.4f}  {row['count']:>6d}"
                    )
