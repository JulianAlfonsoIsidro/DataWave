"""Feature_Builder for the Part2_Network_Pipeline.

Computes one row of network- and money-flow features per client from a
validated transactions frame. This module holds the shared scaffolding that
every feature block builds on:

- the sorted client universe (the reindex target for every block),
- a ``txn_month`` (``YYYY-MM``) column derived from ``txn_date``,
- the ``outflows`` / ``inflows`` / ``ext_outflows`` row slices, and
- a reindex-and-zero-fill helper that aligns a per-client Series onto that
  client universe.

The individual feature computations and the ``build`` / ``write`` functions are
layered on top of these helpers in later tasks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from part2_network.config import (
    EXTERNAL_COUNTERPARTY_TYPE,
    INFLOW_SHARE_COLUMNS,
    INFLOW_SOURCES,
    SPEND_SHARE_PREFIX,
)

# Matches each maximal run of characters that are not a lowercase ASCII letter
# or digit. Applied after lowercasing so uppercase letters never reach it; used
# to collapse every non-alphanumeric run into a single underscore.
_NON_ALNUM_RUN = re.compile(r"[^0-9a-z]+")


def client_universe(txns: pd.DataFrame) -> list:
    """Return the sorted distinct ``client_id`` values.

    This is the client universe onto which every feature block is reindexed so
    the output carries exactly one row per client in ascending order
    (Requirements 8.2, 8.5).
    """
    return sorted(txns.client_id.unique())


def transaction_months(txns: pd.DataFrame) -> pd.Series:
    """Return the ``YYYY-MM`` Transaction_Month for each transaction row.

    Derived from the already-parsed ``txn_date`` datetime column; used by the
    months-with-external-transfer feature (Requirement 5).
    """
    return txns.txn_date.dt.strftime("%Y-%m")


def spend_share_column(category: str) -> str:
    """Return the ``spend_share_*`` column name for a Spending_Category value.

    Builds the output column name for one dynamically discovered spend-share
    feature: the :data:`SPEND_SHARE_PREFIX` ("spend_share_") followed by the
    category value lowercased, with each run of non-alphanumeric characters
    replaced by a single underscore (Requirement 7.3). Examples::

        "E-commerce"   -> "spend_share_e_commerce"
        "Bank transfer" -> "spend_share_bank_transfer"
        "Grocery"      -> "spend_share_grocery"
        "Food & Drink" -> "spend_share_food_drink"

    Leading and trailing non-alphanumeric characters would otherwise yield a
    token with a leading or trailing underscore, so the normalized token is
    stripped of surrounding underscores before the prefix is applied -- e.g.
    ``"  Retail!"`` normalizes to ``"retail"`` and returns
    ``"spend_share_retail"``. A category that is empty or entirely
    non-alphanumeric normalizes to an empty token and returns the bare prefix
    ``"spend_share_"``.
    """
    token = _NON_ALNUM_RUN.sub("_", category.lower()).strip("_")
    return SPEND_SHARE_PREFIX + token


def split_by_direction(
    txns: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split transactions into the row slices every feature block reuses.

    Returns ``(outflows, inflows, ext_outflows)`` where:

    - ``outflows`` are the ``direction == "OUT"`` rows (Outflow),
    - ``inflows`` are the ``direction == "IN"`` rows (Inflow), and
    - ``ext_outflows`` are the Outflow rows whose ``counterparty_type`` equals
      "Other bank" (External_Outflow).

    A transaction whose ``counterparty_type`` is missing or not equal to
    "Other bank" is excluded from ``ext_outflows`` (Requirement 3.2); the
    equality comparison already drops ``NaN`` counterparty types.
    """
    outflows = txns[txns.direction == "OUT"]
    inflows = txns[txns.direction == "IN"]
    ext_outflows = outflows[outflows.counterparty_type == EXTERNAL_COUNTERPARTY_TYPE]
    return outflows, inflows, ext_outflows


def reindex_zero_fill(series: pd.Series, clients) -> pd.Series:
    """Align ``series`` onto the sorted client universe, filling gaps with 0.

    Every feature block produces a per-client Series (e.g. from a ``groupby``)
    that may omit clients with no qualifying transactions. Reindexing onto
    ``clients`` and zero-filling guarantees one value per client in the shared
    order (Requirements 2.2, 3.3, 5.2, 8.2, 8.5).
    """
    return series.reindex(clients).fillna(0)


def total_out(outflows: pd.DataFrame, clients) -> pd.Series:
    """Return each client's Total_Out as an unrounded per-client Series.

    Sums ``amount_php`` over the client's Outflow (``direction == "OUT"``) rows,
    then aligns onto the sorted client universe with gaps zero-filled so clients
    with no outflows report 0 (Requirements 2.1, 2.2).

    The returned Series is left **unrounded** on purpose: ``ext_outflow_ratio``
    (task 4.4) divides by this raw Total_Out, and rounding to 2 decimals
    (Requirement 2.3) is applied once at output assembly (task 7.1). ``outflows``
    is the slice from :func:`split_by_direction`.
    """
    per_client = outflows.groupby("client_id").amount_php.sum()
    return reindex_zero_fill(per_client, clients)


