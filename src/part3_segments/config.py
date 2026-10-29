"""Configuration and domain constants for the Part3_Segments_Pipeline.

A single place for the five input paths and two output paths (with canonical
defaults) and the fixed domain constants, so discrepancy-prone values live in
one place. CLI overrides map onto the path fields.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Input/output paths for the pipeline, with canonical defaults.

    CLI overrides map onto these path fields (Requirements 1.1, 3.1, 4.6, 5.1).
    """

    scores_path: Path = Path("outputs/scores.csv")
    features_path: Path = Path("outputs/features_part2.csv")
    adb_monthly_path: Path = Path("data/adb_monthly.csv")
    promo_history_path: Path = Path("data/promo_history.csv")
    promo_leads_path: Path = Path("data/promo_leads.csv")
    segments_out_path: Path = Path("outputs/segments.csv")
    summary_out_path: Path = Path("outputs/segment_summary.csv")


# Columns the Scores_File must contain (Requirement 1.3).
SCORES_COLUMNS = [
    "promo_id",
    "client_id",
    "p_join",
    "top_driver_1",
    "top_driver_2",
    "top_driver_3",
]

# Columns the Features_File must contain (Requirement 1.3).
FEATURES_REQUIRED = ["client_id", "out_other_bank"]

# Columns the Adb_Monthly_File must contain (Requirement 1.3).
ADB_REQUIRED = ["client_id", "month", "adb_php"]

# Columns the Promo_History_File must contain (Requirement 1.3).
PROMO_HISTORY_REQUIRED = ["promo_id", "threshold_php"]

# Columns the Promo_Leads_File must contain (Requirement 1.3).
PROMO_LEADS_REQUIRED = ["promo_id", "client_id", "control_group", "joined"]

# The four Segment labels in order, indexed by (score_high, capacity_high):
# high/high, high/low, low/high, low/low (Requirements 2.4, 4.1).
SEGMENTS = [
    "Ready Toppers",
    "Willing but Stretched",
    "Untapped Wealth",
    "Not Now",
]

# control_group value marking a Treated_Lead (Requirement 4.3).
TREATED_CONTROL_GROUP = 0
