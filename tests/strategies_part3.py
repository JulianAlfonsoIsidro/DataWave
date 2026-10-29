"""Shared Hypothesis strategies for the Part3_Segments_Pipeline tests.

This module centralizes the composite strategy that generates a *coherent set*
of the five frames the Segmenter and Summary_Builder operate on — shaped
exactly like what ``loader.load`` produces (required columns present, the
numeric columns coerced to numeric dtypes, and ``month`` kept as a ``YYYY-MM``
string). Every Part 3 property test (Properties 1, 2, 3, 4, 5, 6; tasks 3.2,
3.4, 3.5, 4.2, 6.2, 6.4) imports from here so they all exercise the same input
space.

Import it from a test module with an absolute import mirroring the ``src``
package style, for example::

    from tests.strategies_part3 import segment_inputs

    @given(segment_inputs())
    def test_capacity(frames):
        leads = assign(frames)
        ...

Design notes (mirroring ``tests/strategies.py`` conventions):
- The generated schema matches the loader's *output*, so property tests can
  feed these frames straight into ``segments.assign`` (which expects a dict
  keyed ``scores`` / ``features`` / ``adb`` / ``promo_history`` /
  ``promo_leads``) without re-running the loader.
- ``p_join`` is drawn in ``[0, 1]`` and ``out_other_bank`` / ``adb_php`` /
  ``threshold_php`` are finite non-negative values bounded well below the float
  range so per-client and per-cell sums stay precise.
- ``month`` is drawn from a small pool of ``YYYY-MM`` strings so each client
  can have multiple months, exercising the lexicographic-latest selection.
- Some clients are deliberately omitted from the ADB frame and from the
  features frame so the missing-source fallback (Latest_Adb / Out_Other_Bank
  treated as 0) is exercised (Requirement 1.5).
- At least one promo is omitted from the promo-history frame so the
  missing-threshold path (Capacity_High forced false) is exercised
  (Requirement 1.6).
- The promo-leads frame mixes ``control_group`` 0 (treated) and 1 (control),
  and some (promo, segment) cells end up with zero treated leads, exercising
  the empty Actual_Join_Rate path (Requirement 4.4).
"""

from __future__ import annotations

import pandas as pd
from hypothesis import strategies as st

# The pool of YYYY-MM months. Multiple months per client exercise the
# lexicographic-latest ADB selection (Latest_Adb = adb_php at max month).
OBSERVED_MONTHS: list[str] = ["2026-06", "2026-07", "2026-08", "2026-09"]

# Categorical top-driver values carried through to the Segments_File and used
# for the summary mode. A small pool keeps ties (and the deterministic
# tie-break) reachable.
TOP_DRIVERS: list[str] = [
    "payroll",
    "remittance",
    "business_receipts",
    "spend",
    "balance",
]

