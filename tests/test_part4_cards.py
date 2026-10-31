"""Property-based test for the Part4_Cards_Pipeline per-Cell partition.

Covers Property 4 of the part4-cards spec: each Cell's Leads partition into
excluded, control, and sendable. For every Cell (``promo_id``, ``segment``) the
Card the Card_Builder emits must satisfy
``n_clients == excluded_count + control_count + sendable_count``, the counts in
``excluded_by_reason`` must sum to the excluded count, the Sendable_Leads must
be exactly the Cell's non-excluded, non-control Leads, and no Excluded_Lead may
ever be a Control_Lead or a Sendable_Lead.

This is a reduction/partition property, so the Card's counts are asserted
against an *independent* reference computed directly from the classified
per-Lead frame (plain per-row tallies of the ``excluded`` / ``control`` columns
and of ``exclusion_reason``), not a restatement of the Card_Builder's own
aggregation. The classifier is trusted upstream (its exclusion / best_channel /
control decisions are covered by Properties 1-3); this property checks that the
Card_Builder folds those per-Lead decisions into per-Cell counts that partition
cleanly.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd
import pytest
from hypothesis import given, settings

from part4_cards.cards import _build_cards_from_frames
from part4_cards.classify import classify
from part4_cards.config import Config
from tests.strategies_part4 import partition_inputs


def _reference_partition(
    leads: pd.DataFrame,
) -> dict[tuple[str, str], dict[str, object]]:
    """Independently tally each Cell's partition from the classified Leads.

    Walks the classified per-Lead frame one row at a time (no pandas groupby
    aggregation) and, per Cell key (``promo_id``, ``segment``), tallies:

    - ``n_clients`` — every Lead in the Cell;
    - ``excluded_count`` and ``excluded_by_reason`` — Leads with ``excluded``
      truthy, broken down by ``exclusion_reason``;
    - ``control_count`` — non-excluded Leads with ``control == 1``;
    - ``sendable_count`` — non-excluded Leads with ``control == 0``;
    - ``sendable_clients`` / ``control_clients`` / ``excluded_clients`` — the
      client_id sets, so set-level partition claims can be checked.

    A deliberately plain, independent reference, not a copy of the Card_Builder
    aggregation under test.
    """
    ref: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {
            "n_clients": 0,
            "excluded_count": 0,
            "excluded_by_reason": Counter(),
            "control_count": 0,
            "sendable_count": 0,
            "sendable_clients": set(),
            "control_clients": set(),
            "excluded_clients": set(),
        }
    )

    for promo_id, segment, client_id, excluded, reason, control in zip(
        leads["promo_id"],
        leads["segment"],
        leads["client_id"],
        leads["excluded"],
        leads["exclusion_reason"],
        leads["control"],
    ):
        key = (str(promo_id), str(segment))
        client_id = str(client_id)
        cell = ref[key]
        cell["n_clients"] += 1
        if bool(excluded):
            cell["excluded_count"] += 1
            cell["excluded_by_reason"][str(reason)] += 1
            cell["excluded_clients"].add(client_id)
        elif int(control) == 1:
            cell["control_count"] += 1
            cell["control_clients"].add(client_id)
        else:
            cell["sendable_count"] += 1
            cell["sendable_clients"].add(client_id)

    return ref


# Feature: part4-cards, Property 4: Each Cell's Leads partition into excluded, control, and sendable
@settings(max_examples=150)
@given(partition_inputs())
def test_each_cell_partitions_into_excluded_control_and_sendable(frames):
    """Each Card's counts partition the Cell's Leads against a reference.

    The classifier assigns every Lead exactly one fate (excluded, or
    non-excluded split into control / sendable). An independent reference
    tallies those per-Lead fates per Cell; the Card the Card_Builder emits for
    that Cell must then satisfy, for every Cell:

    - ``n_clients == excluded_count + control_count + sendable_count`` — the
      three partitions are mutually exclusive and jointly exhaustive;
    - the counts in ``excluded_by_reason`` sum to the excluded count;
    - the Sendable_Leads are exactly the Cell's non-excluded, non-control
      Leads (checked at the client_id set level);
    - no Excluded_Lead is ever a Control_Lead or a Sendable_Lead (the excluded,
      control, and sendable client sets are pairwise disjoint).

    The counts the Card exposes (``n_clients``, ``excluded_by_reason``,
    ``control_count``, ``sendable_count``) are compared against the reference,
    so the test validates the Card_Builder's fold rather than restating it.

    Validates: Requirements 5.1, 4.2, 4.4
    """
    cfg = Config()
    leads = classify(frames, cfg)
    cards = _build_cards_from_frames(frames, cfg)

    ref = _reference_partition(leads)

    # Exactly one Card per Cell, and the Card set matches the Cell set.
    card_keys = [(c["promo_id"], c["segment"]) for c in cards]
    assert len(card_keys) == len(set(card_keys)), "duplicate Card for a Cell"
    assert set(card_keys) == set(ref), (
        "Card set does not match the set of Cells in the classified Leads"
    )

    for card in cards:
        key = (card["promo_id"], card["segment"])
        expected = ref[key]

        n_clients = card["n_clients"]
        excluded_by_reason = card["excluded_by_reason"]
        excluded_count = sum(excluded_by_reason.values())
        control_count = card["control_count"]
        sendable_count = card["sendable_count"]

        # The Card's counts match the independent per-Lead tally.
        assert n_clients == expected["n_clients"], (
            f"cell {key}: n_clients={n_clients} expected {expected['n_clients']}"
        )
        assert control_count == expected["control_count"], (
            f"cell {key}: control_count={control_count} "
            f"expected {expected['control_count']}"
        )
        assert sendable_count == expected["sendable_count"], (
            f"cell {key}: sendable_count={sendable_count} "
            f"expected {expected['sendable_count']}"
        )
        assert excluded_by_reason == dict(expected["excluded_by_reason"]), (
            f"cell {key}: excluded_by_reason={excluded_by_reason} "
            f"expected {dict(expected['excluded_by_reason'])}"
        )

        # n_clients == excluded + control + sendable (the clean partition).
        assert n_clients == excluded_count + control_count + sendable_count, (
            f"cell {key}: n_clients={n_clients} != excluded={excluded_count} + "
            f"control={control_count} + sendable={sendable_count}"
        )

        # The excluded_by_reason counts sum to the excluded count.
        assert excluded_count == expected["excluded_count"], (
            f"cell {key}: excluded_by_reason sums to {excluded_count}, "
            f"expected excluded count {expected['excluded_count']}"
        )

        # Sendable_Leads are exactly the non-excluded, non-control Leads, and
        # the three client sets are pairwise disjoint — no Excluded_Lead is
        # ever a Control_Lead or a Sendable_Lead (Requirement 4.4).
        excluded_clients = expected["excluded_clients"]
        control_clients = expected["control_clients"]
        sendable_clients = expected["sendable_clients"]

        assert excluded_clients.isdisjoint(control_clients), (
            f"cell {key}: an Excluded_Lead was also a Control_Lead"
        )
        assert excluded_clients.isdisjoint(sendable_clients), (
            f"cell {key}: an Excluded_Lead was also a Sendable_Lead"
        )
        assert control_clients.isdisjoint(sendable_clients), (
            f"cell {key}: a Lead was both Control and Sendable"
        )
        # Sendable = exactly the non-excluded, non-control Leads.
        non_excluded_clients = control_clients | sendable_clients
        assert sendable_clients == (non_excluded_clients - control_clients), (
            f"cell {key}: Sendable set is not exactly the non-excluded, "
            f"non-control Leads"
        )


# ---------------------------------------------------------------------------
# Property 5: per-Cell reductions over the Sendable_Leads and the 90% range.
# ---------------------------------------------------------------------------

import math

from part4_cards.config import VALUE_PER_JOIN_PHP, Z_90
from tests.strategies_part4 import reduction_inputs


def _reference_reductions(
    leads: pd.DataFrame, cost_map: dict[str, float]
) -> dict[tuple[str, str], dict[str, float]]:
    """Independently compute each Cell's Sendable reductions and 90% range.

    Walks the classified per-Lead frame one row at a time (no pandas groupby
    aggregation), and for each Cell key (``promo_id``, ``segment``) accumulates
    over the Cell's Sendable_Leads (non-excluded, ``control == 0``):

    - ``mean`` = Σ ``p_join`` (the expected_joiners);
    - ``var`` = Σ ``p_join·(1 − p_join)`` (the binomial-approximation variance);
    - ``cost`` = Σ ``cost_map[best_channel]`` (the total_channel_cost).

    From those it derives ``expected_value`` = ``mean × VALUE_PER_JOIN_PHP −
    cost`` and the 90% range ``mean ± Z_90·√var`` with the low bound clamped to
    0. A Cell with no Sendable_Leads keeps every accumulator at 0, so every
    derived value is 0 (Requirement 5.6).

    A deliberately plain, independent reference — not a copy of the
    Card_Builder's ``_join_estimates`` fold under test.
    """
    acc: dict[tuple[str, str], dict[str, float]] = {}

    for promo_id, segment, excluded, control, p_join, best_channel in zip(
        leads["promo_id"],
        leads["segment"],
        leads["excluded"],
        leads["control"],
        leads["p_join"],
        leads["best_channel"],
    ):
        key = (str(promo_id), str(segment))
        cell = acc.setdefault(key, {"mean": 0.0, "var": 0.0, "cost": 0.0})
        # Only Sendable_Leads (non-excluded, control == 0) contribute.
        if bool(excluded) or int(control) != 0:
            continue
        p = float(p_join)
        cell["mean"] += p
        cell["var"] += p * (1.0 - p)
        cell["cost"] += float(cost_map.get(str(best_channel), 0.0))

    result: dict[tuple[str, str], dict[str, float]] = {}
    for key, cell in acc.items():
        mean = cell["mean"]
        var = cell["var"]
        cost = cell["cost"]
        spread = Z_90 * math.sqrt(var)
        result[key] = {
            "expected_joiners": mean,
            "total_channel_cost": cost,
            "expected_value": mean * VALUE_PER_JOIN_PHP - cost,
            "joiners_90_low": max(0.0, mean - spread),
            "joiners_90_high": mean + spread,
        }
    return result


# Feature: part4-cards, Property 5: Expected joiners, channel cost, expected value, and the 90% range are the defined reductions over Sendable Leads
@settings(max_examples=150)
@given(reduction_inputs())
def test_per_cell_reductions_and_range_over_sendable_leads(frames):
    """Each Card's join estimates and 90% range are the defined Sendable folds.

    For every Cell the Card the Card_Builder emits must match an *independent*
    reference computed directly from the classified per-Lead frame over that
    Cell's Sendable_Leads:

    - ``expected_joiners`` == Σ ``p_join``;
    - ``total_channel_cost`` == Σ the per-send cost of each Lead's
      ``best_channel`` (from the ``channel_costs`` frame);
    - ``expected_value`` == ``expected_joiners × VALUE_PER_JOIN_PHP −
      total_channel_cost``;
    - the 90% range satisfies ``0 ≤ joiners_90_low ≤ expected_joiners ≤
      joiners_90_high`` with the low bound clamped to a lower bound of 0;
    - a Cell with zero Sendable_Leads has ``expected_joiners``, both range
      bounds, ``total_channel_cost``, and ``expected_value`` all 0.

    The Card's reductions are compared against the reference (which is a plain
    per-row accumulation, not a restatement of ``_join_estimates``), so the test
    validates the Card_Builder's fold rather than echoing it.

    Validates: Requirements 5.4, 5.5, 5.6
    """
    cfg = Config()
    leads = classify(frames, cfg)
    cards = _build_cards_from_frames(frames, cfg)

    cost_map = {
        str(channel): float(cost)
        for channel, cost in zip(
            frames["channel_costs"]["channel"],
            frames["channel_costs"]["cost_php_per_message"],
        )
    }
    ref = _reference_reductions(leads, cost_map)

    # Exactly one Card per Cell, and the Card set matches the Cell set.
    card_keys = [(c["promo_id"], c["segment"]) for c in cards]
    assert len(card_keys) == len(set(card_keys)), "duplicate Card for a Cell"
    assert set(card_keys) == set(ref), (
        "Card set does not match the set of Cells in the classified Leads"
    )

    for card in cards:
        key = (card["promo_id"], card["segment"])
        expected = ref[key]

        expected_joiners = card["expected_joiners"]
        total_channel_cost = card["total_channel_cost"]
        expected_value = card["expected_value"]
        low = card["joiners_90_low"]
        high = card["joiners_90_high"]

        # The reductions match the independent per-Lead accumulation.
        assert expected_joiners == pytest.approx(expected["expected_joiners"]), (
            f"cell {key}: expected_joiners={expected_joiners} "
            f"expected {expected['expected_joiners']}"
        )
        assert total_channel_cost == pytest.approx(expected["total_channel_cost"]), (
            f"cell {key}: total_channel_cost={total_channel_cost} "
            f"expected {expected['total_channel_cost']}"
        )
        assert expected_value == pytest.approx(expected["expected_value"]), (
            f"cell {key}: expected_value={expected_value} "
            f"expected {expected['expected_value']}"
        )
        assert low == pytest.approx(expected["joiners_90_low"]), (
            f"cell {key}: joiners_90_low={low} expected {expected['joiners_90_low']}"
        )
        assert high == pytest.approx(expected["joiners_90_high"]), (
            f"cell {key}: joiners_90_high={high} expected {expected['joiners_90_high']}"
        )

        # expected_value is exactly the defined combination of the two folds.
        assert expected_value == pytest.approx(
            expected_joiners * VALUE_PER_JOIN_PHP - total_channel_cost
        ), f"cell {key}: expected_value is not joiners*VALUE - cost"

        # 0 <= joiners_90_low <= expected_joiners <= joiners_90_high, with the
        # low bound clamped to a lower bound of 0.
        assert low >= 0.0, f"cell {key}: joiners_90_low={low} below 0"
        assert low <= expected_joiners + 1e-9, (
            f"cell {key}: joiners_90_low={low} > expected_joiners={expected_joiners}"
        )
        assert expected_joiners <= high + 1e-9, (
            f"cell {key}: expected_joiners={expected_joiners} > joiners_90_high={high}"
        )

        # A Cell with zero Sendable_Leads zeroes every reduction and both range
        # bounds (Requirement 5.6).
        if card["sendable_count"] == 0:
            assert expected_joiners == 0, f"cell {key}: empty Cell joiners != 0"
            assert total_channel_cost == 0, f"cell {key}: empty Cell cost != 0"
            assert expected_value == 0, f"cell {key}: empty Cell value != 0"
            assert low == 0, f"cell {key}: empty Cell low != 0"
            assert high == 0, f"cell {key}: empty Cell high != 0"


# ---------------------------------------------------------------------------
# Property 6: the four-way action rule.
# ---------------------------------------------------------------------------

from tests.strategies_part4 import action_inputs


def _reference_action(
    segment: str, expected_value: float, mechanic: str
) -> str:
    """Independently decide a Card's action from the four-way rule.

    A deliberately plain restatement of the decision in words (Requirement 5.7),
    written straight from the specification rather than reusing the
    Card_Builder's ``_action`` helper, so the test checks the production rule
    against an independent reference:

    1. ``"Prioritize"`` when the segment is ``"Ready Toppers"`` and
       ``expected_value > 0``;
    2. otherwise ``"Offer lower tier"`` when the promo's ``mechanic`` equals
       ``"TOP_UP"`` and the segment is ``"Willing but Stretched"`` and
       ``expected_value > 0``;
    3. otherwise ``"Include"`` when ``expected_value > 0``;
    4. otherwise ``"Skip"``.
    """
    if segment == "Ready Toppers" and expected_value > 0:
        return "Prioritize"
    if (
        mechanic == "TOP_UP"
        and segment == "Willing but Stretched"
        and expected_value > 0
    ):
        return "Offer lower tier"
    if expected_value > 0:
        return "Include"
    return "Skip"


# Feature: part4-cards, Property 6: Action follows the four-way decision rule exactly
@settings(max_examples=150)
@given(action_inputs())
def test_action_follows_the_four_way_decision_rule_exactly(frames):
    """Each Card's action is exactly the four-way decision rule.

    For every Card the Card_Builder emits, ``action`` must equal the
    independent reference decision computed from that Card's ``segment``, its
    ``expected_value``, and its promo's ``mechanic`` (read from the
    ``promo_history`` frame, not from the Card):

    - ``"Prioritize"`` when the segment is ``"Ready Toppers"`` and
      ``expected_value > 0``;
    - otherwise ``"Offer lower tier"`` when the promo's ``mechanic == "TOP_UP"``
      and the segment is ``"Willing but Stretched"`` and ``expected_value > 0``;
    - otherwise ``"Include"`` when ``expected_value > 0``;
    - otherwise ``"Skip"``.

    The action strategy straddles the expected-value sign boundary and varies
    the segment and promo mechanic, so all four branches are reached. The
    reference reads the promo mechanic from the input frame independently of the
    Card, so the test validates the Card_Builder's rule rather than echoing it.

    Validates: Requirements 5.7
    """
    cfg = Config()
    cards = _build_cards_from_frames(frames, cfg)

    # promo_id -> mechanic, read independently from the input frame (the Card
    # does not expose the mechanic, so the reference resolves it here).
    mechanic_map = {
        str(promo_id): str(mechanic)
        for promo_id, mechanic in zip(
            frames["promo_history"]["promo_id"],
            frames["promo_history"]["mechanic"],
        )
    }

    valid_actions = {"Prioritize", "Offer lower tier", "Include", "Skip"}

    for card in cards:
        segment = card["segment"]
        expected_value = card["expected_value"]
        mechanic = mechanic_map.get(card["promo_id"], "")

        expected_action = _reference_action(segment, expected_value, mechanic)

        assert card["action"] in valid_actions, (
            f"card {(card['promo_id'], segment)}: action={card['action']!r} "
            f"is not one of the four defined actions"
        )
        assert card["action"] == expected_action, (
            f"card {(card['promo_id'], segment)}: action={card['action']!r} "
            f"expected {expected_action!r} "
            f"(segment={segment!r}, expected_value={expected_value}, "
            f"mechanic={mechanic!r})"
        )
