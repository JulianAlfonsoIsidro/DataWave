"""Unit tests for expected_joiners_by_persona (task 13.4; Requirements 7.1-7.5, 7.7, 7.8)."""

from __future__ import annotations

import copy

import pandas as pd
import pytest

from part5_personas.grouping import Persona, PersonaSet
from webapp_core.personas import expected_joiners_by_persona

CHANNEL_LINE = "Reachable on every channel about equally; lead with Email."
OTHER = "Other personas"
UNLABELED = "Not in this persona run"
SAME = "Same message as above."


def _persona(name, actions=None):
    return Persona(
        name=name,
        description="",
        actions=list(actions if actions is not None else [f"Hook {name}", "Second"]),
        profile=None,  # type: ignore[arg-type]
    )


def _pset(personas, group_key=""):
    return PersonaSet(
        group_key=group_key, personas=personas, k_used=len(personas), elbow_costs={}
    )


def _setup(spec, groups=None, unlabeled=0, p_unlabeled=0.1):
    """spec: {name: (n_leads, p_each)} in group ''. Returns inputs for one card."""
    sendable, labels = [], []
    i = 0
    for name, (n, p) in spec.items():
        for _ in range(n):
            cid = f"C{i:05d}"
            i += 1
            sendable.append((cid, p))
            labels.append((cid, "", name))
    for _ in range(unlabeled):
        sendable.append((f"C{i:05d}", p_unlabeled))
        i += 1
    sdf = pd.DataFrame(sendable, columns=["client_id", "p_join"])
    ldf = pd.DataFrame(labels, columns=["client_id", "group", "persona_label"])
    cards = [
        {
            "promo_id": "NEW",
            "segment": "Ready Toppers",
            "expected_joiners": float(sdf["p_join"].sum()),
            "sendable_count": len(sdf),
        }
    ]
    return cards, {"Ready Toppers": sdf}, ldf


def _run(spec, psets=None, **kw):
    cards, sb, ldf = _setup(spec, **kw)
    psets = psets or [_pset([_persona(n) for n in spec])]
    (b,) = expected_joiners_by_persona(cards, sb, ldf, psets)
    return b, cards, sb, ldf


def _by_name(b):
    return {r.name: r for r in b.rows}


def test_total_equals_card_joiners_with_folded_and_unlabeled():
    spec = {"A": (50, 0.5), "B": (40, 0.2), "C": (3, 0.9)}
    b, cards, *_ = _run(spec, unlabeled=7)
    assert b.total_expected_joiners == pytest.approx(cards[0]["expected_joiners"])
    assert sum(r.expected_joiners for r in b.rows) == pytest.approx(
        cards[0]["expected_joiners"]
    )
    assert sum(r.leads for r in b.rows) == 100
    names = [r.name for r in b.rows]
    assert names == ["A", "B", OTHER, UNLABELED]


def test_fold_by_share_below_five_percent():
    # 4 of 200 = 2% share, n<5 too; use n=8 of 200 = 4% to isolate share rule
    b, *_ = _run({"A": (192, 0.3), "S": (8, 0.3)})
    r = _by_name(b)
    assert "S" not in r and r[OTHER].leads == 8
    assert r[OTHER].show_joiners is False


def test_fold_by_count_below_five():
    # 4 of 20 = 20% share but n=4 -> folded
    b, *_ = _run({"A": (16, 0.3), "S": (4, 0.3)})
    r = _by_name(b)
    assert "S" not in r and r[OTHER].leads == 4


def test_boundaries_not_folded():
    # exactly 5 leads and exactly 5% share
    b, *_ = _run({"A": (95, 0.3), "S": (5, 0.3)})
    r = _by_name(b)
    assert "S" in r and OTHER not in r
    assert r["S"].lead_share_pct == pytest.approx(5.0)


def test_unlabeled_never_folded_and_last_without_action():
    b, *_ = _run({"A": (50, 0.3), "S": (2, 0.3)}, unlabeled=1)
    assert [r.name for r in b.rows][-2:] == [OTHER, UNLABELED]
    u = b.rows[-1]
    assert u.leads == 1 and u.action == "" and u.show_joiners is True


def test_other_row_shows_lead_count_only_flag():
    b, *_ = _run({"A": (50, 0.3), "S": (2, 0.5)})
    other = _by_name(b)[OTHER]
    assert other.show_joiners is False
    assert other.expected_joiners == pytest.approx(1.0)  # kept for total


def test_ordering_joiners_desc_then_name():
    spec = {"Zed": (10, 0.5), "Abe": (10, 0.5), "Big": (10, 0.9), "Low": (10, 0.1)}
    b, *_ = _run(spec)
    assert [r.name for r in b.rows] == ["Big", "Abe", "Zed", "Low"]


