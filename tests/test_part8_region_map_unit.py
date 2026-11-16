"""Tests for ``webapp_core.region_map`` (Part 8, F6).

Feature: part8-new-ui-features, Property 1: Region entries are complete, ordered and consistent
Feature: part8-new-ui-features, Property 2: Invalid counts are rejected without a partial result
Feature: part8-new-ui-features, Property 3: Every shape has at most one owner
Validates: Requirements 13.1, 13.6, 13.8, 14.1-14.8
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from webapp_core.region_map import (
    AREA_SHAPES,
    MAP_AREAS,
    area_label,
    build_region_map,
    shape_owner,
    unassigned_shape_codes,
)

_regions = st.sampled_from(["NCR", "Luzon", "Visayas", "Mindanao", "ncr", "Metro Manila", "Luzon "])
_pairs = st.lists(st.tuples(_regions, st.integers(min_value=0, max_value=5000)), max_size=8)
# The 18 PSGC region codes in faeldon/philippines-json-maps v1.1.1.
SOURCE_CODES = [
    100000000, 200000000, 300000000, 400000000, 500000000, 600000000, 700000000,
    800000000, 900000000, 1000000000, 1100000000, 1200000000, 1300000000, 1400000000,
    1600000000, 1700000000, 1800000000, 1900000000,
]


@settings(max_examples=100, deadline=None)
@given(pairs=_pairs)
def test_property_1_entries_complete_ordered_consistent(pairs):
    """Feature: part8-new-ui-features, Property 1: Region entries are complete, ordered and consistent

    **Validates: Requirements 13.1, 13.6, 13.8, 14.2, 14.4, 14.5, 14.6**
    """
    result = build_region_map(pairs)
    assert tuple(e.region for e in result.entries) == MAP_AREAS
    for e in result.entries:
        expected = sum(c for r, c in pairs if r == e.region)
        assert e.lead_count == expected
        assert e.selectable is (expected > 0)
        label = area_label(e)
        assert e.region in label and f"{e.lead_count:,}" in label
    expected_unmatched = []
    for r, _ in pairs:
        if r not in MAP_AREAS and r not in expected_unmatched:
            expected_unmatched.append(r)
    assert list(result.unmatched) == expected_unmatched
    assert build_region_map(pairs) == result


@settings(max_examples=100, deadline=None)
@given(pairs=_pairs, bad=st.one_of(st.integers(max_value=-1), st.floats(allow_nan=False), st.just("12")),
       where=st.integers(min_value=0, max_value=8))
def test_property_2_invalid_counts_rejected(pairs, bad, where):
    """Feature: part8-new-ui-features, Property 2: Invalid counts are rejected without a partial result

    **Validates: Requirements 14.1, 14.7**
    """
    data = list(pairs)
    data.insert(min(where, len(data)), ("Visayas", bad))
    snapshot = list(data)
    with pytest.raises(ValueError, match="Visayas"):
        build_region_map(data)
    assert data == snapshot


@settings(max_examples=100, deadline=None)
@given(codes=st.lists(st.sampled_from(SOURCE_CODES + [1, 1500000000, 42]), max_size=20))
def test_property_3_every_shape_has_at_most_one_owner(codes):
    """Feature: part8-new-ui-features, Property 3: Every shape has at most one owner

    **Validates: Requirements 14.3**
    """
    owners: dict[int, list[str]] = {}
    for area, cs in AREA_SHAPES.items():
        for c in cs:
            owners.setdefault(c, []).append(area)
    assert all(len(v) == 1 for v in owners.values())
    for c in codes:
        assert shape_owner(c) == (owners[c][0] if c in owners else None)
    expected = []
    for c in codes:
        if c not in owners and c not in expected:
            expected.append(c)
    assert list(unassigned_shape_codes(codes)) == expected


def test_each_current_value_maps_to_one_area_and_all_18_owned():
    result = build_region_map([("NCR", 891), ("Luzon", 506), ("Visayas", 362), ("Mindanao", 241)])
    assert [(e.region, e.lead_count, e.selectable) for e in result.entries] == [
        ("NCR", 891, True), ("Luzon", 506, True), ("Visayas", 362, True), ("Mindanao", 241, True),
    ]
    assert unassigned_shape_codes(SOURCE_CODES) == ()


def test_unmatched_zero_and_absent():
    result = build_region_map([("Metro Manila", 5), ("Visayas", 0)])
    assert result.unmatched == ("Metro Manila",)
    visayas = result.entries[2]
    assert visayas.lead_count == 0 and visayas.selectable is False
    assert result.entries[0].lead_count == 0  # NCR absent from the input


def test_negative_count_raises():
    with pytest.raises(ValueError, match="NCR"):
        build_region_map([("NCR", -1)])
