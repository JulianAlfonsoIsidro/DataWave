"""Unit tests for the group-scoped breakdown and group summary (task 13.5; Requirement 7, 6a-6c)."""

from __future__ import annotations

import copy

import pandas as pd
import pytest

from part5_personas.grouping import Persona, PersonaSet
from webapp_core.personas import (
    EQUAL_TAKEAWAY,
    NO_GROUP_NAME,
    expected_joiners_by_persona,
    expected_joiners_for_group,
    group_summary_by_card,
)

SEG = "Ready Toppers"


def _persona(name, actions=None):
    return Persona(
        name=name,
        description="",
        actions=list(actions if actions is not None else [f"Hook {name}"]),
        profile=None,  # type: ignore[arg-type]
    )


def _psets(spec):
    """spec: {group: {persona: (n, p)}}"""
    return [
        PersonaSet(group_key=g, personas=[_persona(n) for n in ps], k_used=len(ps), elbow_costs={})
        for g, ps in spec.items()
    ]


def _setup(spec, unlabeled=0, p_unlabeled=0.1):
    sendable, labels, i = [], [], 0
    for g, personas in spec.items():
        for name, (n, p) in personas.items():
            for _ in range(n):
                cid = f"C{i:05d}"
                i += 1
                sendable.append((cid, p))
                labels.append((cid, g, name))
    for _ in range(unlabeled):
        sendable.append((f"C{i:05d}", p_unlabeled))
        i += 1
    sdf = pd.DataFrame(sendable, columns=["client_id", "p_join"])
    ldf = pd.DataFrame(labels, columns=["client_id", "group", "persona_label"])
    cards = [{"promo_id": "NEW", "segment": SEG, "expected_joiners": float(sdf["p_join"].sum())}]
    return cards, {SEG: sdf}, ldf


SPEC = {
    "G1": {"A": (40, 0.5), "B": (30, 0.1)},
    "G2": {"A": (20, 0.3), "C": (10, 0.2)},
}


def _g(group, spec=SPEC, **kw):
    cards, sb, ldf = _setup(spec, **kw)
    return expected_joiners_for_group(cards, sb, ldf, _psets(spec), group), cards, sb, ldf


def test_only_selected_groups_personas_and_total():
    (b,), cards, *_ = _g("G1")
    assert [r.name for r in b.rows] == ["A", "B"]
    assert b.total_leads == 70
    assert b.total_expected_joiners == pytest.approx(40 * 0.5 + 30 * 0.1)
    assert b.group == "G1" and not b.too_few
    assert b.card_expected_joiners == pytest.approx(cards[0]["expected_joiners"])
    assert b.card_leads == 100


def test_unlabeled_leads_excluded_and_no_unlabeled_row():
    (b,), *_ = _g("G2", unlabeled=5)
    assert b.total_leads == 30
    assert all(r.kind != "unlabeled" for r in b.rows)
    assert b.card_leads == 105


def test_empty_cards_dropped():
    cards, sb, ldf = _setup(SPEC)
    cards = cards + [{"promo_id": "NEW", "segment": "Not Now", "expected_joiners": 0.0}]
    sb["Not Now"] = sb[SEG].iloc[0:0]
    out = expected_joiners_for_group(cards, sb, ldf, _psets(SPEC), "G1")
    assert [b.segment for b in out] == [SEG]
    # a group with no leads in the card is dropped too
    assert expected_joiners_for_group(cards, sb, ldf, _psets(SPEC), "NOPE") == []


def test_all_folded_flag():
    spec = {"G1": {"A": (90, 0.3)}, "G2": {"A": (3, 0.3), "B": (2, 0.3)}}
    (b,), *_ = _g("G2", spec)
    assert b.too_few is True
    assert [r.kind for r in b.rows] == ["other"]
    assert b.total_leads == 5
    assert "G2" in b.too_few_message and "5" in b.too_few_message
    (b1,), *_ = _g("G1", spec)
    assert b1.too_few is False


def test_takeaway_persona_distinct_and_equal():
    (b,), *_ = _g("G1")  # A rate 0.5 vs B 0.1 -> distinct
    assert b.takeaway_persona == "A"
    assert b.takeaway_action == "Hook A"
    eq = {"G1": {"A": (40, 0.3), "B": (30, 0.3)}}
    (e,), *_ = _g("G1", eq)
    assert e.takeaway_persona is None
    assert e.takeaway_action == EQUAL_TAKEAWAY


def test_13_4_breakdown_exposes_takeaway_and_drop_empty():
    spec = {"": {"A": (40, 0.5), "B": (30, 0.1)}}
    cards, sb, ldf = _setup(spec)
    cards.append({"promo_id": "NEW", "segment": "Not Now", "expected_joiners": 0.0})
    sb["Not Now"] = sb[SEG].iloc[0:0]
    full = expected_joiners_by_persona(cards, sb, ldf, _psets(spec))
    assert len(full) == 2
    assert full[0].takeaway_persona == "A" and full[0].takeaway_action == "Hook A"
    assert full[1].takeaway_persona is None
    dropped = expected_joiners_by_persona(cards, sb, ldf, _psets(spec), drop_empty=True)
    assert [b.segment for b in dropped] == [SEG]


def test_13_4_unlabeled_row_only_when_nonempty():
    cards, sb, ldf = _setup(SPEC)
    (b,) = expected_joiners_by_persona(cards, sb, ldf, _psets(SPEC))
    assert all(r.kind != "unlabeled" for r in b.rows)


def test_group_summary_rows_and_no_group_row():
    cards, sb, ldf = _setup(SPEC, unlabeled=4, p_unlabeled=0.2)
    (s,) = group_summary_by_card(cards, sb, ldf, _psets(SPEC))
    assert [r.name for r in s.rows] == ["G1", "G2", NO_GROUP_NAME]
    assert [r.leads for r in s.rows] == [70, 30, 4]
    assert s.rows[0].expected_joiners == pytest.approx(40 * 0.5 + 30 * 0.1)
    assert s.total_leads == 104
    assert s.total_expected_joiners == pytest.approx(cards[0]["expected_joiners"])
    assert sum(r.lead_share_pct for r in s.rows) == pytest.approx(100.0)


def test_group_summary_omits_no_group_row_when_empty_and_drops_empty_cards():
    cards, sb, ldf = _setup(SPEC)
    cards.append({"promo_id": "NEW", "segment": "Not Now", "expected_joiners": 0.0})
    sb["Not Now"] = sb[SEG].iloc[0:0]
    out = group_summary_by_card(cards, sb, ldf, _psets(SPEC))
    assert len(out) == 1 and [r.name for r in out[0].rows] == ["G1", "G2"]


def test_inputs_not_mutated_and_deterministic():
    cards, sb, ldf = _setup(SPEC, unlabeled=3)
    snap = (copy.deepcopy(cards), sb[SEG].copy(), ldf.copy())
    ps = _psets(SPEC)
    r1 = (expected_joiners_for_group(cards, sb, ldf, ps, "G1"), group_summary_by_card(cards, sb, ldf, ps))
    r2 = (expected_joiners_for_group(cards, sb, ldf, ps, "G1"), group_summary_by_card(cards, sb, ldf, ps))
    assert r1 == r2
    assert cards == snap[0]
    pd.testing.assert_frame_equal(sb[SEG], snap[1])
    pd.testing.assert_frame_equal(ldf, snap[2])
