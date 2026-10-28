"""Property-based test for the Avg_Contacts_Per_Month feature block.

# Feature: part1-optin, Property 6: Average contacts per month equals contacts over distinct months

Covers Property 6 of the part1-optin spec: for every treated lead, the
``avg_contacts_per_month`` column produced by
:meth:`part1_optin.features.Feature_Assembler.fit_transform` equals that lead's
client's total count of Contact_History_File rows divided by the number of
distinct ``YYYY-MM`` calendar months in which that client has at least one
contact row, and equals ``0`` for a client with no contact rows (Requirements
2.8, 2.9).

This is a reduction property: the assertion is made against an INDEPENDENT
reference recompute that never reuses the assembler's code -- it re-derives the
expected average straight from the generated contact-history frame -- so a
divergence signals a real feature bug.

The test exercises the real file-reading path: every generated source frame is
written to a temporary CSV, a :class:`part1_optin.config.Config` is pointed at
those files, and :meth:`Feature_Assembler.fit_transform` runs end to end.

No path in this test references a ``*_answer_key*`` file.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings

from part1_optin.config import Config
from part1_optin.features import (
    AVG_CONTACTS_PER_MONTH_COLUMN,
    CONTACT_MONTH_PREFIX_LENGTH,
    Feature_Assembler,
)

from tests.strategies_part1 import consistent_datasets


def _reference_avg_contacts(contacts: pd.DataFrame) -> dict[str, float]:
    """Independently recompute avg_contacts_per_month per client.

    Re-derives, for each client that appears in the Contact_History_File, the
    total count of that client's contact rows divided by the number of distinct
    ``YYYY-MM`` calendar months with at least one contact row (Requirement 2.8),
    without reusing the Feature_Assembler. Clients absent from the file are not
    in the returned mapping; the caller treats them as ``0`` (Requirement 2.9).

    The calendar month is the ``YYYY-MM`` prefix of ``contact_date``, matching
    the field the requirement bins on, so same-month contacts collapse to one
    month in the divisor.
    """
    reference: dict[str, float] = {}
    for client_id, group in contacts.groupby("client_id"):
        total_rows = len(group)
        months = (
            group["contact_date"].astype(str).str[:CONTACT_MONTH_PREFIX_LENGTH]
        )
        distinct_months = months.nunique()
        # distinct_months is >= 1 for any client present here (the months are
        # counted from the very rows being counted), so this never divides by 0.
        reference[client_id] = total_rows / distinct_months
    return reference


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(consistent_datasets())
def test_avg_contacts_per_month_matches_independent_recompute(dataset):
    """avg_contacts_per_month equals contacts over distinct months.

    **Validates: Requirements 2.8, 2.9**
    """
    leads = dataset["leads"]
    contacts = dataset["contact_history"]

    # Build the independent reference before touching the assembler so there is
    # no shared state between the expected value and the system under test.
    expected_by_client = _reference_avg_contacts(contacts)

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
        contacts.to_csv(paths["contact_history_path"], index=False)
        dataset["ndb"].to_csv(paths["ndb_path"], index=False)
        dataset["part2_features"].to_csv(paths["features_part2_path"], index=False)
        dataset["promo_history"].to_csv(paths["promo_history_path"], index=False)

        config = Config(**paths)
        assembler = Feature_Assembler(config)

        X, _schema = assembler.fit_transform(leads)

    # X is indexed like leads, so each row's avg_contacts_per_month must match
    # that lead's client's independent recompute (0 when the client has no
    # contacts, Requirement 2.9).
    assert AVG_CONTACTS_PER_MONTH_COLUMN in X.columns
    assert len(X) == len(leads)

    client_by_pos = leads["client_id"].tolist()
    actual = X[AVG_CONTACTS_PER_MONTH_COLUMN].tolist()

    for client_id, actual_value in zip(client_by_pos, actual):
        expected_value = expected_by_client.get(client_id, 0.0)
        assert math.isclose(
            actual_value, expected_value, rel_tol=1e-9, abs_tol=1e-9
        ), (
            f"avg_contacts_per_month mismatch for client {client_id!r}: "
            f"expected {expected_value}, got {actual_value}"
        )
