"""Shared Hypothesis strategies for the Part4_Cards_Pipeline tests.

This module centralizes the composite strategies that generate *coherent sets*
of the input frames the Lead_Classifier operates on — shaped exactly like what
``loader.load`` produces (required columns present, numeric columns coerced to
numeric dtypes, and ``contact_date`` kept as a ``YYYY-MM-DD`` string). Part 4
property tests import from here so they all exercise the same input space,
following the part1/part2/part3 ``strategies_*.py`` convention.

Import it from a test module with an absolute import mirroring the ``src``
package style, for example::

    from tests.strategies_part4 import classifier_inputs

    @given(classifier_inputs())
    def test_exclusion_cascade(frames):
        leads = classify(frames, Config())
        ...

Design notes (mirroring the part3 conventions):
- The generated schema matches the loader's *output*, so property tests can
  feed these frames straight into ``classify`` without re-running the loader.
- ``classify`` reads the ``segments``, ``ndb``, ``contact_history``,
  ``customer_dna``, and ``promo_history`` frames. ``classifier_inputs`` keeps
  the input space focused on the exclusion cascade by making every client fully
  reachable (all three DNA flags set to 1) and every promo allow every channel,
  so the best_channel selection never produces a "no reachable channel"
  exclusion — the cascade-focused properties (e.g. Property 1) stay valid while
  ``classify`` can still run its best_channel step end to end.
- The three frames are *coherent*: the NDB and contact-history clients are
  drawn from the same client universe the Segments_File uses, with deliberate
  overlaps and omissions so the edge cases the cascade cares about are
  reachable:
    * some Leads' clients are in the NDB set (reason "ndb"),
    * some clients are over-contacted (> 3 contacts/month),
    * some clients are both NDB and over-contacted (precedence: "ndb"),
    * some clients have no contact rows at all (Avg_Contacts_Per_Month == 0,
      never "over_contacted").
- ``contact_date`` values are drawn so a client can have several events across
  one or more distinct ``YYYY-MM`` months, exercising the
  total-events / distinct-months division, including cases that land both just
  above and just below the strict ``> 3`` threshold.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import strategies as st

# Pool of calendar days (a single month) and a small pool of months so a client
# can accumulate several events within a month (pushing the per-month average
# up) and across distinct months (pulling it back down). Averages that land
# both at/below and strictly above the > 3 threshold are reachable.
_MONTHS: list[str] = ["2026-06", "2026-07", "2026-08"]
_DAYS: list[str] = [f"{d:02d}" for d in range(1, 29)]

# Categorical top-driver values carried through on the Segments_File. Part 4's
# exclusion cascade does not use them, but they are part of the loader's
# output schema, so a small pool keeps the frames realistic.
_TOP_DRIVERS: list[str] = ["payroll", "remittance", "spend", "balance"]

# The four Part 3 segment labels, as emitted by part3.
_SEGMENTS: list[str] = [
    "Ready Toppers",
    "Willing but Stretched",
    "Untapped Wealth",
    "Not Now",
]


def _contact_date() -> st.SearchStrategy[str]:
    """A ``YYYY-MM-DD`` string drawn from the small month/day pools."""
    return st.builds(
        lambda month, day: f"{month}-{day}",
        st.sampled_from(_MONTHS),
        st.sampled_from(_DAYS),
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
def classifier_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 3,
    min_clients: int = 1,
    max_clients: int = 8,
    min_leads: int = 1,
    max_leads: int = 40,
) -> dict[str, pd.DataFrame]:
    """Composite strategy producing coherent ``segments`` / ``ndb`` /
    ``contact_history`` frames for the Lead_Classifier.

    Returns a dict keyed ``segments`` / ``ndb`` / ``contact_history``, each a
    pandas ``DataFrame`` shaped exactly like ``loader.load`` yields: the
    Segments_File carries ``promo_id`` / ``client_id`` / ``p_join`` /
    ``capacity_php`` / ``segment`` / ``top_driver_1`` / ``top_driver_2`` /
    ``top_driver_3`` with ``p_join`` numeric; the Ndb_File carries
    ``client_id`` / ``flag_type`` / ``flag_date``; the Contact_History_File
    carries ``client_id`` / ``contact_date`` / ``campaign_id`` / ``channel``
    with ``contact_date`` a ``YYYY-MM-DD`` string.

    The set is *coherent*: NDB and contact-history clients are drawn from the
    same client universe the Leads use, with deliberate overlaps/omissions so
    the exclusion cascade's branches are all reachable.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_clients / max_clients: bounds on the distinct client universe.
        min_leads / max_leads: bounds on the number of Leads (rows of the
            Segments_File). Leads are unique on (``promo_id``, ``client_id``).
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    n_clients = draw(st.integers(min_value=min_clients, max_value=max_clients))

    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]
    clients = [f"C{i:04d}" for i in range(1, n_clients + 1)]

    # --- segments frame: unique (promo_id, client_id) Leads ----------------
    all_pairs = [(p, c) for p in promos for c in clients]
    n_leads = draw(
        st.integers(
            min_value=min(min_leads, len(all_pairs)),
            max_value=min(max_leads, len(all_pairs)),
        )
    )
    lead_pairs = draw(
        st.lists(
            st.sampled_from(all_pairs),
            min_size=n_leads,
            max_size=n_leads,
            unique=True,
        )
    )
    segment_rows = [
        {
            "promo_id": promo_id,
            "client_id": client_id,
            "p_join": draw(_p_join()),
            "capacity_php": str(draw(st.integers(min_value=0, max_value=100_000))),
            "segment": draw(st.sampled_from(_SEGMENTS)),
            "top_driver_1": draw(st.sampled_from(_TOP_DRIVERS)),
            "top_driver_2": draw(st.sampled_from(_TOP_DRIVERS)),
            "top_driver_3": draw(st.sampled_from(_TOP_DRIVERS)),
        }
        for promo_id, client_id in lead_pairs
    ]
    segments = pd.DataFrame(
        segment_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "capacity_php",
            "segment",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    # The distinct clients actually referenced by the Leads.
    lead_clients = sorted({c for _, c in lead_pairs})

    # --- ndb frame: a subset of the lead clients (plus possibly none) ------
    # Drawing a subset (which may be empty or all) lets Hypothesis reach Leads
    # that are / aren't on the do-not-contact list, including NDB clients that
    # are also over-contacted (precedence case).
    ndb_clients = draw(
        st.lists(
            st.sampled_from(lead_clients),
            min_size=0,
            max_size=len(lead_clients),
            unique=True,
        )
    )
    ndb = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "flag_type": draw(st.sampled_from(["manual", "regulatory"])),
                "flag_date": "2026-01-01",
            }
            for client_id in ndb_clients
        ],
        columns=["client_id", "flag_type", "flag_date"],
    )

    # --- contact_history frame: some clients get events, some get none -----
    # Omitting some clients exercises the Avg_Contacts_Per_Month == 0 path
    # (never "over_contacted", Requirement 2.4). For clients that do appear,
    # draw several (month, day) events so the total-events / distinct-months
    # average can land on either side of the strict > 3 threshold.
    contact_clients = draw(
        st.lists(
            st.sampled_from(lead_clients),
            min_size=0,
            max_size=len(lead_clients),
            unique=True,
        )
    )
    contact_rows: list[dict[str, str]] = []
    for client_id in contact_clients:
        n_events = draw(st.integers(min_value=1, max_value=10))
        for _ in range(n_events):
            contact_rows.append(
                {
                    "client_id": client_id,
                    "contact_date": draw(_contact_date()),
                    "campaign_id": draw(st.sampled_from(["CMP1", "CMP2", "CMP3"])),
                    "channel": draw(st.sampled_from(["Email", "SMS", "In-app"])),
                }
            )
    contact_history = pd.DataFrame(
        contact_rows,
        columns=["client_id", "contact_date", "campaign_id", "channel"],
    )

    # --- customer_dna frame: every lead client is fully reachable ----------
    # Setting all three reachability flags to 1 for every client keeps the
    # best_channel step from ever excluding a Lead "no reachable channel", so
    # the cascade-focused properties (Property 1) see only "", "ndb", and
    # "over_contacted". (A dedicated best_channel strategy varies these flags.)
    customer_dna = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "digital_app_user": 1,
                "email_valid": 1,
                "mobile_valid": 1,
            }
            for client_id in lead_clients
        ],
        columns=["client_id", "digital_app_user", "email_valid", "mobile_valid"],
    )

    # --- promo_history frame: every promo allows every channel -------------
    # Allowing all three channels for every promo likewise guarantees a
    # reachable client always finds an allowed-and-reachable channel.
    promo_history = pd.DataFrame(
        [
            {
                "promo_id": promo_id,
                "channels": "Email, In-app, SMS",
                "mechanic": draw(
                    st.sampled_from(["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"])
                ),
            }
            for promo_id in promos
        ],
        columns=["promo_id", "channels", "mechanic"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    # p_join -> float; ids / text / contact_date stay object (YYYY-MM-DD kept
    # as a string, never parsed to a datetime). Empty frames still carry the
    # right columns.
    segments["p_join"] = pd.to_numeric(segments["p_join"], errors="raise")
    for column in (
        "promo_id",
        "client_id",
        "capacity_php",
        "segment",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ):
        segments[column] = segments[column].astype("object")
    for frame, text_cols in (
        (ndb, ["client_id", "flag_type", "flag_date"]),
        (contact_history, ["client_id", "contact_date", "campaign_id", "channel"]),
    ):
        for column in text_cols:
            if not frame.empty:
                frame[column] = frame[column].astype("object")

    # customer_dna: client_id stays object; the three flags are int like the
    # loader coerces them. promo_history columns stay object (string channels).
    for column in ("digital_app_user", "email_valid", "mobile_valid"):
        customer_dna[column] = pd.to_numeric(customer_dna[column]).astype(int)
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    for column in ("promo_id", "channels", "mechanic"):
        promo_history[column] = promo_history[column].astype("object")

    return {
        "segments": segments.reset_index(drop=True),
        "ndb": ndb.reset_index(drop=True),
        "contact_history": contact_history.reset_index(drop=True),
        "customer_dna": customer_dna.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
    }


# Every non-empty subset of the three channels, so a promo's Allowed_Channels
# can be any combination (including a single channel or all three) but never an
# empty allow-list. Promos with a genuinely empty allow-list would make every
# Lead unreachable regardless of DNA; the no-reachable-channel case is already
# richly exercised by varying the DNA flags against varied non-empty
# allow-lists, so we keep every promo allowing at least one channel.
_CHANNEL_SUBSETS: list[str] = [
    "In-app",
    "Email",
    "SMS",
    "In-app, Email",
    "In-app, SMS",
    "Email, SMS",
    "In-app, Email, SMS",
]


@st.composite
def best_channel_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 3,
    min_clients: int = 1,
    max_clients: int = 8,
    min_leads: int = 1,
    max_leads: int = 40,
) -> dict[str, pd.DataFrame]:
    """Composite strategy exercising the best_channel selection and the
    "no reachable channel" exclusion (Property 2).

    Unlike :func:`classifier_inputs` — which pins every DNA flag to 1 and lets
    every promo allow every channel so the cascade-focused Property 1 never
    sees a "no reachable channel" exclusion — this strategy deliberately
    *varies* two axes so both outcomes of the best_channel step are reachable:

    - **DNA reachability flags** (``digital_app_user`` / ``email_valid`` /
      ``mobile_valid``) are each drawn independently from ``{0, 1}`` per client,
      so a client may be reachable on any subset of channels, including none.
    - **promo Allowed_Channels** are drawn from every non-empty subset of
      ``{In-app, Email, SMS}`` per promo, so a promo may allow any combination.

    The combination of a varied allow-list and varied reachability means some
    Leads find an allowed-and-reachable channel (the first in priority order
    In-app -> Email -> SMS) while others find none and must be excluded
    "no reachable channel" (Requirement 3.5). To keep the focus on the
    best_channel step, the NDB set is left empty and no client is contacted, so
    no Lead is pre-excluded "ndb" or "over_contacted" and every Lead reaches the
    best_channel decision.

    The returned dict is keyed and shaped exactly like
    :func:`classifier_inputs` (and like ``loader.load``'s output), so the frames
    can be fed straight into ``classify``.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_clients / max_clients: bounds on the distinct client universe.
        min_leads / max_leads: bounds on the number of Leads (rows of the
            Segments_File). Leads are unique on (``promo_id``, ``client_id``).
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    n_clients = draw(st.integers(min_value=min_clients, max_value=max_clients))

    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]
    clients = [f"C{i:04d}" for i in range(1, n_clients + 1)]

    # --- segments frame: unique (promo_id, client_id) Leads ----------------
    all_pairs = [(p, c) for p in promos for c in clients]
    n_leads = draw(
        st.integers(
            min_value=min(min_leads, len(all_pairs)),
            max_value=min(max_leads, len(all_pairs)),
        )
    )
    lead_pairs = draw(
        st.lists(
            st.sampled_from(all_pairs),
            min_size=n_leads,
            max_size=n_leads,
            unique=True,
        )
    )
    segment_rows = [
        {
            "promo_id": promo_id,
            "client_id": client_id,
            "p_join": draw(_p_join()),
            "capacity_php": str(draw(st.integers(min_value=0, max_value=100_000))),
            "segment": draw(st.sampled_from(_SEGMENTS)),
            "top_driver_1": draw(st.sampled_from(_TOP_DRIVERS)),
            "top_driver_2": draw(st.sampled_from(_TOP_DRIVERS)),
            "top_driver_3": draw(st.sampled_from(_TOP_DRIVERS)),
        }
        for promo_id, client_id in lead_pairs
    ]
    segments = pd.DataFrame(
        segment_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "capacity_php",
            "segment",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    lead_clients = sorted({c for _, c in lead_pairs})

    # --- ndb frame: empty, so no Lead is pre-excluded "ndb" ----------------
    ndb = pd.DataFrame(columns=["client_id", "flag_type", "flag_date"])

    # --- contact_history frame: empty, so Avg_Contacts_Per_Month == 0 for
    # every client and no Lead is pre-excluded "over_contacted" -------------
    contact_history = pd.DataFrame(
        columns=["client_id", "contact_date", "campaign_id", "channel"]
    )

    # --- customer_dna frame: each reachability flag drawn independently ----
    # Drawing each flag from {0, 1} lets a client be reachable on any subset of
    # channels (including none), which together with the varied allow-lists
    # makes both the allowed-and-reachable and no-reachable-channel outcomes of
    # the best_channel step reachable.
    customer_dna = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "digital_app_user": draw(st.integers(min_value=0, max_value=1)),
                "email_valid": draw(st.integers(min_value=0, max_value=1)),
                "mobile_valid": draw(st.integers(min_value=0, max_value=1)),
            }
            for client_id in lead_clients
        ],
        columns=["client_id", "digital_app_user", "email_valid", "mobile_valid"],
    )

    # --- promo_history frame: each promo allows a non-empty channel subset --
    promo_history = pd.DataFrame(
        [
            {
                "promo_id": promo_id,
                "channels": draw(st.sampled_from(_CHANNEL_SUBSETS)),
                "mechanic": draw(
                    st.sampled_from(["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"])
                ),
            }
            for promo_id in promos
        ],
        columns=["promo_id", "channels", "mechanic"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    segments["p_join"] = pd.to_numeric(segments["p_join"], errors="raise")
    for column in (
        "promo_id",
        "client_id",
        "capacity_php",
        "segment",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ):
        segments[column] = segments[column].astype("object")
    for column in ("digital_app_user", "email_valid", "mobile_valid"):
        customer_dna[column] = pd.to_numeric(customer_dna[column]).astype(int)
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    for column in ("promo_id", "channels", "mechanic"):
        promo_history[column] = promo_history[column].astype("object")

    return {
        "segments": segments.reset_index(drop=True),
        "ndb": ndb.reset_index(drop=True),
        "contact_history": contact_history.reset_index(drop=True),
        "customer_dna": customer_dna.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
    }


@st.composite
def control_split_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 2,
    min_cells_per_promo: int = 1,
    min_leads_per_cell: int = 1,
    max_leads_per_cell: int = 30,
) -> dict[str, pd.DataFrame]:
    """Composite strategy exercising the seeded per-Cell control split
    (Property 3).

    Unlike :func:`classifier_inputs` (which caps the client universe small and
    draws Leads from the full promo x client grid, so Cells rarely reach the
    ten-plus non-excluded Leads needed for a ``floor(0.10 x count)`` draw of
    ``k >= 1``), this strategy *builds Cells directly*: it chooses a set of
    (``promo_id``, ``segment``) Cells and gives each Cell a drawn number of
    Leads, each Lead a distinct client. Cell sizes span both sides of the
    ten-Lead boundary so both the ``k == 0`` case (fewer than ten non-excluded
    Leads, every Lead Sendable, Requirement 4.3) and the ``k >= 1`` case (a
    non-empty control holdout, Requirement 4.1) are richly reachable.

    To keep the focus on the split itself, every Lead is non-excluded: the NDB
    set is empty, no client is contacted (``Avg_Contacts_Per_Month == 0``),
    every client is fully reachable (all three DNA flags 1), and every promo
    allows every channel. So the whole of each Cell is the non-excluded Lead
    population the split draws from.

    The returned dict is keyed and shaped exactly like
    :func:`classifier_inputs` (and like ``loader.load``'s output), so the frames
    can be fed straight into ``classify``.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_cells_per_promo: lower bound on the number of distinct segments
            (Cells) drawn per promo.
        min_leads_per_cell / max_leads_per_cell: bounds on the number of Leads
            placed in each Cell. The upper bound comfortably exceeds ten so
            ``k >= 1`` draws are reachable.
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]

    segment_rows: list[dict[str, object]] = []
    client_counter = 0
    for promo_id in promos:
        n_cells = draw(
            st.integers(
                min_value=min(min_cells_per_promo, len(_SEGMENTS)),
                max_value=len(_SEGMENTS),
            )
        )
        cell_segments = draw(
            st.lists(
                st.sampled_from(_SEGMENTS),
                min_size=n_cells,
                max_size=n_cells,
                unique=True,
            )
        )
        for segment in cell_segments:
            n_leads = draw(
                st.integers(
                    min_value=min_leads_per_cell, max_value=max_leads_per_cell
                )
            )
            for _ in range(n_leads):
                client_counter += 1
                segment_rows.append(
                    {
                        "promo_id": promo_id,
                        "client_id": f"C{client_counter:05d}",
                        "p_join": draw(_p_join()),
                        "capacity_php": str(
                            draw(st.integers(min_value=0, max_value=100_000))
                        ),
                        "segment": segment,
                        "top_driver_1": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_2": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_3": draw(st.sampled_from(_TOP_DRIVERS)),
                    }
                )

    segments = pd.DataFrame(
        segment_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "capacity_php",
            "segment",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    lead_clients = sorted({str(c) for c in segments["client_id"]})

    # --- ndb / contact_history: empty, so every Lead is non-excluded -------
    ndb = pd.DataFrame(columns=["client_id", "flag_type", "flag_date"])
    contact_history = pd.DataFrame(
        columns=["client_id", "contact_date", "campaign_id", "channel"]
    )

    # --- customer_dna: every client fully reachable ------------------------
    customer_dna = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "digital_app_user": 1,
                "email_valid": 1,
                "mobile_valid": 1,
            }
            for client_id in lead_clients
        ],
        columns=["client_id", "digital_app_user", "email_valid", "mobile_valid"],
    )

    # --- promo_history: every promo allows every channel -------------------
    promo_history = pd.DataFrame(
        [
            {
                "promo_id": promo_id,
                "channels": "Email, In-app, SMS",
                "mechanic": draw(
                    st.sampled_from(["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"])
                ),
            }
            for promo_id in promos
        ],
        columns=["promo_id", "channels", "mechanic"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    segments["p_join"] = pd.to_numeric(segments["p_join"], errors="raise")
    for column in (
        "promo_id",
        "client_id",
        "capacity_php",
        "segment",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ):
        segments[column] = segments[column].astype("object")
    for column in ("digital_app_user", "email_valid", "mobile_valid"):
        customer_dna[column] = pd.to_numeric(customer_dna[column]).astype(int)
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    for column in ("promo_id", "channels", "mechanic"):
        promo_history[column] = promo_history[column].astype("object")

    return {
        "segments": segments.reset_index(drop=True),
        "ndb": ndb.reset_index(drop=True),
        "contact_history": contact_history.reset_index(drop=True),
        "customer_dna": customer_dna.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
    }


@st.composite
def partition_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 2,
    min_cells_per_promo: int = 1,
    min_leads_per_cell: int = 1,
    max_leads_per_cell: int = 30,
) -> dict[str, pd.DataFrame]:
    """Composite strategy producing Cells whose Leads span all three partitions
    — excluded, control, and sendable (Property 4).

    :func:`classifier_inputs` and :func:`best_channel_inputs` produce exclusions
    but draw Leads from the full promo x client grid, so Cells rarely reach the
    ten-plus non-excluded Leads a ``floor(0.10 x count)`` control draw needs to
    yield ``k >= 1``; :func:`control_split_inputs` builds large Cells but
    pre-excludes nothing, so a Cell never carries an Excluded_Lead. This
    strategy *builds Cells directly* (like :func:`control_split_inputs`, large
    enough for a non-empty control draw) **and** gives each Lead one of three
    independently drawn fates so excluded, control, and sendable Leads all show
    up together in the same Cell:

    - **ndb** — the client is placed on the do-not-contact list and is fully
      reachable, so it is excluded with reason ``"ndb"``;
    - **unreachable** — the client has every DNA reachability flag 0 while its
      promo still allows every channel, so it is excluded with reason
      ``"no reachable channel"``;
    - **reachable** — the client is on no list, has every reachability flag 1,
      and has no contact rows (``Avg_Contacts_Per_Month == 0``), so it is
      non-excluded and enters the per-Cell control split.

    The fate is drawn per Lead, so a Cell typically mixes all three; Cell sizes
    span both sides of the ten-Lead boundary so the ``k == 0`` (all non-excluded
    Leads Sendable) and ``k >= 1`` (a non-empty control holdout) cases are both
    reachable. Contact history is left empty — the ``"over_contacted"`` reason
    is already covered by Property 1's strategy — so the exclusion reasons seen
    here are ``"ndb"`` and ``"no reachable channel"``.

    The returned dict is keyed and shaped exactly like
    :func:`classifier_inputs` (and like ``loader.load``'s output), so the frames
    can be fed straight into ``classify`` and then the Card_Builder.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_cells_per_promo: lower bound on the number of distinct segments
            (Cells) drawn per promo.
        min_leads_per_cell / max_leads_per_cell: bounds on the number of Leads
            placed in each Cell. The upper bound comfortably exceeds ten so
            ``k >= 1`` control draws are reachable.
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]

    segment_rows: list[dict[str, object]] = []
    # Per-client fate, so the classifier's exclusion/reachability decisions can
    # be set up coherently across the NDB / DNA frames.
    client_fate: dict[str, str] = {}
    client_counter = 0
    for promo_id in promos:
        n_cells = draw(
            st.integers(
                min_value=min(min_cells_per_promo, len(_SEGMENTS)),
                max_value=len(_SEGMENTS),
            )
        )
        cell_segments = draw(
            st.lists(
                st.sampled_from(_SEGMENTS),
                min_size=n_cells,
                max_size=n_cells,
                unique=True,
            )
        )
        for segment in cell_segments:
            n_leads = draw(
                st.integers(
                    min_value=min_leads_per_cell, max_value=max_leads_per_cell
                )
            )
            for _ in range(n_leads):
                client_counter += 1
                client_id = f"C{client_counter:05d}"
                client_fate[client_id] = draw(
                    st.sampled_from(["ndb", "unreachable", "reachable"])
                )
                segment_rows.append(
                    {
                        "promo_id": promo_id,
                        "client_id": client_id,
                        "p_join": draw(_p_join()),
                        "capacity_php": str(
                            draw(st.integers(min_value=0, max_value=100_000))
                        ),
                        "segment": segment,
                        "top_driver_1": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_2": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_3": draw(st.sampled_from(_TOP_DRIVERS)),
                    }
                )

    segments = pd.DataFrame(
        segment_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "capacity_php",
            "segment",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    lead_clients = sorted(client_fate)

    # --- ndb frame: the "ndb"-fate clients are on the do-not-contact list ---
    ndb = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "flag_type": "regulatory",
                "flag_date": "2026-01-01",
            }
            for client_id in lead_clients
            if client_fate[client_id] == "ndb"
        ],
        columns=["client_id", "flag_type", "flag_date"],
    )

    # --- contact_history: empty, so no Lead is excluded "over_contacted" ----
    contact_history = pd.DataFrame(
        columns=["client_id", "contact_date", "campaign_id", "channel"]
    )

    # --- customer_dna: "unreachable"-fate clients have every flag 0, the rest
    # (ndb and reachable) have every flag 1 ---------------------------------
    customer_dna = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "digital_app_user": 0 if client_fate[client_id] == "unreachable" else 1,
                "email_valid": 0 if client_fate[client_id] == "unreachable" else 1,
                "mobile_valid": 0 if client_fate[client_id] == "unreachable" else 1,
            }
            for client_id in lead_clients
        ],
        columns=["client_id", "digital_app_user", "email_valid", "mobile_valid"],
    )

    # --- promo_history: every promo allows every channel, so reachability is
    # governed purely by the DNA flags -------------------------------------
    promo_history = pd.DataFrame(
        [
            {
                "promo_id": promo_id,
                "channels": "Email, In-app, SMS",
                "mechanic": draw(
                    st.sampled_from(["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"])
                ),
            }
            for promo_id in promos
        ],
        columns=["promo_id", "channels", "mechanic"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    segments["p_join"] = pd.to_numeric(segments["p_join"], errors="raise")
    for column in (
        "promo_id",
        "client_id",
        "capacity_php",
        "segment",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ):
        segments[column] = segments[column].astype("object")
    for column in ("client_id", "flag_type", "flag_date"):
        if not ndb.empty:
            ndb[column] = ndb[column].astype("object")
    for column in ("digital_app_user", "email_valid", "mobile_valid"):
        customer_dna[column] = pd.to_numeric(customer_dna[column]).astype(int)
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    for column in ("promo_id", "channels", "mechanic"):
        promo_history[column] = promo_history[column].astype("object")

    return {
        "segments": segments.reset_index(drop=True),
        "ndb": ndb.reset_index(drop=True),
        "contact_history": contact_history.reset_index(drop=True),
        "customer_dna": customer_dna.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
    }


# A small pool of per-channel send costs for the Channel_Costs_File. The real
# pipeline's costs (In-app 1.17, Email 0.053, SMS 0.264) sit in this range; the
# values are drawn per channel so the reduction property sees varied, non-zero
# channel costs across examples. All three channels always carry a cost so a
# Sendable_Lead on any best_channel contributes a real per-send cost.
_CHANNEL_COST_CHOICES: list[float] = [0.053, 0.264, 1.17, 0.5, 2.0, 0.0]


@st.composite
def reduction_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 2,
    min_cells_per_promo: int = 1,
    min_leads_per_cell: int = 0,
    max_leads_per_cell: int = 20,
) -> dict[str, pd.DataFrame]:
    """Composite strategy exercising the per-Cell reductions and 90% range
    (Property 5).

    Property 5 is about the per-Cell folds over the Sendable_Leads —
    ``expected_joiners`` = Σ ``p_join``, ``total_channel_cost`` = Σ the per-send
    cost of each Lead's ``best_channel``, ``expected_value`` =
    ``expected_joiners × VALUE_PER_JOIN_PHP − total_channel_cost``, and the 90%
    range ``mean ± Z_90·√var`` with ``low`` clamped to 0 — so the input space it
    needs differs from the earlier strategies in two ways:

    - a **``channel_costs`` frame is present** (neither :func:`partition_inputs`
      nor :func:`control_split_inputs` supplies one, and the Card_Builder reads
      ``cost_map`` from ``frames["channel_costs"]``), carrying the three
      channels In-app / Email / SMS with drawn, mostly non-zero per-send costs
      so ``total_channel_cost`` is a genuine reduction over varied costs;
    - **varied ``best_channel`` across Sendable_Leads** so the cost sum mixes
      several per-channel costs: every client is fully reachable (all three DNA
      flags 1) and every promo allows every channel, so each Sendable_Lead's
      best_channel is simply the first in priority order present — but because
      the earlier priority channels are always allowed-and-reachable here, to
      get channel variety the promos' Allowed_Channels are instead drawn per
      promo from the non-empty channel subsets, which shifts which channel wins.

    Cells mix excluded, control, and sendable Leads (like
    :func:`partition_inputs`) and ``min_leads_per_cell`` defaults to 0 so some
    Cells can end up with **zero Sendable_Leads**, exercising the empty-Cell
    branch of Requirement 5.6 (all reductions and both range bounds 0). Leads
    draw one of three fates — ``ndb`` (excluded "ndb"), ``over`` (excluded
    "over_contacted" via contact history), or ``reachable`` (non-excluded,
    entering the control split) — so excluded, control, and sendable Leads
    coexist and the non-excluded population (hence the Sendable set) varies in
    size across Cells.

    The returned dict is keyed ``segments`` / ``ndb`` / ``contact_history`` /
    ``channel_costs`` / ``customer_dna`` / ``promo_history``, each shaped like
    ``loader.load``'s output, so the frames feed straight into
    ``_build_cards_from_frames``.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_cells_per_promo: lower bound on the number of distinct segments
            (Cells) drawn per promo.
        min_leads_per_cell / max_leads_per_cell: bounds on the number of Leads
            placed in each Cell. The lower bound of 0 lets a Cell end up with no
            Sendable_Leads (Requirement 5.6).
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]

    # Per promo, the Allowed_Channels drawn from the non-empty subsets. Varying
    # the allow-list shifts which priority-ordered channel wins as best_channel,
    # so the Sendable_Leads of different Cells carry different best_channels and
    # the channel-cost sum mixes several per-channel costs.
    promo_channels = {
        promo_id: draw(st.sampled_from(_CHANNEL_SUBSETS)) for promo_id in promos
    }

    segment_rows: list[dict[str, object]] = []
    client_fate: dict[str, str] = {}
    client_counter = 0
    for promo_id in promos:
        n_cells = draw(
            st.integers(
                min_value=min(min_cells_per_promo, len(_SEGMENTS)),
                max_value=len(_SEGMENTS),
            )
        )
        cell_segments = draw(
            st.lists(
                st.sampled_from(_SEGMENTS),
                min_size=n_cells,
                max_size=n_cells,
                unique=True,
            )
        )
        for segment in cell_segments:
            n_leads = draw(
                st.integers(
                    min_value=min_leads_per_cell, max_value=max_leads_per_cell
                )
            )
            for _ in range(n_leads):
                client_counter += 1
                client_id = f"C{client_counter:05d}"
                client_fate[client_id] = draw(
                    st.sampled_from(["ndb", "over", "reachable"])
                )
                segment_rows.append(
                    {
                        "promo_id": promo_id,
                        "client_id": client_id,
                        "p_join": draw(_p_join()),
                        "capacity_php": str(
                            draw(st.integers(min_value=0, max_value=100_000))
                        ),
                        "segment": segment,
                        "top_driver_1": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_2": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_3": draw(st.sampled_from(_TOP_DRIVERS)),
                    }
                )

    segments = pd.DataFrame(
        segment_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "capacity_php",
            "segment",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    lead_clients = sorted(client_fate)

    # --- ndb frame: the "ndb"-fate clients are on the do-not-contact list ---
    ndb = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "flag_type": "regulatory",
                "flag_date": "2026-01-01",
            }
            for client_id in lead_clients
            if client_fate[client_id] == "ndb"
        ],
        columns=["client_id", "flag_type", "flag_date"],
    )

    # --- contact_history: the "over"-fate clients get > 3 contacts/month,
    # excluding them "over_contacted"; all events land in one YYYY-MM month so
    # the average is simply the event count -------------------------------
    contact_rows: list[dict[str, str]] = []
    for client_id in lead_clients:
        if client_fate[client_id] != "over":
            continue
        # 4+ events in a single month -> Avg_Contacts_Per_Month > 3.
        n_events = draw(st.integers(min_value=4, max_value=8))
        for i in range(n_events):
            day = _DAYS[i % len(_DAYS)]
            contact_rows.append(
                {
                    "client_id": client_id,
                    "contact_date": f"{_MONTHS[0]}-{day}",
                    "campaign_id": "CMP1",
                    "channel": "Email",
                }
            )
    contact_history = pd.DataFrame(
        contact_rows,
        columns=["client_id", "contact_date", "campaign_id", "channel"],
    )

    # --- customer_dna: every client fully reachable, so a non-excluded Lead's
    # best_channel is the first channel in priority order its promo allows ---
    customer_dna = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "digital_app_user": 1,
                "email_valid": 1,
                "mobile_valid": 1,
            }
            for client_id in lead_clients
        ],
        columns=["client_id", "digital_app_user", "email_valid", "mobile_valid"],
    )

    # --- promo_history: the per-promo Allowed_Channels drawn above ---------
    promo_history = pd.DataFrame(
        [
            {
                "promo_id": promo_id,
                "channels": promo_channels[promo_id],
                "mechanic": draw(
                    st.sampled_from(["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"])
                ),
            }
            for promo_id in promos
        ],
        columns=["promo_id", "channels", "mechanic"],
    )

    # --- channel_costs frame: the three channels with drawn per-send costs --
    # Shaped like loader.load's output: channel label as object,
    # cost_php_per_message coerced to float.
    channel_costs = pd.DataFrame(
        [
            {
                "channel": channel,
                "cost_php_per_message": draw(st.sampled_from(_CHANNEL_COST_CHOICES)),
                "source": "assumption",
            }
            for channel in ("In-app", "Email", "SMS")
        ],
        columns=["channel", "cost_php_per_message", "source"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    segments["p_join"] = pd.to_numeric(segments["p_join"], errors="raise")
    for column in (
        "promo_id",
        "client_id",
        "capacity_php",
        "segment",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ):
        segments[column] = segments[column].astype("object")
    for column in ("client_id", "flag_type", "flag_date"):
        if not ndb.empty:
            ndb[column] = ndb[column].astype("object")
    for column in ("client_id", "contact_date", "campaign_id", "channel"):
        if not contact_history.empty:
            contact_history[column] = contact_history[column].astype("object")
    for column in ("digital_app_user", "email_valid", "mobile_valid"):
        customer_dna[column] = pd.to_numeric(customer_dna[column]).astype(int)
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    for column in ("promo_id", "channels", "mechanic"):
        promo_history[column] = promo_history[column].astype("object")
    channel_costs["cost_php_per_message"] = pd.to_numeric(
        channel_costs["cost_php_per_message"], errors="raise"
    )
    for column in ("channel", "source"):
        channel_costs[column] = channel_costs[column].astype("object")

    return {
        "segments": segments.reset_index(drop=True),
        "ndb": ndb.reset_index(drop=True),
        "contact_history": contact_history.reset_index(drop=True),
        "channel_costs": channel_costs.reset_index(drop=True),
        "customer_dna": customer_dna.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
    }


# A p_join pool for the action strategy that straddles the expected-value sign
# boundary. ``expected_value = Σ p_join × VALUE_PER_JOIN_PHP − total_channel_cost``
# with per-send costs at most a couple of pesos, so a single Sendable_Lead with
# p_join above ~0.002 already pushes expected_value strictly positive, while a
# Cell whose Sendable_Leads all have p_join == 0 has expected_value ≤ 0 (exactly
# ``−total_channel_cost``, which is ≤ 0). Drawing p_join from {0.0} ∪ a band of
# clearly-positive values lets Hypothesis reach both the EV > 0 and the EV ≤ 0
# sides of every segment's action branch.
_ACTION_P_JOIN_CHOICES: list[float] = [0.0, 0.0, 0.2, 0.5, 0.8, 1.0]


@st.composite
def action_inputs(
    draw: st.DrawFn,
    *,
    min_promos: int = 1,
    max_promos: int = 3,
    min_cells_per_promo: int = 1,
    min_leads_per_cell: int = 0,
    max_leads_per_cell: int = 12,
) -> dict[str, pd.DataFrame]:
    """Composite strategy exercising the four-way action rule (Property 6).

    Property 6 is about the ``action`` field each Card carries: it is
    ``"Prioritize"`` when the segment is ``"Ready Toppers"`` and
    ``expected_value > 0``; else ``"Offer lower tier"`` when the promo's
    ``mechanic == "TOP_UP"`` and the segment is ``"Willing but Stretched"`` and
    ``expected_value > 0``; else ``"Include"`` when ``expected_value > 0``; else
    ``"Skip"``. To make all four branches reachable, this strategy varies three
    axes:

    - **segment** — Cells are built across all four labels, so ``"Ready
      Toppers"`` (the Prioritize branch), ``"Willing but Stretched"`` (the
      Offer-lower-tier branch), and the other two segments (the plain Include
      branch) all appear;
    - **promo mechanic** — drawn per promo from ``{TOP_UP, NEW_ACCOUNT,
      ADB_INCREASE}``, so the ``mechanic == "TOP_UP"`` condition of the
      Offer-lower-tier branch is met for some Cells and not others (a
      ``"Willing but Stretched"`` Cell under a non-``TOP_UP`` promo must fall
      through to ``"Include"``);
    - **expected_value sign** — ``p_join`` is drawn from ``{0.0}`` ∪ a band of
      clearly-positive values, and ``min_leads_per_cell`` defaults to 0, so a
      Cell's Sendable_Leads can sum to a strictly-positive ``expected_joiners``
      (``expected_value > 0``, since the per-send costs are at most a couple of
      pesos) **or** to zero joiners (``expected_value ≤ 0``, driving the
      ``"Skip"`` branch), including Cells with no Sendable_Leads at all
      (``expected_value == 0`` ⇒ ``"Skip"``).

    To keep the focus on the action rule, every Lead is non-excluded: the NDB
    set is empty, no client is contacted (``Avg_Contacts_Per_Month == 0``),
    every client is fully reachable (all three DNA flags 1), and every promo
    allows every channel. So every Lead is a Sendable or Control Lead and the
    Sendable_Leads drive each Cell's ``expected_value``. A ``channel_costs``
    frame is present (the Card_Builder reads ``cost_map`` from it) carrying the
    three channels with small per-send costs.

    The returned dict is keyed ``segments`` / ``ndb`` / ``contact_history`` /
    ``channel_costs`` / ``customer_dna`` / ``promo_history``, each shaped like
    ``loader.load``'s output, so the frames feed straight into
    ``_build_cards_from_frames``.

    Args:
        min_promos / max_promos: bounds on the distinct promo universe.
        min_cells_per_promo: lower bound on the number of distinct segments
            (Cells) drawn per promo.
        min_leads_per_cell / max_leads_per_cell: bounds on the number of Leads
            placed in each Cell. The lower bound of 0 lets a Cell end up with no
            Sendable_Leads (the Skip branch via ``expected_value == 0``).
    """
    n_promos = draw(st.integers(min_value=min_promos, max_value=max_promos))
    promos = [f"P{i:03d}" for i in range(1, n_promos + 1)]

    # Per-promo mechanic, so the action rule's ``mechanic == "TOP_UP"`` branch
    # is met for some Cells and not others.
    promo_mechanic = {
        promo_id: draw(st.sampled_from(["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE"]))
        for promo_id in promos
    }

    segment_rows: list[dict[str, object]] = []
    client_counter = 0
    for promo_id in promos:
        n_cells = draw(
            st.integers(
                min_value=min(min_cells_per_promo, len(_SEGMENTS)),
                max_value=len(_SEGMENTS),
            )
        )
        cell_segments = draw(
            st.lists(
                st.sampled_from(_SEGMENTS),
                min_size=n_cells,
                max_size=n_cells,
                unique=True,
            )
        )
        for segment in cell_segments:
            n_leads = draw(
                st.integers(
                    min_value=min_leads_per_cell, max_value=max_leads_per_cell
                )
            )
            for _ in range(n_leads):
                client_counter += 1
                segment_rows.append(
                    {
                        "promo_id": promo_id,
                        "client_id": f"C{client_counter:05d}",
                        "p_join": draw(st.sampled_from(_ACTION_P_JOIN_CHOICES)),
                        "capacity_php": str(
                            draw(st.integers(min_value=0, max_value=100_000))
                        ),
                        "segment": segment,
                        "top_driver_1": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_2": draw(st.sampled_from(_TOP_DRIVERS)),
                        "top_driver_3": draw(st.sampled_from(_TOP_DRIVERS)),
                    }
                )

    segments = pd.DataFrame(
        segment_rows,
        columns=[
            "promo_id",
            "client_id",
            "p_join",
            "capacity_php",
            "segment",
            "top_driver_1",
            "top_driver_2",
            "top_driver_3",
        ],
    )

    lead_clients = sorted({str(c) for c in segments["client_id"]})

    # --- ndb / contact_history: empty, so every Lead is non-excluded -------
    ndb = pd.DataFrame(columns=["client_id", "flag_type", "flag_date"])
    contact_history = pd.DataFrame(
        columns=["client_id", "contact_date", "campaign_id", "channel"]
    )

    # --- customer_dna: every client fully reachable ------------------------
    customer_dna = pd.DataFrame(
        [
            {
                "client_id": client_id,
                "digital_app_user": 1,
                "email_valid": 1,
                "mobile_valid": 1,
            }
            for client_id in lead_clients
        ],
        columns=["client_id", "digital_app_user", "email_valid", "mobile_valid"],
    )

    # --- promo_history: every promo allows every channel; the mechanic is the
    # per-promo mechanic drawn above ----------------------------------------
    promo_history = pd.DataFrame(
        [
            {
                "promo_id": promo_id,
                "channels": "Email, In-app, SMS",
                "mechanic": promo_mechanic[promo_id],
            }
            for promo_id in promos
        ],
        columns=["promo_id", "channels", "mechanic"],
    )

    # --- channel_costs frame: the three channels with small per-send costs --
    channel_costs = pd.DataFrame(
        [
            {
                "channel": channel,
                "cost_php_per_message": draw(st.sampled_from(_CHANNEL_COST_CHOICES)),
                "source": "assumption",
            }
            for channel in ("In-app", "Email", "SMS")
        ],
        columns=["channel", "cost_php_per_message", "source"],
    )

    # --- dtype coercion matching the loader's output -----------------------
    segments["p_join"] = pd.to_numeric(segments["p_join"], errors="raise")
    for column in (
        "promo_id",
        "client_id",
        "capacity_php",
        "segment",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ):
        segments[column] = segments[column].astype("object")
    for column in ("digital_app_user", "email_valid", "mobile_valid"):
        customer_dna[column] = pd.to_numeric(customer_dna[column]).astype(int)
    customer_dna["client_id"] = customer_dna["client_id"].astype("object")
    for column in ("promo_id", "channels", "mechanic"):
        promo_history[column] = promo_history[column].astype("object")
    channel_costs["cost_php_per_message"] = pd.to_numeric(
        channel_costs["cost_php_per_message"], errors="raise"
    )
    for column in ("channel", "source"):
        channel_costs[column] = channel_costs[column].astype("object")

    return {
        "segments": segments.reset_index(drop=True),
        "ndb": ndb.reset_index(drop=True),
        "contact_history": contact_history.reset_index(drop=True),
        "channel_costs": channel_costs.reset_index(drop=True),
        "customer_dna": customer_dna.reset_index(drop=True),
        "promo_history": promo_history.reset_index(drop=True),
    }
