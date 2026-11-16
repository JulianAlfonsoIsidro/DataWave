"""Unit tests for webapp_core.review_signoff (audit item 1.1, task 3.1)."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from webapp_core.review_signoff import (
    REVIEW_KEY_PREFIX,
    SIGNATURE_STATE_KEY,
    clear_stale_signoffs,
    figures_signature,
    persona_signature,
)

BASE = ("P100", "ABSOLUTE", 530000.0, 1)


def test_equal_inputs_equal_signature_and_hashable():
    a = figures_signature(*BASE)
    assert a == figures_signature(*BASE)
    assert isinstance(hash(a), int)


def test_each_single_field_change_differs():
    base = figures_signature(*BASE)
    assert figures_signature("P101", *BASE[1:]) != base
    assert figures_signature(BASE[0], "PERCENT", *BASE[2:]) != base
    assert figures_signature(BASE[0], BASE[1], 600000, BASE[3]) != base
    assert figures_signature(*BASE[:3], 2) != base


def test_float_noise_below_1e6_ignored():
    assert figures_signature("P", "T", 1.0, 0) == figures_signature("P", "T", 1.0 + 1e-9, 0)


def test_first_call_stores_and_clears_nothing():
    state = {f"{REVIEW_KEY_PREFIX}a": True}
    assert clear_stale_signoffs(state, figures_signature(*BASE)) is False
    assert state[f"{REVIEW_KEY_PREFIX}a"] is True
    assert state[SIGNATURE_STATE_KEY] == figures_signature(*BASE)


def test_changed_signature_clears_only_review_keys():
    state = {f"{REVIEW_KEY_PREFIX}a": True, "other": True}
    clear_stale_signoffs(state, figures_signature(*BASE))
    assert clear_stale_signoffs(state, figures_signature("P101", *BASE[1:])) is True
    assert state[f"{REVIEW_KEY_PREFIX}a"] is False
    assert state["other"] is True


@settings(deadline=None, max_examples=40)
@given(st.integers(0, 10), st.integers(0, 10))
def test_run_seq_bump_clears(a, b):
    state = {}
    clear_stale_signoffs(state, figures_signature("P", "T", 1, a))
    state[f"{REVIEW_KEY_PREFIX}x"] = True
    cleared = clear_stale_signoffs(state, figures_signature("P", "T", 1, b))
    assert cleared == (a != b)
    assert state[f"{REVIEW_KEY_PREFIX}x"] == (a == b)


def test_persona_signature_none():
    assert persona_signature(None) == ("", 0, "")
