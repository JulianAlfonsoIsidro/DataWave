"""Property-based test for Scores_File ordering.

# Feature: part1-optin, Property 19: Scores are ordered by promo_id then client_id

Covers Property 19 of the part1-optin spec: the Scores_File written by
:meth:`part1_optin.scoring.Scorer.write_scores` is ordered by ascending
``promo_id`` then ascending ``client_id`` (Requirement 6.5), regardless of the
order the leads arrive in.

The test fits a small two-class :class:`part1_optin.model.Calibrated_Model`
directly on a numeric X / y (a minimal :class:`part1_optin.features.FeatureSchema`
whose ``columns`` match ``X.columns`` is enough -- the full Feature_Assembler is
not needed to exercise the write-time ordering). It then builds a leads frame
with several unique ``(promo_id, client_id)`` pairs across the three promos in a
shuffled order plus a row-aligned feature matrix ``X_score`` carrying the same
columns, calls :meth:`Scorer.score_leads` + :meth:`Scorer.write_scores` to a
temporary CSV, reads the CSV back, and asserts the list of
``(promo_id, client_id)`` tuples equals its own ``sorted()`` -- i.e. the rows
are sorted ascending by ``promo_id`` then ``client_id``.

Fitting a real model per example is slow, so ``max_examples`` is kept small and
``deadline=None`` is set (each example fits a CalibratedClassifierCV with three
internal XGBoost folds plus a full-data booster, far slower than a pure-function
property, so a per-example deadline would flake). No path in this test references
a ``*_answer_key*`` file; the matrices, leads, and CSV are all generated in
memory / a tempfile.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import Config, PROMO_IDS
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer
from part1_optin.scoring import SCORE_COLUMNS, Scorer

# Feature column names for the generated matrices. A small fixed set keeps each
# fit cheap while still exercising a multi-feature calibrated model/SHAP.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Minimum examples per class. CalibratedClassifierCV uses a 3-fold
# StratifiedKFold internally, so each class needs at least three examples for
# every inner fold to see both classes.
_MIN_PER_CLASS = 3


@st.composite
def _fit_data(draw):
    """Draw a two-class fit matrix and labels for training the model.

    Builds a label vector with at least :data:`_MIN_PER_CLASS` zeros and
    :data:`_MIN_PER_CLASS` ones (so the internal ``cv=3`` calibration folds each
    see both classes) and a matching feature matrix with one row per label.
    Returns ``(X, y)``.
    """
    n_zero = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 2))
    n_one = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 2))
    labels = [0] * n_zero + [1] * n_one

    rows = draw(
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
            min_size=len(labels),
            max_size=len(labels),
        )
    )
    x = pd.DataFrame(rows, columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    return x, y


@st.composite
def _leads_and_features(draw):
    """Draw a shuffled leads frame and a row-aligned feature matrix.

    Generates a set of unique ``(promo_id, client_id)`` pairs across multiple
    promos (from :data:`PROMO_IDS`) with multiple clients per promo, then
    shuffles their order so ``promo_id`` / ``client_id`` ordering is exercised
    non-trivially. The companion ``X_score`` carries exactly ``_FEATURE_COLUMNS``
    with one row per lead, aligned positionally. Returns ``(leads, X_score)``.
    """
    # Pick 2-3 promos and 2-4 distinct clients per promo so there are several
    # rows to order and ties on promo_id are broken by client_id.
    n_promos = draw(st.integers(min_value=2, max_value=len(PROMO_IDS)))
    promos = PROMO_IDS[:n_promos]

    pairs: list[tuple[str, str]] = []
    for promo in promos:
        n_clients = draw(st.integers(min_value=2, max_value=4))
        client_ids = draw(
            st.lists(
                st.integers(min_value=1, max_value=9999),
                min_size=n_clients,
                max_size=n_clients,
                unique=True,
            )
        )
        for cid in client_ids:
            pairs.append((promo, f"C{cid:04d}"))

    # Shuffle so the input order is non-trivial (not already sorted).
    pairs = draw(st.permutations(pairs))

    leads = pd.DataFrame(pairs, columns=["promo_id", "client_id"])

    n_rows = len(leads)
    feature_rows = draw(
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
    x_score = pd.DataFrame(feature_rows, columns=_FEATURE_COLUMNS)
    return leads, x_score


@settings(
    max_examples=10,
    deadline=None,  # each example fits a real calibrated model + booster
    suppress_health_check=[HealthCheck.too_slow],
)
@given(fit=_fit_data(), scoring=_leads_and_features())
def test_scores_are_ordered_by_promo_then_client(fit, scoring):
    """Scores are ordered by promo_id then client_id.

    **Validates: Requirements 6.5**

    Fit a small two-class calibrated model, score a shuffled multi-promo /
    multi-client leads frame, write the Scores_File to a tempfile, read it back,
    and assert the list of ``(promo_id, client_id)`` tuples equals its own
    ``sorted()`` -- i.e. ascending by ``promo_id`` then ``client_id``.
    """
    x_fit, y_fit = fit
    leads, x_score = scoring

    # Minimal schema whose columns match the generated matrices. The full
    # Feature_Assembler is not needed to exercise write-time ordering.
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    config = Config()
    model = Model_Trainer(config).fit(x_fit, y_fit, schema)

    scorer = Scorer(model, config)
    scored = scorer.score_leads(leads, x_score)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "scores.csv"
        scorer.write_scores(scored, out_path)

        written = pd.read_csv(out_path)

        # Header is the fixed six columns, so the identity columns are present.
        assert list(written.columns) == SCORE_COLUMNS

        # client_id may read back as int/str depending on values; compare as
        # strings so the ordering check is on stable, comparable keys.
        tuples = [
            (str(promo), str(client))
            for promo, client in zip(written["promo_id"], written["client_id"])
        ]

    # The rows must already be ascending by promo_id then client_id.
    assert tuples == sorted(tuples)
