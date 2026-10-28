"""Shared Hypothesis strategies for the Part1_Optin_Pipeline tests.

This module is the part1 counterpart to ``tests/strategies.py`` (which serves
the part2 Feature_Builder tests) and is kept deliberately separate from it so
the two suites never share an input space. Every part1 Lead_Loader and
Feature_Assembler property test (Properties 1-9, tasks 2.x-5.x) imports the
composite strategies defined here so they all exercise the same, realistic
source frames.

Import it from a test module with an absolute import mirroring the ``src``
package style, for example::

    from tests.strategies_part1 import consistent_datasets

    @given(consistent_datasets())
    def test_feature_assembly(dataset):
        leads = dataset["leads"]
        ...

Design notes:
- Strategies are grounded in the real ``data/`` CSV schemas and value domains:
  the Customer_DNA categoricals come from the observed domains, the three
  promos are P001/P002/P003 with their real mechanics (``TOP_UP``,
  ``NEW_ACCOUNT``, ``ADB_INCREASE``), and the ADB months use the ``YYYY-MM``
  shape the ADB_File uses.
- ``promo_leads`` injects *bad* ``control_group`` and ``joined`` values (NaN,
  values outside ``{0, 1}``) so the Lead_Loader selection and label-cleaning
  rules (Requirements 1.2, 1.5, 1.6) are exercised, and ``promo_id`` draws from
  the three known promos plus out-of-set ids (Requirement 1.3).
- Each source frame has its own reusable composite strategy so a single
  property test can request exactly the frame it needs; ``consistent_datasets``
  then wires them together over one shared client-id pool so the cross-source
  join behaviour (missing flags, zero-fill) is realistically exercised.
- No strategy, and no value it emits, references an ``*_answer_key*`` file.
  The generated frames are the only inputs the Feature_Assembler ever reads.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import strategies as st

from part1_optin.config import (
    DNA_CATEGORICAL_COLUMNS,
    DNA_NUMERIC_COLUMNS,
    KNOWN_MECHANICS,
    PROMO_IDS,
)

# ---------------------------------------------------------------------------
# Domain pools (grounded in the real data/ CSVs)
# ---------------------------------------------------------------------------

# The three real promos, keyed by promo_id, with their observed mechanic and
# threshold (data/promo_history.csv). Reused for the promo-history frame and
# for the known-promo score_promo dicts.
KNOWN_PROMOS: dict[str, dict] = {
    "P001": {"mechanic": "TOP_UP", "threshold_php": 500000},
    "P002": {"mechanic": "NEW_ACCOUNT", "threshold_php": 1000},
    "P003": {"mechanic": "ADB_INCREASE", "threshold_php": 50000},
}

# promo_ids out of the training set P001/P002/P003 (Requirement 1.3): the
# Lead_Loader must drop leads carrying any of these.
OUT_OF_SET_PROMO_IDS: list[str] = ["P000", "P004", "P099", "PX"]

# Mechanics the Calibrated_Model never saw in training; score_promo must warn
# for these (Requirement 7.4) while still scoring.
UNSEEN_MECHANICS: list[str] = ["CASHBACK", "REFERRAL", "FEE_WAIVER"]

# Customer_DNA categorical domains, taken from the real customer_dna.csv.
DNA_CATEGORICAL_DOMAINS: dict[str, list[str]] = {
    "segment": ["Affluent-Preferred", "Mid-Market", "Mass"],
    "age_band": ["18-24", "25-34", "35-44", "45-54", "55+"],
    "region": ["NCR", "Luzon", "Visayas", "Mindanao"],
    "sec_class": ["A", "B1", "B2", "C1", "C2", "D", "E"],
    "inflow_type": ["Salary", "Remittance", "Business", "Pension", "Mixed"],
    "online_shopper": ["Ultra High", "Very High", "High", "Medium", "Low"],
}

# Product types observed in product_ownership.csv.
PRODUCT_TYPES: list[str] = ["Deposit", "Loan", "Investment", "Card", "Insurance"]

# Product-ownership status values; "Active" is the one Active_Product_Count
# counts (Requirements 2.3, 2.4), the rest exercise the non-Active path.
PRODUCT_STATUSES: list[str] = ["Active", "Dormant", "Closed", "Pending"]

# Contact channels observed in contact_history.csv.
CONTACT_CHANNELS: list[str] = ["Email", "SMS", "In-app", "Call"]

# The part2 numeric feature columns (outputs/features_part2.csv header minus
# client_id). Kept here so the part2-feature-row strategy matches the schema
# the real Part2_Features_File carries.
PART2_FEATURE_COLUMNS: list[str] = [
    "total_out",
    "out_other_bank",
    "ext_outflow_ratio",
    "months_with_ext_transfer",
    "inflow_share_payroll",
    "inflow_share_remittance",
    "inflow_share_business_receipts",
    "spend_share_bank_transfer",
    "spend_share_e_commerce",
    "spend_share_education",
    "spend_share_fuel",
    "spend_share_grocery",
    "spend_share_health",
    "spend_share_insurance_premium",
    "spend_share_p2p_transfer",
    "spend_share_restaurants",
    "spend_share_retail",
    "spend_share_telco",
    "spend_share_travel",
    "spend_share_utilities",
]

# ADB months span, in the YYYY-MM shape the ADB_File uses. A varied-length
# window keeps ADB_Trend (least-squares slope over the last up-to-3 months)
# exercised across the 1-month (slope 0), 2-month, and 3+-month cases.
ADB_MONTHS: list[str] = [
    "2026-01",
    "2026-02",
    "2026-03",
    "2026-04",
    "2026-05",
    "2026-06",
]

# Finite, non-negative money bounds kept well below float overflow so sums and
# slopes stay numerically meaningful.
_MIN_MONEY = 0.0
_MAX_MONEY = 5_000_000.0


# ---------------------------------------------------------------------------
# Client-id pool
# ---------------------------------------------------------------------------


def client_ids(
    *,
    min_clients: int = 1,
    max_clients: int = 6,
) -> st.SearchStrategy[list[str]]:
    """Strategy for a non-empty, unique set of client ids.

    Ids are zero-padded ``C######`` strings matching the real data so their
    natural sort is stable and obvious. A small pool keeps generated datasets
    fast while still producing clients that appear in some sources and are
    absent from others (so missing-flag / zero-fill logic is exercised).
    """
    return st.lists(
        st.integers(min_value=100000, max_value=100099).map(lambda n: f"C{n}"),
        min_size=min_clients,
        max_size=max_clients,
        unique=True,
    )


def _money(min_value: float = _MIN_MONEY) -> st.SearchStrategy[float]:
    """Finite, non-negative money amounts bounded to avoid float overflow."""
    return st.floats(
        min_value=min_value,
        max_value=_MAX_MONEY,
        allow_nan=False,
        allow_infinity=False,
    )


# ---------------------------------------------------------------------------
# Lead frame (Promo_Leads_File shape)
# ---------------------------------------------------------------------------

# control_group values: 0 marks a Treated_Lead (kept); anything else is a
# control row (dropped, Requirement 1.2). ``None`` injects a NaN after the
# frame is built so the coercion path is exercised too.
_CONTROL_GROUP_VALUES: list = [0, 1, 2, None]

# joined values: only 0 and 1 are valid labels (Requirement 1.5); the rest are
# bad labels the Lead_Loader must drop (Requirement 1.6).
_JOINED_VALUES: list = [0, 1, 2, -1, None]


@st.composite
def promo_leads_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    min_rows: int = 1,
    max_rows: int = 40,
    include_out_of_set_promos: bool = True,
) -> pd.DataFrame:
    """Composite strategy producing a Promo_Leads_File-shaped frame.

    Columns match ``data/promo_leads.csv``: ``promo_id``, ``client_id``,
    ``control_group``, ``channel_sent``, ``joined``, ``join_date``.

    The frame deliberately injects rows the Lead_Loader must drop:
    - ``control_group`` other than 0 (controls) and NaN (Requirement 1.2);
    - ``promo_id`` outside P001/P002/P003 (Requirement 1.3);
    - ``joined`` missing or outside ``{0, 1}`` (Requirement 1.6);
    - duplicate ``(promo_id, client_id)`` pairs can recur so dedup
      (Requirement 1.4) is exercised.

    Args:
        client_pool: client ids to draw from. When ``None`` a fresh pool is
            drawn so the strategy is usable standalone.
        min_rows / max_rows: bounds on the number of lead rows.
        include_out_of_set_promos: when ``True`` the ``promo_id`` pool includes
            out-of-set ids that must be filtered out.
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    promo_pool = list(PROMO_IDS)
    if include_out_of_set_promos:
        promo_pool = promo_pool + OUT_OF_SET_PROMO_IDS

    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    rows = []
    for _ in range(n):
        rows.append(
            {
                "promo_id": draw(st.sampled_from(promo_pool)),
                "client_id": draw(st.sampled_from(client_pool)),
                "control_group": draw(st.sampled_from(_CONTROL_GROUP_VALUES)),
                "channel_sent": draw(
                    st.sampled_from(["Email", "SMS", "In-app", "None (control)"])
                ),
                "joined": draw(st.sampled_from(_JOINED_VALUES)),
                "join_date": "",
            }
        )

    columns = [
        "promo_id",
        "client_id",
        "control_group",
        "channel_sent",
        "joined",
        "join_date",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Customer_DNA frame
# ---------------------------------------------------------------------------


@st.composite
def customer_dna_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    coverage: float = 0.8,
) -> pd.DataFrame:
    """Composite strategy producing a Customer_DNA_File-shaped frame.

    Categorical columns (``DNA_CATEGORICAL_COLUMNS``) draw from their observed
    domains so the deterministic ordinal encoding (Requirement 2.1) is
    exercised; numeric columns (``DNA_NUMERIC_COLUMNS``) draw realistic ranges.
    Only a subset of the client pool (governed by ``coverage``) is present, so
    absent clients trigger ``Customer_DNA_Missing_Flag`` (Requirement 2.2).
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    present = _drawn_subset(draw, client_pool, coverage)

    numeric_ranges: dict[str, st.SearchStrategy] = {
        "tenure_years": st.floats(
            min_value=0.0, max_value=40.0, allow_nan=False, allow_infinity=False
        ),
        "digital_app_user": st.sampled_from([0, 1]),
        "frugal_flag": st.sampled_from([0, 1]),
        "investment_propensity_decile": st.integers(min_value=1, max_value=10),
        "email_valid": st.sampled_from([0, 1]),
        "mobile_valid": st.sampled_from([0, 1]),
    }

    rows = []
    for client_id in present:
        row: dict = {"client_id": client_id}
        for column in DNA_CATEGORICAL_COLUMNS:
            row[column] = draw(st.sampled_from(DNA_CATEGORICAL_DOMAINS[column]))
        for column in DNA_NUMERIC_COLUMNS:
            row[column] = draw(numeric_ranges[column])
        rows.append(row)

    columns = ["client_id"] + DNA_CATEGORICAL_COLUMNS + DNA_NUMERIC_COLUMNS
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Product_Ownership frame
# ---------------------------------------------------------------------------


@st.composite
def product_ownership_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    min_rows: int = 0,
    max_rows: int = 40,
) -> pd.DataFrame:
    """Composite strategy producing a Product_Ownership_File-shaped frame.

    Columns match ``data/product_ownership.csv``: ``client_id``,
    ``product_code``, ``product_type``, ``open_date``, ``status``. ``status``
    varies across ``PRODUCT_STATUSES`` (including "Active") so
    Active_Product_Count (Requirements 2.3, 2.4) counts only the Active rows
    per ``product_type``. Zero rows is allowed so clients with no products are
    exercised.
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    rows = []
    for _ in range(n):
        product_type = draw(st.sampled_from(PRODUCT_TYPES))
        rows.append(
            {
                "client_id": draw(st.sampled_from(client_pool)),
                "product_code": draw(
                    st.text(
                        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-",
                        min_size=2,
                        max_size=8,
                    )
                ),
                "product_type": product_type,
                "open_date": "2024-01-01",
                "status": draw(st.sampled_from(PRODUCT_STATUSES)),
            }
        )

    columns = ["client_id", "product_code", "product_type", "open_date", "status"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# ADB_File frame
# ---------------------------------------------------------------------------


@st.composite
def adb_monthly_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    coverage: float = 0.8,
    max_months: int = 6,
) -> pd.DataFrame:
    """Composite strategy producing an ADB_File-shaped frame.

    Columns match ``data/adb_monthly.csv``: ``client_id``, ``month``
    (``YYYY-MM``), ``adb_php``. Each present client gets a *varied-length*
    month series (1..``max_months`` distinct months) so Latest_ADB and
    ADB_Trend (Requirements 2.5, 2.6) are exercised across the single-month
    (slope 0) and multi-month cases. Absent clients trigger
    ``ADB_Missing_Flag`` (Requirement 2.7).
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    present = _drawn_subset(draw, client_pool, coverage)

    rows = []
    for client_id in present:
        n_months = draw(st.integers(min_value=1, max_value=max_months))
        months = draw(
            st.lists(
                st.sampled_from(ADB_MONTHS),
                min_size=n_months,
                max_size=n_months,
                unique=True,
            )
        )
        for month in months:
            rows.append(
                {
                    "client_id": client_id,
                    "month": month,
                    "adb_php": draw(_money()),
                }
            )

    columns = ["client_id", "month", "adb_php"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Contact_History frame
# ---------------------------------------------------------------------------


@st.composite
def contact_history_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    min_rows: int = 0,
    max_rows: int = 40,
) -> pd.DataFrame:
    """Composite strategy producing a Contact_History_File-shaped frame.

    Columns match ``data/contact_history.csv``: ``client_id``,
    ``contact_date`` (``YYYY-MM-DD``), ``campaign_id``, ``channel``. Multiple
    contacts can land in the same or different calendar months so
    Avg_Contacts_Per_Month = total contacts / distinct months (Requirements
    2.8, 2.9) is exercised. Zero rows is allowed so no-contact clients exist.
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    rows = []
    for _ in range(n):
        month = draw(st.sampled_from(ADB_MONTHS))
        day = draw(st.integers(min_value=1, max_value=28))
        rows.append(
            {
                "client_id": draw(st.sampled_from(client_pool)),
                "contact_date": f"{month}-{day:02d}",
                "campaign_id": f"CMP{draw(st.integers(min_value=100, max_value=199))}",
                "channel": draw(st.sampled_from(CONTACT_CHANNELS)),
            }
        )

    columns = ["client_id", "contact_date", "campaign_id", "channel"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# NDB frame
# ---------------------------------------------------------------------------


@st.composite
def ndb_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    coverage: float = 0.4,
) -> pd.DataFrame:
    """Composite strategy producing an NDB_File-shaped frame.

    Columns match ``data/ndb.csv``: ``client_id``, ``flag_type``,
    ``flag_date``. Only a subset of the client pool appears so NDB_Flag is 1
    for members and 0 for non-members (Requirement 2.10).
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    present = _drawn_subset(draw, client_pool, coverage)

    rows = [
        {
            "client_id": client_id,
            "flag_type": draw(
                st.sampled_from(["Loan delinquency", "Card delinquency"])
            ),
            "flag_date": "2026-01-01",
        }
        for client_id in present
    ]

    columns = ["client_id", "flag_type", "flag_date"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Part2 features frame
# ---------------------------------------------------------------------------


@st.composite
def part2_feature_frames(
    draw: st.DrawFn,
    client_pool: list[str] | None = None,
    *,
    coverage: float = 0.8,
) -> pd.DataFrame:
    """Composite strategy producing a Part2_Features_File-shaped frame.

    One row per present ``client_id`` with the numeric part2 feature columns
    (``PART2_FEATURE_COLUMNS``). Only a subset of the pool is present so absent
    clients trigger ``Part2_Features_Missing_Flag`` (Requirement 2.12) and the
    columns are zero-filled.
    """
    if client_pool is None:
        client_pool = draw(client_ids())

    present = _drawn_subset(draw, client_pool, coverage)

    rows = []
    for client_id in present:
        row: dict = {"client_id": client_id}
        for column in PART2_FEATURE_COLUMNS:
            row[column] = draw(
                st.floats(
                    min_value=0.0,
                    max_value=1_000_000.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
        rows.append(row)

    columns = ["client_id"] + PART2_FEATURE_COLUMNS
    frame = pd.DataFrame(rows, columns=columns)
    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Promo_History frame
# ---------------------------------------------------------------------------


def promo_history_frames() -> st.SearchStrategy[pd.DataFrame]:
    """Strategy for a Promo_History_File-shaped frame of the three real promos.

    The frame is fixed to P001/P002/P003 with their real ``mechanic`` and
    ``threshold_php`` (``data/promo_history.csv``) so the Promo_Attributes join
    (Requirement 2.13) resolves for every in-set lead.
    """
    rows = [
        {
            "promo_id": promo_id,
            "promo_name": f"Promo {promo_id}",
            "product_type": "Deposit",
            "mechanic": attrs["mechanic"],
            "threshold_php": attrs["threshold_php"],
            "reward": "reward",
            "start_date": "2026-02-01",
            "end_date": "2026-03-31",
            "channels": "Email, In-app",
        }
        for promo_id, attrs in KNOWN_PROMOS.items()
    ]
    columns = [
        "promo_id",
        "promo_name",
        "product_type",
        "mechanic",
        "threshold_php",
        "reward",
        "start_date",
        "end_date",
        "channels",
    ]
    return st.just(pd.DataFrame(rows, columns=columns))


# ---------------------------------------------------------------------------
# Unseen / known promo dicts (for score_promo)
# ---------------------------------------------------------------------------


def promo_dicts(
    *,
    include_unseen: bool = True,
) -> st.SearchStrategy[dict]:
    """Strategy for an Unseen_Promo-style dict carrying at least
    ``promo_id``, ``mechanic``, and ``threshold_php`` (Requirement 7.1).

    When ``include_unseen`` is ``True`` the ``mechanic`` may be one the model
    never saw (``UNSEEN_MECHANICS``), which must trigger the reduced-reliability
    warning (Requirement 7.4); otherwise it is always a known mechanic.
    """
    mechanic_pool = list(KNOWN_MECHANICS)
    if include_unseen:
        mechanic_pool = mechanic_pool + UNSEEN_MECHANICS

    return st.builds(
        lambda promo_id, mechanic, threshold: {
            "promo_id": promo_id,
            "mechanic": mechanic,
            "threshold_php": threshold,
        },
        promo_id=st.sampled_from(["P900", "P901", "P902"]),
        mechanic=st.sampled_from(mechanic_pool),
        threshold=st.integers(min_value=0, max_value=1_000_000),
    )


# ---------------------------------------------------------------------------
# Combined consistent dataset
# ---------------------------------------------------------------------------


@st.composite
def consistent_datasets(
    draw: st.DrawFn,
    *,
    min_clients: int = 2,
    max_clients: int = 6,
) -> dict[str, pd.DataFrame]:
    """Composite strategy producing one internally consistent dataset.

    All source frames are generated over a single shared client-id pool so the
    cross-source join behaviour the Feature_Assembler relies on — present vs.
    absent clients driving the missing flags and zero-fill (Requirements 2.2,
    2.7, 2.12) — is exercised coherently. The promo frames always carry the
    three real promos so in-set leads resolve their Promo_Attributes.

    Returns:
        A dict keyed ``leads``, ``customer_dna``, ``product_ownership``,
        ``adb_monthly``, ``contact_history``, ``ndb``, ``part2_features``,
        ``promo_history`` — one frame per approved source.
    """
    clients = draw(client_ids(min_clients=min_clients, max_clients=max_clients))

    return {
        "leads": draw(promo_leads_frames(clients)),
        "customer_dna": draw(customer_dna_frames(clients)),
        "product_ownership": draw(product_ownership_frames(clients)),
        "adb_monthly": draw(adb_monthly_frames(clients)),
        "contact_history": draw(contact_history_frames(clients)),
        "ndb": draw(ndb_frames(clients)),
        "part2_features": draw(part2_feature_frames(clients)),
        "promo_history": draw(promo_history_frames()),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drawn_subset(
    draw: st.DrawFn,
    client_pool: list[str],
    coverage: float,
) -> list[str]:
    """Draw a subset of ``client_pool`` where each client is kept with roughly
    the given ``coverage`` probability.

    Keeping only a subset present in a given source is what makes some clients
    absent from it, which is exactly the condition the missing-flag / zero-fill
    requirements (2.2, 2.7, 2.12) and NDB membership (2.10) turn on. One
    independent keep flag is drawn per client, weighted so ``coverage`` is the
    chance a client is kept.
    """
    keep_flag = st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ).map(lambda p: p < coverage)
    return [
        client_id
        for client_id in client_pool
        if draw(keep_flag)
    ]
