"""Example-based unit tests for the Persona_Core per-cell mix join.

Covers :func:`webapp_core.personas.persona_mix_by_cell`, which aligns a per-cell
Persona_Mix onto the existing Part 4 decision cards by ``(promo_id, segment)``.
The cases exercise the three behaviours the Part 7 requirements pin down:

- JOIN BY ``(promo_id, segment)``: the returned dict is keyed by each card's
  original ``(promo_id, segment)``, and the shares for a cell reflect the counts
  of the matching ``(promo_id, segment_slug)`` leads, including the case where the
  card carries a human segment label (e.g. "Ready Toppers") whose slug
  ("ready_toppers") matches the per-lead ``segment_slug`` (Requirements 7.2, 7.3,
  7.4);
- CARDS UNCHANGED BYTE-FOR-BYTE: the function reads but never mutates any Part 4
  card field — a deep copy of the input cards equals the cards after the call
  (Requirements 7.3, 7.4);
- UNAVAILABLE FALLBACK: a card whose cell has no matching assignment returns a
  :class:`~webapp_core.personas.PersonaMix` with ``available == False`` and empty
  ``shares``, while the available cells in the same call still compute correctly
  (Requirement 7.5).

Plain pytest (non-hypothesis), deterministic, directly constructed frames/cards.
Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import copy

import pandas as pd
import pytest

from webapp_core.personas import PersonaMix, persona_mix_by_cell, segment_slug


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _labels(rows: list[dict]) -> pd.DataFrame:
    """Build a per-lead labels frame with the columns the mix join reads.

    Each row carries ``client_id``, ``persona_label``, and the cell keys
    ``promo_id`` and ``segment_slug`` that :func:`persona_mix_by_cell` scopes by.
    """
    return pd.DataFrame(
        rows,
        columns=["client_id", "persona_label", "promo_id", "segment_slug"],
    )


def _card(promo_id: str, segment: str, **extra) -> dict:
    """Build a Part 4 card dict carrying the usual extra Part 4 fields."""
    card = {"promo_id": promo_id, "segment": segment}
    card.update(extra)
    return card


# --------------------------------------------------------------------------- #
# 1. join by (promo_id, segment) with slug matching (Req 7.2/7.3/7.4)         #
# --------------------------------------------------------------------------- #
def test_mix_keyed_by_card_promo_and_segment_with_shares():
    """Shares reflect counts for the matching (promo_id, segment_slug) cell.

    The P001 "ready_toppers" cell holds 3 leads of persona A and 1 of persona B,
    so the mix is {A: 75.0, B: 25.0}; the card uses the human label "Ready
    Toppers" whose slug matches, proving the slug join.
    """
    labels = _labels(
        [
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c2", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c3", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c4", "persona_label": "B", "promo_id": "P001", "segment_slug": "ready_toppers"},
        ]
    )
    cards = [_card("P001", "Ready Toppers")]

    result = persona_mix_by_cell(labels, cards)

    # Keyed by the card's ORIGINAL (promo_id, segment) — the human label, not slug.
    assert set(result.keys()) == {("P001", "Ready Toppers")}
    assert segment_slug("Ready Toppers") == "ready_toppers"

    mix = result[("P001", "Ready Toppers")]
    assert isinstance(mix, PersonaMix)
    assert mix.available is True
    assert mix.promo_id == "P001"
    assert mix.segment == "Ready Toppers"
    assert mix.shares == {"A": 75.0, "B": 25.0}
    assert sum(mix.shares.values()) == pytest.approx(100.0)


def test_mix_scopes_each_cell_independently_by_promo_and_segment():
    """Leads are counted only within their own (promo_id, segment_slug) cell."""
    labels = _labels(
        [
            # P001 / ready_toppers: all persona A.
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c2", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            # P001 / not_now: 1 A, 1 B.
            {"client_id": "c3", "persona_label": "A", "promo_id": "P001", "segment_slug": "not_now"},
            {"client_id": "c4", "persona_label": "B", "promo_id": "P001", "segment_slug": "not_now"},
            # P002 / ready_toppers: all persona B (different promo, same slug).
            {"client_id": "c5", "persona_label": "B", "promo_id": "P002", "segment_slug": "ready_toppers"},
        ]
    )
    cards = [
        _card("P001", "Ready Toppers"),
        _card("P001", "Not Now"),
        _card("P002", "Ready Toppers"),
    ]

    result = persona_mix_by_cell(labels, cards)

    assert result[("P001", "Ready Toppers")].shares == {"A": 100.0}
    assert result[("P001", "Not Now")].shares == {"A": 50.0, "B": 50.0}
    assert result[("P002", "Ready Toppers")].shares == {"B": 100.0}
    # Same slug across promos is NOT merged — P001 and P002 stay independent.
    assert result[("P001", "Ready Toppers")].available is True
    assert result[("P002", "Ready Toppers")].available is True


def test_out_of_pool_empty_label_lead_does_not_contribute():
    """A lead with an empty persona label is ignored in the cell's shares."""
    labels = _labels(
        [
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c2", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c3", "persona_label": "", "promo_id": "P001", "segment_slug": "ready_toppers"},
        ]
    )
    cards = [_card("P001", "Ready Toppers")]

    result = persona_mix_by_cell(labels, cards)

    mix = result[("P001", "Ready Toppers")]
    # Only the two labelled leads count -> a single persona at 100%.
    assert mix.shares == {"A": 100.0}
    assert mix.available is True


