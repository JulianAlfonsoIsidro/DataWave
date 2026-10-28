"""Property-based test for the NDB_Flag feature block.

# Feature: part1-optin, Property 7: NDB flag equals NDB membership

Covers Property 7 of the part1-optin spec: for every treated lead, the
``ndb_flag`` column produced by
:meth:`part1_optin.features.Feature_Assembler.fit_transform` is ``1`` exactly
when that lead's client's ``client_id`` appears anywhere in the NDB_File and
``0`` otherwise (Requirement 2.10). This is a pure membership test, independent
of the ``flag_type`` / ``flag_date`` columns and of how many NDB rows a client
carries.

The assertion is made against an INDEPENDENT reference membership set built
straight from the generated NDB frame -- it never reuses the assembler's code --
so a divergence signals a real feature bug.

The test exercises the real file-reading path: every generated source frame is
written to a temporary CSV, a :class:`part1_optin.config.Config` is pointed at
those files, and :meth:`Feature_Assembler.fit_transform` runs end to end.

No path in this test references a ``*_answer_key*`` file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings

from part1_optin.config import Config
from part1_optin.features import (
    NDB_FLAG_COLUMN,
    Feature_Assembler,
)

from tests.strategies_part1 import consistent_datasets


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(consistent_datasets())
def test_ndb_flag_equals_ndb_membership(dataset):
    """ndb_flag equals an independent NDB membership check.

    **Validates: Requirements 2.10**
    """
    leads = dataset["leads"]
    ndb = dataset["ndb"]

    # Build the independent membership set before touching the assembler so
    # there is no shared state between the expected value and the system under
    # test. A client's mere presence in the NDB_File sets the flag, regardless
    # of flag_type/flag_date or row count (Requirement 2.10).
    ndb_members = set(ndb["client_id"])

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
        ndb.to_csv(paths["ndb_path"], index=False)
        dataset["part2_features"].to_csv(paths["features_part2_path"], index=False)
        dataset["promo_history"].to_csv(paths["promo_history_path"], index=False)

        config = Config(**paths)
        assembler = Feature_Assembler(config)

        X, _schema = assembler.fit_transform(leads)

    # X is indexed like leads, so each row's ndb_flag must equal the independent
    # membership check for that lead's client: 1 if the client appears in the
    # NDB_File, else 0 (Requirement 2.10).
    assert NDB_FLAG_COLUMN in X.columns
    assert len(X) == len(leads)

    client_by_pos = leads["client_id"].tolist()
    actual = X[NDB_FLAG_COLUMN].tolist()

    for client_id, actual_value in zip(client_by_pos, actual):
        expected_value = 1 if client_id in ndb_members else 0
        assert actual_value == expected_value, (
            f"ndb_flag mismatch for client {client_id!r}: "
            f"expected {expected_value}, got {actual_value}"
        )
