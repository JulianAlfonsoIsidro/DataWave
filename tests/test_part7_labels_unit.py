"""Unit tests for the Part 7 Label_Map (``src/labels.py``).

Verifies every driver code in ``outputs/cards.json``, every exclusion code
produced by ``part4_cards``, and every UI-visible feature code maps to a
plain phrase (not the Title Case fallback) with no underscore, and that the
fallback itself is well formed.

Validates: Requirements 4.1, 4.3, 10.2.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from labels import (
    EXCLUSION_LABELS,
    FEATURE_LABELS,
    HIDDEN_DRIVER_CODES,
    is_known,
    plain_driver_phrase,
    plain_label,
)

ROOT = Path(__file__).resolve().parents[1]
CARDS_JSON = ROOT / "outputs" / "cards.json"
CLASSIFY_PY = ROOT / "src" / "part4_cards" / "classify.py"

# Feature codes the Webapp UI can show (Requirement 4.1).
UI_FEATURE_CODES = [
    "out_other_bank",
    "ext_outflow_ratio",
    "spend_share_retail",
    "latest_adb",
    "avg_contacts_per_month",
    "digital_app_user",
    "ndb_flag",
    "investment_propensity_decile",
]
UI_EXCLUSION_CODES = ["over_contacted", "ndb", "no reachable channel"]


def _driver_codes_from_cards() -> set[str]:
    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    return {d for card in cards for d in card.get("top_drivers", [])}


def _exclusion_codes_from_cards() -> set[str]:
    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    return {r for card in cards for r in card.get("excluded_by_reason", {})}


def _exclusion_codes_from_part4() -> set[str]:
    """Exclusion reason literals assigned in part4_cards/classify.py."""
    src = CLASSIFY_PY.read_text(encoding="utf-8")
    codes: set[str] = set()
    # np.select choice list: ["ndb", "over_contacted"]
    for m in re.finditer(r'\[("[a-z_ ]+"(?:,\s*"[a-z_ ]+")+)\],\s*default=""', src):
        codes |= set(re.findall(r'"([^"]+)"', m.group(1)))
    # Direct assignment: ["exclusion_reason"] = "no reachable channel"
    codes |= set(re.findall(r'"exclusion_reason"\]\s*=\s*"([^"]+)"', src))
    return codes


def _assert_plain(code: str) -> None:
    label = plain_label(code)
    assert is_known(code), f"{code!r} falls back to Title Case"
    assert "_" not in label, f"{code!r} -> {label!r} contains an underscore"
    assert label.strip() == label and label


def test_cards_json_driver_codes_are_known_and_plain():
    codes = _driver_codes_from_cards()
    assert codes, "cards.json should contain driver codes"
    for code in codes:
        _assert_plain(code)


def test_cards_json_exclusion_codes_are_known_and_plain():
    for code in _exclusion_codes_from_cards():
        _assert_plain(code)


def test_part4_exclusion_codes_are_known_and_plain():
    codes = _exclusion_codes_from_part4()
    assert {"ndb", "over_contacted", "no reachable channel"} <= codes
    for code in codes:
        _assert_plain(code)


@pytest.mark.parametrize("code", UI_FEATURE_CODES + UI_EXCLUSION_CODES)
def test_ui_visible_codes_are_known_and_plain(code):
    _assert_plain(code)


def test_all_mapped_labels_have_no_underscore():
    for table in (FEATURE_LABELS, EXCLUSION_LABELS):
        for code, label in table.items():
            assert "_" not in label, (code, label)
            assert label == label.strip() and label


def test_hidden_driver_codes_are_known():
    assert HIDDEN_DRIVER_CODES == {"mechanic", "threshold_php"}
    for code in HIDDEN_DRIVER_CODES:
        _assert_plain(code)


@pytest.mark.parametrize(
    "code, expected",
    [
        ("some_new_feature", "Some New Feature"),
        ("a__b___c", "A B C"),
        ("lowercase", "Lowercase"),
        ("  padded_code  ", "Padded Code"),
        ("MIXED_case_Code", "Mixed Case Code"),
    ],
)
def test_unmapped_codes_use_title_case_fallback(code, expected):
    assert not is_known(code)
    label = plain_label(code)
    assert label == expected
    assert "_" not in label


def test_driver_phrase_is_limited_to_max_chars():
    phrase = plain_driver_phrase("x_" * 80)
    assert len(phrase) <= 60 and "_" not in phrase
    assert plain_driver_phrase("out_other_bank") == plain_label("out_other_bank")
