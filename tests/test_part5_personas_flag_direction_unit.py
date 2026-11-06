"""Unit tests for binary-flag direction (task 4.6; Requirement 4.4, revised).

A 0/1 flag must be compared on its share of ``"1"`` (yes), not the share of the
persona's dominant category. A persona of mostly non-users (dominant ``"0"``) is
therefore "fewer", never "more". Non-binary categoricals keep the
dominant-category comparison. The same direction feeds the persona name, the
trait tags, and the plain sentence.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.persona_page import distinguishing_sentences, persona_trait_tags
from part5_personas.labels import attribute_label
from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import PersonaProfile, build_profiles

FLAG = "digital_app_user"


def _flag_profiles(ones_and_sizes: list[tuple[int, int]]) -> list[PersonaProfile]:
    """One persona per ``(n_ones, size)`` pair over the ``digital_app_user`` flag."""
    values: list[int] = []
    labels: list[int] = []
    for label, (ones, size) in enumerate(ones_and_sizes):
        values += [1] * ones + [0] * (size - ones)
        labels += [label] * size
    frame = pd.DataFrame({FLAG: values})
    return build_profiles(frame, np.array(labels), [], [FLAG])


def _direction(profile: PersonaProfile) -> str:
    return profile.distinguishing_directions[FLAG]


# --------------------------------------------------------------------------- #
# Direction of a binary flag                                                   #
# --------------------------------------------------------------------------- #
def test_three_personas_direction_follows_share_of_yes():
    a, b, c = _flag_profiles([(80, 100), (30, 100), (60, 100)])

    assert _direction(a) == "more"  # 80% vs pooled 45%
    assert _direction(b) == "fewer"  # 30% vs pooled 70%; dominant is "0"
    assert _direction(b) != "more"
    assert _direction(c) == "more"  # 60% vs pooled 55%
    # B really is a mostly-non-user persona (dominant category "0").
    assert b.top_categories[FLAG][0][0] == "0"


def test_equal_shares_are_flat():
    a, b = _flag_profiles([(50, 100), (50, 100)])
    assert _direction(a) == "flat"
    assert _direction(b) == "flat"


def test_persona_with_no_yes_is_fewer():
    a, b = _flag_profiles([(0, 50), (40, 50)])
    assert a.top_categories[FLAG] == [("0", 50)]
    assert _direction(a) == "fewer"
    assert _direction(b) == "more"


def test_non_binary_categorical_keeps_dominant_category_logic():
    # P: x=4,y=3,z=3 (dominant x, share .4); Q: x=8,y=1,z=1 (x share .8).
    rows = ["x"] * 4 + ["y"] * 3 + ["z"] * 3 + ["x"] * 8 + ["y"] + ["z"]
    labels = np.array([0] * 10 + [1] * 10)
    p, q = build_profiles(pd.DataFrame({"age_band": rows}), labels, [], ["age_band"])

    assert p.distinguishing_directions["age_band"] == "fewer"  # .4 < .8
    assert q.distinguishing_directions["age_band"] == "more"  # .8 > .4


def test_real_example_shape_counts_145_70_reads_fewer():
    # The 215-lead persona: 70 users / 145 non-users, against four others that
    # are ~78% users overall (counts from the real k=5 run).
    shape = [(70, 215), (431, 485), (188, 250), (676, 902), (105, 148)]
    profiles = _flag_profiles(shape)
    target = profiles[0]

    assert target.top_categories[FLAG] == [("0", 145), ("1", 70)]
    assert _direction(target) == "fewer"


# --------------------------------------------------------------------------- #
# User-visible strings for the mostly-non-user persona                         #
# --------------------------------------------------------------------------- #
def _mostly_non_user_set() -> tuple[PersonaProfile, list[PersonaProfile]]:
    profiles = _flag_profiles([(80, 100), (30, 100), (60, 100)])
    return profiles[1], profiles


def test_name_says_fewer_not_more():
    b, _ = _mostly_non_user_set()
    name = RuleBasedNamer().name(b, set())["name"]
    assert "Fewer" in name
    assert "More" not in name


def test_trait_tags_say_fewer_not_more():
    b, _ = _mostly_non_user_set()
    tags = persona_trait_tags(b)
    assert f"Fewer {attribute_label(FLAG)}" in tags
    assert not any("More" in t for t in tags)


def test_sentence_says_fewer_not_more_likely():
    b, profiles = _mostly_non_user_set()
    sentence = distinguishing_sentences(b, profiles).lower()
    assert "less likely to use the mobile app" in sentence
    assert "more likely" not in sentence


def test_old_output_was_more_for_mostly_non_users():
    """Fails on the old code, which compared the dominant category ("0")."""
    b, profiles = _mostly_non_user_set()
    assert _direction(b) != "more"
    assert "More" not in RuleBasedNamer().name(b, set())["name"]
    assert "more likely" not in distinguishing_sentences(b, profiles)
