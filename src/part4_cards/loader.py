"""Input_Loader for the Part4_Cards_Pipeline.

Loads, structurally validates, and type-coerces the seven input files. This is
the only component permitted to halt the run: if a file is missing or a
required column is absent it raises before any classification, card building,
output directory creation, or file write happens, satisfying the
halt-without-output guarantee of Requirement 1 (reinforced by Requirement 6.6).

Processing is split into ordered passes so the first problem of each kind is the
one reported and nothing is read halfway:

1. Existence pass over the seven configured paths in fixed order, raising
   ``FileNotFoundError`` naming the first missing path (Requirement 1.2).
2. Read each file with ``pd.read_csv(path, dtype=str, keep_default_na=False)``
   so raw values can be checked before coercion.
3. Columns pass validating each file against its required-column constant,
   raising a single ``ValueError`` naming every affected file together with its
   missing columns (Requirement 1.3). The Segment_Summary_File has no check.
4. Numeric coercion of the columns the downstream components depend on.

The loader never writes anything, so a raised error leaves ``outputs/``
untouched and no output directory is created.
"""

from __future__ import annotations

import pandas as pd

from .config import (
    CHANNEL_COSTS_REQUIRED,
    CONTACT_HISTORY_REQUIRED,
    CUSTOMER_DNA_REQUIRED,
    Config,
    NDB_REQUIRED,
    PROMO_HISTORY_REQUIRED,
    SEGMENTS_REQUIRED,
)


def load(cfg: Config) -> dict[str, pd.DataFrame]:
    """Load and validate the seven inputs, returning a dict of frames.

    The returned frames are keyed ``segments``, ``segment_summary``, ``ndb``,
    ``contact_history``, ``channel_costs``, ``customer_dna``, and
    ``promo_history``. Validation runs in ordered passes (existence, read,
    required columns) so the first structural defect of each kind is the one
    reported, then numeric columns are coerced. The loader never writes any
    output, so a raised error leaves ``outputs/`` untouched.
    """
    # (key, path, required-columns) in the fixed order of Requirement 1.1. The
    # Segment_Summary_File is a passthrough input with no required-column check,
    # signalled by ``None``.
    specs: list[tuple[str, "object", list[str] | None]] = [
        ("segments", cfg.segments_path, SEGMENTS_REQUIRED),
        ("segment_summary", cfg.segment_summary_path, None),
        ("ndb", cfg.ndb_path, NDB_REQUIRED),
        ("contact_history", cfg.contact_history_path, CONTACT_HISTORY_REQUIRED),
        ("channel_costs", cfg.channel_costs_path, CHANNEL_COSTS_REQUIRED),
        ("customer_dna", cfg.customer_dna_path, CUSTOMER_DNA_REQUIRED),
        ("promo_history", cfg.promo_history_path, PROMO_HISTORY_REQUIRED),
    ]

    # 1. Existence pass over every configured path in fixed order, raising on
    #    the first missing path before anything is read (Requirement 1.2).
    for _key, path, _required in specs:
        if not path.exists():
            raise FileNotFoundError(f"Input file does not exist: {path}")

    # 2. Read every file as raw strings so values can be checked before
    #    coercion.
    frames: dict[str, pd.DataFrame] = {}
    for key, path, _required in specs:
        frames[key] = pd.read_csv(path, dtype=str, keep_default_na=False)

    # 3. Columns pass: collect every affected file with all of its missing
    #    columns, then raise a single ValueError naming them (Requirement 1.3).
    problems: list[str] = []
    for key, path, required in specs:
        if required is None:
            continue
        missing = [col for col in required if col not in frames[key].columns]
        if missing:
            problems.append(f"{path} is missing required column(s): {', '.join(missing)}")
    if problems:
        raise ValueError("; ".join(problems))

    # 4. Numeric coercion (Requirement 1.1). ``contact_date`` stays a
    #    YYYY-MM-DD string so the distinct-month derivation works on raw text.
    frames["segments"]["p_join"] = pd.to_numeric(frames["segments"]["p_join"])
    for flag in ("digital_app_user", "email_valid", "mobile_valid"):
        frames["customer_dna"][flag] = pd.to_numeric(frames["customer_dna"][flag]).astype(int)
    frames["channel_costs"]["cost_php_per_message"] = pd.to_numeric(
        frames["channel_costs"]["cost_php_per_message"]
    )

    return frames