def out_other_bank(ext_outflows: pd.DataFrame, clients) -> pd.Series:
    """Return each client's Out_Other_Bank as an unrounded per-client Series.

    Sums ``amount_php`` over the client's External_Outflow rows -- Outflow rows
    whose ``counterparty_type`` equals "Other bank"; missing or other
    counterparty types are already excluded by :func:`split_by_direction`
    (Requirements 3.1, 3.2). Aligning onto the sorted client universe with gaps
    zero-filled sets clients with no external outflows to 0 (Requirement 3.3).

    The returned Series is left **unrounded** so ``ext_outflow_ratio`` (task
    4.4) can reuse the raw numerator; rounding to 2 decimals (Requirement 3.4)
    happens at output assembly (task 7.1). ``ext_outflows`` is the slice from
    :func:`split_by_direction`.
    """
    per_client = ext_outflows.groupby("client_id").amount_php.sum()
    return reindex_zero_fill(per_client, clients)


def inflow_shares(inflows: pd.DataFrame, clients) -> dict:
    """Return the three Inflow_Share features as unrounded per-client Series.

    For each client, the total Inflow amount is the sum of ``amount_php`` over
    that client's Inflow (``direction == "IN"``) rows. For each Inflow_Source in
    :data:`INFLOW_SOURCES` -- "Payroll", "Remittance", "Business receipts" --
    the share is the sum of ``amount_php`` over that client's Inflow rows whose
    ``counterparty_category`` equals the source, divided by the client's total
    Inflow (Requirement 6.1).

    Divide-by-zero is guarded: a client whose total Inflow is 0 reports 0 for
    all three shares (Requirement 6.2), and a client with positive inflow but
    none in a given source reports 0 for that source (Requirement 6.3). Every
    returned Series is aligned onto the sorted client universe with gaps
    zero-filled, so clients with no inflow rows at all are covered too.

    Returns a dict keyed by the output column name
    (:data:`INFLOW_SHARE_COLUMNS` -- ``inflow_share_payroll``,
    ``inflow_share_remittance``, ``inflow_share_business_receipts``) mapping to
    the per-client share Series (Requirement 6.6). The Series are left
    **unrounded** to match the ``total_out`` / ``out_other_bank`` pattern;
    rounding to 6 decimals (Requirement 6.4) is applied once at output assembly
    (task 7.1), which preserves the sum-to-one tolerance (Requirements 6.4,
    6.5). ``inflows`` is the slice from :func:`split_by_direction`.
    """
    # Total inflow per client, aligned onto the client universe (0 where absent).
    inflow_total = reindex_zero_fill(
        inflows.groupby("client_id").amount_php.sum(), clients
    )

    # Per-source inflow sums: group by client and source, pivot sources to
    # columns, then restrict to the fixed INFLOW_SOURCES so the output column
    # set is stable regardless of which categories appear in the data.
    per_source = (
        inflows.groupby(["client_id", "counterparty_category"]).amount_php.sum()
        .unstack(fill_value=0)
        .reindex(columns=INFLOW_SOURCES, fill_value=0)
    )

    # Guard divide-by-zero: replace a 0 total with NaN so the division yields
    # NaN, then zero-fill. This forces every share to 0 when total inflow is 0
    # (Requirement 6.2) while leaving positive-inflow clients unaffected.
    safe_total = inflow_total.replace(0, pd.NA)

    shares = {}
    for source in INFLOW_SOURCES:
        source_sum = reindex_zero_fill(
            per_source[source] if source in per_source else pd.Series(dtype=float),
            clients,
        )
        share = (source_sum / safe_total).fillna(0)
        shares[INFLOW_SHARE_COLUMNS[source]] = share
    return shares


def ext_outflow_ratio(
    total_out_series: pd.Series, out_other_bank_series: pd.Series
) -> pd.Series:
    """Return each client's Ext_Outflow_Ratio as an unrounded per-client Series.

    The ratio is Out_Other_Bank divided by Total_Out (Requirement 4.1). Both
    arguments are the already-aligned, **unrounded** per-client Series from
    :func:`out_other_bank` and :func:`total_out`, reused here so the ratio is
    computed from the raw numerator and denominator rather than recomputed.

    Divide-by-zero is guarded: a 0 denominator is replaced with NA so the
    division yields NA, which is then zero-filled. This sets Ext_Outflow_Ratio
    to 0 for every client whose Total_Out is 0 (Requirement 4.2). Because
    Out_Other_Bank sums a subset of the Outflow rows that Total_Out sums and
    both treat ``amount_php`` as non-negative, the result falls in the inclusive
    range 0 to 1 for every client (Requirement 4.3).

    The returned Series is left **unrounded** to match the ``total_out`` /
    ``out_other_bank`` pattern; rounding to 4 decimals (Requirement 4.4) is
    applied once at output assembly (task 7.1).
    """
    safe_total = total_out_series.replace(0, pd.NA)
    return (out_other_bank_series / safe_total).fillna(0)


