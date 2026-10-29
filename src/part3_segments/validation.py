"""Summary_Builder for the Part3_Segments_Pipeline.

Builds the per-cell Segment_Summary over the assigned leads crossed with the
fixed four-segment universe, and writes the Segment_Summary_File. This module
never halts the run on input-shape grounds; the Input_Loader has already
guaranteed valid, coerced frames and the Segmenter has assigned every Lead.

``build`` groups the assigned leads by (``promo_id``, ``segment``) to compute
the per-cell client count, mean ``p_join``, Expected_Joiners (sum of
``p_join``), and the most common ``top_driver_1`` (mode, with a deterministic
tie-break), then reindexes onto the full cross product of distinct scores
``promo_id`` x the four ``SEGMENTS`` so every cell appears, zero/empty-filling
the empty ones (Requirements 4.1, 4.2, 4.5). It then attaches the treated-lead
``actual_join_rate``: the fraction of each cell's Treated_Leads (promo-leads
with ``control_group`` 0, inner-joined to the assigned leads on
(``promo_id``, ``client_id``)) whose ``joined`` equals 1, leaving the rate
empty for cells with zero treated leads (Requirements 4.3, 4.4). A later task
adds ``write``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import SEGMENTS, TREATED_CONTROL_GROUP

# The Segment_Summary_File columns, in the exact required output order
# (design "Output: Segment_Summary_File schema").
SUMMARY_COLUMNS = [
    "promo_id",
    "segment",
    "n_clients",
    "mean_p_join",
    "expected_joiners",
    "actual_join_rate",
    "top_driver_1",
]


def _mode_top_driver(values: pd.Series) -> str:
    """Most common ``top_driver_1`` in a cell, with a deterministic tie-break.

    Returns the modal value; when several values tie for most common, the one
    that sorts first (lexicographically) is chosen so the result is
    reproducible across runs (Requirement 4.5). An empty cell yields the empty
    string.
    """
    counts = values.value_counts()
    if counts.empty:
        return ""
    top_count = counts.iloc[0]
    tied = [value for value, count in counts.items() if count == top_count]
    return sorted(tied)[0]


def _actual_join_rate(leads: pd.DataFrame, promo_leads: pd.DataFrame) -> pd.Series:
    """Per-cell Actual_Join_Rate over Treated_Leads.

    Filters ``promo_leads`` to Treated_Leads (``control_group`` equal to the
    treated marker), inner-joins them to the assigned ``leads`` on the Lead key
    (``promo_id``, ``client_id``) so each treated lead inherits its cell's
    ``segment``, then computes per (``promo_id``, ``segment``) cell the fraction
    of treated leads whose ``joined`` equals 1 (Requirement 4.3).

    Because ``promo_leads`` is loaded as strings by the Input_Loader,
    ``control_group`` is compared to the treated marker in a string-robust way
    and ``joined`` is coerced to numeric (non-numeric values become NaN and are
    excluded from the mean). The returned Series is indexed by
    (``promo_id``, ``segment``) and contains only the cells that have at least
    one treated lead; cells with zero treated leads are simply absent so the
    caller leaves their rate empty (Requirement 4.4).
    """
    if promo_leads.empty or leads.empty:
        return pd.Series(
            dtype="float64",
            index=pd.MultiIndex.from_arrays(
                [[], []], names=["promo_id", "segment"]
            ),
        )

    # control_group arrives as a string from the loader; compare robustly to
    # the treated marker so "0" (and a stray "0.0") count as treated.
    control = promo_leads["control_group"].astype(str).str.strip()
    treated_marker = str(TREATED_CONTROL_GROUP)
    is_treated = (control == treated_marker) | (control == f"{treated_marker}.0")
    treated = promo_leads.loc[is_treated, ["promo_id", "client_id", "joined"]]

    if treated.empty:
        return pd.Series(
            dtype="float64",
            index=pd.MultiIndex.from_arrays(
                [[], []], names=["promo_id", "segment"]
            ),
        )

    # Inner-join to attach each treated lead's segment; a treated promo-lead
    # with no matching scored Lead drops out (it belongs to no cell).
    attached = treated.merge(
        leads[["promo_id", "client_id", "segment"]],
        on=["promo_id", "client_id"],
        how="inner",
    )

    if attached.empty:
        return pd.Series(
            dtype="float64",
            index=pd.MultiIndex.from_arrays(
                [[], []], names=["promo_id", "segment"]
            ),
        )

    # joined is a string from the loader; coerce to numeric so the mean is the
    # fraction of treated leads with joined == 1.
    attached = attached.assign(
        joined=pd.to_numeric(attached["joined"], errors="coerce")
    )

    return attached.groupby(["promo_id", "segment"], sort=False)["joined"].mean()


def build(leads: pd.DataFrame, promo_leads: pd.DataFrame) -> pd.DataFrame:
    """Build the per-cell Segment_Summary.

    Groups the assigned ``leads`` by (``promo_id``, ``segment``) and computes,
    per cell: ``n_clients`` (count of Leads), ``mean_p_join`` (mean of
    ``p_join``), ``expected_joiners`` (sum of ``p_join``), and ``top_driver_1``
    (the most common ``top_driver_1`` value, ties broken by sort order for
    determinism) (Requirement 4.2).

    The per-cell aggregates are then reindexed onto the full cross product of
    the distinct scores ``promo_id`` values with the four ``SEGMENTS`` labels,
    so a cell with no Leads still appears with ``n_clients`` 0, ``mean_p_join``
    0, ``expected_joiners`` 0, and a blank ``top_driver_1`` (Requirements 4.1,
    4.5).

    The ``actual_join_rate`` column is the fraction of each cell's Treated_Leads
    (``promo_leads`` rows with ``control_group`` 0, inner-joined to the assigned
    leads on (``promo_id``, ``client_id``)) whose ``joined`` equals 1; a cell
    with zero treated leads keeps an empty rate rather than 0 (Requirements 4.3,
    4.4). The returned frame carries the full summary column set in the required
    order.
    """
    # Per-cell aggregates over the assigned leads. Grouping with a non-empty
    # frame yields one row per populated (promo_id, segment) pair.
    if leads.empty:
        grouped = pd.DataFrame(
            {
                "promo_id": pd.Series(dtype=object),
                "segment": pd.Series(dtype=object),
                "n_clients": pd.Series(dtype="int64"),
                "mean_p_join": pd.Series(dtype="float64"),
                "expected_joiners": pd.Series(dtype="float64"),
                "top_driver_1": pd.Series(dtype=object),
            }
        )
    else:
        grouped = (
            leads.groupby(["promo_id", "segment"], sort=False)
            .agg(
                n_clients=("p_join", "size"),
                mean_p_join=("p_join", "mean"),
                expected_joiners=("p_join", "sum"),
                top_driver_1=("top_driver_1", _mode_top_driver),
            )
            .reset_index()
        )

    # Full cross product of distinct scores promo_id x the four SEGMENTS. Using
    # the distinct promos in lead order keeps the promo ordering stable, and
    # SEGMENTS fixes the four-segment order (Requirements 4.1, 4.5).
    promo_ids = pd.unique(leads["promo_id"]) if not leads.empty else []
    cells = pd.MultiIndex.from_product(
        [promo_ids, SEGMENTS], names=["promo_id", "segment"]
    )

    summary = (
        grouped.set_index(["promo_id", "segment"])
        .reindex(cells)
        .reset_index()
    )

    # Zero-fill the numeric aggregates and blank-fill the text for empty cells
    # (Requirement 4.5).
    summary["n_clients"] = summary["n_clients"].fillna(0).astype("int64")
    summary["mean_p_join"] = summary["mean_p_join"].fillna(0.0)
    summary["expected_joiners"] = summary["expected_joiners"].fillna(0.0)
    summary["top_driver_1"] = summary["top_driver_1"].fillna("")

    # Treated-lead Actual_Join_Rate per cell (Requirements 4.3, 4.4). Map the
    # per-cell rate onto the full cross product by cell key; cells with no
    # treated leads are absent from the rate Series and so map to NaN, i.e. an
    # empty rate rather than 0.
    rate = _actual_join_rate(leads, promo_leads)
    cell_key = pd.MultiIndex.from_frame(summary[["promo_id", "segment"]])
    summary["actual_join_rate"] = rate.reindex(cell_key).to_numpy()

    return summary[SUMMARY_COLUMNS]


def write(summary: pd.DataFrame, path: Path) -> None:
    """Write the per-cell Segment_Summary_File.

    Creates the parent directory if needed (Requirement 4.6), then writes the
    summary frame as CSV without the index, with a single header row carrying
    the ``SUMMARY_COLUMNS`` in their required order (``promo_id``, ``segment``,
    ``n_clients``, ``mean_p_join``, ``expected_joiners``, ``actual_join_rate``,
    ``top_driver_1``). A cell with an empty ``actual_join_rate`` (NaN, for a
    cell with zero treated leads) serializes as an empty field (Requirement
    4.4).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    summary[SUMMARY_COLUMNS].to_csv(path, index=False)
