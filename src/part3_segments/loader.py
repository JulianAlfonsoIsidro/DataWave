"""Input_Loader for the Part3_Segments_Pipeline.

Loads, structurally validates, and type-coerces the five input files. This is
the only component permitted to halt the run: if a file is missing or a
required column is absent it raises before any segment computation or output
write happens, satisfying the halt-without-output guarantee of Requirement 1.

For each file, validation runs in a fixed order so the first problem is the one
reported: existence, then read, then required columns, then numeric coercion.
"""

from __future__ import annotations

import pandas as pd

from .config import (
    ADB_REQUIRED,
    Config,
    FEATURES_REQUIRED,
    PROMO_HISTORY_REQUIRED,
    PROMO_LEADS_REQUIRED,
    SCORES_COLUMNS,
)


def _read_validated(path, required_columns: list[str]) -> pd.DataFrame:
    """Check existence, read raw strings, and validate required columns.

    Steps, in the fixed order required by the design:

    1. Existence: raise ``FileNotFoundError`` naming the path if absent
       (Requirement 1.2).
    2. Read: ``dtype=str, keep_default_na=False`` so raw values can be checked
       before coercion.
    3. Columns: raise ``ValueError`` naming the file and every missing column
       if any required column is absent (Requirement 1.3).
    """
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)

    missing = [col for col in required_columns if col not in frame.columns]
    if missing:
        raise ValueError(
            f"{path} is missing required column(s): {', '.join(missing)}"
        )

    return frame


def load(cfg: Config) -> dict[str, pd.DataFrame]:
    """Load and validate the five inputs, returning a dict of frames.

    The returned frames are keyed ``scores``, ``features``, ``adb``,
    ``promo_history``, and ``promo_leads``. Each file is validated (existence,
    then required columns) in a fixed order so the first structural defect is
    the one reported, and the numeric columns are coerced via
    ``pd.to_numeric`` while ``month`` is kept as a ``YYYY-MM`` string
    (Requirements 1.1-1.4). The loader never writes any output, so a raised
    error leaves ``outputs/`` untouched.
    """
    scores = _read_validated(cfg.scores_path, SCORES_COLUMNS)
    features = _read_validated(cfg.features_path, FEATURES_REQUIRED)
    adb = _read_validated(cfg.adb_monthly_path, ADB_REQUIRED)
    promo_history = _read_validated(cfg.promo_history_path, PROMO_HISTORY_REQUIRED)
    promo_leads = _read_validated(cfg.promo_leads_path, PROMO_LEADS_REQUIRED)

    # Numeric coercion (Requirement 1.4). ``month`` stays a YYYY-MM string so
    # the lexicographic latest-month selection in the Segmenter works on the
    # raw text.
    scores["p_join"] = pd.to_numeric(scores["p_join"])
    features["out_other_bank"] = pd.to_numeric(features["out_other_bank"])
    adb["adb_php"] = pd.to_numeric(adb["adb_php"])
    promo_history["threshold_php"] = pd.to_numeric(promo_history["threshold_php"])

    return {
        "scores": scores,
        "features": features,
        "adb": adb,
        "promo_history": promo_history,
        "promo_leads": promo_leads,
    }
