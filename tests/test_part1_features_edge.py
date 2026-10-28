"""Example/edge-case unit tests for the Part1_Optin_Pipeline Feature_Assembler
ADB and Active_Product_Count feature blocks (task 4.7).

These are concrete-example tests (not Hypothesis) covering two edge cases of
``part1_optin.features.Feature_Assembler.fit_transform``:

- **Single-month ADB (Requirement 2.6).** A client with exactly one month of
  ADB data has no unique line through a single point, so ``adb_trend`` must be
  ``0``.
- **Inactive-only product ownership (Requirement 2.4).** A client whose only
  Product_Ownership_File rows carry a non-"Active" ``status`` has no Active rows
  for any ``product_type``, so every ``active_count_<product_type>`` column must
  be ``0``.

Each test writes minimal source CSVs to a pytest ``tmp_path`` and points a
:class:`~part1_optin.config.Config` at them. ``Feature_Assembler.fit_transform``
reads all eight approved sources, so a minimal valid CSV is written for every
one of them (a header plus a single row, or header-only where a block tolerates
no rows). No fixture or path references a ``*_answer_key*`` file (Requirement
2.14).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from part1_optin.config import Config
from part1_optin.features import (
    ACTIVE_COUNT_PREFIX,
    ADB_TREND_COLUMN,
    AVG_CONTACTS_PER_MONTH_COLUMN,
    Feature_Assembler,
)

# ---------------------------------------------------------------------------
# Canonical source headers (column order mirrors the real data/ CSVs and the
# tests/strategies_part1.py schemas).
# ---------------------------------------------------------------------------

LEADS_HEADER = "promo_id,client_id,control_group,channel_sent,joined,join_date"
DNA_HEADER = (
    "client_id,segment,age_band,region,sec_class,inflow_type,online_shopper,"
    "tenure_years,digital_app_user,frugal_flag,investment_propensity_decile,"
    "email_valid,mobile_valid"
)
PRODUCT_HEADER = "client_id,product_code,product_type,open_date,status"
ADB_HEADER = "client_id,month,adb_php"
CONTACT_HEADER = "client_id,contact_date,campaign_id,channel"
NDB_HEADER = "client_id,flag_type,flag_date"
PART2_HEADER = "client_id,total_out,ext_outflow_ratio"
PROMO_HISTORY_HEADER = (
    "promo_id,promo_name,product_type,mechanic,threshold_php,reward,"
    "start_date,end_date,channels"
)

# A single treated P001 lead for client C100000, used by both tests.
CLIENT_ID = "C100000"
PROMO_ID = "P001"


def _write(path: Path, lines: list[str]) -> None:
    """Write ``lines`` (newline-joined, trailing newline) to ``path``."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_common_sources(tmp_path: Path) -> dict[str, Path]:
    """Write minimal valid CSVs for every source and return their paths.

    Every one of the eight approved sources gets a minimal valid CSV because
    ``fit_transform`` reads all of them. The ADB and product-ownership files are
    the ones each test overrides to exercise its edge case; the rest are shared
    boilerplate (one treated P001 lead for a single client, a matching DNA row,
    a promo-history row for P001, a part2 row, a contact row, and an NDB row).
    """
    paths = {
        "promo_leads": tmp_path / "promo_leads.csv",
        "customer_dna": tmp_path / "customer_dna.csv",
        "product_ownership": tmp_path / "product_ownership.csv",
        "adb_monthly": tmp_path / "adb_monthly.csv",
        "contact_history": tmp_path / "contact_history.csv",
        "ndb": tmp_path / "ndb.csv",
        "features_part2": tmp_path / "features_part2.csv",
        "promo_history": tmp_path / "promo_history.csv",
    }

    # One treated P001 lead for CLIENT_ID (control_group 0, joined 1).
    _write(
        paths["promo_leads"],
        [LEADS_HEADER, f"{PROMO_ID},{CLIENT_ID},0,Email,1,2026-07-10"],
    )
    # A matching Customer_DNA row so the DNA block resolves (not under test).
    _write(
        paths["customer_dna"],
        [
            DNA_HEADER,
            f"{CLIENT_ID},Mass,25-34,NCR,B1,Salary,Medium,"
            "5.0,1,0,5,1,1",
        ],
    )
    # ADB defaults to a single month for CLIENT_ID; the inactive-only test keeps
    # this and the single-month test overrides it explicitly for clarity.
    _write(
        paths["adb_monthly"],
        [ADB_HEADER, f"{CLIENT_ID},2026-03,100000"],
    )
    # product_ownership defaults to a single Active row; the inactive-only test
    # overrides this with non-Active rows only.
    _write(
        paths["product_ownership"],
        [PRODUCT_HEADER, f"{CLIENT_ID},DEP-01,Deposit,2024-01-01,Active"],
    )
    # One contact row (not under test).
    _write(
        paths["contact_history"],
        [CONTACT_HEADER, f"{CLIENT_ID},2026-03-15,CMP100,Email"],
    )
    # One NDB row (not under test).
    _write(
        paths["ndb"],
        [NDB_HEADER, f"{CLIENT_ID},Loan delinquency,2026-01-01"],
    )
    # One part2 feature row (not under test).
    _write(
        paths["features_part2"],
        [PART2_HEADER, f"{CLIENT_ID},1000.0,0.25"],
    )
    # Promo history carrying P001 so the Promo_Attributes join resolves.
    _write(
        paths["promo_history"],
        [
            PROMO_HISTORY_HEADER,
            f"{PROMO_ID},Promo P001,Deposit,TOP_UP,500000,reward,"
            "2026-02-01,2026-03-31,Email",
        ],
    )
    return paths