# --------------------------------------------------------------------------- #
# 2. cards unchanged byte-for-byte (Req 7.3/7.4)                              #
# --------------------------------------------------------------------------- #
def test_cards_are_not_mutated_by_the_mix_join():
    """Every Part 4 card field is identical after the call (no mutation)."""
    cards = [
        _card(
            "P001",
            "Ready Toppers",
            action="Offer premium savings",
            dominant_channel="In-app",
            expected_joiners=42,
            expected_value=12345.67,
            top_drivers=["monthly_income", "owns_investment", "total_inflow"],
            message_angle="savings-bundle",
        ),
        _card(
            "P002",
            "Not Now",
            action="Hold",
            dominant_channel="Email",
            expected_joiners=0,
            expected_value=0.0,
            top_drivers=[],
            message_angle="tailored",
        ),
    ]
    labels = _labels(
        [
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c2", "persona_label": "B", "promo_id": "P002", "segment_slug": "not_now"},
        ]
    )

    before = copy.deepcopy(cards)
    persona_mix_by_cell(labels, cards)

    # The input cards list and each card dict (incl. nested lists) are unchanged.
    assert cards == before


def test_labels_frame_is_not_mutated():
    """The labels frame is read only — unchanged after computing the mix."""
    labels = _labels(
        [
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c2", "persona_label": "B", "promo_id": "P001", "segment_slug": "ready_toppers"},
        ]
    )
    before = labels.copy(deep=True)
    persona_mix_by_cell(labels, [_card("P001", "Ready Toppers")])

    pd.testing.assert_frame_equal(labels, before)


# --------------------------------------------------------------------------- #
# 3. unavailable-mix fallback (Req 7.5)                                       #
# --------------------------------------------------------------------------- #
def test_card_with_no_matching_assignment_is_unavailable():
    """A cell with no matching leads yields available=False and empty shares."""
    labels = _labels(
        [
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
        ]
    )
    # Card is for a cell (P003 / Not Now) that has no assignments at all.
    cards = [_card("P003", "Not Now")]

    result = persona_mix_by_cell(labels, cards)

    mix = result[("P003", "Not Now")]
    assert mix.available is False
    assert mix.shares == {}
    assert mix.promo_id == "P003"
    assert mix.segment == "Not Now"


def test_available_and_unavailable_cells_in_one_call():
    """Available cells still compute when another cell is unavailable."""
    labels = _labels(
        [
            {"client_id": "c1", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c2", "persona_label": "A", "promo_id": "P001", "segment_slug": "ready_toppers"},
            {"client_id": "c3", "persona_label": "B", "promo_id": "P001", "segment_slug": "ready_toppers"},
        ]
    )
    cards = [
        _card("P001", "Ready Toppers"),  # available
        _card("P002", "Untapped Wealth"),  # no assignments -> unavailable
    ]

    result = persona_mix_by_cell(labels, cards)

    available = result[("P001", "Ready Toppers")]
    assert available.available is True
    assert available.shares == {"A": pytest.approx(66.66666666666666), "B": pytest.approx(33.33333333333333)}
    assert sum(available.shares.values()) == pytest.approx(100.0)

    unavailable = result[("P002", "Untapped Wealth")]
    assert unavailable.available is False
    assert unavailable.shares == {}


def test_empty_labels_frame_marks_every_card_unavailable():
    """With no labelled leads at all, each card's mix is unavailable."""
    labels = _labels([])
    cards = [_card("P001", "Ready Toppers"), _card("P002", "Not Now")]

    result = persona_mix_by_cell(labels, cards)

    assert all(mix.available is False for mix in result.values())
    assert all(mix.shares == {} for mix in result.values())
    assert set(result.keys()) == {("P001", "Ready Toppers"), ("P002", "Not Now")}
