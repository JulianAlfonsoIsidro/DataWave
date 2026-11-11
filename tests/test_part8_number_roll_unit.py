"""Tests for ``webapp_core.number_roll.plan_roll`` (Part 8, F5).

Feature: part8-new-ui-features, Property 4: The roll plan always ends on the current value and animates only what changed
Validates: Requirements 11.2, 11.3, 11.5, 11.8
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from webapp_core.number_roll import plan_roll

_numbers = st.text(alphabet="0123456789,.%₱-", max_size=9)


@settings(max_examples=100, deadline=None)
@given(prev=st.one_of(st.none(), _numbers), cur=_numbers)
def test_property_4_plan_ends_on_current_and_rolls_only_changes(prev, cur):
    """Feature: part8-new-ui-features, Property 4: The roll plan always ends on the current value and animates only what changed

    **Validates: Requirements 11.2, 11.3, 11.5, 11.8**
    """
    cells = plan_roll(prev, cur)
    assert "".join(c.char for c in cells) == cur
    if prev is None or prev == cur or prev == "--":
        assert all(c.kind == "static" for c in cells)
        return
    offset = len(cur) - len(prev)
    for i, c in enumerate(cells):
        j = i - offset
        counterpart = prev[j] if 0 <= j < len(prev) else None
        if c.kind == "roll":
            assert counterpart is not None and counterpart.isdigit() and c.char.isdigit()
            assert counterpart != c.char and c.prev == counterpart
        elif c.kind == "enter":
            assert counterpart is None
        else:
            assert counterpart is not None


def test_examples():
    cells = plan_roll("98", "1,203")
    assert "".join(c.char for c in cells) == "1,203"
    assert [c.kind for c in cells] == ["enter", "enter", "enter", "roll", "roll"]
    assert all(c.kind == "static" for c in plan_roll("--", "1,203"))
    assert all(c.kind == "static" for c in plan_roll("204", "204"))
    assert all(c.kind == "static" for c in plan_roll(None, "204"))
    assert [c.kind for c in plan_roll("204", "214")] == ["static", "roll", "static"]
