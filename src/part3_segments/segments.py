"""Segmenter for the Part3_Segments_Pipeline.

Computes per-lead capacity, score, and segment assignment over the validated
input frames, and writes the per-lead Segments_File. This module never halts
the run on input-shape grounds; the Input_Loader has already guaranteed valid,
coerced frames.

``assign`` builds the per-lead frame from the scores frame and augments it with
the computed columns: ``latest_adb``, ``out_other_bank``, ``capacity_php``,
``threshold_php``, ``capacity_high``, ``promo_median``, ``score_high``, and
``segment``. A later task adds ``write``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import SEGMENTS

# The Segments_File columns, in the exact required output order
# (Requirement 3.1).
SEGMENTS_FILE_COLUMNS = [
    "promo_id",
    "client_id",
    "p_join",
    "capacity_php",
    "segment",
    "top_driver_1",
    "top_driver_2",
    "top_driver_3",
]


def _latest_adb(adb: pd.DataFrame) -> pd.DataFrame:
    """Latest-month ``adb_php`` per client.

    For each client, select the row with the lexicographically greatest
    ``month`` (the ``YYYY-MM`` strings sort correctly as text) and take its
    ``adb_php``. Returns a frame with columns ``client_id`` and ``latest_adb``
    (Requirements 1.5, 2.1).
    """
    if adb.empty:
        return pd.DataFrame({"client_id": [], "latest_adb": []})

    # Pick the greatest month per client by sorting and taking the last row.
    idx = adb.groupby("client_id")["month"].idxmax()
    latest = adb.loc[idx, ["client_id", "adb_php"]].rename(
        columns={"adb_php": "latest_adb"}
    )
    return latest.reset_index(drop=True)


def assign(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the per-lead frame and compute capacity.

    Starts from the scores frame (one row per Lead) and attaches:

    - ``latest_adb``: each client's ``adb_php`` at the lexicographically
      greatest ``month`` in the ADB frame, left-joined by ``client_id`` and
      ``fillna(0)`` for clients with no ADB row (Requirements 1.5, 2.1).
    - ``out_other_bank``: the features ``out_other_bank`` left-joined by
      ``client_id`` and ``fillna(0)`` for clients with no features row
      (Requirement 1.5).
    - ``capacity_php``: ``latest_adb + out_other_bank`` (Requirement 2.1).

    The frame is intentionally structured so later tasks can append
    ``capacity_high``, ``promo_median``, ``score_high``, and ``segment``.
    """
    leads = frames["scores"].copy()

    # latest_adb per client, left-joined onto leads with missing -> 0.
    latest = _latest_adb(frames["adb"])
    leads = leads.merge(latest, on="client_id", how="left")
    leads["latest_adb"] = leads["latest_adb"].fillna(0)

    # out_other_bank per client, left-joined onto leads with missing -> 0.
    features = frames["features"][["client_id", "out_other_bank"]]
    leads = leads.merge(features, on="client_id", how="left")
    leads["out_other_bank"] = leads["out_other_bank"].fillna(0)

    # Capacity is the sum of the two terms (Requirement 2.1).
    leads["capacity_php"] = leads["latest_adb"] + leads["out_other_bank"]

    # threshold_php per promo, left-joined by promo_id. A promo absent from the
    # promo history leaves threshold_php as NaN (Requirement 1.6).
    promo_history = frames["promo_history"][["promo_id", "threshold_php"]]
    leads = leads.merge(promo_history, on="promo_id", how="left")

    # capacity_high: capacity_php >= threshold_php. A NaN threshold (missing
    # promo) yields False, placing every Lead of that promo in the low-capacity
    # column (Requirements 1.6, 2.2).
    leads["capacity_high"] = leads["capacity_php"] >= leads["threshold_php"]

    # promo_median: per-promo median p_join; score_high is the at-or-above
    # test so a Lead at its promo median counts as high (Requirement 2.3).
    leads["promo_median"] = leads.groupby("promo_id")["p_join"].transform(
        "median"
    )
    leads["score_high"] = leads["p_join"] >= leads["promo_median"]

    # segment: map the 2x2 quadrant of (score_high, capacity_high) onto the
    # four labels, in the SEGMENTS order high/high, high/low, low/high, low/low
    # (Requirement 2.4).
    score_high = leads["score_high"]
    capacity_high = leads["capacity_high"]
    conditions = [
        score_high & capacity_high,
        score_high & ~capacity_high,
        ~score_high & capacity_high,
        ~score_high & ~capacity_high,
    ]
    leads["segment"] = np.select(conditions, SEGMENTS, default="")

    return leads


def write(leads: pd.DataFrame, path: Path) -> None:
    """Write the per-lead Segments_File.

    Creates the parent directory if needed (Requirement 3.3), then writes the
    leads frame as CSV without the index, selecting and ordering exactly the
    eight required columns (Requirement 3.1): ``promo_id``, ``client_id``,
    ``p_join``, ``capacity_php``, ``segment``, ``top_driver_1``,
    ``top_driver_2``, ``top_driver_3``. One row is written per Lead
    (Requirement 3.2); the intermediate columns produced by ``assign``
    (``latest_adb``, ``out_other_bank``, ``threshold_php``, ``capacity_high``,
    ``promo_median``, ``score_high``) are dropped.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    leads[SEGMENTS_FILE_COLUMNS].to_csv(path, index=False)
