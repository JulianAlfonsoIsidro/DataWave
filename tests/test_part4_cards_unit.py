"""Example/edge-case unit tests for the Part4_Cards_Pipeline Card_Builder.

These are concrete-example tests (not Hypothesis) covering the message angle
and the public ``build_cards`` convenience API against Requirement 5.8:

- ``message_angle`` maps each of the four segments to its fixed text, including
  the exact entry ``"Untapped Wealth"`` -> ``"Bring your savings home and keep
  your status"``.
- ``build_cards(segments_df, promo_dict)`` returns the list of Cards **in
  memory**, writing no output file and printing nothing.

``build_cards`` loads the reference frames (NDB, contact history, channel
costs, customer DNA, promo history) via :class:`~part4_cards.config.Config`
defaults, which point at the real workspace ``data/*.csv`` files. The tests are
therefore designed to work with those real files present: the Leads are built
from a small, hand-picked set of ``client_id`` values that exist in the real
``customer_dna.csv`` with all three reachability flags set and that are absent
from the real ``ndb.csv`` and ``contact_history.csv`` — so every Lead is
non-excluded and the four segment Cells are all populated.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from part4_cards.cards import build_cards
from part4_cards.config import MESSAGE_ANGLES, SEGMENTS, Config

# Eight client_ids that exist in the real data/customer_dna.csv with all three
# reachability flags (digital_app_user / email_valid / mobile_valid) set to 1,
# and that are absent from the real data/ndb.csv and data/contact_history.csv.
# So with a promo that allows every channel, each of these Leads is
# non-excluded (not "ndb", not "over_contacted", reachable In-app) and lands in
# its segment's Cell. Two clients per segment keep floor(0.10 x 2) == 0 control,
# so both Leads in each Cell are Sendable and every Cell is populated.
_REACHABLE_CLIENTS: list[str] = [
    "C100002",
    "C100007",
    "C100018",
    "C100035",
    "C100036",
    "C100039",
    "C100042",
    "C100044",
]

_PROMO_ID = "P001"


def _segments_all_segments() -> pd.DataFrame:
    """A Segments_File frame placing two reachable Leads in each of the four
    segments under a single promo.

    Shaped exactly like ``loader.load`` yields (required columns present,
    ``p_join`` numeric), so it can be passed straight to ``build_cards``.
    """
    rows = []
    for i, client_id in enumerate(_REACHABLE_CLIENTS):
        segment = SEGMENTS[i // 2]  # two clients per segment, all four segments
        rows.append(
            {
                "promo_id": _PROMO_ID,
                "client_id": client_id,
                "p_join": 0.5,
                "capacity_php": "10000",
                "segment": segment,
                "top_driver_1": "payroll",
                "top_driver_2": "remittance",
                "top_driver_3": "spend",
            }
        )
    segments = pd.DataFrame(
        rows,
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
    segments["p_join"] = pd.to_numeric(segments["p_join"])
    return segments


def _promo_dict() -> dict[str, dict]:
    """A ``promo_dict`` for the single promo, allowing every channel.

    ``build_cards`` expects ``promo_id -> {"mechanic": str, "channels":
    list[str], ...}``. Allowing all three channels guarantees every reachable
    Lead finds an allowed-and-reachable best_channel.
    """
    return {
        _PROMO_ID: {
            "mechanic": "TOP_UP",
            "channels": ["In-app", "Email", "SMS"],
        }
    }


def test_message_angle_maps_each_segment_to_its_fixed_text():
    """Every Card's ``message_angle`` is the fixed text for its segment (5.8).

    Builds one Cell per segment and asserts each Card's ``message_angle`` equals
    ``MESSAGE_ANGLES[segment]``, covering all four segments, and in particular
    that ``"Untapped Wealth"`` maps to the exact text ``"Bring your savings home
    and keep your status"``.
    """
    cards = build_cards(_segments_all_segments(), _promo_dict())

    # One Card per segment Cell (single promo, four segments).
    by_segment = {card["segment"]: card for card in cards}
    assert set(by_segment) == set(SEGMENTS), (
        f"expected one Card per segment {SEGMENTS}, got {sorted(by_segment)}"
    )

    for segment in SEGMENTS:
        card = by_segment[segment]
        assert card["message_angle"] == MESSAGE_ANGLES[segment], (
            f"segment {segment!r}: message_angle={card['message_angle']!r} "
            f"expected {MESSAGE_ANGLES[segment]!r}"
        )

    # The specific entry named in Requirement 5.8.
    assert (
        by_segment["Untapped Wealth"]["message_angle"]
        == "Bring your savings home and keep your status"
    )


def test_build_cards_returns_cards_in_memory_without_writing_or_printing(capsys):
    """``build_cards`` returns Cards in memory, writing no file and printing
    nothing (5.8).

    Snapshots the existence and modification time of the canonical output paths
    (``outputs/cards.json`` and ``outputs/leads/``) before and after the call,
    and captures stdout/stderr with ``capsys``. The call must:

    - return a non-empty list of Card dicts (one per Cell);
    - leave ``outputs/cards.json`` and ``outputs/leads/`` exactly as they were
      (not created, and if already present, not modified);
    - print nothing to stdout or stderr.
    """
    cfg = Config()
    cards_path = cfg.cards_out_path
    leads_dir = cfg.leads_out_dir

    def _snapshot(path):
        """(exists, mtime) for ``path``; mtime is None when absent."""
        if os.path.exists(path):
            return True, os.path.getmtime(path)
        return False, None

    before_cards = _snapshot(cards_path)
    before_leads = _snapshot(leads_dir)

    cards = build_cards(_segments_all_segments(), _promo_dict())

    after_cards = _snapshot(cards_path)
    after_leads = _snapshot(leads_dir)

    # Returns a non-empty list of Card dicts in memory.
    assert isinstance(cards, list), "build_cards did not return a list"
    assert cards, "build_cards returned an empty list"
    assert all(isinstance(card, dict) for card in cards), (
        "build_cards returned non-dict entries"
    )
    # One Card per (promo, segment) Cell — four segments under the one promo.
    assert len(cards) == len(SEGMENTS)
    assert {card["segment"] for card in cards} == set(SEGMENTS)

    # Wrote no output file: the cards file and leads dir are unchanged
    # (neither created nor, if already present, modified).
    assert after_cards == before_cards, (
        f"outputs/cards.json changed: before={before_cards} after={after_cards}"
    )
    assert after_leads == before_leads, (
        f"outputs/leads/ changed: before={before_leads} after={after_leads}"
    )

    # Printed nothing.
    captured = capsys.readouterr()
    assert captured.out == "", f"build_cards printed to stdout: {captured.out!r}"
    assert captured.err == "", f"build_cards printed to stderr: {captured.err!r}"
