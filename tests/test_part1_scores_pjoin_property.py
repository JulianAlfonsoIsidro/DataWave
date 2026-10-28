"""Property-based test for written p_join bounds and rounding.

# Feature: part1-optin, Property 18: Written p_join values are bounded and rounded

Covers Property 18 of the part1-optin spec: every ``p_join`` value in the
written Scores_File lies in the inclusive range ``[0, 1]`` and is rounded to at
most six decimal places (Requirement 6.4).

``Scorer.write_scores`` clips ``p_join`` into ``[0, 1]`` and rounds it to six
decimals before persisting the fixed six-column ``scores.csv`` with no index
column. This test exercises that end to end: it fits a small two-class
:class:`part1_optin.model.Calibrated_Model` directly on a numeric X/y (no full
Feature_Assembler is needed -- the trainer only reads X/y and carries the schema
through), builds a treated-leads frame and an aligned feature matrix with the
same columns as the schema, scores the leads, and writes them to a temp CSV.
Reading the file back, it asserts two things per written value:

- bounds: ``0.0 <= p_join <= 1.0`` (read back as float), and
- rounding: the *written string* for ``p_join`` has at most six decimal digits,
  the robust check against the on-disk formatting Requirement 6.4 mandates; a
  float equality ``p == round(p, 6)`` is also asserted as a backstop.

This test fits a real model per example, so it keeps ``max_examples`` modest
(10) and sets ``deadline=None``: each Hypothesis example fits a
``CalibratedClassifierCV`` (three internal XGBoost folds) plus a full-data
booster, which is far slower than a pure-function property, and a per-example
deadline would flake on that cost. A function-scoped pytest fixture cannot be
combined with ``@given``, so the temp directory is created inside the test body
with ``tempfile`` and cleaned up explicitly. No path in this test references a
``*_answer_key*`` file; everything is generated in memory and written to a temp
file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import Config
from part1_optin.features import FeatureSchema
from part1_optin.model import Model_Trainer
from part1_optin.scoring import Scorer

# Feature column names for the generated matrices. A small fixed set keeps each
# fit cheap while still exercising a multi-feature calibrated model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Minimum examples per class. CalibratedClassifierCV uses a 3-fold
# StratifiedKFold internally, so each class needs at least three examples for
# every inner fold to see both classes.
_MIN_PER_CLASS = 3

# The p_join column must be rounded to at most this many decimal places
# (Requirement 6.4); write_scores rounds to 6 dp before persisting.
_P_JOIN_DECIMALS = 6


@st.composite
def _feature_matrix(draw, n_rows: int) -> pd.DataFrame:
    """Draw an ``n_rows`` x len(_FEATURE_COLUMNS) float feature matrix.

    Values are finite, bounded floats so XGBoost fits without NaNs or
    infinities; the columns are exactly ``_FEATURE_COLUMNS`` so the fitted
    schema applies to the score-time matrix unchanged.
    """
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
            min_size=n_rows,
            max_size=n_rows,
        )
    )
    return pd.DataFrame(rows, columns=_FEATURE_COLUMNS)


@st.composite
def _scoring_scenario(draw):
    """Draw a fit matrix/labels plus an aligned leads frame and score matrix.

    Builds a label vector with at least :data:`_MIN_PER_CLASS` zeros and ones
    (so the internal ``cv=3`` calibration folds each see both classes) and a
    matching fit matrix. Then draws a separate score-time matrix ``X_score``
    (same columns) and a row-aligned ``leads`` frame carrying ``promo_id`` /
    ``client_id`` identity columns. Returns ``(X_fit, y, leads, X_score)``.
    """
    n_zero = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 3))
    n_one = draw(st.integers(min_value=_MIN_PER_CLASS, max_value=_MIN_PER_CLASS + 3))
    labels = [0] * n_zero + [1] * n_one
    y = pd.Series(labels, name="Join_Label")
    x_fit = draw(_feature_matrix(len(labels)))

    n_score = draw(st.integers(min_value=1, max_value=6))
    x_score = draw(_feature_matrix(n_score))

    promo_ids = draw(
        st.lists(
            st.sampled_from(["P001", "P002", "P003"]),
            min_size=n_score,
            max_size=n_score,
        )
    )
    leads = pd.DataFrame(
        {
            "promo_id": promo_ids,
            "client_id": [f"C{i:04d}" for i in range(n_score)],
        }
    )
    return x_fit, y, leads, x_score


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(scenario=_scoring_scenario())
def test_written_p_join_is_bounded_and_rounded(scenario):
    """Written p_join values are bounded and rounded.

    **Validates: Requirements 6.4**

    Fit a small two-class ``Calibrated_Model``, score a row-aligned leads frame,
    write the scores to a temp CSV, read them back, and assert every written
    ``p_join`` is within ``[0, 1]`` and rounded to at most six decimal places.
    """
    x_fit, y, leads, x_score = scenario

    # A minimal schema whose columns match the generated matrices. The full
    # Feature_Assembler is not needed here; the trainer only reads X/y and
    # carries the schema through to the Scorer.
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))
    model = Model_Trainer(Config()).fit(x_fit, y, schema)

    scored = Scorer(model, Config()).score_leads(leads, x_score)

    # tempfile is used inside the test body: a function-scoped pytest fixture
    # cannot be combined with @given, so the temp dir is created and cleaned up
    # explicitly here.
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "scores.csv"
        Scorer(model, Config()).write_scores(scored, path)

        # Read p_join back as strings to validate the on-disk 6-dp formatting
        # robustly (the primary rounding check, Requirement 6.4), and as float
        # for the bounds check and a float-equality backstop.
        written_str = pd.read_csv(path, dtype=str)
        written_num = pd.read_csv(path)

    assert "p_join" in written_str.columns

    for raw in written_str["p_join"]:
        text = str(raw)
        # Bounds: 0.0 <= p_join <= 1.0 (Requirement 6.4).
        value = float(text)
        assert 0.0 <= value <= 1.0

        # Rounding: the written string has at most six decimal digits
        # (Requirement 6.4). Tolerate an optional sign and an exponent-free
        # decimal form, which is how pandas writes these rounded floats.
        if "." in text:
            decimals = text.split(".", 1)[1]
            assert len(decimals) <= _P_JOIN_DECIMALS, (
                f"p_join {text!r} has more than {_P_JOIN_DECIMALS} decimals"
            )

    # Float backstop: each value equals its own round-to-6dp.
    for value in written_num["p_join"]:
        assert value == round(float(value), _P_JOIN_DECIMALS)
