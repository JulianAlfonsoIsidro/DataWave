"""Example/edge unit tests for the Part1_Optin LOPO Validator.

Targeted (non-Hypothesis) tests for :meth:`part1_optin.validation.Validator.run`
against Requirement 4's per-promo reporting, covering:

- The result carries one per-promo fold entry for each of P001/P002/P003, and
  each fold exposes the three metric fields ``roc_auc``,
  ``capture_rate_top_quintile``, and ``calibration_table`` (Requirement 4.6).
- A held-out promo with zero joiners has its ROC_AUC and
  Capture_Rate_Top_Quintile left undefined (``None``) while the other folds
  still report, without halting the run (Requirement 4.5).

The data is small, fixed, and deterministic: a numeric feature matrix, a
Join_Label vector, and a ``promo_ids`` Series over P001/P002/P003, built
directly rather than through the full Feature_Assembler. Each LOPO fold trains
on the two *other* promos combined and ``CalibratedClassifierCV`` uses an
internal 3-fold ``StratifiedKFold``, so every promo that supplies training rows
is given enough per-class examples for those inner folds to fit. A
:class:`FeatureSchema` whose ``columns`` match the matrix is built directly.
No path in this module references a ``*_answer_key*`` file; all matrices are
constructed in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from part1_optin.config import PROMO_IDS, Config
from part1_optin.features import FeatureSchema
from part1_optin.validation import Validator

# Feature columns for the generated matrix; a small fixed set keeps each
# per-fold fit cheap while still exercising a multi-feature calibrated model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Rows per class, per promo. Each LOPO fold trains on two promos combined and
# CalibratedClassifierCV uses a 3-fold StratifiedKFold, so each class needs at
# least three examples in the two-promo training subset; four per class per
# promo gives any two-promo union eight of each class, a comfortable margin.
_PER_CLASS = 4


def _rows(n_rows: int, loc: float, seed: int) -> np.ndarray:
    """Return ``n_rows`` deterministic feature rows centered near ``loc``.

    The two classes are given slightly offset centers so the booster has a
    signal to learn, but these tests assert structure (field presence,
    undefined-metric handling), not accuracy.
    """
    rng = np.random.RandomState(seed)
    return rng.normal(loc=loc, scale=1.0, size=(n_rows, len(_FEATURE_COLUMNS)))


def _both_class_dataset() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Build (X, y, promo_ids) where every promo has both classes.

    Each of P001/P002/P003 gets ``_PER_CLASS`` joiners and ``_PER_CLASS``
    non-joiners, so every two-promo LOPO training subset fits cleanly and every
    held-out promo defines all three metrics. Returns ``(X, y, promo_ids)``.
    """
    all_rows: list[np.ndarray] = []
    labels: list[int] = []
    promos: list[str] = []
    for i, promo in enumerate(PROMO_IDS):
        all_rows.append(_rows(_PER_CLASS, loc=1.0, seed=2 * i))
        all_rows.append(_rows(_PER_CLASS, loc=-1.0, seed=2 * i + 1))
        labels.extend([1] * _PER_CLASS + [0] * _PER_CLASS)
        promos.extend([promo] * (2 * _PER_CLASS))

    x = pd.DataFrame(np.vstack(all_rows), columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    return x, y, promo_ids


def _zero_joiner_dataset() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    """Build (X, y, promo_ids, zero_promo) with one zero-joiner held-out promo.

    P001 and P002 carry both classes (so they can serve as the two-promo
    training subset when P003 is held out, and so their own held-out folds
    define metrics). P003 is made entirely non-joiners, so when it is held out
    its ROC_AUC and capture rate must be undefined (Requirement 4.5). Returns
    ``(X, y, promo_ids, "P003")``.
    """
    zero_promo = "P003"
    all_rows: list[np.ndarray] = []
    labels: list[int] = []
    promos: list[str] = []
    for i, promo in enumerate(PROMO_IDS):
        if promo == zero_promo:
            # All non-joiners: zero actual joiners in this held-out promo.
            all_rows.append(_rows(_PER_CLASS, loc=0.0, seed=100 + i))
            labels.extend([0] * _PER_CLASS)
            promos.extend([promo] * _PER_CLASS)
        else:
            all_rows.append(_rows(_PER_CLASS, loc=1.0, seed=2 * i))
            all_rows.append(_rows(_PER_CLASS, loc=-1.0, seed=2 * i + 1))
            labels.extend([1] * _PER_CLASS + [0] * _PER_CLASS)
            promos.extend([promo] * (2 * _PER_CLASS))

    x = pd.DataFrame(np.vstack(all_rows), columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    return x, y, promo_ids, zero_promo


def test_result_has_per_promo_entry_with_three_metric_fields():
    """One fold per P001/P002/P003, each exposing the three metric fields.

    _Requirements: 4.6_
    """
    x, y, promo_ids = _both_class_dataset()
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    # Exactly three folds, one per held-out promo.
    assert len(result.folds) == 3

    # The held-out promos present are exactly {P001, P002, P003}.
    present = {fold.promo_id for fold in result.folds}
    assert present == set(PROMO_IDS)

    # Every fold presents the three metrics separately (Requirement 4.6).
    for fold in result.folds:
        assert hasattr(fold, "roc_auc")
        assert hasattr(fold, "capture_rate_top_quintile")
        assert hasattr(fold, "calibration_table")
        # The calibration table is always a list (possibly empty).
        assert isinstance(fold.calibration_table, list)


def test_zero_joiner_heldout_promo_has_undefined_auc_and_capture():
    """A zero-joiner held-out promo leaves AUC/capture undefined; others report.

    The all-non-joiner P003 fold reports ``roc_auc`` and
    ``capture_rate_top_quintile`` as ``None`` (Requirement 4.5), while the
    P001 and P002 folds still have entries. Those two promos carry both
    classes, so their ROC_AUC is defined and bounded in [0, 1].

    _Requirements: 4.5_
    """
    x, y, promo_ids, zero_promo = _zero_joiner_dataset()
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    by_promo = {fold.promo_id: fold for fold in result.folds}

    # All three promos still have a fold entry (the run did not halt).
    assert set(by_promo) == set(PROMO_IDS)

    # The zero-joiner held-out promo has undefined AUC and capture, and zero
    # recorded joiners (Requirement 4.5).
    zero_fold = by_promo[zero_promo]
    assert zero_fold.joiners == 0
    assert zero_fold.roc_auc is None
    assert zero_fold.capture_rate_top_quintile is None

    # The other folds still report: both classes present, so ROC_AUC is defined
    # and bounded, and capture rate is defined (>= 1 joiner).
    for promo in PROMO_IDS:
        if promo == zero_promo:
            continue
        fold = by_promo[promo]
        assert fold.roc_auc is not None
        assert 0.0 <= fold.roc_auc <= 1.0
        assert fold.capture_rate_top_quintile is not None
        assert 0.0 <= fold.capture_rate_top_quintile <= 1.0
