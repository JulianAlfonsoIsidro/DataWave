"""Property-based test for the Part4_Cards_Pipeline exclusion cascade.

Covers Property 1 of the part4-cards spec: exclusion is exactly the ordered
cascade, with NDB membership taking precedence over over-contact. A Lead is
excluded "ndb" whenever its client is in the NDB set (even if that client is
also over-contacted), and "over_contacted" for a Lead not in the NDB set whose
``Avg_Contacts_Per_Month`` is strictly greater than 3, where
``Avg_Contacts_Per_Month`` is the client's total contact events divided by its
number of distinct ``YYYY-MM`` months and is 0 for a client with no contact
rows.

This is a classification property, so the assertion is made against an
independent, straightforward reference computation (a plain per-client Python
count of contact events grouped by distinct ``YYYY-MM`` month, and a plain NDB
set-membership test) rather than a restatement of the vectorized
implementation in ``classify``.

Scope note: ``best_channel`` and the "no reachable channel" exclusion are
later-task placeholders (tasks 3.3 / 3.5), so this test exercises and asserts
only the NDB and over_contacted portions of the cascade that task 3.1
implements. It additionally confirms that no *other* exclusion reason leaks in
from this task.
"""

from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd
from hypothesis import given, settings

from part4_cards.classify import classify
from part4_cards.config import Config
from tests.strategies_part4 import (
    best_channel_inputs,
    classifier_inputs,
    control_split_inputs,
)

# The best_channel priority order from the spec (Requirement 3.1), named here
# independently of the implementation constant, together with the DNA flag that
# gates each channel (Requirements 3.2-3.4): In-app by digital_app_user, Email
# by email_valid, SMS by mobile_valid.
_PRIORITY: list[tuple[str, str]] = [
    ("In-app", "digital_app_user"),
    ("Email", "email_valid"),
    ("SMS", "mobile_valid"),
]

# The over-contact threshold from the spec: strictly more than 3 contacts per
# month is over-contacted (Requirement 2.2). Named here independently of the
# implementation constant so the reference does not import the module under
# test's threshold.
_OVER_CONTACT_THRESHOLD = 3


def _reference_avg_contacts_per_month(
    contact_history: pd.DataFrame,
) -> dict[str, float]:
    """Independently compute Avg_Contacts_Per_Month per client.

    Walks the contact rows one at a time (no pandas groupby), tallying each
    client's total event count and the set of distinct ``YYYY-MM`` months in
    which those events fall (the leading seven characters of the
    ``YYYY-MM-DD`` string). The average is total events / distinct months. A
    client with no contact rows is simply absent from the mapping, and the
    caller treats a miss as 0 (Requirements 2.3, 2.4). This is a deliberately
    plain, independent reference, not a copy of the vectorized computation.
    """
    totals: dict[str, int] = defaultdict(int)
    months: dict[str, set[str]] = defaultdict(set)
    for client_id, contact_date in zip(
        contact_history["client_id"], contact_history["contact_date"]
    ):
        totals[str(client_id)] += 1
        months[str(client_id)].add(str(contact_date)[:7])
    return {
        client_id: totals[client_id] / len(months[client_id])
        for client_id in totals
    }


# Feature: part4-cards, Property 1: Exclusion is exactly the ordered cascade, NDB taking precedence over over-contact
@settings(max_examples=200)
@given(classifier_inputs())
def test_exclusion_is_the_ordered_ndb_then_over_contacted_cascade(frames):
    """Exclusion matches an independent reference of the ordered cascade.

    For every Lead, an independent reference computes the NDB membership and
    the Avg_Contacts_Per_Month, then derives the expected exclusion from the
    ordered cascade (NDB first, then over-contacted). The classifier's
    ``excluded`` / ``exclusion_reason`` must agree with that reference:

    - a Lead whose client is in the NDB set is excluded "ndb" — even when the
      same client is over-contacted (precedence, Requirement 2.1);
    - a Lead whose client is *not* in the NDB set and whose
      Avg_Contacts_Per_Month is strictly greater than 3 is excluded
      "over_contacted" (Requirement 2.2);
    - a client with no contact rows has Avg_Contacts_Per_Month 0 and is never
      "over_contacted" (Requirements 2.3, 2.4).

    Only the NDB / over_contacted portions of the cascade are implemented by
    this task, so the test also asserts the classifier produces no other
    exclusion reason here.

    Validates: Requirements 2.1, 2.2, 2.3, 2.4
    """
    leads = classify(frames, Config())

    ndb_set = {str(c) for c in frames["ndb"]["client_id"]}
    avg_contacts = _reference_avg_contacts_per_month(frames["contact_history"])

    assert len(leads) == len(frames["segments"])

    for client_id, excluded, reason in zip(
        leads["client_id"], leads["excluded"], leads["exclusion_reason"]
    ):
        client_id = str(client_id)
        in_ndb = client_id in ndb_set
        avg = avg_contacts.get(client_id, 0.0)
        over_contacted = (not in_ndb) and (avg > _OVER_CONTACT_THRESHOLD)

        # Derive the expected cascade outcome from the independent reference.
        if in_ndb:
            expected_reason = "ndb"
        elif over_contacted:
            expected_reason = "over_contacted"
        else:
            # No NDB/over_contacted exclusion; best_channel/unreachable is a
            # later task, so the Lead is not excluded by this task.
            expected_reason = ""

        # Only the two implemented reasons may appear from this task.
        assert reason in ("", "ndb", "over_contacted"), (
            f"client {client_id}: unexpected exclusion_reason {reason!r}"
        )

        # exclusion_reason matches the ordered cascade exactly.
        assert reason == expected_reason, (
            f"client {client_id}: in_ndb={in_ndb} avg={avg} "
            f"reason={reason!r} expected={expected_reason!r}"
        )

        # excluded is the iff companion of a non-empty reason.
        assert bool(excluded) == (expected_reason != ""), (
            f"client {client_id}: excluded={excluded} reason={expected_reason!r}"
        )

        # NDB precedence: an NDB client is never recorded as over_contacted,
        # even when its contacts/month exceeds the threshold (Requirement 2.1).
        if in_ndb:
            assert reason == "ndb"
            assert reason != "over_contacted"