def _config_for(paths: dict[str, Path]) -> Config:
    """Build a Config pointing at the written source CSVs."""
    return Config(
        promo_leads_path=paths["promo_leads"],
        customer_dna_path=paths["customer_dna"],
        product_ownership_path=paths["product_ownership"],
        adb_monthly_path=paths["adb_monthly"],
        contact_history_path=paths["contact_history"],
        ndb_path=paths["ndb"],
        features_part2_path=paths["features_part2"],
        promo_history_path=paths["promo_history"],
    )


def _leads_frame() -> pd.DataFrame:
    """The one-row treated-lead frame handed to ``fit_transform``.

    Matches the single treated P001 lead written to ``promo_leads.csv``; the
    assembler keys every block off ``client_id`` / ``promo_id``.
    """
    return pd.DataFrame(
        [{"promo_id": PROMO_ID, "client_id": CLIENT_ID, "Join_Label": 1}]
    )


def test_single_month_adb_yields_zero_trend(tmp_path: Path) -> None:
    """A client with exactly one month of ADB data has ``adb_trend == 0`` (2.6).

    There is no unique regression line through a single point, so the ADB_Trend
    slope must be 0 for a single-month client even though Latest_ADB is defined.
    """
    paths = _write_common_sources(tmp_path)
    # Override ADB with exactly one month for CLIENT_ID (Requirement 2.6).
    _write(
        paths["adb_monthly"],
        [ADB_HEADER, f"{CLIENT_ID},2026-03,123456.78"],
    )

    assembler = Feature_Assembler(_config_for(paths))
    X, schema = assembler.fit_transform(_leads_frame())

    # The single lead's ADB trend is exactly 0 (Requirement 2.6).
    assert ADB_TREND_COLUMN in X.columns
    assert X[ADB_TREND_COLUMN].iloc[0] == 0.0


def test_inactive_only_client_yields_zero_active_counts(tmp_path: Path) -> None:
    """A client with only non-Active products has every ``active_count`` 0 (2.4).

    All of the client's Product_Ownership_File rows carry a non-"Active"
    ``status`` (Dormant / Closed), so no ``product_type`` has an Active count and
    every discovered ``active_count_<product_type>`` column must be 0.
    """
    paths = _write_common_sources(tmp_path)
    # Override product ownership with non-Active rows only across two product
    # types, so active-count columns are discovered at fit time yet all count 0
    # (Requirement 2.4).
    _write(
        paths["product_ownership"],
        [
            PRODUCT_HEADER,
            f"{CLIENT_ID},DEP-01,Deposit,2024-01-01,Dormant",
            f"{CLIENT_ID},LN-01,Loan,2024-01-01,Closed",
        ],
    )

    assembler = Feature_Assembler(_config_for(paths))
    X, schema = assembler.fit_transform(_leads_frame())

    # Both product types are discovered as active-count columns at fit time...
    active_count_columns = [
        column for column in X.columns if column.startswith(ACTIVE_COUNT_PREFIX)
    ]
    assert active_count_columns, "expected at least one active_count_* column"
    assert set(active_count_columns) == set(schema.product_type_columns)

    # ...yet every active count is 0 because the client has no Active rows
    # (Requirement 2.4).
    for column in active_count_columns:
        assert X[column].iloc[0] == 0


def test_no_contact_client_yields_zero_avg_contacts(tmp_path: Path) -> None:
    """A client with no Contact_History_File rows has ``avg_contacts_per_month == 0`` (2.9).

    ``avg_contacts_per_month`` is a guarded division of total contact rows over
    distinct contact months, so a client with zero contact rows -- here the
    lead's client has no row in ``contact_history.csv`` -- must resolve to 0
    rather than dividing by zero.
    """
    paths = _write_common_sources(tmp_path)
    # Override contact history so the lead's client CLIENT_ID has NO rows. The
    # file carries a header plus one contact for a *different* client only, so
    # CLIENT_ID is genuinely absent from the Contact_History_File (Requirement
    # 2.9).
    _write(
        paths["contact_history"],
        [CONTACT_HEADER, "C999999,2026-03-15,CMP999,Email"],
    )

    assembler = Feature_Assembler(_config_for(paths))
    X, schema = assembler.fit_transform(_leads_frame())

    # The no-contact lead's average contacts per month is exactly 0
    # (Requirement 2.9).
    assert AVG_CONTACTS_PER_MONTH_COLUMN in X.columns
    assert X[AVG_CONTACTS_PER_MONTH_COLUMN].iloc[0] == 0.0
