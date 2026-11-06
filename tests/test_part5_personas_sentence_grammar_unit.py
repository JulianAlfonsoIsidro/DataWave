"""Grammar unit tests for persona sentences (task 14.11; Requirement 4.10).

A "fewer" direction must read "less likely to ..." in the sentence, while trait
tags ("Fewer app users") and persona names ("Fewer App Users") stay unchanged.
"""

from __future__ import annotations

import pytest

from app.persona_page import (
    _phrase_for,
    distinguishing_sentences,
    persona_trait_tags,
)
from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import PersonaProfile


def _profile(columns, directions, top=None) -> PersonaProfile:
    return PersonaProfile(
        cluster_label=0,
        size=10,
        pct_of_leads=50.0,
        numeric_mean={"total_out": 1.0},
        numeric_median={"total_out": 1.0},
        top_categories=top or {},
        distinguishing=columns,
        distinguishing_directions=directions,
    )


def _raw(p: PersonaProfile) -> str:
    return distinguishing_sentences(p, [p])


def _one(column, cats, direction) -> str:
    return _raw(_profile([column], {column: direction}, {column: cats}))


CASES = [
    ("digital_app_user", [("0", 7), ("1", 3)], "to use the mobile app"),
    ("owns_Deposit", [("0", 7), ("1", 3)], "to own deposit account"),
    ("age_band", [("55+", 6), ("25-34", 4)], "to be in the 55+ age band"),
    ("region", [("NCR", 6), ("Luzon", 4)], "to be in the NCR region"),
    ("online_shopper", [("Low", 6), ("High", 4)], "to be a low online shopper"),
]


@pytest.mark.parametrize("column,cats,tail", CASES)
def test_fewer_reads_less_likely(column, cats, tail):
    s = _one(column, cats, "fewer")
    assert f"less likely {tail}".lower() in s.lower()
    assert "fewer likely" not in s.lower()


@pytest.mark.parametrize("column,cats,tail", CASES)
def test_more_wording_unchanged(column, cats, tail):
    s = _one(column, cats, "more")
    assert f"more likely {tail}".lower() in s.lower()
    assert "less likely" not in s.lower()


def test_label_fallbacks():
    assert _phrase_for("fewer", "Has a loan") == "less likely to have a loan"
    assert _phrase_for("fewer", "Shops online") == "less likely to shop online"
    assert _phrase_for("more", "Has a loan") == "more likely to have a loan"
    assert _phrase_for("more", "Shops online") == "more likely to shop online"


def test_sentence_initial_capitalisation():
    s = _one("age_band", [("55+", 6)], "fewer")
    assert s.startswith("Less likely to be in the 55+ age band")


def test_multi_attribute_sentence():
    p = _profile(
        ["digital_app_user", "total_out"],
        {"digital_app_user": "fewer", "total_out": "high"},
        {"digital_app_user": [("0", 7), ("1", 3)]},
    )
    assert _raw(p) == (
        "Less likely to use the mobile app and higher total outflows "
        "than other personas."
    )


def test_fewer_likely_never_appears():
    for column, cats, _ in CASES:
        for direction in ("fewer", "more"):
            assert "fewer likely" not in _one(column, cats, direction).lower()


def test_numeric_wording_unchanged():
    assert _raw(_profile(["total_out"], {"total_out": "high"})) == (
        "Higher total outflows than other personas."
    )
    assert _raw(_profile(["total_out"], {"total_out": "low"})) == (
        "Lower total outflows than other personas."
    )


def test_tags_and_names_unchanged():
    p = _profile(
        ["digital_app_user"],
        {"digital_app_user": "fewer"},
        {"digital_app_user": [("0", 7), ("1", 3)]},
    )
    assert "Fewer app users" in persona_trait_tags(p)
    assert "Fewer App Users" in RuleBasedNamer().name(p, taken=set())["name"]


def test_deterministic():
    a = _one("region", [("NCR", 6), ("Luzon", 4)], "fewer")
    assert a == _one("region", [("NCR", 6), ("Luzon", 4)], "fewer")
