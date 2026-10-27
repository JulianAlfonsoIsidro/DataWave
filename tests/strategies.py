"""Shared Hypothesis strategies for the Part2_Network_Pipeline tests.

This module centralizes the composite strategy that generates *valid*
transactions frames — frames shaped exactly like what ``reader.read`` produces:
the required columns present, ``amount_php`` numeric, and ``txn_date`` as a
``datetime64`` column. Every Feature_Builder property test (Properties 1-12,
tasks 4.x-7.x) imports from here so they all exercise the same input space.

Import it from a test module with an absolute import mirroring the ``src``
package style, for example::

    from tests.strategies import transactions_frames

    @given(transactions_frames())
    def test_total_out(txns):
        ...

Design notes:
- The generated schema matches the reader's *output*, so property tests can
  feed these frames straight into ``features`` functions without re-running the
  reader (which would just coerce already-correct types).
- ``amount_php`` is bounded to finite, non-negative values well below the float
  range so that per-client and per-category sums cannot overflow or lose so
  much precision that the sum-to-one tolerances (Properties 6 and 8) become
  meaningless.
- ``txn_date`` is drawn from the three observed months (2026-07/08/09) matching
  the real dataset, which keeps ``months_with_ext_transfer`` bounded to 0..3
  (Property 4).
- ``counterparty_type`` includes "Other bank" (so External_Outflow logic is
  exercised, Property 2) alongside non-external types and a missing/empty
  value (so the "missing or not Other bank is excluded" rule, Requirement 3.2,
  is covered).
- ``counterparty_category`` pools include the three Inflow_Sources
  (Payroll / Remittance / Business receipts) plus realistic spend categories,
  so inflow-share and spend-share logic is exercised.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import strategies as st

from part2_network.config import EXTERNAL_COUNTERPARTY_TYPE, INFLOW_SOURCES

# The three calendar months the real transactions span (see requirements intro).
OBSERVED_MONTHS: list[str] = ["2026-07", "2026-08", "2026-09"]

# counterparty_type pool. "Other bank" drives External_Outflow (Property 2);
# the non-external types and the empty string exercise the "missing or not
# 'Other bank' is excluded" rule (Requirement 3.2).
COUNTERPARTY_TYPES: list[str] = [
    EXTERNAL_COUNTERPARTY_TYPE,  # "Other bank"
    "Same bank",
    "Merchant",
    "Government",
    "",  # missing / blank counterparty_type
]

# Spend categories observed on OUT transactions (Requirement 7 / design doc),
# kept deliberately small but varied (includes a hyphenated value so
# normalization is exercised downstream).
SPEND_CATEGORIES: list[str] = [
    "Grocery",
    "Restaurants",
    "Utilities",
    "Telco",
    "Retail",
    "E-commerce",
    "Bank transfer",
]

# Inflow categories: the three known Inflow_Sources plus an "other" source so
# that not-all-known-source clients exist (Property 5 vs Property 6 split).
INFLOW_CATEGORIES_KNOWN: list[str] = list(INFLOW_SOURCES)
INFLOW_CATEGORIES_OTHER: list[str] = ["Interest", "Refund"]
INFLOW_CATEGORIES_ALL: list[str] = (
    INFLOW_CATEGORIES_KNOWN + INFLOW_CATEGORIES_OTHER
)

# Amount bounds: finite, non-negative, and small enough that sums of up to a
# few hundred rows stay far from float64 overflow and keep good precision for
# the sum-to-one tolerance checks.
_MIN_AMOUNT = 0.0
_MAX_AMOUNT = 1_000_000.0


def client_ids(
    *,
    min_clients: int = 1,
    max_clients: int = 6,
) -> st.SearchStrategy[list[str]]:
    """Strategy for a non-empty, sorted-unique set of client ids.

    A non-empty client universe keeps the sorted client index well-defined
    (Requirements 8.2, 8.5). Ids are zero-padded numeric strings so their
    natural (lexicographic) sort matches a stable, obvious order.
    """
    return st.integers(min_value=0, max_value=9999).map(
        lambda n: f"C{n:04d}"
    ).flatmap(
        lambda _: st.lists(
            st.integers(min_value=0, max_value=9999).map(lambda n: f"C{n:04d}"),
            min_size=min_clients,
            max_size=max_clients,
            unique=True,
        )
    )


def _amounts() -> st.SearchStrategy[float]:
    """Finite, non-negative amounts bounded to avoid float overflow in sums."""
    return st.floats(
        min_value=_MIN_AMOUNT,
        max_value=_MAX_AMOUNT,
        allow_nan=False,
        allow_infinity=False,
    )


@st.composite
def _transaction_row(
    draw: st.DrawFn,
    client_pool: list[str],
) -> dict:
    """Draw a single transaction row as a plain dict.

    Direction is chosen first; IN and OUT rows then draw from the appropriate
    counterparty-category pool (inflow sources for IN, spend categories for
    OUT) so the generated frame mirrors the real data's shape.
    """
    client_id = draw(st.sampled_from(client_pool))
    month = draw(st.sampled_from(OBSERVED_MONTHS))
    day = draw(st.integers(min_value=1, max_value=28))
    txn_date = f"{month}-{day:02d}"
    amount = draw(_amounts())
    direction = draw(st.sampled_from(["IN", "OUT"]))

    if direction == "OUT":
        counterparty_type = draw(st.sampled_from(COUNTERPARTY_TYPES))
        counterparty_category = draw(st.sampled_from(SPEND_CATEGORIES))
    else:  # IN
        # Inflows have no meaningful counterparty_type for these features;
        # keep it a non-external value to avoid accidental External_Outflow.
        counterparty_type = draw(
            st.sampled_from(["Same bank", "Merchant", ""])
        )
        counterparty_category = draw(st.sampled_from(INFLOW_CATEGORIES_ALL))

    return {
        "client_id": client_id,
        "txn_date": txn_date,
        "direction": direction,
        "amount_php": amount,
        "counterparty_type": counterparty_type,
        "counterparty_category": counterparty_category,
    }


@st.composite
def transactions_frames(
    draw: st.DrawFn,
    *,
    min_clients: int = 1,
    max_clients: int = 6,
    min_rows: int = 0,
    max_rows: int = 80,
    all_inflows_known_sources: bool = False,
    force_outflow: bool = False,
) -> pd.DataFrame:
    """Composite strategy producing a valid transactions DataFrame.

    The returned frame matches the schema ``reader.read`` yields: the six
    required columns, ``amount_php`` as ``float64``, and ``txn_date`` as
    ``datetime64[ns]``. A ``txn_id`` column is included too (the reader keeps
    extra columns and uses ``txn_id`` for error messages).

    Args:
        min_clients / max_clients: bounds on the distinct client universe.
        min_rows / max_rows: bounds on the number of transaction rows. ``0``
            rows is allowed so downstream tests can exercise clients that have
            no transactions of a given kind; the client universe itself is
            still non-empty.
        all_inflows_known_sources: when ``True``, every IN row's
            ``counterparty_category`` is one of {Payroll, Remittance,
            Business receipts}. This forces the precondition of Property 6
            (inflow shares sum to one).
        force_outflow: when ``True``, guarantees at least one OUT row exists so
            the generated frame has a client with ``total_out > 0`` — the
            precondition of Property 8 (spend shares sum to one).

    Returns:
        A pandas ``DataFrame`` with columns ``txn_id``, ``client_id``,
        ``txn_date`` (datetime64), ``direction``, ``amount_php`` (float),
        ``counterparty_type``, ``counterparty_category``.
    """
    clients = draw(client_ids(min_clients=min_clients, max_clients=max_clients))

    row_strategy = _transaction_row(clients)
    rows = draw(
        st.lists(row_strategy, min_size=min_rows, max_size=max_rows)
    )

    if all_inflows_known_sources:
        known = st.sampled_from(INFLOW_CATEGORIES_KNOWN)
        for row in rows:
            if row["direction"] == "IN":
                row["counterparty_category"] = draw(known)

    if force_outflow and not any(r["direction"] == "OUT" for r in rows):
        # Append a guaranteed OUT row for a known client so total_out > 0.
        rows.append(
            {
                "client_id": clients[0],
                "txn_date": f"{OBSERVED_MONTHS[0]}-01",
                "direction": "OUT",
                "amount_php": draw(
                    st.floats(
                        min_value=1.0,
                        max_value=_MAX_AMOUNT,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                ),
                "counterparty_type": draw(st.sampled_from(COUNTERPARTY_TYPES)),
                "counterparty_category": draw(st.sampled_from(SPEND_CATEGORIES)),
            }
        )

    columns = [
        "txn_id",
        "client_id",
        "txn_date",
        "direction",
        "amount_php",
        "counterparty_type",
        "counterparty_category",
    ]

    if rows:
        frame = pd.DataFrame(rows)
        frame.insert(0, "txn_id", [f"T{i:06d}" for i in range(len(frame))])
    else:
        frame = pd.DataFrame({column: [] for column in columns})

    # Coerce to the dtypes the reader guarantees so property tests operate on
    # exactly the same shape the real pipeline sees.
    frame["amount_php"] = pd.to_numeric(frame["amount_php"], errors="raise")
    frame["txn_date"] = pd.to_datetime(
        frame["txn_date"], format="%Y-%m-%d", errors="raise"
    )
    for text_column in (
        "txn_id",
        "client_id",
        "direction",
        "counterparty_type",
        "counterparty_category",
    ):
        frame[text_column] = frame[text_column].astype("object")

    return frame[columns].reset_index(drop=True)
