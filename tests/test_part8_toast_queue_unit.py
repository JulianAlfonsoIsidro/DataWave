"""Tests for ``webapp_core.toast_queue.consume_flag``.

Feature: part8-new-ui-features, Property 7: A one-shot flag is consumed exactly once
Validates: Requirements 5.1, 5.2, 5.8
"""

from __future__ import annotations

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
