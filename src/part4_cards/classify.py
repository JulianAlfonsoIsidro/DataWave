"""Lead_Classifier for the Part4_Cards_Pipeline.

Turns the validated input frames into a per-Lead frame carrying the exclusion,
best_channel, and control decisions. This module never halts the run on
input-shape grounds; the Input_Loader has already guaranteed valid, coerced
frames.

``classify`` returns the Segments_File columns plus:

- ``excluded`` (bool): whether the Lead is removed from contact.
- ``exclusion_reason`` (str): the cause, empty when not excluded. One of
  ``"ndb"``, ``"over_contacted"``, or ``"no reachable channel"``.
- ``best_channel`` (str): the chosen channel, empty when excluded.
- ``control`` (int 0/1): the control-holdout flag.

The computation runs in a deterministic order: Avg_Contacts_Per_Month, then the
exclusion cascade (NDB first, then over-contact, then unreachable), then
best_channel, then the per-Cell control split. It implements the
Avg_Contacts_Per_Month computation, the NDB / over-contacted portions of the
cascade (Requirements 2.1-2.4), the best_channel selection gated by the promo's
Allowed_Channels and the client's reachability flags (Requirements 3.1-3.5,
including the "no reachable channel" exclusion), and the seeded per-Cell control
split that marks each Cell's holdout ``control=1`` and the remaining
non-excluded Leads ``control=0`` (Sendable) (Requirements 4.1-4.5).
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .config import (
    CHANNEL_FLAG,
    CHANNEL_PRIORITY,
    CONTROL_FRACTION,
    CONTROL_SEED,
    Config,
)

# The over-contact threshold: strictly more than 3 contacts per month is
# over-contacted (Requirement 2.2).
OVER_CONTACT_THRESHOLD = 3


def _cell_rng(control_seed: int, promo_id: str, segment: str) -> np.random.Generator:
    """A NumPy ``Generator`` seeded from a stable combination of the inputs.

    The seed is derived by hashing the three fields together with a BLAKE2b
    digest, so it is a pure function of ``(control_seed, promo_id, segment)`` —
    stable run-to-run and independent of Cell processing order (Requirement
    4.5). Python's built-in ``hash`` is unsuitable here because it is salted
    per-process for strings, so it would not be reproducible across runs; the
    cryptographic digest gives a fixed, portable 64-bit seed instead.
    """
    key = f"{control_seed}|{promo_id}|{segment}".encode("utf-8")
    digest = hashlib.blake2b(key, digest_size=8).digest()
    seed = int.from_bytes(digest, "big")
    return np.random.default_rng(seed)


def _allowed_channels(promo_history: pd.DataFrame) -> dict[str, set[str]]:
    """Parse each promo's ``channels`` string into its Allowed_Channels set.

    The Promo_History_File ``channels`` column is a comma-separated list such
    as ``"Email, In-app"``; it is parsed by splitting on comma and stripping
    whitespace from each entry (empty entries dropped). Returns a mapping of
    ``promo_id`` -> set of allowed channel labels (e.g. ``{"Email", "In-app"}``).
    """
    allowed: dict[str, set[str]] = {}
    for promo_id, channels in zip(
        promo_history["promo_id"], promo_history["channels"]
    ):
        parts = {c.strip() for c in str(channels).split(",") if c.strip()}
        allowed[str(promo_id)] = parts
    return allowed


def _avg_contacts_per_month(contact_history: pd.DataFrame) -> pd.Series:
    """Average contacts per month per client.

    Derives a ``YYYY-MM`` month from each ``contact_date`` (the leading seven
    characters of the ``YYYY-MM-DD`` string) and, per ``client_id``, divides the
    client's total count of contact events by the number of distinct months in
    which those events occurred (Requirement 2.3). Returns a Series indexed by
    ``client_id``; clients with no contact rows are simply absent and are
    treated as ``0`` when left-joined onto Leads (Requirement 2.4).
    """
    if contact_history.empty:
        return pd.Series(dtype=float, name="avg_contacts")

    months = contact_history["contact_date"].str.slice(0, 7)
    grouped = months.groupby(contact_history["client_id"])
    total_events = grouped.size()
    distinct_months = grouped.nunique()
    avg = (total_events / distinct_months).astype(float)
    avg.name = "avg_contacts"
    return avg


def classify(frames: dict[str, pd.DataFrame], cfg: Config) -> pd.DataFrame:
    """Classify each Lead: exclusion, best_channel, and control.

    Builds the per-Lead frame from the Segments_File and attaches the decision
    columns. It computes Avg_Contacts_Per_Month, applies the NDB /
    over-contacted portions of the exclusion cascade (Requirements 2.1-2.4),
    selects ``best_channel`` for the not-yet-excluded Leads, excluding the rest
    ``"no reachable channel"`` (Requirements 3.1-3.5), and then runs the seeded
    per-Cell control split to set ``control`` (Requirements 4.1-4.5).

    The exclusion cascade is first-match-wins in a fixed order so that NDB
    membership takes precedence: an NDB client is excluded ``"ndb"`` even if it
    is also over-contacted, so it never receives ``"over_contacted"``
    (Requirement 2.1).

    ``best_channel`` is chosen for a Lead that is not already excluded by
    walking ``CHANNEL_PRIORITY`` (In-app -> Email -> SMS) and taking the first
    channel that is both in the Lead promo's Allowed_Channels and reachable by
    the client's gating flag (``CHANNEL_FLAG``: In-app by ``digital_app_user``,
    Email by ``email_valid``, SMS by ``mobile_valid``). A not-yet-excluded Lead
    with no allowed-and-reachable channel is excluded ``"no reachable channel"``
    and its ``best_channel`` is left empty (Requirement 3.5).
    """
    leads = frames["segments"].copy()

    # --- Avg_Contacts_Per_Month, left-joined onto Leads; missing -> 0 ---
    # (Requirements 2.3, 2.4).
    avg = _avg_contacts_per_month(frames["contact_history"])
    leads = leads.merge(
        avg.rename("avg_contacts_per_month"),
        left_on="client_id",
        right_index=True,
        how="left",
    )
    leads["avg_contacts_per_month"] = leads["avg_contacts_per_month"].fillna(0.0)

    # --- Exclusion cascade (fixed order, first match wins) ---
    # 1. NDB membership -> "ndb" (evaluated first so NDB clients never get
    #    "over_contacted", Requirement 2.1).
    # 2. else Avg_Contacts_Per_Month > 3 -> "over_contacted" (Requirement 2.2).
    # 3. else (later task) no reachable channel -> "no reachable channel".
    ndb_set = set(frames["ndb"]["client_id"])
    is_ndb = leads["client_id"].isin(ndb_set)
    is_over_contacted = (~is_ndb) & (
        leads["avg_contacts_per_month"] > OVER_CONTACT_THRESHOLD
    )

    leads["exclusion_reason"] = np.select(
        [is_ndb, is_over_contacted],
        ["ndb", "over_contacted"],
        default="",
    )
    leads["excluded"] = leads["exclusion_reason"] != ""

    # --- best_channel selection, gated by promo allow-list and reachability ---
    # For a Lead not already excluded above, walk CHANNEL_PRIORITY
    # (In-app -> Email -> SMS) and take the first channel that is both in the
    # promo's Allowed_Channels and reachable by the client's gating flag
    # (Requirements 3.1-3.4). A not-yet-excluded Lead with no qualifying channel
    # is excluded "no reachable channel" with an empty best_channel
    # (Requirement 3.5).
    allowed = _allowed_channels(frames["promo_history"])

    # Bring the three DNA reachability flags onto the Leads by client_id.
    # Missing clients (absent from the DNA file) have no valid channel, so
    # their flags are treated as 0 (unreachable on every channel).
    dna = frames["customer_dna"]
    flag_cols = list(dict.fromkeys(CHANNEL_FLAG.values()))
    leads = leads.merge(
        dna[["client_id", *flag_cols]],
        on="client_id",
        how="left",
    )
    for flag in flag_cols:
        leads[flag] = leads[flag].fillna(0).astype(int)

    # Each Lead's set of promo-allowed channels, looked up by promo_id.
    promo_allowed = leads["promo_id"].map(lambda pid: allowed.get(str(pid), set()))

    # Walk the priority order, assigning the first allowed-and-reachable channel
    # to Leads that are not yet excluded and do not yet have a best_channel.
    best_channel = pd.Series("", index=leads.index, dtype="object")
    candidate_mask = ~leads["excluded"]
    for channel in CHANNEL_PRIORITY:
        flag = CHANNEL_FLAG[channel]
        is_allowed = promo_allowed.map(lambda chans, ch=channel: ch in chans)
        is_reachable = leads[flag] == 1
        assign = candidate_mask & (best_channel == "") & is_allowed & is_reachable
        best_channel = best_channel.mask(assign, channel)

    leads["best_channel"] = best_channel

    # Not-yet-excluded Leads that found no channel are unreachable: exclude them
    # "no reachable channel" and leave best_channel empty (Requirement 3.5).
    unreachable = candidate_mask & (best_channel == "")
    leads.loc[unreachable, "exclusion_reason"] = "no reachable channel"
    leads.loc[unreachable, "excluded"] = True

    # Drop the DNA flag helper columns; they are not part of the Lead frame's
    # output schema.
    leads = leads.drop(columns=flag_cols)

    # --- Seeded per-Cell control split (Requirements 4.1-4.5) ---
    # For each Cell (promo_id, segment): take the non-excluded Leads sorted by
    # client_id (a stable, input-order-independent key) and draw
    # k = floor(CONTROL_FRACTION x count) of them with a NumPy Generator seeded
    # from a stable combination of (CONTROL_SEED, promo_id, segment). Drawn
    # Leads get control=1; every other non-excluded Lead gets control=0
    # (Sendable). Excluded Leads get control=0 but are never Sendable
    # (Sendable = not excluded and control == 0). When k == 0 every non-excluded
    # Lead is Sendable (Requirement 4.3). Seeding per Cell from the fixed base
    # seed makes the control set identical on re-run with the same seed and
    # independent of Cell processing order (Requirement 4.5).
    control = pd.Series(0, index=leads.index, dtype=int)
    not_excluded = leads[~leads["excluded"]]
    for (promo_id, segment), cell in not_excluded.groupby(
        ["promo_id", "segment"], sort=False
    ):
        # Sort the Cell's non-excluded Leads by client_id so the draw is
        # independent of the input row order.
        ordered = cell.sort_values("client_id")
        count = len(ordered)
        k = int(np.floor(CONTROL_FRACTION * count))
        if k == 0:
            continue
        rng = _cell_rng(CONTROL_SEED, str(promo_id), str(segment))
        drawn = rng.choice(count, size=k, replace=False)
        control_index = ordered.index[np.sort(drawn)]
        control.loc[control_index] = 1

    leads["control"] = control

    return leads
