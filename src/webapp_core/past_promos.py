"""Predicted-vs-actual join rates for the PAST PROMOS tab (Requirements 5.2, 5.4).

The PAST PROMOS surface reads the on-disk Cards_File (``outputs/cards.json``)
and the historical outcomes in ``data/promo_leads.csv`` and shows, per Past_Promo
cell (a ``(promo_id, segment)`` pair), the model's Predicted_Join_Rate next to
the Actual_Join_Rate that actually happened.

This module is pure. :func:`predicted_vs_actual` computes both rates from data
passed in; the small :func:`read_sendable_ids_by_cell` helper does the one bit
of I/O -- reading each cell's Sendable_Lead client ids from the per-segment CSVs
the Part 4 pipeline wrote under ``outputs/leads/``.

Rates and NA handling (design Property 4):

- ``predicted = expected_joiners / sendable_count``, NA when ``sendable_count``
  is 0 (never a divide-by-zero).
- ``actual = mean(joined)`` over that cell's Sendable_Leads found in
  ``promo_leads``, NA when the cell has no Sendable_Leads.

NA is represented as ``float("nan")`` consistently (both rate fields are floats
or NaN), so downstream formatting can test with ``math.isnan`` / ``pd.isna``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd

# Columns of the per-segment sendable-lead CSVs the Part 4 pipeline writes.
_LEADS_CLIENT_COL = "client_id"
_LEADS_CONTROL_COL = "control"

# Default location of the per-cell sendable-lead CSVs.
_DEFAULT_LEADS_DIR = Path("outputs/leads")


def _segment_slug(segment: str) -> str:
    """Slugify a segment label the same way the Part 4 Reporter does.

    The segment is lowercased and every run of one or more non-alphanumeric
    characters is replaced by a single underscore, matching
    ``part4_cards.main._segment_slug`` so the filenames line up exactly
    ("Ready Toppers" -> "ready_toppers", "Willing but Stretched" ->
    "willing_but_stretched").
    """
    return re.sub(r"[^a-z0-9]+", "_", str(segment).lower())


def read_sendable_ids_by_cell(
    cards: Iterable[Mapping],
    leads_dir: Path | str = _DEFAULT_LEADS_DIR,
) -> dict[tuple[str, str], set[str]]:
    """Read each cell's Sendable_Lead client ids from ``outputs/leads/``.

    For every ``(promo_id, segment)`` cell named in ``cards``, reads the
    per-cell CSV ``<promo_id>_<segment_slug>.csv`` under ``leads_dir`` and
    returns the set of its Sendable_Lead ``client_id`` values -- the rows whose
    ``control`` is 0. The Part 4 Reporter already writes only sendable rows
    (``control`` always 0) to these files, so the ``control == 0`` filter is a
    defensive no-op that also tolerates a file that happens to carry control
    rows.

    A cell whose file is missing or empty maps to an empty set, so the caller
    can treat "no file" and "file with no sendable rows" identically (both mean
    the cell has no Sendable_Leads). Returns a dict keyed by
    ``(promo_id, segment)``.
    """
    leads_dir = Path(leads_dir)
    by_cell: dict[tuple[str, str], set[str]] = {}

    for card in cards:
        promo_id = str(card["promo_id"])
        segment = str(card["segment"])
        key = (promo_id, segment)
        if key in by_cell:
            continue

        path = leads_dir / f"{promo_id}_{_segment_slug(segment)}.csv"
        if not path.exists():
            by_cell[key] = set()
            continue

        frame = pd.read_csv(path, dtype={_LEADS_CLIENT_COL: "object"})
        if frame.empty or _LEADS_CLIENT_COL not in frame.columns:
            by_cell[key] = set()
            continue

        if _LEADS_CONTROL_COL in frame.columns:
            control = pd.to_numeric(frame[_LEADS_CONTROL_COL], errors="coerce")
            frame = frame[control == 0]

        by_cell[key] = set(frame[_LEADS_CLIENT_COL].astype(str))

    return by_cell


def predicted_vs_actual(
    cards: Iterable[Mapping],
    promo_leads: pd.DataFrame,
    sendable_ids_by_cell: Mapping[tuple[str, str], Iterable[str]],
) -> list[dict]:
    """Predicted vs actual join rate per Past_Promo cell (Requirements 5.2, 5.4).

    For each card (one per ``(promo_id, segment)`` cell), returns a Row dict::

        {
            "promo_id": str,
            "segment": str,
            "sendable_count": int,
            "predicted": float | nan,   # expected_joiners / sendable_count
            "actual": float | nan,      # mean(joined) over sendable leads
        }

    ``predicted`` is NA (``float("nan")``) when the card's ``sendable_count`` is
    0, never a divide-by-zero. ``actual`` is the mean of ``joined`` over the
    rows of ``promo_leads`` for this ``promo_id`` whose ``client_id`` is in the
    cell's sendable id set, and is NA when that set is empty (the cell has no
    Sendable_Leads). Both rates, when present, lie in ``[0, 1]`` (``joined`` is
    0/1 and ``expected_joiners`` is a sum of per-lead probabilities bounded by
    the sendable count).

    The function is pure: ``sendable_ids_by_cell`` is supplied by the caller
    (typically via :func:`read_sendable_ids_by_cell`), so it performs no I/O.
    """
    rows: list[dict] = []

    # Index promo_leads once by promo_id for the per-cell actual computation.
    has_leads = (
        promo_leads is not None
        and not promo_leads.empty
        and {"promo_id", "client_id", "joined"}.issubset(promo_leads.columns)
    )
    if has_leads:
        leads = promo_leads.copy()
        leads["promo_id"] = leads["promo_id"].astype(str)
        leads["client_id"] = leads["client_id"].astype(str)
        leads["joined"] = pd.to_numeric(leads["joined"], errors="coerce")

    for card in cards:
        promo_id = str(card["promo_id"])
        segment = str(card["segment"])
        sendable_count = int(card.get("sendable_count", 0) or 0)
        expected_joiners = float(card.get("expected_joiners", 0.0) or 0.0)

        # Predicted: NA when there are no sendable leads to divide across.
        predicted = (
            expected_joiners / sendable_count
            if sendable_count > 0
            else math.nan
        )

        # Actual: mean(joined) over this cell's sendable leads; NA when the cell
        # has no Sendable_Leads.
        sendable_ids = {str(cid) for cid in sendable_ids_by_cell.get((promo_id, segment), ())}
        if not sendable_ids or not has_leads:
            actual = math.nan
        else:
            cell = leads[
                (leads["promo_id"] == promo_id)
                & (leads["client_id"].isin(sendable_ids))
            ]
            actual = float(cell["joined"].mean()) if not cell.empty else math.nan

        rows.append(
            {
                "promo_id": promo_id,
                "segment": segment,
                "sendable_count": sendable_count,
                "predicted": predicted,
                "actual": actual,
            }
        )

    return rows
