"""Property-based test for stratified AUC and capture bounds (Requirement 8).

# Feature: part1-optin, Property 22: Stratified AUC and capture are bounded when defined

Covers Property 22 of the part1-optin spec: whenever the headline
StratifiedGroupKFold scheme
(:meth:`part1_optin.validation.Validator.run_stratified`) reports an
``overall_auc``, an ``overall_capture_rate_top_quintile``, a
``per_promo_auc[promo]``, or a ``per_promo_capture[promo]`` that is *defined*
(not ``None``), that value lies in the inclusive range ``[0, 1]``
(Requirements 8.4, 8.5). An undefined slice -- a pooled or per-promo slice that
lacks both classes (for AUC) or has no joiners (for capture), or a promo whose
leads all fell in folds that could not be trained -- yields ``None`` without
halting the rest of the reporting (Requirement 8.7), so every promo in
:data:`~part1_optin.config.PROMO_IDS` still has an entry in both per-promo
dicts.

The stratified AUC comes from ``sklearn.metrics.roc_auc_score`` on out-of-fold
probabilities clipped to ``[0, 1]``, and the capture rate is joiners-in-top over
total joiners, so any defined value is mathematically in ``[0, 1]``; the
Validator only computes AUC when a slice has both classes and capture when a
slice has at least one joiner, so an undefined slice is ``None`` by
construction. This test exercises that invariant end-to-end against the real
Validator rather than re-deriving the arithmetic, so it is a bounds property,
not a reduction.

``run_stratified`` uses ``StratifiedGroupKFold(n_splits=5)`` with
``groups=client_ids`` and ``y=Join_Label``, so it needs at least five distinct
client groups and each outer training fold must carry enough of both classes for
the inner ``cv=3`` ``StratifiedKFold`` calibration folds to each see both
classes. The data is therefore generated directly as a numeric feature matrix, a
balanced Join_Label vector, a ``promo_ids`` Series over P001/P002/P003, and a
``client_ids`` Series of one lead per client (so every client is its own group
and no client straddles a fold). With a comfortable number of joiners and
non-joiners spread across many single-lead clients, every 4/5 training split
keeps both classes well above the ``cv=3`` floor.

Running the real Validator fits five StratifiedGroupKFold folds per example and
each fold fits a ``CalibratedClassifierCV`` (three internal XGBoost folds) plus a
full-data booster, which is far slower than a pure-function property, so
``max_examples`` is kept small and ``deadline=None`` -- a per-example deadline
would flake on the fit cost. No path in this test references a ``*_answer_key*``
file; the matrices are generated in memory.
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

# Leads per class, per promo. StratifiedGroupKFold(n_splits=5) holds out ~1/5 of
# the leads per fold, so each 4/5 training split retains ~0.8 of each class;
# with this floor every promo contributes enough joiners and non-joiners that
# both the 5 outer folds and the inner cv=3 calibration folds always see both
# classes, so no fold trips Model_Trainer's single-class guard.
_PER_CLASS_PER_PROMO = 8


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
def _stratified_dataset(draw):
    """Draw X, y, promo_ids, client_ids where every promo has both classes.

    Each of P001/P002/P003 gets at least :data:`_PER_CLASS_PER_PROMO` joiners
    and the same number of non-joiners, so the pooled out-of-fold vector and
    every per-promo slice carry both classes (so every reported AUC/capture is
    defined) and every StratifiedGroupKFold training split clears the inner
    ``cv=3`` floor. Each lead is given a unique ``client_id`` so every client is
    its own single-lead group -- there are far more than the five groups
    ``StratifiedGroupKFold(n_splits=5)`` requires, and no client straddles a
    fold. Returns ``(X, y, promo_ids, client_ids)``.
    """
    labels: list[int] = []
    promos: list[str] = []
    for promo in PROMO_IDS:
        n_one = draw(
            st.integers(
                min_value=_PER_CLASS_PER_PROMO,
                max_value=_PER_CLASS_PER_PROMO + 4,
            )
        )
        n_zero = draw(
            st.integers(
                min_value=_PER_CLASS_PER_PROMO,
                max_value=_PER_CLASS_PER_PROMO + 4,
            )
        )
        labels.extend([1] * n_one + [0] * n_zero)
        promos.extend([promo] * (n_one + n_zero))

    rows = draw(_feature_rows(len(labels)))
    x = pd.DataFrame(rows, columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    # One lead per client: a unique, zero-padded client id per row so every
    # client is its own group for StratifiedGroupKFold.
    client_ids = pd.Series(
        [f"C{i:06d}" for i in range(len(labels))], name="client_id"
    )
    return x, y, promo_ids, client_ids


@st.composite
def _single_class_promo_dataset(draw):
    """Draw a dataset where one promo's slice lacks both classes.

    Two promos carry both classes with a comfortable per-class floor; the third
    promo is made entirely one class -- all joiners or all non-joiners. When the
    out-of-fold vector is sliced to that promo it lacks both classes, so its
    ``per_promo_auc`` must be ``None`` (Requirement 8.7) while the overall and
    other per-promo metrics still report. Every lead gets a unique single-lead
    ``client_id``. Returns ``(X, y, promo_ids, client_ids, single_promo)``.
    """
    single_promo = draw(st.sampled_from(PROMO_IDS))
    all_joiners = draw(st.booleans())

    labels: list[int] = []
    promos: list[str] = []
    for promo in PROMO_IDS:
        if promo == single_promo:
            # One class only for this promo so its slice lacks both classes.
            single_label = 1 if all_joiners else 0
            n_single = draw(
                st.integers(
                    min_value=_PER_CLASS_PER_PROMO,
                    max_value=_PER_CLASS_PER_PROMO + 4,
                )
            )
            labels.extend([single_label] * n_single)
            promos.extend([promo] * n_single)
        else:
            n_one = draw(
                st.integers(
                    min_value=_PER_CLASS_PER_PROMO,
                    max_value=_PER_CLASS_PER_PROMO + 4,
                )
            )
            n_zero = draw(
                st.integers(
                    min_value=_PER_CLASS_PER_PROMO,
                    max_value=_PER_CLASS_PER_PROMO + 4,
                )
            )
            labels.extend([1] * n_one + [0] * n_zero)
            promos.extend([promo] * (n_one + n_zero))

    rows = draw(_feature_rows(len(labels)))
    x = pd.DataFrame(rows, columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    client_ids = pd.Series(
        [f"C{i:06d}" for i in range(len(labels))], name="client_id"
    )
    return x, y, promo_ids, client_ids, single_promo


def _assert_bounded_or_none(value, label: str) -> None:
    """Assert ``value`` is either ``None`` or a float in ``[0, 1]``."""
    if value is not None:
        assert 0.0 <= value <= 1.0, f"{label} out of bounds: {value}"


@settings(
    max_examples=8,
    deadline=None,  # each example fits 5 StratifiedGroupKFold folds; a
    # per-example deadline would flake on the fit cost.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_stratified_dataset())
def test_stratified_auc_and_capture_bounded_when_defined(data):
    """Overall and per-promo stratified AUC/capture are in [0, 1] when defined.

    **Validates: Requirements 8.4, 8.5, 8.7**

    Run the headline StratifiedGroupKFold scheme on data where every promo
    carries both classes, then assert every defined metric -- the overall AUC
    and capture, and each promo's AUC and capture -- lies in the inclusive range
    ``[0, 1]``. Both per-promo dicts cover every promo in ``PROMO_IDS`` (an
    undefined slice would be ``None``, not a missing key), confirming undefined
    slices never halt the reporting (Requirement 8.7).
    """
    x, y, promo_ids, client_ids = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run_stratified(
        x, y, promo_ids, client_ids, schema
    )

    _assert_bounded_or_none(result.overall_auc, "overall_auc")
    _assert_bounded_or_none(
        result.overall_capture_rate_top_quintile,
        "overall_capture_rate_top_quintile",
    )

    # Every promo has an entry in both per-promo dicts; an undefined slice is
    # recorded as None rather than dropped (Requirement 8.7).
    assert set(result.per_promo_auc) == set(PROMO_IDS)
    assert set(result.per_promo_capture) == set(PROMO_IDS)

    for promo in PROMO_IDS:
        _assert_bounded_or_none(
            result.per_promo_auc[promo], f"per_promo_auc[{promo}]"
        )
        _assert_bounded_or_none(
            result.per_promo_capture[promo], f"per_promo_capture[{promo}]"
        )


@settings(
    max_examples=6,
    deadline=None,  # each example fits 5 StratifiedGroupKFold folds; a
    # per-example deadline would flake on the fit cost.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_single_class_promo_dataset())
def test_single_class_promo_slice_yields_none_without_halting(data):
    """A single-class promo slice yields None AUC without halting reporting.

    **Validates: Requirements 8.4, 8.7**

    When one promo's out-of-fold slice lacks both classes, its
    ``per_promo_auc`` is ``None`` (ROC_AUC is undefined for a single-class
    slice), yet the overall metrics and the other promos' metrics still report
    and stay in ``[0, 1]`` -- the undefined slice does not halt the rest of the
    reporting (Requirement 8.7). Every promo still has an entry in both
    per-promo dicts.
    """
    x, y, promo_ids, client_ids, single_promo = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run_stratified(
        x, y, promo_ids, client_ids, schema
    )

    assert result.per_promo_auc[single_promo] is None, (
        f"single-class promo {single_promo} slice should have None AUC, "
        f"got {result.per_promo_auc[single_promo]}"
    )

    # The reporting was not halted: every promo still has an entry and every
    # defined metric is bounded.
    assert set(result.per_promo_auc) == set(PROMO_IDS)
    assert set(result.per_promo_capture) == set(PROMO_IDS)

    _assert_bounded_or_none(result.overall_auc, "overall_auc")
    _assert_bounded_or_none(
        result.overall_capture_rate_top_quintile,
        "overall_capture_rate_top_quintile",
    )
    for promo in PROMO_IDS:
        _assert_bounded_or_none(
            result.per_promo_auc[promo], f"per_promo_auc[{promo}]"
        )
        _assert_bounded_or_none(
            result.per_promo_capture[promo], f"per_promo_capture[{promo}]"
        )
