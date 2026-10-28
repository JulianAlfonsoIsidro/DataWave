"""Example/edge unit tests for the headline stratified validation report.

Targeted (non-Hypothesis) tests for the StratifiedGroupKFold scheme on
:class:`part1_optin.validation.Validator` against Requirement 8's headline
reporting, covering:

- The :class:`part1_optin.validation.StratifiedValidationResult` carried on
  :attr:`ValidationResult.stratified` exposes the overall AUC/capture fields
  and the per-promo AUC/capture mappings with the expected types and keys
  (Requirements 8.4, 8.5).
- :meth:`Validator.print_report` presents the stratified block as the headline
  and labels the LOPO block "Cold-start: unseen promo type" (Requirements 8.6,
  4.6).

The data is small, fixed, and deterministic: a numeric feature matrix, a
Join_Label vector, a ``promo_ids`` Series over P001/P002/P003, and a
``client_ids`` Series with one distinct client per lead, built directly rather
than through the full Feature_Assembler. Supplying ``client_ids`` to
:meth:`Validator.run` turns on the headline StratifiedGroupKFold scheme
(``n_splits=5``), so every promo is given plenty of joiners and non-joiners,
each a distinct client, so the five group folds split cleanly, the inner 3-fold
``StratifiedKFold`` of ``CalibratedClassifierCV`` sees both classes, and every
per-promo out-of-fold slice carries both classes. No path in this module
references a ``*_answer_key*`` file; all matrices are constructed in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from part1_optin.config import PROMO_IDS, Config
from part1_optin.features import FeatureSchema
from part1_optin.validation import StratifiedValidationResult, Validator

# Feature columns for the generated matrix; a small fixed set keeps the fit
# cheap while still exercising a multi-feature calibrated model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]

# Joiners (and non-joiners) per promo. The headline scheme uses
# StratifiedGroupKFold(n_splits=5) grouped by client, and the inner
# CalibratedClassifierCV uses a 3-fold StratifiedKFold, so each class needs a
# comfortable count per promo: 10 per class per promo (30 joiners / 30
# non-joiners overall, one distinct client each) leaves every fold's training
# slice and every per-promo out-of-fold slice with both classes.
_PER_CLASS = 10


def _rows(n_rows: int, loc: float, seed: int) -> np.ndarray:
    """Return ``n_rows`` deterministic feature rows centered near ``loc``.

    The two classes are given slightly offset centers so the booster has a
    signal to learn, but these tests assert structure (field presence, types,
    report labeling), not accuracy.
    """
    rng = np.random.RandomState(seed)
    return rng.normal(loc=loc, scale=1.0, size=(n_rows, len(_FEATURE_COLUMNS)))


def _stratified_dataset() -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Build (X, y, promo_ids, client_ids) spanning all three promos.

    Each of P001/P002/P003 gets ``_PER_CLASS`` joiners and ``_PER_CLASS``
    non-joiners. Every lead is a distinct client, so StratifiedGroupKFold never
    straddles a client and each per-promo out-of-fold slice carries both
    classes. Returns ``(X, y, promo_ids, client_ids)``.
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
    # One distinct client per lead (zero-padded C###### ids matching the data).
    client_ids = pd.Series(
        [f"C{100000 + k}" for k in range(len(labels))], name="client_id"
    )
    return x, y, promo_ids, client_ids


def test_stratified_result_carries_overall_and_per_promo_fields():
    """The stratified result exposes overall and per-promo AUC/capture fields.

    With ``client_ids`` supplied, ``run`` populates
    :attr:`ValidationResult.stratified` with a
    :class:`StratifiedValidationResult` whose overall AUC and overall capture
    are floats in [0, 1], and whose per-promo AUC and per-promo capture maps are
    keyed by exactly {P001, P002, P003} with float values in [0, 1]. ``n`` and
    ``joiners`` are the whole-dataset counts.

    _Requirements: 8.4, 8.5_
    """
    x, y, promo_ids, client_ids = _stratified_dataset()
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(
        x, y, promo_ids, schema, client_ids=client_ids
    )

    strat = result.stratified
    assert isinstance(strat, StratifiedValidationResult)

    # Overall AUC/capture fields (Requirements 8.4, 8.5): both classes and
    # joiners present overall, so both are defined floats bounded in [0, 1].
    assert isinstance(strat.overall_auc, float)
    assert 0.0 <= strat.overall_auc <= 1.0
    assert isinstance(strat.overall_capture_rate_top_quintile, float)
    assert 0.0 <= strat.overall_capture_rate_top_quintile <= 1.0

    # Per-promo AUC/capture maps are keyed by exactly the three promos.
    assert isinstance(strat.per_promo_auc, dict)
    assert isinstance(strat.per_promo_capture, dict)
    assert set(strat.per_promo_auc) == set(PROMO_IDS)
    assert set(strat.per_promo_capture) == set(PROMO_IDS)

    # Every promo slice carries both classes and at least one joiner here, so
    # each per-promo AUC and capture is a defined float in [0, 1].
    for promo in PROMO_IDS:
        auc = strat.per_promo_auc[promo]
        capture = strat.per_promo_capture[promo]
        assert isinstance(auc, float)
        assert 0.0 <= auc <= 1.0
        assert isinstance(capture, float)
        assert 0.0 <= capture <= 1.0

    # Whole-dataset counts: 60 leads, 30 joiners (10 joiners x 3 promos).
    assert strat.n == 2 * _PER_CLASS * len(PROMO_IDS)
    assert strat.joiners == _PER_CLASS * len(PROMO_IDS)


def test_print_report_has_stratified_headline_and_cold_start_lopo_heading(capsys):
    """print_report leads with the stratified block and labels LOPO cold-start.

    The headline StratifiedGroupKFold block is printed first and the LOPO block
    is labeled "Cold-start: unseen promo type" (Requirements 8.6, 4.6). We
    assert both the stratified/headline labeling and the exact cold-start
    heading text appear, and that the stratified block precedes the cold-start
    heading.

    _Requirements: 8.6_
    """
    x, y, promo_ids, client_ids = _stratified_dataset()
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run(
        x, y, promo_ids, schema, client_ids=client_ids
    )
    Validator(Config()).print_report(result)

    out = capsys.readouterr().out
    lowered = out.lower()

    # The LOPO block is labeled as the cold-start / unseen-promo-type scheme.
    assert "cold-start: unseen promo type" in lowered

    # A headline stratified label is present (the stratified block is the
    # headline). Accept either "stratified" or "headline" wording.
    assert "stratified" in lowered or "headline" in lowered

    # The stratified headline block is printed before the cold-start heading.
    strat_pos = (
        lowered.find("stratified")
        if "stratified" in lowered
        else lowered.find("headline")
    )
    cold_start_pos = lowered.find("cold-start: unseen promo type")
    assert strat_pos != -1
    assert cold_start_pos != -1
    assert strat_pos < cold_start_pos
