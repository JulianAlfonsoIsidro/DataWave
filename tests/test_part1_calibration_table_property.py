"""Property-based test for calibration-table well-formedness in LOPO validation.

# Feature: part1-optin, Property 15: Calibration table bins are well-formed

Covers Property 15 of the part1-optin spec: for every fold of
:meth:`part1_optin.validation.Validator.run`, the ``calibration_table`` (one
dict per non-empty predicted-probability bin, with keys ``bin_lo``, ``bin_hi``,
``mean_pred``, ``observed_rate``, ``count``) is well-formed (Requirement 4.4):

- Each reported bin has ``count >= 1`` -- empty bins are omitted.
- ``bin_lo < bin_hi`` and the interval ``[bin_lo, bin_hi]`` lies within
  ``[0, 1]``.
- The bins are the 10 equal-width edges over ``[0, 1]`` (width ``0.1``), so
  ``bin_lo`` and ``bin_hi`` align to that grid -- each edge is a multiple of
  ``0.1`` within float tolerance.
- ``mean_pred`` lies within ``[bin_lo, bin_hi]`` (within a tiny float
  tolerance), consistent with the bin the leads were assigned to.
- ``observed_rate`` lies within ``[0, 1]``.
- Summing every reported bin's ``count`` recovers the held-out lead count for
  that fold (``fold.n``), so every held-out lead is binned exactly once.
- The reported bins are non-overlapping and appear in ascending order.

This test runs the real Validator, which fits three LOPO folds and each fold
fits a ``CalibratedClassifierCV`` (three internal XGBoost folds) plus a
full-data booster, so it is far slower than a pure-function property. It keeps
``max_examples`` small and sets ``deadline=None`` because a per-example deadline
would flake on the fit cost rather than reveal a real defect. It takes no
pytest fixture, so no ``@given`` keyword/HealthCheck juggling is needed.

The data is constructed directly -- a numeric feature matrix, a Join_Label
vector, and a ``promo_ids`` Series over P001/P002/P003 -- rather than going
through the full Feature_Assembler. Because each LOPO fold trains on the two
*other* promos combined and ``CalibratedClassifierCV`` uses an internal 3-fold
``StratifiedKFold``, every promo is given at least
:data:`_MIN_PER_CLASS_PER_PROMO` joiners and the same number of non-joiners, so
any two-promo training subset has enough of each class for the inner folds to
fit and every fold actually produces a calibration table. A
:class:`FeatureSchema` whose ``columns`` match the generated matrix is built
directly. No path in this test references a ``*_answer_key*`` file; the matrices
are generated in memory.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part1_optin.config import N_CALIBRATION_BINS, PROMO_IDS, Config
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

# The equal-width bin grid over [0, 1]: width 0.1 with N_CALIBRATION_BINS bins.
_BIN_WIDTH = 1.0 / N_CALIBRATION_BINS

# Float tolerance for grid alignment and mean-within-bin containment.
_TOL = 1e-9


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
    subset can fit the calibrated model and every held-out fold produces a
    calibration table. Returns ``(X, y, promo_ids)``.
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


def _assert_on_grid(value: float, label: str) -> None:
    """Assert ``value`` is a multiple of the 0.1 bin width within tolerance."""
    nearest = round(value / _BIN_WIDTH) * _BIN_WIDTH
    assert abs(value - nearest) <= _TOL, (
        f"{label}={value} is not aligned to the {_BIN_WIDTH} grid "
        f"(nearest edge {nearest})"
    )


@settings(
    max_examples=6,
    deadline=None,  # each example fits 3 LOPO folds; a deadline would flake.
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_two_class_dataset())
def test_calibration_table_bins_are_well_formed(data):
    """Calibration table bins are well-formed for every fold.

    **Validates: Requirements 4.4**

    Run the Validator on data where every held-out promo has both classes, then
    assert each fold's ``calibration_table`` satisfies the well-formedness
    invariants: non-empty bins only, edges on the equal-width ``[0, 1]`` grid,
    ``mean_pred`` inside its bin, ``observed_rate`` in ``[0, 1]``, counts summing
    to ``fold.n``, and bins non-overlapping and ascending.
    """
    x, y, promo_ids = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(x, y, promo_ids, schema)

    for fold in result.folds:
        table = fold.calibration_table

        total_count = 0
        prev_hi: float | None = None
        for row in table:
            bin_lo = row["bin_lo"]
            bin_hi = row["bin_hi"]
            mean_pred = row["mean_pred"]
            observed_rate = row["observed_rate"]
            count = row["count"]

            # Empty bins are omitted: every reported bin holds >= 1 lead.
            assert count >= 1, (
                f"{fold.promo_id}: reported bin {row} has count {count} < 1"
            )

            # bin_lo < bin_hi and the interval sits within [0, 1].
            assert bin_lo < bin_hi, (
                f"{fold.promo_id}: bin_lo {bin_lo} not < bin_hi {bin_hi}"
            )
            assert 0.0 - _TOL <= bin_lo <= 1.0 + _TOL, (
                f"{fold.promo_id}: bin_lo {bin_lo} outside [0, 1]"
            )
            assert 0.0 - _TOL <= bin_hi <= 1.0 + _TOL, (
                f"{fold.promo_id}: bin_hi {bin_hi} outside [0, 1]"
            )

            # Edges align to the 10 equal-width (0.1) edges over [0, 1], and the
            # bin width is exactly 0.1 within tolerance.
            _assert_on_grid(bin_lo, f"{fold.promo_id} bin_lo")
            _assert_on_grid(bin_hi, f"{fold.promo_id} bin_hi")
            assert abs((bin_hi - bin_lo) - _BIN_WIDTH) <= _TOL, (
                f"{fold.promo_id}: bin width {bin_hi - bin_lo} != {_BIN_WIDTH}"
            )

            # mean_pred lies within the bin it was computed from (tiny float
            # tolerance), and therefore within [0, 1].
            assert bin_lo - _TOL <= mean_pred <= bin_hi + _TOL, (
                f"{fold.promo_id}: mean_pred {mean_pred} outside bin "
                f"[{bin_lo}, {bin_hi}]"
            )

            # observed_rate is a fraction of joiners in the bin, so in [0, 1].
            assert 0.0 <= observed_rate <= 1.0, (
                f"{fold.promo_id}: observed_rate {observed_rate} outside [0, 1]"
            )

            # Bins are non-overlapping and in ascending order: each bin starts
            # at or after the previous bin's upper edge.
            if prev_hi is not None:
                assert bin_lo >= prev_hi - _TOL, (
                    f"{fold.promo_id}: bin_lo {bin_lo} overlaps/precedes "
                    f"previous bin_hi {prev_hi}"
                )
            prev_hi = bin_hi

            total_count += count

        # Every held-out lead is binned exactly once: the per-bin counts sum to
        # the fold's held-out lead count.
        assert total_count == fold.n, (
            f"{fold.promo_id}: bin counts sum to {total_count}, expected "
            f"fold.n={fold.n}"
        )
