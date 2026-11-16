"""Configuration and domain constants for the Persona_Pipeline.

A single place for the input/output paths (with canonical defaults) and the
fixed domain constants, so discrepancy-prone values live in one place
(mirrors ``part1_optin/config.py`` and ``part4_cards/config.py``).

Governing requirements: the frozen path/constant Config and CLI override
mapping (Requirement 9.1), the match-rate gate (Requirement 1.9), the
sampling cap and cluster-count constants (Requirements 2.8, 2.9), and the
k-range selection bounds (Requirement 3.12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Input/output paths plus domain constants for the Persona_Pipeline.

    CLI overrides map ``--customer-dna``, ``--product-ownership``,
    ``--features-part2``, ``--segments``, ``--cards``, ``--leads-dir``,
    ``--promo-leads``, and ``--labeled-leads-out`` onto these fields
    (Requirement 9.1).
    """

    # Inputs reused read-only (Requirements 1.1, 1.5, 9.4)
    customer_dna_path: Path = Path("data/customer_dna.csv")
    product_ownership_path: Path = Path("data/product_ownership.csv")
    features_part2_path: Path = Path("outputs/features_part2.csv")
    segments_path: Path = Path("outputs/segments.csv")
    cards_path: Path = Path("outputs/cards.json")
    leads_dir: Path = Path("outputs/leads/")
    promo_leads_path: Path = Path("data/promo_leads.csv")
    # Output (Requirements 8.1, 8.5)
    labeled_leads_out_path: Path = Path("outputs/persona_labeled_leads.csv")

    # --- labelled domain constants (Requirements 1.9, 2.8, 2.9, 3.12) ---

    # Minimum per-source join match rate before the pipeline halts.
    min_match_rate: float = 0.5
    # Minimum group size that is large enough to cluster.
    min_group_size: int = 30
    # Per-group sampling cap for the k-prototypes fit.
    max_sample_size: int = 2000
    # Fixed seed for all stochastic operations.
    random_seed: int = 42
    # Default cluster count when k is unspecified.
    default_k: int = 3
    # Inclusive lower/upper bounds on an accepted integer k.
    k_min: int = 2
    k_max: int = 6
    # Sweep the Elbow_Plot costs during clustering. The CLI keeps it (it draws
    # the plot); the web app turns it off because it never shows the plot and
    # the sweep was most of a build's time.
    compute_elbow: bool = True


# Substring that marks a forbidden Answer_Key_File (Requirement 1.10).
ANSWER_KEY_MARKER = "_answer_key"

# k values swept for the Elbow_Plot cost curve (Requirement 2.12).
ELBOW_K_RANGE = (2, 3, 4, 5, 6)

# The only promo_ids usable as a campaign pool (Requirement 5.1).
CAMPAIGN_PROMO_IDS = ("P001", "P002", "P003")
