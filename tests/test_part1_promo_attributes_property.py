"""Property-based test for the Promo_Attributes feature block.

# Feature: part1-optin, Property 8: Promo attributes match the joined promo's mechanic and threshold

Covers Property 8 of the part1-optin spec: for every treated lead, the promo
attribute columns produced by
:meth:`part1_optin.features.Feature_Assembler.fit_transform` match that lead's
promo as joined from the Promo_History_File on ``promo_id`` (Requirements 2.11,
2.13):

- the ``mechanic`` code column equals the ordinal code for that lead's promo's
  ``mechanic`` under the fitted ``schema.categorical_maps[PROMO_MECHANIC_COLUMN]``
  (code ``0`` reserved for a missing promo or a mechanic unseen at fit time),
  and
- the ``threshold_php`` column equals the promo's ``threshold_php`` from the
  Promo_History_File (``0`` for a promo absent from the file).

This is a reduction property: the expected values come from an INDEPENDENT join
of ``promo_history`` onto ``leads`` on ``promo_id`` -- it never reuses the
assembler's block code -- so a divergence signals a real feature bug. The
mechanic code is derived from the *fitted* schema map so the reference honours
the deterministic ``value -> code`` encoding rather than hard-coding it.

The test exercises the real file-reading path: every generated source frame is
written to a temporary CSV, a :class:`part1_optin.config.Config` is pointed at
those files, and :meth:`Feature_Assembler.fit_transform` runs end to end.

No path in this test references a ``*_answer_key*`` file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings

from part1_optin.config import Config, PROMO_MECHANIC_COLUMN
from part1_optin.features import (
    PROMO_THRESHOLD_COLUMN,
    Feature_Assembler,
)

from tests.strategies_part1 import consistent_datasets


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(consistent_datasets())
def test_promo_attributes_match_joined_promo(dataset):
    """mechanic code and threshold_php equal an independent promo join.

    **Validates: Requirements 2.11, 2.13**
    """
    leads = dataset["leads"]
    promo_history = dataset["promo_history"]

    # Build the independent promo lookup before touching the assembler so there
    # is no shared state between the expected values and the system under test.
    # Keep the first row per promo_id to mirror a one-to-one join on promo_id
    # (Requirement 2.13).
    promo_first = promo_history.drop_duplicates(subset="promo_id", keep="first")
    mechanic_by_promo = dict(
        zip(promo_first["promo_id"], promo_first[PROMO_MECHANIC_COLUMN])
    )
    threshold_by_promo = dict(
        zip(promo_first["promo_id"], promo_first[PROMO_THRESHOLD_COLUMN])
    )

    # Write every approved source to a temp CSV and point a Config at them so
    # the real read_csv path (and the answer-key guard) runs. A self-managed
    # temp dir keeps each Hypothesis example isolated without a function-scoped
    # pytest fixture (which Hypothesis cannot drive per example).
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        paths = {
            "promo_leads_path": tmp / "promo_leads.csv",
            "customer_dna_path": tmp / "customer_dna.csv",
            "product_ownership_path": tmp / "product_ownership.csv",
            "adb_monthly_path": tmp / "adb_monthly.csv",
            "contact_history_path": tmp / "contact_history.csv",
            "ndb_path": tmp / "ndb.csv",
            "features_part2_path": tmp / "features_part2.csv",
            "promo_history_path": tmp / "promo_history.csv",
        }
        leads.to_csv(paths["promo_leads_path"], index=False)
        dataset["customer_dna"].to_csv(paths["customer_dna_path"], index=False)
        dataset["product_ownership"].to_csv(
            paths["product_ownership_path"], index=False
        )
        dataset["adb_monthly"].to_csv(paths["adb_monthly_path"], index=False)
        dataset["contact_history"].to_csv(
            paths["contact_history_path"], index=False
        )
        dataset["ndb"].to_csv(paths["ndb_path"], index=False)
        dataset["part2_features"].to_csv(paths["features_part2_path"], index=False)
        promo_history.to_csv(paths["promo_history_path"], index=False)

        config = Config(**paths)
        assembler = Feature_Assembler(config)

        X, schema = assembler.fit_transform(leads)

    # The fitted mechanic value -> code map; code 0 is reserved for a missing
    # promo or a mechanic unseen at fit time (Requirement 2.13). Deriving the
    # expected code from the fitted schema keeps the reference honest about the
    # deterministic encoding without re-implementing how codes are assigned.
    mechanic_code_map = schema.categorical_maps[PROMO_MECHANIC_COLUMN]

    assert PROMO_MECHANIC_COLUMN in X.columns
    assert PROMO_THRESHOLD_COLUMN in X.columns
    assert len(X) == len(leads)

    # X is indexed like leads, so position-align the lead promo_ids with the
    # emitted feature columns.
    promo_by_pos = leads["promo_id"].tolist()
    actual_mechanic = X[PROMO_MECHANIC_COLUMN].tolist()
    actual_threshold = X[PROMO_THRESHOLD_COLUMN].tolist()

    for promo_id, mech_value, thr_value in zip(
        promo_by_pos, actual_mechanic, actual_threshold
    ):
        # Expected mechanic code: look the promo's mechanic up in the
        # independent join, then map it through the fitted code map. A promo
        # absent from promo_history (mechanic is None) or a mechanic not in the
        # map resolves to the reserved code 0 (Requirement 2.13).
        raw_mechanic = mechanic_by_promo.get(promo_id)
        expected_code = mechanic_code_map.get(raw_mechanic, 0)
        assert mech_value == expected_code, (
            f"mechanic code mismatch for promo {promo_id!r}: "
            f"expected {expected_code}, got {mech_value}"
        )

        # Expected threshold: the promo's threshold_php from the independent
        # join; a promo absent from promo_history resolves to 0 (Requirement
        # 2.13).
        if promo_id in threshold_by_promo:
            expected_threshold = float(threshold_by_promo[promo_id])
        else:
            expected_threshold = 0.0
        assert float(thr_value) == expected_threshold, (
            f"threshold_php mismatch for promo {promo_id!r}: "
            f"expected {expected_threshold}, got {thr_value}"
        )
