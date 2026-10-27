"""Configuration and domain constants for the Part2_Network_Pipeline.

A single place for the input/output paths (with canonical defaults) and the
fixed domain constants, so discrepancy-prone values live in one place.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Input/output paths for the pipeline, with canonical defaults.

    CLI overrides map ``--transactions``, ``--promo-leads``, and ``--out`` onto
    these three fields (Requirements 1.1, 8.1, 9.1).
    """

    transactions_path: Path = Path("data/transactions.csv")
    promo_leads_path: Path = Path("data/promo_leads.csv")
    output_path: Path = Path("outputs/features_part2.csv")


# Columns the Transactions_File must contain (Requirement 1.3).
REQUIRED_COLUMNS = [
    "client_id",
    "txn_date",
    "direction",
    "amount_php",
    "counterparty_type",
    "counterparty_category",
]

# An External_Outflow is an Outflow whose counterparty_type equals this value
# (Requirement 3.2).
EXTERNAL_COUNTERPARTY_TYPE = "Other bank"

# The funding categories used for inflow-share features (Requirement 6.1).
INFLOW_SOURCES = ["Payroll", "Remittance", "Business receipts"]

# Mapping from each Inflow_Source to its output column name (Requirement 6.6).
INFLOW_SHARE_COLUMNS = {
    "Payroll": "inflow_share_payroll",
    "Remittance": "inflow_share_remittance",
    "Business receipts": "inflow_share_business_receipts",
}

# Column-name prefix for each dynamically discovered Spending_Category share
# (Requirement 7.3); the normalized category value is appended to it.
SPEND_SHARE_PREFIX = "spend_share_"

# Promo identifier whose treated leads drive the validation report
# (Requirement 9.2).
P001_PROMO_ID = "P001"

# control_group value marking a Treated_Lead (Requirement 9.2).
TREATED_CONTROL_GROUP = 0
