"""Property-based test for ROC_AUC bounds in LOPO validation.

# Feature: part1-optin, Property 13: ROC_AUC is bounded when defined

Covers Property 13 of the part1-optin spec: every fold of
:meth:`part1_optin.validation.Validator.run` that reports a ``roc_auc`` (i.e.
the held-out promo contained both a joiner and a non-joiner) reports it as a
value in the inclusive range ``[0, 1]``, and a fold whose held-out promo lacks
both classes (all joiners, all non-joiners, or zero joiners) reports
``roc_auc`` as ``None`` (Requirements 4.2, 4.5).

``roc_auc`` is produced by ``sklearn.metrics.roc_auc_score`` on calibrated
probabilities clipped to ``[0, 1]``, so a defined value is mathematically in
``[0, 1]``; the Validator only computes it when ``0 < joiners < n`` for the
held-out promo, so a single-class held-out fold is ``None`` by construction.

This test runs the real Validator, which fits three LOPO folds and each fold
fits a ``CalibratedClassifierCV`` (three internal XGBoost folds) plus a
full-data booster. That is far slower than a pure-function property, so it keeps
``max_examples`` small and sets ``deadline=None`` -- a per-example deadline would
flake on the fit cost.

The data is constructed directly -- a numeric feature matrix, a Join_Label
vector, and a ``promo_ids`` Series over P001/P002/P003 -- rather than going
through the full Feature_Assembler. Because each LOPO fold trains on the two
*other* promos combined and ``CalibratedClassifierCV`` uses an internal 3-fold
``StratifiedKFold``, every promo is given at least :data:`_MIN_PER_CLASS_PER_PROMO`
joiners and the same number of non-joiners, so any two-promo training subset has
enough of each class for the inner folds to fit. A :class:`FeatureSchema` whose
``columns`` match the generated matrix is built directly. No path in this test
references a ``*_answer_key*`` file; the matrices are generated in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import PROMO_IDS, Config
from part1_optin.features import FeatureSchema
from part1_optin.validation import Validator

# Feature column names for the generated matrix. A small fixed set keeps each
# per-fold fit cheap while still exercising a multi-feature calibrated model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Minimum joiners (and non-joiners) per promo. Each LOPO fold trains on two
# promos combined and CalibratedClassifierCV uses a 3-fold StratifiedKFold, so
# each class needs at least three examples in the two-promo training subset;
# with 2 per class per promo, any two-promo union has >= 4 of each class.
_MIN_PER_CLASS_PER_PROMO = 2


@st.composite
def _feature_rows(draw, n_rows: int) -> list[list[float]]:
    """Draw ``n_rows`` rows of finite floats over ``_FEATURE_COLUMNS``.

    Values are finite and bounded so XGBoost fits without NaNs or infinities
    derailing the trees.
    """
    return draw(
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


@st.composite
def _two_class_dataset(draw):
    """Draw X, y, promo_ids where every promo has both classes.

    Each of P001/P002/P003 gets at least :data:`_MIN_PER_CLASS_PER_PROMO`
    joiners and the same number of non-joiners, so every two-promo LOPO training
    subset can fit the calibrated model and every held-out promo has both
    classes (so every fold defines ``roc_auc``). Returns ``(X, y, promo_ids)``.
    """
    labels: list[int] = []
    promos: list[str] = []
    for promo in PROMO_IDS:
        n_one = draw(
            st.integers(
                min_value=_MIN_PER_CLASS_PER_PROMO,
                max_value=_MIN_PER_CLASS_PER_PROMO + 2,
            )
        )
        n_zero = draw(
            st.integers(
                min_value=_MIN_PER_CLASS_PER_PROMO,
                max_value=_MIN_PER_CLASS_PER_PROMO + 2,
            )
        )
        labels.extend([1] * n_one + [0] * n_zero)
        promos.extend([promo] * (n_one + n_zero))

    rows = draw(_feature_rows(len(labels)))
    x = pd.DataFrame(rows, columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    return x, y, promo_ids


@st.composite
def _single_class_heldout_dataset(draw):
    """Draw a dataset where one promo is single-class (no defined ROC_AUC).

    Two promos carry both classes (so they can serve as the training subset for
    the single-class fold). The third promo is made entirely one class -- either
    all joiners or all non-joiners -- so when it is held out its ``roc_auc`` must
    be ``None`` (Requirement 4.5). Returns ``(X, y, promo_ids, single_promo)``.
    """
    single_promo = draw(st.sampled_from(PROMO_IDS))
    all_joiners = draw(st.booleans())

    labels: list[int] = []
    promos: list[str] = []
    for promo in PROMO_IDS:
        if promo == single_promo:
            # One class only: all joiners or all non-joiners. Give enough rows
            # that ceil(0.20 * N) and binning are exercised.
            single_label = 1 if all_joiners else 0
            n_single = draw(st.integers(min_value=3, max_value=6))
            labels.extend([single_label] * n_single)
            promos.extend([promo] * n_single)
        else:
            # Both classes, enough per class for the inner 3-fold calibration CV
            # when this promo is part of a two-promo training subset.
            n_one = draw(
                st.integers(
                    min_value=_MIN_PER_CLASS_PER_PROMO,
                    max_value=_MIN_PER_CLASS_PER_PROMO + 2,
                )
            )
            n_zero = draw(
                st.integers(
                    min_value=_MIN_PER_CLASS_PER_PROMO,
                    max_value=_MIN_PER_CLASS_PER_PROMO + 2,
                )
            )
            labels.extend([1] * n_one + [0] * n_zero)
            promos.extend([promo] * (n_one + n_zero))

    rows = draw(_feature_rows(len(labels)))
    x = pd.DataFrame(rows, columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    return x, y, promo_ids, single_promo


@settings(
    max_examples=8,
    deadline=None,  # each example fits 3 LOPO folds; a deadline would flake.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_two_class_dataset())
def test_roc_auc_is_bounded_when_defined(data):
    """ROC_AUC is in [0, 1] for every fold that defines it.

    **Validates: Requirements 4.2**

    Run the Validator on data where every held-out promo has both a joiner and a
    non-joiner, then assert each fold's ``roc_auc`` is defined and lies in the
    inclusive range ``[0, 1]``.
    """
    x, y, promo_ids = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    for fold in result.folds:
        if fold.roc_auc is not None:
            assert 0.0 <= fold.roc_auc <= 1.0, (
                f"roc_auc out of bounds for held-out {fold.promo_id}: "
                f"{fold.roc_auc}"
            )


@settings(
    max_examples=8,
    deadline=None,  # each example fits 3 LOPO folds; a deadline would flake.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_single_class_heldout_dataset())
def test_roc_auc_is_none_when_heldout_lacks_both_classes(data):
    """ROC_AUC is None for a held-out promo that lacks both classes.

    **Validates: Requirements 4.2**

    When a held-out promo is all joiners or all non-joiners (including the
    zero-joiner case), the Validator leaves its ``roc_auc`` undefined
    (Requirement 4.5). Every other fold that does define ``roc_auc`` stays in
    ``[0, 1]``.
    """
    x, y, promo_ids, single_promo = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    by_promo = {fold.promo_id: fold for fold in result.folds}
    assert by_promo[single_promo].roc_auc is None, (
        f"single-class held-out {single_promo} should have roc_auc None, "
        f"got {by_promo[single_promo].roc_auc}"
    )

    for fold in result.folds:
        if fold.roc_auc is not None:
            assert 0.0 <= fold.roc_auc <= 1.0
