"""Property-based test for the missing-source flags and zero-fill behaviour.

# Feature: part1-optin, Property 3: Missing-source flags and zero-fill track client presence

Covers Property 3 of the part1-optin spec: for every treated lead, each of the
three missing-source flags produced by
:meth:`part1_optin.features.Feature_Assembler.fit_transform` is ``1`` exactly
when that lead's ``client_id`` is absent from the corresponding source frame
and ``0`` otherwise, and when a flag is raised the source's predictor columns
for that lead are zero-filled:

- ``Customer_DNA_Missing_Flag`` == 1 iff the client is absent from the
  customer_dna frame; when missing, every DNA predictor column is ``0``
  (Requirement 2.2).
- ``ADB_Missing_Flag`` == 1 iff the client is absent from the adb frame; when
  missing, ``latest_adb`` and ``adb_trend`` are ``0`` (Requirement 2.7).
- ``Part2_Features_Missing_Flag`` == 1 iff the client is absent from the part2
  frame; when missing, every part2 feature column is ``0`` (Requirement 2.12).

Membership is computed INDEPENDENTLY from the generated frames -- it never
reuses the assembler's code -- so a divergence signals a real feature bug.

The test exercises the real file-reading path: every generated source frame is
written to a temporary CSV, a :class:`part1_optin.config.Config` is pointed at
those files, and :meth:`Feature_Assembler.fit_transform` runs end to end.

No path in this test references a ``*_answer_key*`` file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings

from part1_optin.config import (
    Config,
    DNA_CATEGORICAL_COLUMNS,
    DNA_NUMERIC_COLUMNS,
)
from part1_optin.features import (
    ADB_MISSING_FLAG,
    ADB_TREND_COLUMN,
    CUSTOMER_DNA_MISSING_FLAG,
    LATEST_ADB_COLUMN,
    PART2_FEATURES_MISSING_FLAG,
    Feature_Assembler,
)

from tests.strategies_part1 import consistent_datasets


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(consistent_datasets())
def test_missing_flags_and_zero_fill_track_client_presence(dataset):
    """Each missing flag tracks client absence and zero-fills its predictors.

    **Validates: Requirements 2.2, 2.7, 2.12**
    """
    leads = dataset["leads"]

    # Build the independent membership sets straight from the generated frames,
    # before touching the assembler, so there is no shared state between the
    # expected values and the system under test. A lead's client is "present"
    # in a source exactly when its client_id appears in that source frame.
    dna_members = set(dataset["customer_dna"]["client_id"])
    adb_members = set(dataset["adb_monthly"]["client_id"])
    part2_members = set(dataset["part2_features"]["client_id"])

    # The part2 predictor columns are every part2 source column except the
    # client_id join key -- these are the columns that must be zero-filled for
    # an absent client (Requirement 2.12).
    part2_predictor_columns = [
        column
        for column in dataset["part2_features"].columns
        if column != "client_id"
    ]

    # The DNA predictor columns are the numeric pass-throughs plus the
    # categorical code columns -- every one must be 0 for an absent client
    # (Requirement 2.2).
    dna_predictor_columns = list(DNA_NUMERIC_COLUMNS) + list(DNA_CATEGORICAL_COLUMNS)

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
        dataset["promo_history"].to_csv(paths["promo_history_path"], index=False)

        config = Config(**paths)
        assembler = Feature_Assembler(config)

        X, _schema = assembler.fit_transform(leads)

    # X is indexed like leads, so each row lines up with the lead at the same
    # position; its missing flags and predictor values are checked against the
    # independent membership sets for that lead's client.
    assert CUSTOMER_DNA_MISSING_FLAG in X.columns
    assert ADB_MISSING_FLAG in X.columns
    assert PART2_FEATURES_MISSING_FLAG in X.columns
    assert len(X) == len(leads)

    client_by_pos = leads["client_id"].tolist()

    for pos, client_id in enumerate(client_by_pos):
        row = X.iloc[pos]

        # --- Customer_DNA (Requirement 2.2) --------------------------------
        dna_present = client_id in dna_members
        expected_dna_flag = 0 if dna_present else 1
        assert row[CUSTOMER_DNA_MISSING_FLAG] == expected_dna_flag, (
            f"Customer_DNA_Missing_Flag mismatch for client {client_id!r}: "
            f"expected {expected_dna_flag}, got {row[CUSTOMER_DNA_MISSING_FLAG]}"
        )
        if not dna_present:
            for column in dna_predictor_columns:
                assert row[column] == 0, (
                    f"DNA predictor {column!r} not zero-filled for absent "
                    f"client {client_id!r}: got {row[column]}"
                )

        # --- ADB (Requirement 2.7) -----------------------------------------
        adb_present = client_id in adb_members
        expected_adb_flag = 0 if adb_present else 1
        assert row[ADB_MISSING_FLAG] == expected_adb_flag, (
            f"ADB_Missing_Flag mismatch for client {client_id!r}: "
            f"expected {expected_adb_flag}, got {row[ADB_MISSING_FLAG]}"
        )
        if not adb_present:
            assert row[LATEST_ADB_COLUMN] == 0, (
                f"latest_adb not zero-filled for absent client {client_id!r}: "
                f"got {row[LATEST_ADB_COLUMN]}"
            )
            assert row[ADB_TREND_COLUMN] == 0, (
                f"adb_trend not zero-filled for absent client {client_id!r}: "
                f"got {row[ADB_TREND_COLUMN]}"
            )

        # --- Part2 features (Requirement 2.12) -----------------------------
        part2_present = client_id in part2_members
        expected_part2_flag = 0 if part2_present else 1
        assert row[PART2_FEATURES_MISSING_FLAG] == expected_part2_flag, (
            f"Part2_Features_Missing_Flag mismatch for client {client_id!r}: "
            f"expected {expected_part2_flag}, got "
            f"{row[PART2_FEATURES_MISSING_FLAG]}"
        )
        if not part2_present:
            for column in part2_predictor_columns:
                assert row[column] == 0, (
                    f"part2 column {column!r} not zero-filled for absent "
                    f"client {client_id!r}: got {row[column]}"
                )
