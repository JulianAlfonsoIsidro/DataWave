"""Property-based test for one scores row per treated lead.

# Feature: part1-optin, Property 20: Exactly one scores row per treated lead

Covers Property 20 of the part1-optin spec: the Scorer writes exactly one
Scores_File row per treated lead (Requirement 6.6). Given ``N`` treated leads
with distinct ``(promo_id, client_id)`` identities,
:meth:`part1_optin.scoring.Scorer.score_leads` followed by
:meth:`part1_optin.scoring.Scorer.write_scores` must produce a CSV whose data
rows number exactly ``N``, with each ``(promo_id, client_id)`` appearing
exactly once.

This property is about scoring cardinality, not feature assembly, so the test
feeds the trainer a small numeric feature matrix ``X`` built directly (no
Feature_Assembler) paired with a trivially constructed
:class:`part1_optin.features.FeatureSchema` whose ``columns`` match
``X.columns``. The model is fit on a generated two-class training set (at least
three examples of each class so the internal ``cv=3`` calibration folds each see
both classes); the SCORING step then builds ``N`` leads with unique
``(promo_id, client_id)`` pairs and reuses a generated feature matrix
``X_score`` with the same columns as the model schema and ``N`` rows, row
aligned with the leads.

No path in this test references a ``*_answer_key*`` file; the only disk access
is a Python ``tempfile`` directory created inside the test body (Hypothesis
cannot use function-scoped fixtures per example), which is cleaned up before the
test returns.
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

# Minimum per-class examples so each of the cv=3 calibration folds can contain
# both classes (design: "callers provide at least three minority-class
# examples"). We keep this at 3 for both classes in the TRAINING set.
_MIN_PER_CLASS = 3

# A modest fixed number of feature columns. This property is about scoring
# cardinality, not feature content, so a small numeric matrix is enough and
# keeps model fitting fast.
_N_FEATURES = 4


@st.composite
def model_training_data(draw):
    """Draw a small numeric ``X`` and a two-class ``y`` with >=3 of each class.

    Rows are kept modest because each generated example fits XGBoost models,
    which is slow. ``y`` is built with a positive count and a negative count,
    each at least :data:`_MIN_PER_CLASS`, so both classes are present with
    enough minority-class examples for the internal ``cv=3`` stratified
    calibration folds. ``X`` is a dense numeric matrix whose columns are named
    ``f0..f{n-1}``.
    """
    n_pos = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=12))
    n_neg = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=12))
    n_rows = n_pos + n_neg

    y_values = [1] * n_pos + [0] * n_neg

    cell = st.floats(
        min_value=-1000.0,
        max_value=1000.0,
        allow_nan=False,
        allow_infinity=False,
    )
    rows = draw(
        st.lists(
            st.lists(cell, min_size=_N_FEATURES, max_size=_N_FEATURES),
            min_size=n_rows,
            max_size=n_rows,
        )
    )

    columns = [f"f{i}" for i in range(_N_FEATURES)]
    X = pd.DataFrame(rows, columns=columns, dtype=float)
    y = pd.Series(y_values, name="Join_Label")
    return X, y


@st.composite
def treated_leads_and_scoring_matrix(draw):
    """Draw ``N`` treated leads with distinct identities and an aligned matrix.

    Builds ``N`` leads each with a ``promo_id`` from the three real promos
    (``P001/P002/P003``) and a ``client_id``, where every ``(promo_id,
    client_id)`` pair is unique, plus a row-aligned numeric feature matrix
    ``X_score`` with the same ``N`` rows and the ``f0..f{n-1}`` columns the model
    was trained on. ``N`` is kept small (1-8) so scoring stays fast while still
    exercising the one-row-per-lead cardinality.
    """
    n_leads = draw(st.integers(min_value=1, max_value=8))

    # Draw N distinct (promo_id, client_id) pairs. client_id ints come from a
    # pool large enough that uniqueness is easy; promo_id is one of the three.
    pairs = draw(
        st.lists(
            st.tuples(
                st.sampled_from(PROMO_IDS),
                st.integers(min_value=1, max_value=10_000),
            ),
            min_size=n_leads,
            max_size=n_leads,
            unique=True,
        )
    )

    leads = pd.DataFrame(
        {
            "promo_id": [p for p, _ in pairs],
            "client_id": [c for _, c in pairs],
            # A Join_Label column is carried on the leads frame as in production;
            # score_leads ignores it, but it mirrors the real leads shape.
            "Join_Label": [0] * n_leads,
        }
    )

    cell = st.floats(
        min_value=-1000.0,
        max_value=1000.0,
        allow_nan=False,
        allow_infinity=False,
    )
    score_rows = draw(
        st.lists(
            st.lists(cell, min_size=_N_FEATURES, max_size=_N_FEATURES),
            min_size=n_leads,
            max_size=n_leads,
        )
    )
    columns = [f"f{i}" for i in range(_N_FEATURES)]
    X_score = pd.DataFrame(score_rows, columns=columns, dtype=float)

    return leads, X_score


# max_examples is kept small because EACH example fits the calibrated model
# (three internal cv folds) plus a full-data booster, then runs SHAP -- all
# slow. deadline=None because a single fit easily exceeds Hypothesis's default
# per-example deadline.
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(model_training_data(), treated_leads_and_scoring_matrix())
def test_exactly_one_scores_row_per_treated_lead(training, scoring):
    """Exactly one scores row per treated lead.

    **Validates: Requirements 6.6**

    Scoring ``N`` treated leads with distinct ``(promo_id, client_id)``
    identities and writing the result must yield a CSV with exactly ``N`` data
    rows, each ``(promo_id, client_id)`` lead appearing exactly once.
    """
    X_train, y_train = training
    leads, X_score = scoring

    schema = FeatureSchema(columns=list(X_train.columns))
    config = Config()

    # Fit a small two-class calibrated model on the direct numeric X/y.
    model = Model_Trainer(config).fit(X_train, y_train, schema)

    # Score the treated leads (leads and X_score are row-aligned) and write the
    # Scores_File to a tmp path created inside the test body -- Hypothesis cannot
    # use function-scoped fixtures per example.
    scorer = Scorer(model, config)
    scored = scorer.score_leads(leads, X_score)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "scores.csv"
        scorer.write_scores(scored, out_path)

        written = pd.read_csv(out_path)

    # Exactly one data row per treated lead (Requirement 6.6).
    assert len(written) == len(leads)

    # The written identity columns are exactly the treated leads' identities,
    # each appearing exactly once.
    written_pairs = list(
        zip(written["promo_id"].astype(str), written["client_id"].astype(int))
    )
    expected_pairs = list(
        zip(leads["promo_id"].astype(str), leads["client_id"].astype(int))
    )

    # No duplicate (promo_id, client_id) in the output.
    assert len(set(written_pairs)) == len(written_pairs)
    # The same multiset of identities as the treated leads.
    assert sorted(written_pairs) == sorted(expected_pairs)

    # The output carries exactly the fixed six-column header (Requirement 6.3),
    # confirming the row-count assertion is over the real Scores_File layout.
    assert list(written.columns) == SCORE_COLUMNS