def months_with_ext_transfer(ext_outflows: pd.DataFrame, clients) -> pd.Series:
    """Return each client's Months_With_Ext_Transfer as a per-client Series.

    Counts the distinct Transaction_Month (``YYYY-MM``) values in which the
    client has at least one External_Outflow (Requirement 5.1). The month is
    derived per row via :func:`transaction_months` and the distinct count per
    client comes from ``groupby(client_id)[month].nunique()``, so multiple
    External_Outflow transactions within the same Transaction_Month count that
    month exactly once (Requirement 5.4).

    Aligning onto the sorted client universe with gaps zero-filled sets clients
    with no external outflows to 0 (Requirement 5.2). The transaction data spans
    three calendar months, so the count is a non-negative integer in the
    inclusive range 0 to 3 (Requirement 5.3); the result is cast to ``int``.
    ``ext_outflows`` is the slice from :func:`split_by_direction`.
    """
    months = transaction_months(ext_outflows)
    per_client = months.groupby(ext_outflows.client_id).nunique()
    return reindex_zero_fill(per_client, clients).astype(int)


def spend_shares(
    outflows: pd.DataFrame, total_out_series: pd.Series, clients
) -> tuple[list[str], dict]:
    """Return the dynamically discovered Spending_Share features.

    For each client and each discovered Spending_Category, the share is the sum
    of ``amount_php`` over that client's Outflow rows whose
    ``counterparty_category`` equals the category, divided by the client's
    Total_Out (Requirement 7.1).

    **Global column discovery (Requirement 7.2).** The set of spend-share
    columns is derived once from the distinct ``counterparty_category`` values
    appearing on Outflow rows *across all clients*, not per client. Every
    returned Series is reindexed onto the full sorted client universe, so a
    category that only a single client uses still appears for every client --
    as 0 for the clients who never spent in it (Requirement 7.4).

    **Column ordering (stable, deterministic).** The returned column list is
    sorted ascending by the normalized ``spend_share_*`` column name. Ordering
    by the *output* name (rather than the raw category) keeps the order aligned
    with what actually lands in the Features_File and makes collisions (below)
    well defined, since colliding raw categories share one name and therefore
    one position.

    **Collision handling (Requirement 7.3).** Two distinct raw categories can
    normalize to the same ``spend_share_*`` column -- e.g. ``"E-commerce"`` and
    ``"E Commerce"`` both normalize to ``spend_share_e_commerce``. Such rows are
    grouped under the single shared column and their outflow amounts summed, so
    the colliding categories contribute one combined share rather than
    overwriting each other. This also preserves the partition that makes the
    shares sum to 1 (Requirement 7.7): every Outflow row still maps to exactly
    one output column.

    Divide-by-zero is guarded with the same pattern as
    :func:`inflow_shares` / :func:`ext_outflow_ratio`: a client whose Total_Out
    is 0 has its denominator replaced with NA so the division yields NA, which
    is then zero-filled, forcing every spend share to 0 for that client
    (Requirement 7.5). A client with no outflow in a given category reports 0
    for that column (Requirement 7.4).

    Returns ``(columns, shares)`` where ``columns`` is the ordered list of
    ``spend_share_*`` column names and ``shares`` maps each column name to its
    per-client Series aligned onto ``clients``. The Series are left
    **unrounded** to match the ``total_out`` / ``inflow_shares`` pattern;
    rounding to 6 decimals (Requirement 7.6) is applied once at output assembly
    (task 7.1), which preserves the sum-to-one tolerance (Requirement 7.7).
    ``outflows`` is the slice from :func:`split_by_direction` and
    ``total_out_series`` is the aligned, unrounded Series from
    :func:`total_out`.
    """
    # Guard divide-by-zero: a 0 Total_Out becomes NA so every division yields
    # NA for that client, forcing all of its spend shares to 0 after fillna
    # (Requirement 7.5).
    safe_total = total_out_series.replace(0, pd.NA)

    # Map each raw outflow category to its normalized output column name, then
    # group by that name so distinct raw categories colliding on one name are
    # summed into a single column (Requirement 7.3). The per-client/per-column
    # outflow sum is pivoted to columns, with absent client/column pairs 0.
    if len(outflows):
        spend_column = outflows.counterparty_category.map(spend_share_column)
        per_client_column = (
            outflows.amount_php.groupby([outflows.client_id, spend_column]).sum()
            .unstack(fill_value=0)
        )
    else:
        per_client_column = pd.DataFrame(index=pd.Index([], name="client_id"))

    # Global discovery: the complete column set is every normalized name seen on
    # any client's outflows, ordered deterministically by column name
    # (Requirement 7.2).
    columns = sorted(per_client_column.columns)

    shares = {}
    for column in columns:
        category_sum = reindex_zero_fill(per_client_column[column], clients)
        shares[column] = (category_sum / safe_total).fillna(0)
    return columns, shares