def _reference_allowed_channels(promo_history: pd.DataFrame) -> dict[str, set[str]]:
    """Independently parse each promo's Allowed_Channels from its ``channels``.

    Splits the comma-separated ``channels`` string on commas and strips
    whitespace from each entry (empty entries dropped), yielding a mapping of
    ``promo_id`` -> set of allowed channel labels. A deliberately plain, direct
    parse, not a copy of the classifier's helper.
    """
    allowed: dict[str, set[str]] = {}
    for promo_id, channels in zip(promo_history["promo_id"], promo_history["channels"]):
        allowed[str(promo_id)] = {
            part.strip() for part in str(channels).split(",") if part.strip()
        }
    return allowed


def _reference_dna_flags(customer_dna: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Independently index each client's three reachability flags by client_id."""
    flags: dict[str, dict[str, int]] = {}
    for _, row in customer_dna.iterrows():
        flags[str(row["client_id"])] = {
            "digital_app_user": int(row["digital_app_user"]),
            "email_valid": int(row["email_valid"]),
            "mobile_valid": int(row["mobile_valid"]),
        }
    return flags


# Feature: part4-cards, Property 2: best_channel is the first allowed-and-reachable channel in priority order, else the Lead is excluded unreachable
@settings(max_examples=200)
@given(best_channel_inputs())
def test_best_channel_is_first_allowed_and_reachable_else_excluded_unreachable(frames):
    """best_channel matches an independent reference of the priority walk.

    For every Lead an independent reference walks the priority order
    [In-app, Email, SMS] and picks the first channel that is both in the
    promo's Allowed_Channels and reachable by the client's gating flag (In-app
    by digital_app_user, Email by email_valid, SMS by mobile_valid). The
    classifier's ``best_channel`` / ``excluded`` / ``exclusion_reason`` must
    agree with that reference:

    - a Lead with at least one allowed-and-reachable channel gets exactly the
      first such channel in priority order and is not excluded by this step
      (Requirements 3.1-3.4);
    - that chosen ``best_channel`` is always a member of the promo's
      Allowed_Channels;
    - a Lead with no allowed-and-reachable channel is excluded with
      ``exclusion_reason`` "no reachable channel" and has no ``best_channel``
      (Requirement 3.5).

    This strategy pre-excludes no Lead (empty NDB, empty contact history), so
    every Lead reaches the best_channel decision and the only exclusion reason
    that can appear is "no reachable channel".

    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
    """
    leads = classify(frames, Config())

    allowed = _reference_allowed_channels(frames["promo_history"])
    dna_flags = _reference_dna_flags(frames["customer_dna"])

    assert len(leads) == len(frames["segments"])

    for promo_id, client_id, excluded, reason, best_channel in zip(
        leads["promo_id"],
        leads["client_id"],
        leads["excluded"],
        leads["exclusion_reason"],
        leads["best_channel"],
    ):
        promo_id = str(promo_id)
        client_id = str(client_id)
        promo_allowed = allowed.get(promo_id, set())
        client_flags = dna_flags.get(
            client_id,
            {"digital_app_user": 0, "email_valid": 0, "mobile_valid": 0},
        )

        # Independent reference: first allowed-and-reachable channel in order.
        expected_channel = ""
        for channel, flag in _PRIORITY:
            if channel in promo_allowed and client_flags[flag] == 1:
                expected_channel = channel
                break

        if expected_channel:
            # A reachable Lead: best_channel is exactly the first qualifying
            # channel, the Lead is not excluded by this step, and the chosen
            # channel is a member of the promo's Allowed_Channels.
            assert best_channel == expected_channel, (
                f"promo {promo_id} client {client_id}: best_channel="
                f"{best_channel!r} expected {expected_channel!r} "
                f"(allowed={promo_allowed}, flags={client_flags})"
            )
            assert not bool(excluded), (
                f"promo {promo_id} client {client_id}: reachable Lead "
                f"unexpectedly excluded (reason {reason!r})"
            )
            assert reason == ""
            assert best_channel in promo_allowed, (
                f"promo {promo_id} client {client_id}: best_channel "
                f"{best_channel!r} not in Allowed_Channels {promo_allowed}"
            )
        else:
            # No allowed-and-reachable channel: excluded "no reachable channel"
            # with no best_channel (Requirement 3.5).
            assert bool(excluded), (
                f"promo {promo_id} client {client_id}: unreachable Lead not "
                f"excluded (allowed={promo_allowed}, flags={client_flags})"
            )
            assert reason == "no reachable channel", (
                f"promo {promo_id} client {client_id}: expected "
                f"'no reachable channel', got {reason!r}"
            )
            assert best_channel == "", (
                f"promo {promo_id} client {client_id}: excluded Lead has "
                f"best_channel {best_channel!r}"
            )


# Feature: part4-cards, Property 3: The control holdout is a reproducible floor-10% subset of the non-excluded Leads
@settings(max_examples=150)
@given(control_split_inputs())
def test_control_holdout_is_reproducible_floor_10pct_subset_of_non_excluded(frames):
    """The control split matches an independent reference of the floor-10% draw.

    For every Cell (``promo_id``, ``segment``) an independent reference counts
    the Cell's non-excluded Leads and derives the expected control size as
    ``floor(0.10 x count)``. The classifier's ``control`` flags must satisfy,
    per Cell:

    - the control count equals ``floor(0.10 x non-excluded count)``
      (Requirements 4.1, 4.3 — zero control Leads when the floor is 0);
    - every Control_Lead is one of that Cell's non-excluded Leads (no excluded
      Lead is ever a Control_Lead);
    - the Sendable_Leads are exactly the non-excluded Leads that are not
      Control_Leads (``Sendable = not excluded and control == 0``).

    Reproducibility (Requirement 4.5) is asserted directly by classifying the
    identical inputs a second time with the same ``Control_Seed`` and checking
    the set of Control_Lead keys is identical on both runs.

    The ``control_split_inputs`` strategy makes every Lead non-excluded and
    sizes Cells on both sides of the ten-Lead boundary, so both the ``k == 0``
    (all Sendable) and ``k >= 1`` (non-empty holdout) cases are exercised.

    Validates: Requirements 4.1, 4.3, 4.5
    """
    cfg = Config()
    leads = classify(frames, cfg)
    leads_again = classify(frames, cfg)

    assert len(leads) == len(frames["segments"])

    # Key each Lead by its (promo_id, client_id) pair so control membership can
    # be compared across the two independent runs regardless of row order.
    def _control_keys(frame: pd.DataFrame) -> set[tuple[str, str]]:
        return {
            (str(promo_id), str(client_id))
            for promo_id, client_id, control in zip(
                frame["promo_id"], frame["client_id"], frame["control"]
            )
            if int(control) == 1
        }

    # --- Reproducibility: identical inputs + same seed -> identical control set
    assert _control_keys(leads) == _control_keys(leads_again), (
        "control holdout differs between two runs on identical inputs"
    )

    # --- Per-Cell floor-10% size, subset, and sendable partition -----------
    for (promo_id, segment), cell in leads.groupby(
        ["promo_id", "segment"], sort=False
    ):
        non_excluded = cell[~cell["excluded"]]
        non_excluded_count = len(non_excluded)
        expected_control = math.floor(0.10 * non_excluded_count)

        control_leads = cell[cell["control"] == 1]
        control_count = len(control_leads)

        # control_count == floor(0.10 x non-excluded count) (4.1, 4.3).
        assert control_count == expected_control, (
            f"cell ({promo_id!r}, {segment!r}): control_count={control_count} "
            f"expected floor(0.10 x {non_excluded_count})={expected_control}"
        )

        # Every Control_Lead is a non-excluded Lead of this Cell (4.1): no
        # Control_Lead may be excluded.
        assert not control_leads["excluded"].any(), (
            f"cell ({promo_id!r}, {segment!r}): an excluded Lead was marked "
            f"control=1"
        )

        # Sendable_Leads are exactly the non-excluded Leads that are not
        # Control_Leads (Sendable = not excluded and control == 0).
        sendable = cell[(~cell["excluded"]) & (cell["control"] == 0)]
        sendable_keys = {str(c) for c in sendable["client_id"]}
        non_excluded_keys = {str(c) for c in non_excluded["client_id"]}
        control_keys = {str(c) for c in control_leads["client_id"]}

        assert sendable_keys == (non_excluded_keys - control_keys), (
            f"cell ({promo_id!r}, {segment!r}): Sendable set is not exactly the "
            f"non-excluded, non-control Leads"
        )
        # The non-excluded Leads partition cleanly into control + sendable.
        assert control_keys <= non_excluded_keys
        assert len(sendable) + control_count == non_excluded_count
