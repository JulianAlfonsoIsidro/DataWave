"""Property-based test for leave-one-promo-out (LOPO) leakage.

# Feature: part1-optin, Property 11: Leave-one-promo-out fitting never touches the held-out promo

Covers Property 11 of the part1-optin spec: in each LOPO fold the
``Model_Trainer`` is fit on only the *other two* promos' leads, and the
held-out promo's leads never enter the fit -- neither the outer classifier nor
the inner isotonic calibration CV (Requirements 3.3, 3.4, 4.1).

Verification strategy (a spy on the trainer fit):

- Each promo's rows carry a UNIQUE sentinel value in a ``promo_marker`` feature
  column: ``1`` for P001 rows, ``2`` for P002, ``3`` for P003. The marker is a
  real column in the feature matrix ``X``, so it travels through the
  Validator's internal index reset and positional train/held-out masking
  untouched.
- ``part1_optin.validation.Model_Trainer`` is monkeypatched with a wrapper
  whose ``fit(X, y, schema)`` records ``set(X["promo_marker"].unique())`` into a
  per-fold list, then delegates to the real ``Model_Trainer.fit``.
- The Validator holds each promo out exactly once in ``PROMO_IDS`` order, so the
  k-th recorded training-marker set belongs to the fold that holds out the k-th
  promo. For that fold the held-out promo's sentinel must be absent from the
  recorded training markers, and the two training promos' sentinels must be
  present.

Each two-promo training subset is made 2-class (every promo gets both joiners
and non-joiners, at least three of each per class across the two training
promos) so the internal ``CalibratedClassifierCV(cv=3)`` fit does not raise and
every fold actually trains, exercising the leakage guarantee rather than the
undefined-metric fallback.

No path in this test references a ``*_answer_key*`` file; nothing is read from
disk at all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import part1_optin.validation as validation
from part1_optin.config import Config, PROMO_IDS
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer as _Real_Model_Trainer
from part1_optin.validation import Validator

# Sentinel marker value per promo: P001 -> 1, P002 -> 2, P003 -> 3. The marker
# uniquely identifies which promo each training row came from so a fold's
# recorded training markers reveal exactly which promos it trained on.
_PROMO_MARKER = {promo: idx + 1 for idx, promo in enumerate(PROMO_IDS)}

# Each promo contributes at least this many joiners and this many non-joiners.
# With this floor every two-promo training subset has >=6 of each class, enough
# for the internal cv=3 stratified calibration folds to each see both classes
# so Model_Trainer.fit never raises the single-class guard.
_MIN_PER_CLASS_PER_PROMO = 3

# A couple of ordinary numeric feature columns beside the sentinel marker, so
# the booster/calibrator have real signal to fit on. Their values are
# irrelevant to the leakage property.
_N_FEATURES = 3


@st.composite
def lopo_dataset(draw):
    """Draw X/y/promo_ids covering all three promos, each 2-class.

    For each promo in :data:`part1_optin.config.PROMO_IDS` the strategy draws a
    joiner count and a non-joiner count, each at least
    :data:`_MIN_PER_CLASS_PER_PROMO`, and emits that many rows tagged with the
    promo's id, its ``Join_Label``, and its unique ``promo_marker`` sentinel.
    Row counts per promo stay modest because each fold fits XGBoost models.

    ``X`` carries ``_N_FEATURES`` ordinary numeric columns plus the
    ``promo_marker`` column; ``y`` is the aligned ``Join_Label``; ``promo_ids``
    is the aligned per-row promo id. The three series share one positional index
    after the Validator resets it internally.
    """
    markers: list[int] = []
    promo_id_values: list[str] = []
    y_values: list[int] = []

    for promo in PROMO_IDS:
        n_pos = draw(
            st.integers(min_value=_MIN_PER_CLASS_PER_PROMO, max_value=6)
        )
        n_neg = draw(
            st.integers(min_value=_MIN_PER_CLASS_PER_PROMO, max_value=6)
        )
        for _ in range(n_pos):
            promo_id_values.append(promo)
            y_values.append(1)
            markers.append(_PROMO_MARKER[promo])
        for _ in range(n_neg):
            promo_id_values.append(promo)
            y_values.append(0)
            markers.append(_PROMO_MARKER[promo])

    n_rows = len(y_values)

    cell = st.floats(
        min_value=-1000.0,
        max_value=1000.0,
        allow_nan=False,
        allow_infinity=False,
    )
    feature_rows = draw(
        st.lists(
            st.lists(cell, min_size=_N_FEATURES, max_size=_N_FEATURES),
            min_size=n_rows,
            max_size=n_rows,
        )
    )

    feature_columns = [f"f{i}" for i in range(_N_FEATURES)]
    X = pd.DataFrame(feature_rows, columns=feature_columns, dtype=float)
    # The sentinel marker is a genuine feature column so it rides along through
    # the Validator's index reset and positional masking.
    X["promo_marker"] = markers

    y = pd.Series(y_values, name="Join_Label")
    promo_ids = pd.Series(promo_id_values, name="promo_id")
    return X, y, promo_ids


# max_examples kept small: EACH example fits the calibrated model (three
# internal cv folds) plus a full-data booster once per LOPO fold -- three folds
# per example -- so model fitting dominates runtime. deadline=None because a
# single fold's fits comfortably exceed Hypothesis's default per-example
# deadline.
@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        # monkeypatch is function-scoped and not reset between generated
        # inputs, but this test re-patches to the same stable spy and builds a
        # fresh per-invocation record list, so it is correct regardless.
        HealthCheck.function_scoped_fixture,
    ],
)
@given(data=lopo_dataset())
def test_lopo_fitting_never_touches_held_out_promo(data, monkeypatch):
    """LOPO fitting never touches the held-out promo.

    **Validates: Requirements 3.3, 3.4, 4.1**

    Each fold's training matrix, spied on via the unique ``promo_marker``
    sentinel, must exclude the held-out promo's marker and include exactly the
    two training promos' markers.
    """
    X, y, promo_ids = data

    # Per-fold record of the promo markers present in the training matrix handed
    # to Model_Trainer.fit. The Validator holds promos out in PROMO_IDS order,
    # so the k-th entry corresponds to holding out PROMO_IDS[k].
    recorded_training_markers: list[set[int]] = []

    class SpyModelTrainer:
        """Wrapper recording training markers, then delegating to the real fit.

        Mirrors ``Model_Trainer``'s constructor and ``fit`` signature so the
        Validator uses it transparently. ``fit`` records the set of
        ``promo_marker`` sentinels in the training ``X`` -- revealing which
        promos the fold trained on -- before delegating to the genuine
        :class:`part1_optin.model.Model_Trainer`.
        """

        def __init__(self, config: Config) -> None:
            self._real = _Real_Model_Trainer(config)

        def fit(self, X_train, y_train, schema):
            recorded_training_markers.append(
                set(int(m) for m in X_train["promo_marker"].unique())
            )
            return self._real.fit(X_train, y_train, schema)

    # Patch the name the Validator resolves inside validation.py.
    monkeypatch.setattr(validation, "Model_Trainer", SpyModelTrainer)

    schema = FeatureSchema(columns=list(X.columns))
    Validator(Config()).run(X, y, promo_ids, schema)

    # Every fold actually trained (2-class training subsets guaranteed), so one
    # recorded training-marker set per held-out promo, in PROMO_IDS order.
    assert len(recorded_training_markers) == len(PROMO_IDS)

    for held_out, training_markers in zip(PROMO_IDS, recorded_training_markers):
        held_marker = _PROMO_MARKER[held_out]
        expected_training = {
            _PROMO_MARKER[p] for p in PROMO_IDS if p != held_out
        }

        # The held-out promo's leads never entered the fit (Requirements 3.3,
        # 3.4, 4.1): its sentinel is absent from the training markers.
        assert held_marker not in training_markers

        # The fold trained on exactly the other two promos' leads.
        assert training_markers == expected_training