def build(txns: pd.DataFrame) -> pd.DataFrame:
    """Assemble the full per-client Features_File frame.

    Derives the sorted client universe once, splits the transactions into the
    Outflow / Inflow / External_Outflow slices once, computes every feature
    block from the shared **unrounded** Series (so ``ext_outflow_ratio`` and the
    spend shares divide by the same raw ``total_out`` the summaries report), and
    concatenates them into a single frame with ``client_id`` as the first column
    (Requirement 8.3).

    The frame is indexed and ordered by ascending ``client_id`` -- ``clients``
    is already sorted -- with exactly one row per distinct client (Requirements
    8.2, 8.5). Column order is the fixed block ``client_id``, ``total_out``,
    ``out_other_bank``, ``ext_outflow_ratio``, ``months_with_ext_transfer``, the
    three inflow shares, followed by the dynamically discovered ``spend_share_*``
    columns in the deterministic order returned by :func:`spend_shares`.

    Rounding is applied once here, at assembly, from the raw Series: ``total_out``
    and ``out_other_bank`` to 2 decimals (Requirements 2.3, 3.4),
    ``ext_outflow_ratio`` to 4 decimals (Requirement 4.4),
    ``months_with_ext_transfer`` kept as an integer (Requirements 5.3, 5.5), and
    each inflow and spend share to 6 decimals (Requirements 6.4, 7.6). The ratio
    Series carries an object dtype from its NA divide-by-zero guard, so it is
    coerced to float before rounding.

    A transactions frame with zero distinct clients yields a frame carrying the
    fixed header columns -- ``client_id`` through the three inflow shares -- but
    no rows (Requirement 8.6); no spend-share columns appear because none can be
    discovered from an empty outflow slice.
    """
    clients = client_universe(txns)
    outflows, inflows, ext_outflows = split_by_direction(txns)

    total_out_series = total_out(outflows, clients)
    out_other_bank_series = out_other_bank(ext_outflows, clients)
    ratio_series = ext_outflow_ratio(total_out_series, out_other_bank_series)
    months_series = months_with_ext_transfer(ext_outflows, clients)
    inflow_share_series = inflow_shares(inflows, clients)
    spend_columns, spend_share_series = spend_shares(
        outflows, total_out_series, clients
    )

    # Fixed-order feature columns, each rounded from the raw Series to the
    # precision its requirement specifies. ext_outflow_ratio is object-dtyped by
    # its NA guard, so coerce it to float before rounding.
    columns = {
        "total_out": total_out_series.round(2),
        "out_other_bank": out_other_bank_series.round(2),
        "ext_outflow_ratio": ratio_series.astype(float).round(4),
        "months_with_ext_transfer": months_series,
    }
    for output_name in INFLOW_SHARE_COLUMNS.values():
        columns[output_name] = inflow_share_series[output_name].round(6)
    for column in spend_columns:
        columns[column] = spend_share_series[column].round(6)

    features = pd.DataFrame(columns, index=pd.Index(clients, name="client_id"))
    # client_id is a real first column, not just the index (Requirement 8.3);
    # the index is already ascending so rows come out sorted (Requirement 8.5).
    return features.reset_index()


def write(features: pd.DataFrame, path: Path) -> None:
    """Write the assembled Features_File frame to ``path`` as CSV.

    Emits the frame from :func:`build` to ``path`` as a comma-separated file
    with a single header row naming every column and ``client_id`` as the first
    column (Requirements 8.1, 8.3). The pandas index is suppressed
    (``index=False``) so no extra leading column precedes ``client_id`` --
    ``build`` already exposes ``client_id`` as a real column.

    The parent directory is created first if it does not exist, so writing to
    the default ``outputs/features_part2.csv`` succeeds even when ``outputs/``
    is absent (Requirement 8.4). A zero-client frame -- carrying the fixed
    header columns but no rows (Requirement 8.6) -- is written as the header row
    only, which is what ``to_csv(index=False)`` emits for an empty-but-columned
    frame.

    ``path`` may be a :class:`~pathlib.Path` or a ``str``; it is coerced to
    ``Path`` so ``path.parent.mkdir`` works for either.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(path, index=False)
