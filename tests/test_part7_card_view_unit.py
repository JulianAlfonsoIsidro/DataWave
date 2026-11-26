"""Unit tests for the decision-card view (Part 7, task 6.3).

Covers title format, tooltip lengths, the fixed "None" choice, headings, and
that ``outputs/cards.json`` is byte-for-byte unchanged after rendering.

Validates: Requirements 4.7, 4.9, 4.10, 4.11
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from webapp_core.card_view import (
    NO_EXCLUSIONS_TEXT,
    NOT_CONTACTED_HEADING,
    WHY_HEADING,
    build_card_view,
)

CARDS_JSON = Path(__file__).resolve().parents[1] / "outputs" / "cards.json"


def _card(**overrides):
    card = {
        "promo_id": "NEW-001",
        "segment": "Untapped Wealth",
        "action": "Send",
        "dominant_channel": "Email",
        "message_angle": "Savings boost",
        "top_drivers": ["latest_adb", "digital_app_user"],
        "excluded_by_reason": {},
        "expected_joiners": 10.5,
        "joiners_90_low": 4.2,
        "joiners_90_high": 20.7,
        "expected_value": 12345.5,
    }
    card.update(overrides)
    return card


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_title_format_uses_promo_id_dot_segment():
    assert build_card_view(_card()).title == "NEW-001 · Untapped Wealth"


def test_title_for_each_part3_segment():
    for segment in ("Ready Toppers", "Untapped Wealth", "Willing but Stretched", "Not Now"):
        view = build_card_view(_card(segment=segment, promo_id="P001"))
        assert view.title == f"P001 · {segment}"


def test_exactly_three_stats_with_tooltips_within_120_chars():
    view = build_card_view(_card())
    assert len(view.stats) == 3
    for stat in view.stats:
        assert stat.tooltip.strip()
        assert len(stat.tooltip) <= 120


def test_stat_labels_are_whole_numbers_with_peso_value():
    view = build_card_view(_card())
    assert view.stats[0].label == "About 11 Expected Joiners"
    assert view.stats[1].label == "Likely Range: 4 To 21"
    assert view.stats[2].label == "Expected Value: ₱12,346"


def test_no_exclusions_shows_fixed_none_choice_on_every_card():
    assert NO_EXCLUSIONS_TEXT == "None"
    for segment in ("Ready Toppers", "Not Now"):
        view = build_card_view(_card(segment=segment, excluded_by_reason={}))
        assert view.exclusions == ()
        assert view.not_contacted_heading == NOT_CONTACTED_HEADING


def test_zero_count_exclusions_are_treated_as_none():
    view = build_card_view(_card(excluded_by_reason={"do_not_contact": 0}))
    assert view.exclusions == ()


def test_headings_are_exact():
    view = build_card_view(_card(excluded_by_reason={"do_not_contact": 3}))
    assert view.why_heading == WHY_HEADING == "Why This Group:"
    assert view.not_contacted_heading == NOT_CONTACTED_HEADING == "Not Contacted:"
    assert len(view.exclusions) == 1
    assert view.exclusions[0].endswith(": 3")


def test_cards_json_hash_unchanged_after_rendering():
    assert CARDS_JSON.exists()
    before = _sha(CARDS_JSON)
    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    items = cards if isinstance(cards, list) else list(cards.values())
    rendered = 0
    for item in items:
        if isinstance(item, dict) and "segment" in item:
            build_card_view(item)
            rendered += 1
    assert rendered > 0
    assert _sha(CARDS_JSON) == before
