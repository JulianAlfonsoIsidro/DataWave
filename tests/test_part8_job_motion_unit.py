"""Tests for ``webapp_core.job_motion.ring_phase`` and ``is_duplicate_submit``.

Feature: part8-new-ui-features, Property 14: The ring phase is a periodic fraction of a lap
Feature: part8-new-ui-features, Property 15: A duplicate submit needs the same inputs inside the window
Validates: Requirements 7.5, 7.8, 7.11, 7.12
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, strategies as st

from webapp_core.job_motion import DUPLICATE_WINDOW_S, is_duplicate_submit, ring_phase

_started = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_elapsed = st.floats(min_value=0.0, max_value=1e5, allow_nan=False, allow_infinity=False)
_laps = st.floats(min_value=0.05, max_value=100.0, allow_nan=False, allow_infinity=False)


def _circular_distance(a: float, b: float) -> float:
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


# --- Property 14 -----------------------------------------------------------


@settings(max_examples=100)
@given(started_at=_started, elapsed=_elapsed, lap_s=_laps)
def test_property_14_ring_phase_is_periodic_fraction(started_at, elapsed, lap_s):
    """Feature: part8-new-ui-features, Property 14: The ring phase is a periodic fraction of a lap

    **Validates: Requirements 7.5, 7.8**
    """
    now = started_at + elapsed
    phase = ring_phase(started_at, now, lap_s)
    assert 0.0 <= phase < 1.0

    later = ring_phase(started_at, now + lap_s, lap_s)
    assert 0.0 <= later < 1.0
    assert _circular_distance(phase, later) < 1e-6


@settings(max_examples=100)
@given(
    started_at=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False),
    lap_s=_laps,
    k=st.integers(min_value=0, max_value=1000),
    f1=st.floats(min_value=0.001, max_value=0.998),
    gap=st.floats(min_value=0.001, max_value=0.997),
)
def test_property_14_ring_phase_increases_within_a_lap(started_at, lap_s, k, f1, gap):
    """Feature: part8-new-ui-features, Property 14: The ring phase is a periodic fraction of a lap

    **Validates: Requirements 7.5, 7.8**
    """
    f2 = min(f1 + gap, 0.999)
    if f2 - f1 < 0.001:
        f1 = f2 - 0.001
    p1 = ring_phase(started_at, started_at + (k + f1) * lap_s, lap_s)
    p2 = ring_phase(started_at, started_at + (k + f2) * lap_s, lap_s)
    assert p1 < p2


@settings(max_examples=100)
@given(started_at=_started, back=st.floats(min_value=1e-3, max_value=1e5), lap_s=_laps)
def test_property_14_now_before_start_is_zero(started_at, back, lap_s):
    """Feature: part8-new-ui-features, Property 14: The ring phase is a periodic fraction of a lap

    **Validates: Requirements 7.5, 7.8**
    """
    assert ring_phase(started_at, started_at - back, lap_s) == 0.0


@settings(max_examples=100)
@given(
    started_at=_started,
    elapsed=_elapsed,
    lap_s=st.floats(max_value=0.0, allow_nan=False),
)
def test_property_14_non_positive_lap_raises(started_at, elapsed, lap_s):
    """Feature: part8-new-ui-features, Property 14: The ring phase is a periodic fraction of a lap

    **Validates: Requirements 7.5, 7.8**
    """
    with pytest.raises(ValueError):
        ring_phase(started_at, started_at + elapsed, lap_s)


# --- Property 15 -----------------------------------------------------------

_signatures = st.sampled_from(["a", "b", "promo|x", ""])
_times = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_windows = st.floats(min_value=0.01, max_value=10.0, allow_nan=False)


@settings(max_examples=100)
@given(
    has_end=st.booleans(),
    end_sig=_signatures,
    signature=_signatures,
    ended_at=_times,
    offset=st.floats(min_value=-20.0, max_value=20.0, allow_nan=False),
    window_s=_windows,
)
def test_property_15_duplicate_needs_same_inputs_in_window(
    has_end, end_sig, signature, ended_at, offset, window_s
):
    """Feature: part8-new-ui-features, Property 15: A duplicate submit needs the same inputs inside the window

    **Validates: Requirements 7.11, 7.12**
    """
    now = ended_at + offset
    last_end = (
        {"ok": True, "started_at": ended_at - 1.0, "ended_at": ended_at, "signature": end_sig}
        if has_end
        else None
    )
    expected = (
        last_end is not None
        and end_sig == signature
        and 0.0 <= now - ended_at <= window_s
    )
    assert is_duplicate_submit(last_end, signature, now, window_s) is expected

    if last_end is None or end_sig != signature:
        assert is_duplicate_submit(last_end, signature, now, window_s) is False


@settings(max_examples=100)
@given(
    signature=_signatures,
    ended_at=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False),
    window_s=_windows,
    beyond=st.floats(min_value=1e-3, max_value=100.0, allow_nan=False),
)
def test_property_15_just_outside_window_is_false(signature, ended_at, window_s, beyond):
    """Feature: part8-new-ui-features, Property 15: A duplicate submit needs the same inputs inside the window

    **Validates: Requirements 7.11, 7.12**
    """
    last_end = {"ok": True, "started_at": ended_at, "ended_at": ended_at, "signature": signature}
    assert is_duplicate_submit(last_end, signature, ended_at + window_s + beyond, window_s) is False
    assert is_duplicate_submit(last_end, signature, ended_at - beyond, window_s) is False


# --- Examples --------------------------------------------------------------


def test_ring_phase_example_half_lap():
    assert math.isclose(ring_phase(10, 12.1, 1.4), 0.5, abs_tol=1e-9)


def test_duplicate_at_window_boundary_is_true():
    last_end = {"ok": True, "started_at": 98.0, "ended_at": 100.0, "signature": "s"}
    assert is_duplicate_submit(last_end, "s", 100.0 + DUPLICATE_WINDOW_S) is True
    assert is_duplicate_submit(last_end, "s", 100.0) is True


def test_duplicate_with_other_signature_is_false():
    last_end = {"ok": False, "started_at": 98.0, "ended_at": 100.0, "signature": "s"}
    assert is_duplicate_submit(last_end, "t", 100.5) is False
    assert is_duplicate_submit(None, "s", 100.5) is False
