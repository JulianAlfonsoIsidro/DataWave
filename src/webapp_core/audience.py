"""Eligible-audience selection for the Part 5 webapp.

This module holds the pure eligibility filter the NEW PROMO flow uses to turn
the raw ``data/`` frames into the subset of clients a promo should be scored
against (Requirement 3.2). It computes each client's latest-month ADB and keeps
only clients whose Customer_DNA ``segment`` is in the promo's eligible segments
and whose latest ADB meets the promo's ``min_adb`` floor.

The eligible segments here are the Customer_DNA segments (e.g.
"Affluent-Preferred"), which are distinct from the four Part 3 Segment_Labels
used in the Results_Grid.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def latest_adb(adb_monthly: pd.DataFrame) -> pd.DataFrame:
    """Latest-month ``adb_php`` per client.

    For each ``client_id`` in ``adb_monthly``, select the row with the
    lexicographically greatest ``month`` (the ``YYYY-MM`` strings sort
    correctly as plain text) and take its ``adb_php``. Returns a frame with
    columns ``client_id`` and ``latest_adb``.

    An empty input yields an empty frame with the same two columns. Clients
    absent from ``adb_monthly`` are not represented here; the "missing -> 0"
    rule is applied by :func:`select_eligible_clients` via a left join plus
    ``fillna(0)``.
    """
    if adb_monthly.empty:
        return pd.DataFrame(
            {
                "client_id": pd.Series([], dtype="object"),
                "latest_adb": pd.Series([], dtype="float64"),
            }
        )

    adb = adb_monthly.copy()
    adb["adb_php"] = pd.to_numeric(adb["adb_php"], errors="coerce")

    # Greatest month per client, then its adb_php renamed to latest_adb.
    idx = adb.groupby("client_id")["month"].idxmax()
    latest = adb.loc[idx, ["client_id", "adb_php"]].rename(
        columns={"adb_php": "latest_adb"}
    )
    return latest.reset_index(drop=True)


def select_eligible_clients(
    customer_dna: pd.DataFrame,
    adb_monthly: pd.DataFrame,
    eligible_segments: Iterable[str],
    min_adb: float,
) -> pd.DataFrame:
    """Select the clients a promo should be scored against (Requirement 3.2).

    Keeps clients whose Customer_DNA ``segment`` is in ``eligible_segments``
    AND whose latest-month ADB is at least ``min_adb``. A client's latest ADB
    is its ``adb_php`` at the greatest ``month`` in ``adb_monthly``; a client
    with no ADB row is treated as latest ADB ``0``.

    Returns a frame with columns ``client_id``, ``latest_adb``, and ``segment``
    in stable ascending ``client_id`` order. The returned ``client_id`` values
    are unique (one Customer_DNA row per client).
    """
    eligible = set(eligible_segments)

    clients = customer_dna[["client_id", "segment"]].copy()

    # latest_adb per client, left-joined with missing -> 0.
    latest = latest_adb(adb_monthly)
    clients = clients.merge(latest, on="client_id", how="left")
    clients["latest_adb"] = pd.to_numeric(
        clients["latest_adb"], errors="coerce"
    ).fillna(0.0)

    keep = clients["segment"].isin(eligible) & (clients["latest_adb"] >= min_adb)
    selected = clients.loc[keep, ["client_id", "latest_adb", "segment"]]

    return selected.sort_values("client_id").reset_index(drop=True)
