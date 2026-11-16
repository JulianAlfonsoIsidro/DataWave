"""Tests for ``webapp_core.toast_queue.consume_flag``.

Feature: part8-new-ui-features, Property 7: A one-shot flag is consumed exactly once
Validates: Requirements 5.1, 5.2, 5.8
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from webapp_core.toast_queue import consume_flag

_values = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False),
    st.text(),
    st.lists(st.integers(), max_size=3),
)
_states = st.dictionaries(st.text(max_size=8), _values, max_size=6)


@settings(max_examples=100)
@given(state=_states, key=st.text(max_size=8))
def test_property_7_flag_consumed_exactly_once(state, key):
    """Feature: part8-new-ui-features, Property 7: A one-shot flag is consumed exactly once

    **Validates: Requirements 5.1, 5.2, 5.8**
    """
    expected_first = bool(state[key]) if key in state else False
    others = {k: v for k, v in state.items() if k != key}

    assert consume_flag(state, key) is expected_first
    assert key not in state
    assert consume_flag(state, key) is False
    assert consume_flag(state, key) is False
    assert state == others


def test_absent_key_returns_false_and_leaves_state():
    state = {"a": 1}
    assert consume_flag(state, "missing") is False
    assert state == {"a": 1}


def test_falsy_value_is_removed_and_returns_false():
    state = {"flag": 0, "other": True}
    assert consume_flag(state, "flag") is False
    assert state == {"other": True}


# --- Toast queue (F3) ------------------------------------------------------

from webapp_core.toast_queue import (  # noqa: E402
    ALL_LEADS_TEXT,
    LIFE_S,
    MAX_VISIBLE,
    Toast,
    plan_view,
    prune,
    push,
    settle,
    start_text,
)

_gaps = st.lists(st.floats(min_value=0.0, max_value=3.0, allow_nan=False), min_size=1, max_size=8)


@settings(max_examples=100, deadline=None)
@given(gaps=_gaps, extra=st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
def test_property_5_queue_bound_and_no_expired(gaps, extra):
    """Feature: part8-new-ui-features, Property 5: The toast queue never shows more than three and never shows an expired toast

    **Validates: Requirements 5.7, 8.3, 8.4, 8.5**
    """
    queue: list[Toast] = []
    t = 1000.0
    for i, g in enumerate(gaps):
        t += g
        queue = push(queue, Toast(f"t{i}", "analysis", "start", f"x{i}", t))
    now = t + extra

    pruned = prune(queue, now)
    views = plan_view(pruned, now)

    assert sum(1 for v in views if not v.evicting) <= MAX_VISIBLE
    if views:
        newest = max(pruned, key=lambda x: (x.created_at, pruned.index(x)))
        assert views[0].toast is newest and views[0].slot == 0
    assert all(0 <= v.elapsed_s < LIFE_S for v in views)
    assert all(now - x.created_at < LIFE_S for x in pruned)
    assert prune(pruned, now) == pruned
    evicting = {id(v.toast) for v in views if v.evicting}
    settled = settle(pruned)
    assert {id(x) for x in pruned} - {id(x) for x in settled} == evicting


_labels = st.lists(st.text(alphabet="ABCDEFGHIJ abcdefghij", min_size=1, max_size=12), max_size=4)


@settings(max_examples=100, deadline=None)
@given(promo=st.text(alphabet="NEW-0123456789", min_size=1, max_size=8), labels=_labels)
def test_property_6_start_text(promo, labels):
    """Feature: part8-new-ui-features, Property 6: Start toast text uses display labels in order

    **Validates: Requirements 8.8**
    """
    assert promo in start_text("analysis", promo)
    text = start_text("personas", labels)
    kept = [l for l in labels if l]
    if not kept:
        assert text == ALL_LEADS_TEXT
    else:
        pos = 0
        for label in kept:
            found = text.find(label, pos)
            assert found >= 0
            pos = found + len(label)
        assert "age_band" not in text and "owns_Loan" not in text


def test_start_text_examples():
    assert start_text("analysis", "NEW-001") == "Running analysis for NEW-001..."
    assert start_text("personas", []) == "Building personas for all leads..."
    assert start_text("personas", ["Age band", "Region"]) == "Building personas by Age band, Region..."


def test_fourth_toast_evicts_oldest_once():
    queue = []
    for i in range(4):
        queue = push(queue, Toast(f"t{i}", "analysis", "start", "x", 100.0 + i * 0.1))
    views = plan_view(queue, 100.5)
    assert [v.toast.id for v in views] == ["t3", "t2", "t1", "t0"]
    assert [v.evicting for v in views] == [False, False, False, True]
    assert [t.id for t in settle(queue)] == ["t1", "t2", "t3"]


def test_delayed_toast_waits_then_lives_full_life():
    toast = Toast("t1", "personas", "done", "Personas ready", 50.0, delay_s=0.6)
    (view,) = plan_view([toast], 50.0)
    assert view.elapsed_s == pytest.approx(-0.6)
    assert prune([toast], 50.0 + 0.6 + LIFE_S - 0.01) == [toast]
    assert prune([toast], 50.0 + 0.6 + LIFE_S) == []
