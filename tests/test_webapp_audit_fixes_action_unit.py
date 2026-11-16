"""required_message action parameter (audit item 1.15).

**Validates: Requirements 2.15, 3.15**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from webapp_core.required_fields import required_message

NAMES = st.lists(st.text(alphabet="ABCdef ", min_size=1, max_size=12), min_size=1, max_size=4)


def _joined(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@given(NAMES)
def test_default_unchanged(names):
    assert required_message(names) == (
        f"Fill in {_joined(names)} before running. Fields marked * are required."
    )


@given(NAMES, st.text(alphabet="abcdefg ", min_size=1, max_size=15))
def test_action_is_used(names, action):
    assert required_message(names, action=action) == (
        f"Fill in {_joined(names)} before {action}. Fields marked * are required."
    )


def test_empty_list_gives_empty_string():
    assert required_message([]) == ""
    assert required_message([], action="building personas") == ""


def test_personas_text():
    text = required_message(["Split by"], action="building personas")
    assert text == "Fill in Split by before building personas. Fields marked * are required."
    assert "before running" not in text
