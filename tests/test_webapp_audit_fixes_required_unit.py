"""Webapp audit fixes, item 1.11 (task 3.9): required fields and model display.

Spec ``webapp-audit-fixes``, Requirements 1.11 and 2.11. Covers the pure
helpers in ``webapp_core.required_fields`` and ``theme.model_display``.
``required_message`` is tested through its default call only.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import theme  # noqa: E402
from webapp_core.required_fields import (  # noqa: E402
    missing_persona_split,
    missing_promo_fields,
    required_message,
)

_items = st.lists(st.sampled_from(["A", "B", "C"]), max_size=4)
_none_or_items = st.one_of(st.none(), _items)


# --- missing_promo_fields -----------------------------------------------------

@given(seg=_none_or_items, ch=_none_or_items)
def test_missing_promo_fields_names_exactly_the_empty_ones(seg, ch):
    expected = []
    if not seg:
        expected.append("Eligible Segments")
    if not ch:
        expected.append("Channels")
    assert missing_promo_fields(seg, ch) == expected


def test_missing_promo_fields_examples():
    assert missing_promo_fields(["Ready Toppers"], ["SMS"]) == []
    assert missing_promo_fields([], ["SMS"]) == ["Eligible Segments"]
    assert missing_promo_fields(["x"], None) == ["Channels"]
    assert missing_promo_fields(None, []) == ["Eligible Segments", "Channels"]


# --- missing_persona_split ----------------------------------------------------

@given(ticked=st.booleans(), attrs=_none_or_items)
def test_missing_persona_split_only_when_ticked_and_empty(ticked, attrs):
    assert missing_persona_split(ticked, attrs) == (ticked and not attrs)


def test_missing_persona_split_accepts_generators():
    assert missing_persona_split(True, iter(["Region"])) is False
    assert missing_persona_split(True, iter([])) is True
    assert missing_persona_split(False, None) is False


# --- required_message (default call only) ------------------------------------

def test_required_message_empty_is_blank():
    assert required_message([]) == ""


@given(names=st.lists(st.sampled_from(["Eligible Segments", "Channels", "Split by"]),
                      min_size=1, max_size=3, unique=True))
def test_required_message_names_every_missing_field(names):
    msg = required_message(names)
    assert msg.startswith("Fill in ") and msg.endswith(" before running.")
    assert all(n in msg for n in names)


def test_required_message_examples():
    assert required_message(["Channels"]) == "Fill in Channels before running."
    assert required_message(["Eligible Segments", "Channels"]) == (
        "Fill in Eligible Segments and Channels before running."
    )
    assert required_message(["A", "B", "C"]) == "Fill in A, B and C before running."


# --- theme.model_display ------------------------------------------------------

def test_model_display_known_ids():
    assert theme.model_display("global.anthropic.claude-sonnet-5-5") == ("Anthropic", "Claude Sonnet 5.5")
    assert theme.model_display("anthropic.claude-3-5-sonnet-20240620-v1:0") == ("Anthropic", "Claude 3.5 Sonnet")


def test_model_display_unreadable_id_falls_back_to_itself():
    assert theme.model_display("mystery") == ("", "mystery")


def test_model_display_empty_string_is_blank_pair():
    assert theme.model_display("") == ("", "")


@given(text=st.text(max_size=40))
def test_model_display_never_raises_and_returns_two_strings(text):
    provider, name = theme.model_display(text)
    assert isinstance(provider, str) and isinstance(name, str)
