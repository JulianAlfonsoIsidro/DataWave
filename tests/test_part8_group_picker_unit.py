"""Tests for ``webapp_core.group_picker_items`` (Part 8, F6, F7, F9).

Feature: part8-new-ui-features, Property 8: The picker kind follows the split and the groups
Feature: part8-new-ui-features, Property 9: Component events are applied once and never revert a dropdown change
Feature: part8-new-ui-features, Property 11: Glass levels are symmetric around the front and wrap
Feature: part8-new-ui-features, Property 12: A group-change fade needs a real change and no reveal
Feature: part8-new-ui-features, Property 13: The shortest step is minimal and lands on the target
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from webapp_core.group_picker_items import (
    MAX_COMBINED_GROUPS,
    MULTI_SEP,
    YES_NO_ART,
    art_for,
    glass_level,
    group_changed,
    plan_picker,
    resolve_component_value,
    shortest_step,
)

_columns = st.sampled_from(["segment", "age_band", "sec_class", "inflow_type", "online_shopper", "frugal_flag"])


@settings(max_examples=100, deadline=None)
@given(
    cols=st.lists(_columns, min_size=0, max_size=3, unique=True),
    n=st.integers(min_value=0, max_value=16),
    yes_no=st.booleans(),
)
def test_property_8_kind_follows_split_and_groups(cols, n, yes_no):
    """Feature: part8-new-ui-features, Property 8: The picker kind follows the split and the groups

    **Validates: Requirements 12.8, 12.11, 13.1, 15.1, 15.11, 15.12, 18.4, 18.5**
    """
    if len(cols) == 1 and n == 2 and yes_no:
        keys = ["0", "1"]
    else:
        keys = [MULTI_SEP.join(f"v{i}c{j}" for j in range(len(cols))) if len(cols) > 1 else f"v{i}"
                for i in range(n)]
    counts = {k: (i + 1) * 10 for i, k in enumerate(keys)}
    plan = plan_picker(cols, keys, counts)
    if not cols or n <= 1:
        assert plan.kind == "none"
    elif len(cols) == 1:
        if n == 2:
            assert plan.kind == "toggle"
            assert plan.yes_no is (keys == ["0", "1"])
        else:
            assert plan.kind == "carousel"
    else:
        if n == 2:
            assert plan.kind == "toggle" and plan.yes_no is False
        elif n <= MAX_COMBINED_GROUPS:
            assert plan.kind == "carousel"
        else:
            assert plan.kind == "none"
    if plan.kind != "none":
        assert {i.value for i in plan.items} == set(keys)
        assert all(i.lead_count == counts[i.value] for i in plan.items)
        if plan.kind == "carousel" and len(cols) > 1:
            assert [i.value for i in plan.items] == keys  # run order kept


def test_region_alone_gives_map_even_with_two_groups():
    plan = plan_picker(["region"], ["NCR", "Visayas"], {"NCR": 891, "Visayas": 362})
    assert plan.kind == "map"
    assert [(i.value, i.selectable) for i in plan.items] == [
        ("NCR", True), ("Luzon", False), ("Visayas", True), ("Mindanao", False),
    ]


def test_yes_no_toggle_uses_column_icon_and_check_cross():
    plan = plan_picker(["digital_app_user"], ["1", "0"], {"0": 530, "1": 1470},
                       lambda c: "Uses the mobile app")
    assert plan.kind == "toggle" and plan.yes_no
    assert plan.column_art == YES_NO_ART["digital_app_user"]
    assert [(i.label, i.art) for i in plan.items] == [
        ("Uses the mobile app: Yes", "yn-check"), ("Uses the mobile app: No", "yn-cross"),
    ]


def test_ring_order_and_unknown_art():
    plan = plan_picker(["online_shopper"], ["High", "Low", "Ultra High", "Medium"], {})
    assert [i.value for i in plan.items] == ["Low", "Medium", "High", "Ultra High"]
    assert all(i.selectable and i.lead_count is None for i in plan.items)
    assert art_for("age_band", "99+") == "unknown"
    assert len(set(YES_NO_ART.values())) == 8


def test_multi_split_labels_join_with_dot():
    keys = ["NCR | 25-34", "Luzon | 25-34", "NCR | 35-44"]
    plan = plan_picker(["region", "age_band"], keys, {})
    assert plan.kind == "carousel"
    assert plan.items[0].label == "NCR · 25-34"
    assert plan.items[0].art == "unknown"  # region has no illustration


_event = st.one_of(st.none(), st.fixed_dictionaries({
    "value": st.sampled_from(["A", "B", "C", "Z"]), "nonce": st.integers(0, 3),
}))


@settings(max_examples=100, deadline=None)
@given(last=_event, new=_event)
def test_property_9_events_applied_once(last, new):
    """Feature: part8-new-ui-features, Property 9: Component events are applied once and never revert a dropdown change

    **Validates: Requirements 12.4, 12.10, 12.12, 12.13**
    """
    options = ["A", "B", "C", "All groups"]
    d = resolve_component_value(last, new, options)
    if new is None or new == last:
        assert d.apply is None
    else:
        assert d.apply == (new["value"] if new["value"] in options else None)
    if new is not None:
        assert d.last == new
        again = resolve_component_value(d.last, new, options)
        assert again.apply is None


@settings(max_examples=100, deadline=None)
@given(n=st.integers(1, 14), data=st.data())
def test_property_11_glass_levels(n, data):
    """Feature: part8-new-ui-features, Property 11: Glass levels are symmetric around the front and wrap

    **Validates: Requirements 15.2, 15.20, 15.21, 15.23**
    """
    f = data.draw(st.integers(0, n - 1))
    i = data.draw(st.integers(0, n - 1))
    level = glass_level(i, f, n)
    assert (level == 0) is (i == f)
    assert level == glass_level((2 * f - i) % n, f, n)
    dist = min((i - f) % n, (f - i) % n)
    if dist == 1:
        assert level == 1
    if dist >= 2:
        assert level == (1 if n <= 4 else 2)
    if n <= 4:
        assert level <= 1
    assert abs(glass_level(i, (f + 1) % n, n) - level) <= 1


@settings(max_examples=100, deadline=None)
@given(prev=st.one_of(st.none(), st.sampled_from(["A", "B"])),
       cur=st.one_of(st.none(), st.sampled_from(["A", "B"])), reveal=st.booleans())
def test_property_12_group_change(prev, cur, reveal):
    """Feature: part8-new-ui-features, Property 12: A group-change fade needs a real change and no reveal

    **Validates: Requirements 22.13, 22.14, 5.4**
    """
    expected = prev is not None and cur is not None and prev != cur and not reveal
    assert group_changed(prev, cur, reveal=reveal) is expected


@settings(max_examples=100, deadline=None)
@given(n=st.integers(1, 14), data=st.data())
def test_property_13_shortest_step(n, data):
    """Feature: part8-new-ui-features, Property 13: The shortest step is minimal and lands on the target

    **Validates: Requirements 12.15, 15.8**
    """
    f = data.draw(st.integers(0, n - 1))
    t = data.draw(st.integers(0, n - 1))
    d = shortest_step(f, t, n)
    assert -(n // 2) <= d <= n // 2
    assert (f + d) % n == t % n
    assert all(abs(d) <= abs(e) for e in range(-n, n + 1) if (f + e) % n == t % n)
