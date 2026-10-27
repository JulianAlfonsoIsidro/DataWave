"""Validation_Reporter for the Part2_Network_Pipeline.

Reports how the P001 promo's Treated_Leads land against the computed
Features_File. This module holds the lead-side scaffolding every later report
step builds on:

- reading the Promo_Leads_File into a frame with ``control_group`` and
  ``joined`` coerced to numbers so they compare reliably (Requirement 9.1),
- selecting the P001 Treated_Leads -- ``promo_id`` "P001" and ``control_group``
  0 (Requirement 9.2), and
- inner-joining those leads to the Features_File on ``client_id``
  (Requirement 9.3).

On top of those helpers it layers the quartile binning and Join_Rate reporting:

- assigning each joined lead to one of four equal-count Ext_Outflow_Quartile
  bins ordered by ascending ``ext_outflow_ratio`` and tie-broken by ascending
  ``client_id`` (Requirements 9.4, 9.5),
- computing the per-quartile Join_Rate and the overall inner-join rate
  (Requirements 9.6, 9.8),
- building a structured report result tests can assert on without parsing
  stdout, and
- printing that report -- one line per quartile plus the overall rate, or a
  no-matching-leads message when no P001 Treated_Leads are selected
  (Requirements 9.7, 9.9).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from part2_network.config import P001_PROMO_ID, TREATED_CONTROL_GROUP

# Ext_Outflow_Quartile bin labels, in report order (Requirements 9.4, 9.7).
QUARTILE_LABELS = ["Q1", "Q2", "Q3", "Q4"]


def read_leads(path: Path) -> pd.DataFrame:
    """Load the Promo_Leads_File (Requirement 9.1).

    Reads the CSV with pandas and coerces the two columns the selection depends
    on -- ``control_group`` and ``joined`` -- to numbers via ``to_numeric`` so
    they compare reliably against the integer constants regardless of how the
    raw CSV typed them (e.g. a quoted "0"). Unparseable values become ``NaN``,
    which simply fails the ``== 0`` / ``== 1`` equality tests downstream rather
    than raising, so a malformed flag drops a lead instead of halting the
    report.

    ``promo_id`` and ``client_id`` are left as read so they match the string
    ``P001_PROMO_ID`` and the Features_File ``client_id`` values on their native
    types. Unlike the Transaction_Reader, this reader never halts the pipeline.

    Args:
        path: Path to the Promo_Leads_File CSV.

    Returns:
        The promo-leads frame with numeric ``control_group`` and ``joined``.
    """
    leads = pd.read_csv(Path(path))
    if "control_group" in leads.columns:
        leads["control_group"] = pd.to_numeric(
            leads["control_group"], errors="coerce"
        )
    if "joined" in leads.columns:
        leads["joined"] = pd.to_numeric(leads["joined"], errors="coerce")
    return leads


def select_treated_leads(leads: pd.DataFrame) -> pd.DataFrame:
    """Keep only the P001 Treated_Leads (Requirement 9.2).

    A P001 Treated_Lead is a row whose ``promo_id`` equals
    :data:`P001_PROMO_ID` ("P001") and whose ``control_group`` equals
    :data:`TREATED_CONTROL_GROUP` (0). Rows for other promos (e.g. "P002") and
    control rows (``control_group`` 1) are dropped; rows whose numeric
    ``control_group`` is ``NaN`` also fail the equality test and are dropped.

    Args:
        leads: The promo-leads frame from :func:`read_leads`.

    Returns:
        The subset of rows that are P001 Treated_Leads.
    """
    is_p001 = leads["promo_id"] == P001_PROMO_ID
    is_treated = leads["control_group"] == TREATED_CONTROL_GROUP
    return leads[is_p001 & is_treated]


def join_to_features(
    treated_leads: pd.DataFrame, features: pd.DataFrame
) -> pd.DataFrame:
    """Inner-join P001 Treated_Leads to the Features_File (Requirement 9.3).

    Joins on ``client_id`` with an inner join, so only leads whose
    ``client_id`` appears in ``features`` survive -- and only feature rows that
    a selected lead points at. The result carries the lead columns (including
    ``joined``, used for Join_Rate) alongside the feature columns (including
    ``ext_outflow_ratio``, used for quartile binning) for each matched client.

    Args:
        treated_leads: The P001 Treated_Leads from :func:`select_treated_leads`.
        features: The per-client Features_File frame (one row per ``client_id``).

    Returns:
        The inner join of the treated leads and features on ``client_id``.
    """
    return treated_leads.merge(features, on="client_id", how="inner")


def assign_quartiles(joined_leads: pd.DataFrame) -> pd.Series:
    """Assign each joined P001 Treated_Lead to a quartile label (Req 9.4, 9.5).

    Orders the joined leads by ascending ``ext_outflow_ratio``, breaking ties by
    ascending ``client_id`` (Requirement 9.5), then splits them into four
    equal-count Ext_Outflow_Quartile bins whose counts differ by at most one
    (Requirement 9.4). The split is purely position-based over the sorted order
    -- :func:`numpy.array_split` partitions the sorted row positions into four
    contiguous groups -- so it does *not* merge or split ties by value the way
    :func:`pandas.qcut` would; a tie that straddles a bin boundary is placed by
    the ``client_id`` tie-break, not collapsed into one bin.

    With ``n`` leads, ``array_split`` yields bins of size ``ceil(n/4)`` for the
    first ``n % 4`` bins and ``floor(n/4)`` for the rest, so sizes differ by at
    most one. When ``n < 4`` some trailing bins are empty (e.g. ``n == 2`` gives
    Q1 and Q2 one lead each and Q3, Q4 none); empty bins carry no rows and are
    handled as non-contributing by the report (Requirement 9.6).

    Args:
        joined_leads: The inner join from :func:`join_to_features`, carrying
            ``ext_outflow_ratio`` (from the features) and ``client_id``.

    Returns:
        A Series of quartile labels ("Q1".."Q4") indexed exactly like
        ``joined_leads`` -- each original row mapped to its bin -- so it can be
        assigned straight back as a column or grouped on.
    """
    # Sort by ratio, tie-broken by client_id, capturing the original index so
    # the resulting labels realign to the caller's rows (Requirement 9.5).
    order = joined_leads.sort_values(
        ["ext_outflow_ratio", "client_id"], kind="mergesort"
    ).index

    # Position-based split: partition the sorted positions into four contiguous,
    # near-equal groups (Requirement 9.4). array_split tolerates n < 4 by
    # emitting empty trailing groups rather than raising.
    labels = pd.Series(index=order, dtype=object)
    for label, positions in zip(QUARTILE_LABELS, np.array_split(order, 4)):
        labels.loc[positions] = label

    # Return in the caller's original row order.
    return labels.reindex(joined_leads.index)


def join_rate(group: pd.DataFrame) -> float:
    """Return a group's Join_Rate: fraction of leads with ``joined`` 1 (Req 9.6).

    The Join_Rate is the count of leads whose ``joined`` equals 1 divided by the
    number of leads in ``group``, which equals the mean of the ``joined`` flag.
    Because ``joined`` is a 0/1 flag the result falls in the inclusive range 0
    to 1 (Requirement 9.6).

    An empty group has no leads to average; this returns 0.0 for that case so
    callers never divide by zero. Per Requirement 9.6 only non-empty quartiles
    are reported, so the report skips empty bins rather than relying on this
    fallback -- it is a safety net.

    Args:
        group: A frame of leads carrying the numeric ``joined`` flag.

    Returns:
        The Join_Rate as a float in [0, 1].
    """
    if len(group) == 0:
        return 0.0
    return float((group["joined"] == 1).mean())


def compute_report(treated_leads: pd.DataFrame, features: pd.DataFrame) -> dict:
    """Compute the structured quartile / join-rate report (Req 9.6, 9.8).

    Inner-joins the P001 Treated_Leads to the Features_File (Requirement 9.3 via
    :func:`join_to_features`), assigns the joined leads to quartiles
    (:func:`assign_quartiles`), and computes each non-empty quartile's Join_Rate
    plus the overall inner-join rate -- returning them as data so tests can
    assert on the numbers without parsing printed output.

    The **overall inner-join rate** (Requirement 9.8) is the count of P001
    Treated_Leads matched to the Features_File divided by the *total* count of
    P001 Treated_Leads selected -- i.e. matched / total-treated, computed from
    both ``treated_leads`` (the pre-join total) and the inner-join result (the
    matched count), not from the joined frame alone. It is 0.0 when no treated
    leads were selected.

    Per-quartile entries are included for every one of Q1..Q4 that is non-empty,
    in order; an empty trailing bin (possible when fewer than four leads joined)
    is omitted (Requirement 9.6). Each entry's Join_Rate comes from
    :func:`join_rate`.

    Args:
        treated_leads: The P001 Treated_Leads from :func:`select_treated_leads`
            -- the pre-join population whose size is the overall-rate denominator.
        features: The per-client Features_File frame (carries
            ``ext_outflow_ratio``).

    Returns:
        A dict with:

        - ``total_treated``: count of selected P001 Treated_Leads,
        - ``matched``: count that inner-joined to the Features_File,
        - ``overall_join_rate``: ``matched / total_treated`` in [0, 1] (0.0 when
          no treated leads),
        - ``quartiles``: a list of ``{"label", "count", "join_rate"}`` dicts for
          each non-empty quartile Q1..Q4 in order.
    """
    total_treated = int(len(treated_leads))
    joined = join_to_features(treated_leads, features)
    matched = int(len(joined))

    overall_join_rate = matched / total_treated if total_treated else 0.0

    quartiles = []
    if matched:
        labels = assign_quartiles(joined)
        for label in QUARTILE_LABELS:
            group = joined[labels == label]
            if len(group) == 0:
                # Skip empty quartiles: only non-empty bins get a rate (9.6).
                continue
            quartiles.append(
                {
                    "label": label,
                    "count": int(len(group)),
                    "join_rate": join_rate(group),
                }
            )

    return {
        "total_treated": total_treated,
        "matched": matched,
        "overall_join_rate": overall_join_rate,
        "quartiles": quartiles,
    }


def print_report(treated_leads: pd.DataFrame, features: pd.DataFrame) -> dict:
    """Print the quartile / join-rate report (Requirements 9.7, 9.8, 9.9).

    Builds the structured report via :func:`compute_report` and prints it. When
    at least one P001 Treated_Lead was selected, prints one line per non-empty
    quartile in the order Q1, Q2, Q3, Q4 showing the quartile label, lead count,
    and Join_Rate (Requirement 9.7), then a final line with the overall
    inner-join rate (Requirement 9.8).

    When zero P001 Treated_Leads are selected, prints a message that no matching
    leads were found and prints no quartile or overall-rate lines -- the
    quartile computation is skipped entirely (Requirement 9.9). This mirrors the
    guard in :func:`compute_report`, which leaves ``quartiles`` empty and
    ``overall_join_rate`` 0.0 for that case.

    Returns the structured report dict from :func:`compute_report` so callers
    (and tests) can both print and inspect the result from one call.

    Args:
        treated_leads: The P001 Treated_Leads from :func:`select_treated_leads`.
        features: The per-client Features_File frame.

    Returns:
        The structured report dict (see :func:`compute_report`).
    """
    report = compute_report(treated_leads, features)

    if report["total_treated"] == 0:
        print("No matching P001 treated leads found; skipping quartile report.")
        return report

    for quartile in report["quartiles"]:
        print(
            f"{quartile['label']}: count={quartile['count']} "
            f"join_rate={quartile['join_rate']:.4f}"
        )
    print(f"Overall inner-join rate: {report['overall_join_rate']:.4f}")
    return report