def test_action_skips_channel_line_and_dedups():
    spec = {"A": (10, 0.9), "B": (10, 0.5), "C": (10, 0.1), "D": (10, 0.05)}
    psets = [
        _pset(
            [
                _persona("A", ["Pitch X", "y"]),
                _persona("B", [CHANNEL_LINE, "Pitch X", "z"]),
                _persona("C", ["Pitch C"]),
                _persona("D", [CHANNEL_LINE]),
            ]
        )
    ]
    b, *_ = _run(spec, psets=psets)
    r = _by_name(b)
    assert r["A"].action == "Pitch X"
    assert r["B"].action == SAME
    assert r["C"].action == "Pitch C"
    assert r["D"].action == ""


def test_takeaway_distinct():
    b, *_ = _run({"A": (50, 0.6), "B": (50, 0.2)})
    # A: 50% leads, 75% of joiners
    assert b.takeaway == "A is 50% of leads but 75% of expected joiners. Lead with its hook."


def test_takeaway_similar_rates():
    b, *_ = _run({"A": (50, 0.5), "B": (50, 0.45)})
    assert b.takeaway == "Personas respond about equally; one message fits this card."


def test_takeaway_boundary_exactly_1_2_is_distinct():
    b, *_ = _run({"A": (10, 0.6), "B": (10, 0.5)})
    assert "Lead with its hook." in b.takeaway
    b2, *_ = _run({"A": (10, 0.59), "B": (10, 0.5)})
    assert b2.takeaway.startswith("Personas respond")


def test_takeaway_zero_min_rate_is_distinct():
    b, *_ = _run({"A": (10, 0.4), "B": (10, 0.0)})
    assert b.takeaway.startswith("A is 50% of leads but 100%")


def test_takeaway_single_persona_is_equal_branch():
    b, *_ = _run({"A": (10, 0.4)})
    assert b.takeaway.startswith("Personas respond")


def test_takeaway_ignores_folded_and_unlabeled():
    b, *_ = _run({"A": (50, 0.5), "B": (50, 0.5), "S": (2, 0.99)}, unlabeled=5, p_unlabeled=0.0)
    assert b.takeaway.startswith("Personas respond")


def test_same_name_in_two_groups_not_merged_and_prefixed():
    sdf = pd.DataFrame(
        {"client_id": [f"C{i}" for i in range(20)], "p_join": [0.5] * 10 + [0.1] * 10}
    )
    ldf = pd.DataFrame(
        {
            "client_id": sdf["client_id"],
            "group": ["g1"] * 10 + ["g2"] * 10,
            "persona_label": ["Same"] * 20,
        }
    )
    cards = [{"promo_id": "NEW", "segment": "S", "expected_joiners": 6.0}]
    psets = [_pset([_persona("Same")], "g1"), _pset([_persona("Same")], "g2")]
    (b,) = expected_joiners_by_persona(cards, {"S": sdf}, ldf, psets)
    assert [r.name for r in b.rows] == ["g1: Same", "g2: Same"]
    assert [r.leads for r in b.rows] == [10, 10]


def test_single_group_has_no_prefix():
    b, *_ = _run({"A": (10, 0.5)})
    assert b.rows[0].name == "A"


def test_empty_card():
    cards, sb, ldf = _setup({"A": (10, 0.5)})
    cards.append({"promo_id": "NEW", "segment": "Not Now", "expected_joiners": 0.0})
    out = expected_joiners_by_persona(cards, sb, ldf, [_pset([_persona("A")])])
    e = out[1]
    assert e.rows == [] or tuple(e.rows) == ()
    assert e.total_expected_joiners == 0
    assert e.takeaway == "No sendable leads in this card."


def test_inputs_not_mutated_and_deterministic():
    cards, sb, ldf = _setup({"A": (20, 0.5), "B": (20, 0.2)}, unlabeled=3)
    psets = [_pset([_persona("A"), _persona("B")])]
    c0 = copy.deepcopy(cards)
    s0 = sb["Ready Toppers"].copy()
    l0 = ldf.copy()
    r1 = expected_joiners_by_persona(cards, sb, ldf, psets)
    r2 = expected_joiners_by_persona(cards, sb, ldf, psets)
    assert r1 == r2
    assert cards == c0
    pd.testing.assert_frame_equal(sb["Ready Toppers"], s0)
    pd.testing.assert_frame_equal(ldf, l0)


def test_duplicate_label_rows_keep_first_sorted():
    sdf = pd.DataFrame({"client_id": ["C1"] * 1 + [f"D{i}" for i in range(9)], "p_join": [0.5] * 10})
    ldf = pd.DataFrame(
        {
            "client_id": ["C1", "C1"] + [f"D{i}" for i in range(9)],
            "group": ["g2", "g1"] + ["g1"] * 9,
            "persona_label": ["B", "A"] + ["A"] * 9,
        }
    )
    cards = [{"promo_id": "NEW", "segment": "S", "expected_joiners": 5.0}]
    psets = [_pset([_persona("A"), _persona("B")], "g1"), _pset([_persona("A")], "g2")]
    (b,) = expected_joiners_by_persona(cards, {"S": sdf}, ldf, psets)
    assert sum(r.leads for r in b.rows) == 10
    assert b.total_expected_joiners == pytest.approx(5.0)
