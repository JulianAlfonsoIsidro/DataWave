"""Property-based test for the Feature_Assembler ADB block.

# Feature: part1-optin, Property 5: Latest ADB and ADB trend match an independent recompute

Covers Property 5 of the part1-optin spec: given any internally consistent
dataset, the ``latest_adb`` and ``adb_trend`` columns produced by
:meth:`part1_optin.features.Feature_Assembler.fit_transform` match an
independent reference recompute (Requirements 2.5, 2.6):

- ``latest_adb`` is the ``adb_php`` at the client's chronologically most recent
  ``month`` (Requirement 2.5);
- ``adb_trend`` is the least-squares slope of ``adb_php`` against an ascending
  month index over the client's most recent up-to-three months, with a single
  month yielding slope ``0`` (Requirements 2.5, 2.6);
- a client absent from the ADB_File yields ``latest_adb == 0`` and
  ``adb_trend == 0``.

This is a reduction property: the test asserts the assembled values against an
*independent* recompute that never reuses the production ``_least_squares_slope``
helper -- the slope is recomputed with :func:`numpy.polyfit`. A divergence
therefore signals a real bug in the ADB block rather than a shared mistake.

The test exercises the real file-reading path: it writes the generated source
frames to temporary CSVs, points a :class:`part1_optin.config.Config` at them,
runs ``fit_transform``, and compares row by row. No path references a
``*_answer_key*`` file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings

from part1_optin.config import Config
from part1_optin.features import (
    ADB_TREND_COLUMN,
    ADB_TREND_WINDOW,
    LATEST_ADB_COLUMN,
    Feature_Assembler,
)
from part1_optin.leads import Lead_Loader

from tests.strategies_part1 import consistent_datasets


def _reference_latest_and_trend(adb: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """Independently recompute (latest_adb, adb_trend) per client from the ADB frame.

    Re-derives the expected ADB features directly from the raw ADB_File frame
    without reusing the Feature_Assembler or its ``_least_squares_slope`` helper:

    - sort each client's rows by ``month`` (``YYYY-MM`` strings sort
      chronologically), take the last row's ``adb_php`` as ``latest_adb``
      (Requirement 2.5);
    - take the last up-to-:data:`ADB_TREND_WINDOW` months and fit the slope with
      :func:`numpy.polyfit` over an ascending ``0, 1, 2, ...`` index; a single
      month yields slope ``0`` (Requirements 2.5, 2.6).

    Returns a ``{client_id: (latest_adb, adb_trend)}`` map covering only the
    clients present in the ADB_File; absent clients are handled by the caller.
    """
    work = adb.copy()
    work["adb_php"] = pd.to_numeric(work["adb_php"], errors="coerce")

    reference: dict[str, tuple[float, float]] = {}
    for client_id, group in work.groupby("client_id"):
        ordered = group.sort_values("month")
        values = ordered["adb_php"].to_numpy(dtype="float64")

        latest = float(values[-1])

        window = values[-ADB_TREND_WINDOW:]
        if len(window) < 2:
            # A single point has no unique regression line -> slope 0 (2.6).
            trend = 0.0
        else:
            # Independent slope via numpy.polyfit over the ascending index.
            x = np.arange(len(window), dtype="float64")
            trend = float(np.polyfit(x, window, 1)[0])

        reference[client_id] = (latest, trend)

    return reference


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(consistent_datasets())
def test_latest_adb_and_trend_match_independent_recompute(dataset):
    """``latest_adb`` and ``adb_trend`` match an independent recompute.

    **Validates: Requirements 2.5, 2.6**
    """
    # Write every approved source to a temp CSV and point a Config at them so
    # the real read path (and answer-key guard) runs. A self-managed temp dir
    # keeps each Hypothesis example isolated.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        paths = {
            "promo_leads.csv": dataset["leads"],
            "customer_dna.csv": dataset["customer_dna"],
            "product_ownership.csv": dataset["product_ownership"],
            "adb_monthly.csv": dataset["adb_monthly"],
            "contact_history.csv": dataset["contact_history"],
            "ndb.csv": dataset["ndb"],
            "features_part2.csv": dataset["part2_features"],
            "promo_history.csv": dataset["promo_history"],
        }
        for name, frame in paths.items():
            frame.to_csv(tmp / name, index=False)

        config = Config(
            promo_leads_path=tmp / "promo_leads.csv",
            customer_dna_path=tmp / "customer_dna.csv",
            product_ownership_path=tmp / "product_ownership.csv",
            adb_monthly_path=tmp / "adb_monthly.csv",
            contact_history_path=tmp / "contact_history.csv",
            ndb_path=tmp / "ndb.csv",
            features_part2_path=tmp / "features_part2.csv",
            promo_history_path=tmp / "promo_history.csv",
        )

        # Select the treated leads the assembler actually builds rows for. If no
        # treated leads survive, the loader halts (Requirement 1.8) and there is
        # nothing to assemble -- the ADB property targets the populated case.
        try:
            leads = Lead_Loader(config).load()
        except ValueError:
            return

        X, _schema = Feature_Assembler(config).fit_transform(leads)

    # Independent per-client reference from the raw ADB frame (no production
    # slope helper reused).
    reference = _reference_latest_and_trend(dataset["adb_monthly"])

    # The feature matrix is indexed like ``leads``, so each lead row lines up
    # with its ``client_id`` by shared index.
    assert X.index.equals(leads.index)
    client_by_index = leads["client_id"]

    for row_index in X.index:
        client_id = client_by_index.loc[row_index]
        actual_latest = float(X.loc[row_index, LATEST_ADB_COLUMN])
        actual_trend = float(X.loc[row_index, ADB_TREND_COLUMN])

        if client_id in reference:
            expected_latest, expected_trend = reference[client_id]
        else:
            # Client absent from the ADB_File -> both zero (Requirement 2.7's
            # zero-fill; here it anchors the recompute for missing clients).
            expected_latest, expected_trend = 0.0, 0.0

        assert actual_latest == pytest.approx(expected_latest, rel=1e-9, abs=1e-6)
        assert actual_trend == pytest.approx(expected_trend, rel=1e-9, abs=1e-6)