# Money bounds: finite, non-negative, and small enough that sums of a handful
# of rows stay far from float64 overflow with good precision.
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
def segment_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 3,
    min_clients: int = 1,
    max_clients: int = 6,
    min_leads: int = 1,
    max_leads: int = 40,
) -> dict[str, pd.DataFrame]:
    """Composite strategy producing a coherent set of the five Part 3 frames.

    Returns a dict keyed ``scores`` / ``features`` / ``adb`` /
    ``promo_history`` / ``promo_leads``, each a pandas ``DataFrame`` shaped
    exactly like ``loader.load`` yields (required columns present, numeric
    columns numeric, ``month`` a ``YYYY-MM`` string). The set is *coherent*:
    the ADB, features, promo-history, and promo-leads frames reference the same
    promos and clients the scores frame uses, with deliberate omissions to
    exercise the defined edge cases.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_clients / max_clients: bounds on the distinct client universe.
        min_leads / max_leads: bounds on the number of scored Leads (rows of
            the scores frame). Leads are unique on (``promo_id``,
            ``client_id``).

    Edge cases exercised by construction:
        - Some clients are omitted from the ADB frame and from the features
          frame (missing-source -> 0 contribution to capacity, Requirement 1.5).
        - At least one promo (when more than one exists) is omitted from the
          promo-history frame (missing threshold -> Capacity_High false,
          Requirement 1.6).
        - The promo-leads frame mixes ``control_group`` 0 and 1 and leaves some
          cells with zero treated leads (empty Actual_Join_Rate, Req 4.4).
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    n_clients = draw(st.integers(min_value=min_clients, max_value=max_clients))

    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]
    clients = [f"C{i:04d}" for i in range(1, n_clients + 1)]

    # --- scores frame: unique (promo_id, client_id) Leads ------------------
    all_pairs = [(p, c) for p in promos for c in clients]
    n_leads = draw(
        st.integers(
            min_value=min(min_leads, len(all_pairs)),
            max_value=min(max_leads, len(all_pairs)),
        )
    )
    # Draw a unique subset of the promo x client grid as the Leads.
    lead_pairs = draw(
        st.lists(
            st.sampled_from(all_pairs),
            min_size=n_leads,
            max_size=n_leads,
            unique=True,
        )
    )
    score_rows = []
    for promo_id, client_id in lead_pairs:
        score_rows.append(
            {
                "promo_id": promo_id,
                "client_id": client_id,
                "p_join": draw(_p_join()),
                "top_driver_1": draw(st.sampled_from(TOP_DRIVERS)),
                "top_driver_2": draw(st.sampled_from(TOP_DRIVERS)),
                "top_driver_3": draw(st.sampled_from(TOP_DRIVERS)),
            }
        )
    scores = pd.DataFrame(
        score_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    # The clients actually referenced by the Leads; capacity joins key on these.
    lead_clients = sorted({c for _, c in lead_pairs})
    lead_promos = sorted({p for p, _ in lead_pairs})

    # --- adb frame: multiple months per client, some clients omitted -------
    # Decide which lead-clients get ADB rows (omit some to exercise the 0
    # fallback). Drawing a subset keeps at least the possibility of all/none.
    adb_clients = draw(
        st.lists(
            st.sampled_from(lead_clients),
            min_size=0,
            max_size=len(lead_clients),
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

    # --- features frame: out_other_bank, some clients omitted --------------
    feature_clients = draw(
        st.lists(
            st.sampled_from(lead_clients),
            min_size=0,
            max_size=len(lead_clients),
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

    # --- promo-history frame: at least one promo omitted when possible -----
    if len(lead_promos) > 1:
        # Keep a strict, non-empty subset so at least one promo is missing.
        history_promos = draw(
            st.lists(
                st.sampled_from(lead_promos),
                min_size=0,
                max_size=len(lead_promos) - 1,
                unique=True,
            )
        )
    else:
        # With a single promo, either include it or omit it (both paths valid).
        history_promos = draw(
            st.lists(
                st.sampled_from(lead_promos),
                min_size=0,
                max_size=1,
                unique=True,
            )
        )
    promo_history = pd.DataFrame(
        [
            {"promo_id": promo_id, "threshold_php": draw(_money())}
            for promo_id in history_promos
        ],
        columns=["promo_id", "threshold_php"],
    )

    # --- promo-leads frame: mix of control_group 0 and 1 -------------------
    # Draw a subset of the Leads to appear as promo-leads rows; assign each a
    # control_group (0 treated / 1 control) and a joined flag (0/1). Some cells
    # end up with zero treated leads, exercising the empty join-rate path.
    promo_lead_pairs = draw(
        st.lists(
            st.sampled_from(lead_pairs),
            min_size=0,
            max_size=len(lead_pairs),
            unique=True,
        )
    )
    promo_lead_rows = [
        {
            "promo_id": promo_id,
            "client_id": client_id,
            "control_group": draw(st.sampled_from([0, 1])),
            "joined": draw(st.sampled_from([0, 1])),
        }
        for promo_id, client_id in promo_lead_pairs
    ]
    promo_leads = pd.DataFrame(
        promo_lead_rows,
        columns=["promo_id", "client_id", "control_group", "joined"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    # Numeric columns -> numeric; month stays a YYYY-MM string; ids/text stay
    # object. Empty frames still carry the right columns and dtypes.
    scores["p_join"] = pd.to_numeric(scores["p_join"], errors="raise")
    features["out_other_bank"] = pd.to_numeric(
        features["out_other_bank"] if not features.empty else [],
        errors="raise",
    )
    adb["adb_php"] = pd.to_numeric(
        adb["adb_php"] if not adb.empty else [], errors="raise"
    )
    promo_history["threshold_php"] = pd.to_numeric(
        promo_history["threshold_php"] if not promo_history.empty else [],
        errors="raise",
    )

    for column in ("promo_id", "client_id", "top_driver_1", "top_driver_2", "top_driver_3"):
        scores[column] = scores[column].astype("object")
    for frame, text_cols in (
        (features, ["client_id"]),
        (adb, ["client_id", "month"]),
        (promo_history, ["promo_id"]),
        (promo_leads, ["promo_id", "client_id"]),
    ):
        for column in text_cols:
            if not frame.empty:
                frame[column] = frame[column].astype("object")

    return {
        "scores": scores.reset_index(drop=True),
        "features": features.reset_index(drop=True),
        "adb": adb.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
        "promo_leads": promo_leads.reset_index(drop=True),
    }
