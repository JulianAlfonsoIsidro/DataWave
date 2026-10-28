"""Configuration and domain constants for the Part1_Optin_Pipeline.

A single place for the input/output paths (with canonical defaults) and the
fixed domain constants, so discrepancy-prone values live in one place
(mirrors ``part2_network/config.py``).
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Input/output paths for the pipeline, with canonical defaults.

    CLI overrides map ``--promo-leads``, ``--customer-dna``,
    ``--product-ownership``, ``--adb``, ``--contact-history``, ``--ndb``,
    ``--features-part2``, ``--promo-history``, ``--model-out``, and
    ``--scores-out`` onto these fields (Requirement 7.8).
    """

    # Inputs (Requirements 1.1, 2.*, 7.8)
    promo_leads_path: Path = Path("data/promo_leads.csv")
    customer_dna_path: Path = Path("data/customer_dna.csv")
    product_ownership_path: Path = Path("data/product_ownership.csv")
    adb_monthly_path: Path = Path("data/adb_monthly.csv")
    contact_history_path: Path = Path("data/contact_history.csv")
    ndb_path: Path = Path("data/ndb.csv")
    features_part2_path: Path = Path("outputs/features_part2.csv")
    promo_history_path: Path = Path("data/promo_history.csv")
    # Outputs (Requirements 6.1, 6.3)
    model_output_path: Path = Path("outputs/model_part1.json")
    scores_output_path: Path = Path("outputs/scores.csv")


# control_group value marking a Treated_Lead (Requirement 1.2).
TREATED_CONTROL_GROUP = 0

# The only promo_ids kept for training (Requirement 1.3) and the LOPO folds
# (Requirement 4.1).
PROMO_IDS = ["P001", "P002", "P003"]

# Fixed seed for all stochastic operations (Requirement 3.2).
RANDOM_SEED = 42

# Calibration table bin count over [0, 1] (Requirement 4.4).
N_CALIBRATION_BINS = 10

# Top-quintile fraction for capture rate (Requirement 4.3).
TOP_QUINTILE = 0.20

# Customer_DNA categorical columns encoded to numeric codes (Requirement 2.1).
DNA_CATEGORICAL_COLUMNS = [
    "segment",
    "age_band",
    "region",
    "sec_class",
    "inflow_type",
    "online_shopper",
]

# Customer_DNA numeric/binary columns passed through as-is (Requirement 2.1).
DNA_NUMERIC_COLUMNS = [
    "tenure_years",
    "digital_app_user",
    "frugal_flag",
    "investment_propensity_decile",
    "email_valid",
    "mobile_valid",
]

# Promo mechanic is a categorical predictor (Requirement 2.13).
PROMO_MECHANIC_COLUMN = "mechanic"

# Mechanics observed in the known promos, for the unseen-mechanic warning
# (Requirement 7.4).
KNOWN_MECHANICS = ["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"]

# Substring that marks a forbidden Answer_Key_File (Requirement 2.14).
ANSWER_KEY_MARKER = "_answer_key"
