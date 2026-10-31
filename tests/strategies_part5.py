"""Shared Hypothesis strategies for the Part 5 webapp property tests.

This module centralizes the generators the Part 5 property tests (Properties 1,
2, 3; task 2.5) share, following the ``tests/strategies_part3.py`` convention of
one composite per coherent frame-set. The three properties exercise three pure
functions, so three focused generators live here:

- :func:`eligibility_inputs` -- a coherent ``(customer_dna, adb_monthly,
  eligible_segments, min_adb)`` tuple shaped exactly like what
  :func:`webapp_core.audience.select_eligible_clients` consumes (Property 1).
- :func:`scored_audience` -- a ``(scored, promo_dict, frames)`` tuple shaped
  exactly like what :func:`part3_segments.segments.assign_segments` consumes,
  mirroring the frame shapes ``strategies_part3.segment_inputs`` builds so the
  quadrant property reuses the proven input space (Property 2).
- :func:`existing_promo_ids` -- a list of candidate ids, a mix of ``NEW-###``
  ids and unrelated ids, for :func:`webapp_core.promo_id.next_promo_id`
  (Property 3).
- :func:`predicted_actual_inputs` -- a coherent ``(cards, promo_leads,
  sendable_ids_by_cell)`` tuple shaped exactly like what
  :func:`webapp_core.past_promos.predicted_vs_actual` consumes, with some cells
  deliberately empty so the NA branch is exercised (Property 4).

All money values are finite, non-negative, and bounded well below the float
range so per-client sums stay precise; ``month`` is a ``YYYY-MM`` string drawn
from a small pool so the lexicographic-latest ADB selection is exercised.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import strategies as st

# The pool of YYYY-MM months; multiple months per client exercise the
# lexicographic-latest ADB selection.
OBSERVED_MONTHS: list[str] = ["2026-06", "2026-07", "2026-08", "2026-09"]

# The Customer_DNA segment labels (distinct from the four Part 3 Segment_Labels).
# A small pool keeps both the in- and out-of-eligible-set paths reachable.
DNA_SEGMENTS: list[str] = [
    "Affluent-Preferred",
    "Mass-Affluent",
    "Mass-Market",
    "Emerging",
]

# Categorical top-driver values carried through the scored frame.
TOP_DRIVERS: list[str] = [
    "payroll",
    "remittance",
    "business_receipts",
    "spend",
    "balance",
]

# Money bounds: finite, non-negative, small enough that sums of a handful of
# rows stay far from float64 overflow with good precision.
_MIN_MONEY = 0.0
_MAX_MONEY = 1_000_000.0


def _money() -> st.SearchStrategy[float]:
    """Finite, non-negative money amounts bounded to avoid float overflow."""
    return st.floats(
        min_value=_MIN_MONEY,
        max_value=_MAX_MONEY,
        allow_nan=False,
        allow_infinity=False,
    )


def _p_join() -> st.SearchStrategy[float]:
    """Join probabilities in the closed unit interval [0, 1]."""
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )


@st.composite
def eligibility_inputs(
    draw: st.DrawFn,
    *,
    min_clients: int = 0,
    max_clients: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], float]:
    """Coherent inputs for :func:`select_eligible_clients` (Property 1).

    Returns a ``(customer_dna, adb_monthly, eligible_segments, min_adb)`` tuple:

    - ``customer_dna`` has one row per client (unique ``client_id``) with a
      ``segment`` drawn from :data:`DNA_SEGMENTS`.
    - ``adb_monthly`` carries ``client_id`` / ``month`` / ``adb_php`` with
      multiple months per client; some clients are deliberately omitted so the
      "missing latest ADB -> 0" path is exercised.
    - ``eligible_segments`` is a (possibly empty) subset of :data:`DNA_SEGMENTS`.
    - ``min_adb`` is a finite non-negative floor.
    """
    n_clients = draw(st.integers(min_value=min_clients, max_value=max_clients))
    clients = [f"C{i:04d}" for i in range(1, n_clients + 1)]

    # One Customer_DNA row per client -> unique client_id.
    dna_rows = [
        {"client_id": client_id, "segment": draw(st.sampled_from(DNA_SEGMENTS))}
        for client_id in clients
    ]
    customer_dna = pd.DataFrame(dna_rows, columns=["client_id", "segment"])

    # ADB rows for a subset of clients (omit some to exercise the 0 fallback).
    adb_clients = draw(
        st.lists(
            st.sampled_from(clients) if clients else st.nothing(),
            min_size=0,
            max_size=len(clients),
            unique=True,
        )
    )
    adb_rows = []
    for client_id in adb_clients:
        months = draw(
            st.lists(
                st.sampled_from(OBSERVED_MONTHS),
                min_size=1,
                max_size=len(OBSERVED_MONTHS),
                unique=True,
            )
        )
        for month in months:
            adb_rows.append(
                {
                    "client_id": client_id,
                    "month": month,
                    "adb_php": draw(_money()),
                }
            )
    adb_monthly = pd.DataFrame(
        adb_rows, columns=["client_id", "month", "adb_php"]
    )

    eligible_segments = draw(
        st.lists(
            st.sampled_from(DNA_SEGMENTS),
            min_size=0,
            max_size=len(DNA_SEGMENTS),
            unique=True,
        )
    )

    min_adb = draw(_money())

    # dtype coercion matching the loader's output.
    if not adb_monthly.empty:
        adb_monthly["adb_php"] = pd.to_numeric(
            adb_monthly["adb_php"], errors="raise"
        )
        adb_monthly["client_id"] = adb_monthly["client_id"].astype("object")
        adb_monthly["month"] = adb_monthly["month"].astype("object")
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    customer_dna["segment"] = customer_dna["segment"].astype("object")
    if adb_monthly.empty:
        adb_monthly = pd.DataFrame(
            {
                "client_id": pd.Series([], dtype="object"),
                "month": pd.Series([], dtype="object"),
                "adb_php": pd.Series([], dtype="float64"),
            }
        )

    return (
        customer_dna.reset_index(drop=True),
        adb_monthly.reset_index(drop=True),
        eligible_segments,
        min_adb,
    )


@st.composite
def scored_audience(
    draw: st.DrawFn,
    *,
    min_clients: int = 1,
    max_clients: int = 8,
) -> tuple[pd.DataFrame, dict, dict[str, pd.DataFrame]]:
    """Coherent inputs for :func:`assign_segments` (Property 2).

    Returns a ``(scored, promo_dict, frames)`` tuple:

    - ``scored`` is a ``score_promo``-shaped frame -- columns ``client_id``,
      ``p_join``, ``top_driver_1..3`` -- one row per (unique) client.
    - ``promo_dict`` carries ``promo_id`` and ``threshold_php``.
    - ``frames`` carries the ``adb`` and ``features`` frames the capacity
      computation reads, shaped like ``loader.load`` output. Some clients are
      omitted from each so the "missing -> 0" capacity path is exercised.
    """
    n_clients = draw(st.integers(min_value=min_clients, max_value=max_clients))
    clients = [f"C{i:04d}" for i in range(1, n_clients + 1)]

    promo_id = draw(
        st.sampled_from(["P001", "P002", "NEW-001", "NEW-017"])
    )

    scored_rows = [
        {
            "client_id": client_id,
            "p_join": draw(_p_join()),
            "top_driver_1": draw(st.sampled_from(TOP_DRIVERS)),
            "top_driver_2": draw(st.sampled_from(TOP_DRIVERS)),
            "top_driver_3": draw(st.sampled_from(TOP_DRIVERS)),
        }
        for client_id in clients
    ]
    scored = pd.DataFrame(
        scored_rows,
        columns=[
            "client_id",
            "p_join",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    promo_dict = {"promo_id": promo_id, "threshold_php": draw(_money())}

    # adb frame: multiple months per client, some clients omitted.
    adb_clients = draw(
        st.lists(
            st.sampled_from(clients),
            min_size=0,
            max_size=len(clients),
            unique=True,
        )
    )
    adb_rows = []
    for client_id in adb_clients:
        months = draw(
            st.lists(
                st.sampled_from(OBSERVED_MONTHS),
                min_size=1,
                max_size=len(OBSERVED_MONTHS),
                unique=True,
            )
        )
        for month in months:
            adb_rows.append(
                {
                    "client_id": client_id,
                    "month": month,
                    "adb_php": draw(_money()),
                }
            )
    adb = pd.DataFrame(adb_rows, columns=["client_id", "month", "adb_php"])

    # features frame: out_other_bank per client, some clients omitted.
    feature_clients = draw(
        st.lists(
            st.sampled_from(clients),
            min_size=0,
            max_size=len(clients),
            unique=True,
        )
    )
    feature_rows = [
        {"client_id": client_id, "out_other_bank": draw(_money())}
        for client_id in feature_clients
    ]
    features = pd.DataFrame(
        feature_rows, columns=["client_id", "out_other_bank"]
    )

    # dtype coercion matching the loader's output.
    scored["p_join"] = pd.to_numeric(scored["p_join"], errors="raise")
    for column in ("client_id", "top_driver_1", "top_driver_2", "top_driver_3"):
        scored[column] = scored[column].astype("object")
    if not adb.empty:
        adb["adb_php"] = pd.to_numeric(adb["adb_php"], errors="raise")
        adb["client_id"] = adb["client_id"].astype("object")
        adb["month"] = adb["month"].astype("object")
    if not features.empty:
        features["out_other_bank"] = pd.to_numeric(
            features["out_other_bank"], errors="raise"
        )
        features["client_id"] = features["client_id"].astype("object")

    frames = {
        "adb": adb.reset_index(drop=True),
        "features": features.reset_index(drop=True),
    }

    return scored.reset_index(drop=True), promo_dict, frames


@st.composite
def existing_promo_ids(draw: st.DrawFn) -> list[str]:
    """A list of candidate existing ids for :func:`next_promo_id` (Property 3).

    Mixes ``NEW-###`` ids (varying digit counts, including leading zeros),
    unrelated ids (``P001``-style and free text that must be ignored), and the
    occasional ``None`` so the function's id-filtering path is exercised. The
    list may be empty, which must yield ``NEW-001``.
    """
    new_ids = st.builds(
        lambda n: f"NEW-{n:03d}",
        st.integers(min_value=0, max_value=1500),
    )
    raw_new_ids = st.builds(
        lambda n: f"NEW-{n}",
        st.integers(min_value=0, max_value=1500),
    )
    unrelated = st.one_of(
        st.builds(lambda n: f"P{n:03d}", st.integers(min_value=1, max_value=999)),
        st.text(max_size=8),
        st.just("NEW-"),
        st.just("new-001"),  # case-sensitive: must be ignored
        st.none(),
    )
    return draw(
        st.lists(
            st.one_of(new_ids, raw_new_ids, unrelated),
            min_size=0,
            max_size=12,
        )
    )


# The four Part 3 Segment_Labels, reused as the per-cell segment of a card.
SEGMENT_LABELS: list[str] = [
    "Ready Toppers",
    "Willing but Stretched",
    "Untapped Wealth",
    "Not Now",
]


@st.composite
def predicted_actual_inputs(
    draw: st.DrawFn,
    *,
    min_cells: int = 1,
    max_cells: int = 6,
) -> tuple[list[dict], pd.DataFrame, dict[tuple[str, str], set[str]]]:
    """Coherent inputs for :func:`predicted_vs_actual` (Property 4).

    Returns a ``(cards, promo_leads, sendable_ids_by_cell)`` tuple:

    - ``cards`` is a list of card dicts, one per ``(promo_id, segment)`` cell,
      each carrying ``promo_id``, ``segment``, ``sendable_count`` and
      ``expected_joiners``. To keep ``predicted`` in ``[0, 1]``,
      ``expected_joiners`` is drawn in ``[0, sendable_count]``. Some cells get
      ``sendable_count == 0`` so the predicted-NA branch is exercised.
    - ``promo_leads`` carries ``promo_id`` / ``client_id`` / ``joined`` with
      ``joined`` drawn 0/1 so any computed ``actual`` mean lies in ``[0, 1]``.
    - ``sendable_ids_by_cell`` maps each cell to its Sendable_Lead id set; some
      cells map to an empty set so the actual-NA branch is exercised.

    The three structures are built together so each card's sendable id set and
    the ``promo_leads`` rows for those ids are mutually consistent -- the exact
    contract :func:`predicted_vs_actual` relies on.
    """
    n_cells = draw(st.integers(min_value=min_cells, max_value=max_cells))

    # Distinct (promo_id, segment) cells. A small promo pool with the four
    # segment labels keeps cells unique and the input space tractable.
    cell_space = [
        (promo_id, segment)
        for promo_id in ("P001", "P002", "P003")
        for segment in SEGMENT_LABELS
    ]
    cells = draw(
        st.lists(
            st.sampled_from(cell_space),
            min_size=n_cells,
            max_size=n_cells,
            unique=True,
        )
    )

    cards: list[dict] = []
    sendable_ids_by_cell: dict[tuple[str, str], set[str]] = {}
    lead_rows: list[dict] = []
    client_counter = 0

    for promo_id, segment in cells:
        sendable_count = draw(st.integers(min_value=0, max_value=6))

        # expected_joiners in [0, sendable_count] keeps predicted in [0, 1].
        expected_joiners = draw(
            st.floats(
                min_value=0.0,
                max_value=float(sendable_count),
                allow_nan=False,
                allow_infinity=False,
            )
        )

        cards.append(
            {
                "promo_id": promo_id,
                "segment": segment,
                "sendable_count": sendable_count,
                "expected_joiners": expected_joiners,
            }
        )

        # The cell's sendable id set. Independently of sendable_count, draw a
        # (possibly empty) set so both the actual-NA and actual-present branches
        # are reachable. Ids are globally unique so cells do not share leads.
        n_sendable = draw(st.integers(min_value=0, max_value=5))
        ids: set[str] = set()
        for _ in range(n_sendable):
            client_counter += 1
            client_id = f"L{client_counter:05d}"
            ids.add(client_id)
            lead_rows.append(
                {
                    "promo_id": promo_id,
                    "client_id": client_id,
                    "joined": draw(st.sampled_from([0, 1])),
                }
            )
        sendable_ids_by_cell[(promo_id, segment)] = ids

    promo_leads = pd.DataFrame(
        lead_rows, columns=["promo_id", "client_id", "joined"]
    )
    if promo_leads.empty:
        promo_leads = pd.DataFrame(
            {
                "promo_id": pd.Series([], dtype="object"),
                "client_id": pd.Series([], dtype="object"),
                "joined": pd.Series([], dtype="int64"),
            }
        )
    else:
        promo_leads["promo_id"] = promo_leads["promo_id"].astype("object")
        promo_leads["client_id"] = promo_leads["client_id"].astype("object")
        promo_leads["joined"] = pd.to_numeric(
            promo_leads["joined"], errors="raise"
        )

    return cards, promo_leads.reset_index(drop=True), sendable_ids_by_cell
