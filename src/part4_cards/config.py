"""Configuration and domain constants for the Part4_Cards_Pipeline.

A single place for the seven input paths and two output paths (with canonical
defaults), the fixed domain constants stated as labelled assumptions, and the
required-column lists used by the loader. CLI overrides map onto the path
fields (Requirements 1.1, 1.4, 6.1).
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Input/output paths for the pipeline, with canonical defaults.

    CLI overrides map onto these path fields exactly as in part3_segments
    (Requirements 1.1, 1.4, 6.1).
    """

    segments_path: Path = Path("outputs/segments.csv")
    segment_summary_path: Path = Path("outputs/segment_summary.csv")
    ndb_path: Path = Path("data/ndb.csv")
    contact_history_path: Path = Path("data/contact_history.csv")
    channel_costs_path: Path = Path("data/channel_costs.csv")
    customer_dna_path: Path = Path("data/customer_dna.csv")
    promo_history_path: Path = Path("data/promo_history.csv")
    cards_out_path: Path = Path("outputs/cards.json")
    leads_out_dir: Path = Path("outputs/leads/")


# --- labelled assumptions (config constants, Requirement 1.4) ---

# ASSUMPTION: peso value of one join.
VALUE_PER_JOIN_PHP = 1000

# ASSUMPTION: fixed seed for the control holdout (never changes between runs).
CONTROL_SEED = 42

# ASSUMPTION: control holdout fraction per cell.
CONTROL_FRACTION = 0.10

# ASSUMPTION: z-score for a 90% two-sided range.
Z_90 = 1.645

# ASSUMPTION: strict best_channel priority order (In-app before Email before SMS).
CHANNEL_PRIORITY = ["In-app", "Email", "SMS"]

# The four Part 3 segment labels, in fixed order.
SEGMENTS = [
    "Ready Toppers",
    "Willing but Stretched",
    "Untapped Wealth",
    "Not Now",
]

# ASSUMPTION: fixed per-segment message angle.
MESSAGE_ANGLES = {
    "Ready Toppers": "Top up now and unlock your next reward tier",
    "Willing but Stretched": "A smaller step that still moves you forward",
    "Untapped Wealth": "Bring your savings home and keep your status",
    "Not Now": "Stay with us — here when you are ready",
}

# channel -> DNA reachability flag that gates it.
CHANNEL_FLAG = {
    "In-app": "digital_app_user",
    "Email": "email_valid",
    "SMS": "mobile_valid",
}


# --- required-column constants per file (for loader validation, Requirement 1.3) ---

# Columns the Segments_File must contain.
SEGMENTS_REQUIRED = ["promo_id", "client_id", "p_join", "segment", "top_driver_1"]

# Columns the Customer_Dna_File must contain.
CUSTOMER_DNA_REQUIRED = ["client_id", "digital_app_user", "email_valid", "mobile_valid"]

# Columns the Promo_History_File must contain.
PROMO_HISTORY_REQUIRED = ["promo_id", "channels", "mechanic"]

# Columns the Channel_Costs_File must contain.
CHANNEL_COSTS_REQUIRED = ["channel", "cost_php_per_message"]

# Columns the Ndb_File must contain.
NDB_REQUIRED = ["client_id"]

# Columns the Contact_History_File must contain.
CONTACT_HISTORY_REQUIRED = ["client_id", "contact_date"]
