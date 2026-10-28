"""Property-based test for Capture_Rate_Top_Quintile in LOPO validation.

# Feature: part1-optin, Property 14: Capture rate matches the cutoff/tie definition and is bounded

Covers Property 14 of the part1-optin spec: for every LOPO fold of
:meth:`part1_optin.validation.Validator.run` whose held-out promo contains at
least one joiner, the reported ``capture_rate_top_quintile`` is (a) in the
inclusive range ``[0, 1]`` and (b) exactly equal to an INDEPENDENT reference
recompute of the capture-rate definition (Requirement 4.3). A held-out promo
with zero joiners reports ``capture_rate_top_quintile`` as ``None``
(Requirement 4.5).

This is a reduction property, so it asserts against a from-scratch reference
rather than re-deriving the Validator's own arithmetic. The capture-rate
definition under test (Requirement 4.3):

- cutoff position = ``ceil(0.20 * N)`` for ``N`` held-out leads (clamped to
  ``[1, N]``),
- sort predicted probabilities descending; the threshold is the probability at
  the cutoff position (1-based rank),
- every lead whose predicted probability is ``>=`` that threshold is "in the
  top quintile" (boundary ties all count),
- capture rate = (# joiners in the top quintile) / (total joiners).

The challenge: ``Validator.run`` does not expose the per-lead probabilities it
used, and the reference needs them. We reproduce them independently. Each LOPO
fold fits a fresh ``Model_Trainer`` on exactly the rows whose promo is NOT the
held-out promo (``train = rows where promo != held_out``) and predicts the
held-out rows. Because :data:`~part1_optin.config.RANDOM_SEED` makes both the
``XGBClassifier`` estimators and the inner ``StratifiedKFold`` deterministic, an
independent re-fit of the same ``Model_Trainer`` on the same two-promo training
split, predicting the same held-out rows, yields the IDENTICAL probabilities the
Validator used. We then apply the capture-rate definition to those probabilities
ourselves and compare to ``fold.capture_rate_top_quintile``.

Running the real Validator fits three LOPO folds per example and each fold fits
a ``CalibratedClassifierCV`` (three internal XGBoost folds) plus a full-data
booster; the reference re-fits those folds again. That is far slower than a
pure-function property, so ``max_examples`` is kept small and ``deadline=None``
-- a per-example deadline would flake on the fit cost. This test needs no pytest
fixture, so ``@given`` is used plainly. No path in this test references a
``*_answer_key*`` file; the matrices are generated in memory.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import PROMO_IDS, TOP_QUINTILE, Config
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer
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
    joiners and the same count of non-joiners, so every two-promo LOPO training
    subset can fit the calibrated model and every held-out promo has at least
    one joiner (so every fold defines ``capture_rate_top_quintile``). Returns
    ``(X, y, promo_ids)``.
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
def _zero_joiner_heldout_dataset(draw):
    """Draw a dataset where one promo has zero joiners (undefined capture).

    Two promos carry both classes (so they can serve as the training subset for
    the zero-joiner fold). The third promo is made entirely non-joiners, so when
    it is held out its ``capture_rate_top_quintile`` must be ``None``
    (Requirement 4.5). Returns ``(X, y, promo_ids, zero_promo)``.
    """
    zero_promo = draw(st.sampled_from(PROMO_IDS))

    labels: list[int] = []
    promos: list[str] = []
    for promo in PROMO_IDS:
        if promo == zero_promo:
            # Zero joiners: all non-joiners. Enough rows that ceil(0.20 * N)
            # and the top-quintile cutoff would be exercised if it ran.
            n_zero = draw(st.integers(min_value=3, max_value=6))
            labels.extend([0] * n_zero)
            promos.extend([promo] * n_zero)
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
    return x, y, promo_ids, zero_promo


def _reference_capture_rate(probs: np.ndarray, labels: np.ndarray) -> float:
    """Independent from-scratch recompute of the capture-rate definition.

    Deliberately re-derives Requirement 4.3 without reusing the Validator's
    helper: cutoff position ``ceil(0.20 * N)`` clamped to ``[1, N]``; the
    threshold is the probability at that 1-based rank in descending order; every
    lead with ``prob >= threshold`` is in the top quintile (boundary ties
    included); the rate is joiners-in-top over total joiners.

    Callers guarantee at least one joiner.
    """
    n = len(probs)
    total_joiners = int(labels.sum())

    cutoff_pos = max(1, math.ceil(TOP_QUINTILE * n))
    cutoff_pos = min(cutoff_pos, n)

    descending = sorted(probs, reverse=True)
    threshold = descending[cutoff_pos - 1]

    joiners_in_top = int(
        sum(
            1
            for prob, label in zip(probs, labels)
            if prob >= threshold and label == 1
        )
    )
    return joiners_in_top / total_joiners


def _independent_fold_probs(
    X: pd.DataFrame,
    y: pd.Series,
    promo_ids: pd.Series,
    schema: FeatureSchema,
    held_out: str,
) -> np.ndarray:
    """Re-derive the held-out fold's predicted probabilities independently.

    Rebuilds exactly the two-promo training split the Validator uses
    (``train = rows where promo != held_out``), fits a fresh ``Model_Trainer``
    on it, and predicts the held-out rows. The fixed ``RANDOM_SEED`` makes the
    fit deterministic, so these probabilities are identical to the ones the
    Validator computed for this fold. Indices are reset the same way
    ``Validator.run`` resets them so the positional masks line up.
    """
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y)).reset_index(drop=True)
    promo_ids = pd.Series(np.asarray(promo_ids)).reset_index(drop=True)

    held_mask = (promo_ids == held_out).to_numpy()
    train_mask = ~held_mask

    model = Model_Trainer(Config()).fit(
        X.loc[train_mask], y.loc[train_mask], schema
    )
    return np.asarray(model.predict_proba(X.loc[held_mask]), dtype=float)


@settings(
    max_examples=6,
    deadline=None,  # each example fits 3 LOPO folds twice; a deadline flakes.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_two_class_dataset())
def test_capture_rate_matches_definition_and_is_bounded(data):
    """Capture rate is in [0, 1] and equals the independent recompute.

    **Validates: Requirements 4.3**

    Run the Validator on data where every held-out promo has at least one
    joiner, then for each fold assert ``capture_rate_top_quintile`` is defined,
    lies in ``[0, 1]``, and equals a from-scratch reference recompute built from
    an independent deterministic re-fit of the same two-promo training split.
    """
    x, y, promo_ids = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    x_reset = x.reset_index(drop=True)
    y_reset = pd.Series(np.asarray(y)).reset_index(drop=True)
    promo_reset = pd.Series(np.asarray(promo_ids)).reset_index(drop=True)

    for fold in result.folds:
        assert fold.capture_rate_top_quintile is not None, (
            f"held-out {fold.promo_id} has joiners but capture is None"
        )
        assert 0.0 <= fold.capture_rate_top_quintile <= 1.0, (
            f"capture out of bounds for held-out {fold.promo_id}: "
            f"{fold.capture_rate_top_quintile}"
        )

        # Independent recompute: re-fit the same two-promo split (deterministic
        # under RANDOM_SEED), predict the held-out rows, apply the definition.
        held_mask = (promo_reset == fold.promo_id).to_numpy()
        probs = _independent_fold_probs(
            x_reset, y_reset, promo_reset, schema, fold.promo_id
        )
        labels = y_reset.loc[held_mask].to_numpy().astype(int)
        expected = _reference_capture_rate(probs, labels)

        assert fold.capture_rate_top_quintile == pytest.approx(expected), (
            f"capture mismatch for held-out {fold.promo_id}: "
            f"validator={fold.capture_rate_top_quintile} reference={expected}"
        )


@settings(
    max_examples=6,
    deadline=None,  # each example fits 3 LOPO folds; a deadline would flake.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_zero_joiner_heldout_dataset())
def test_capture_rate_is_none_when_heldout_has_zero_joiners(data):
    """Capture rate is None for a held-out promo with zero joiners.

    **Validates: Requirements 4.3**

    When a held-out promo has no actual joiners, the Validator leaves its
    ``capture_rate_top_quintile`` undefined (Requirement 4.5). Every other fold
    that does define a capture rate stays in ``[0, 1]``.
    """
    x, y, promo_ids, zero_promo = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    by_promo = {fold.promo_id: fold for fold in result.folds}
    assert by_promo[zero_promo].capture_rate_top_quintile is None, (
        f"zero-joiner held-out {zero_promo} should have capture None, "
        f"got {by_promo[zero_promo].capture_rate_top_quintile}"
    )

    for fold in result.folds:
        if fold.capture_rate_top_quintile is not None:
            assert 0.0 <= fold.capture_rate_top_quintile <= 1.0
