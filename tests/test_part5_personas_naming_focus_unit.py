"""Unit tests for focus-category persona names (task 8.1g; Requirements 4.4, 4.6, 4.9).

Names, descriptions and category-specific actions show the persona's focus
category (from task 4.7) for non-flag text categoricals, using the shared wording
in ``part5_personas.labels``. Yes/no flags and numeric wording are unchanged.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import pytest

from part5_personas.labels import category_phrase
from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import PersonaProfile


def _profile(
    distinguishing: list[str],
    directions: dict[str, str] | None = None,
    top_categories: dict[str, list[tuple[str, int]]] | None = None,
    focus: dict[str, str] | None = None,
    numeric_mean: dict[str, float] | None = None,
    label: int = 0,
) -> PersonaProfile:
    return PersonaProfile(
        cluster_label=label,
        size=100,
        pct_of_leads=25.0,
        numeric_mean=numeric_mean or {},
        numeric_median={},
        top_categories=top_categories or {},
        distinguishing=distinguishing,
        distinguishing_directions=directions or {},
        focus_categories=focus or {},
    )


def _name(profile: PersonaProfile, taken: set[str] | None = None) -> str:
    return RuleBasedNamer().name(profile, taken or set())["name"]


# --------------------------------------------------------------------------- #
# Wording per column                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("column", "category", "expected"),
    [
        ("age_band", "25-34", "25-34 Age Band"),
        ("region", "Luzon", "Luzon Region"),
        ("segment", "Mass", "Mass Segment"),
        ("sec_class", "C1", "Class C1"),
        ("inflow_type", "Salary", "Salary Inflows"),
        ("online_shopper", "High", "High Online Shoppers"),
        ("inflow_type_other", "X", "Inflow Type Other: X"),
        ("preferred_theme", "Dark", "Preferred Theme: Dark"),
    ],
)
def test_category_phrase_wording(column, category, expected):
    assert category_phrase(column, category) == expected


@pytest.mark.parametrize(
    ("column", "category", "phrase"),
    [
        ("age_band", "25-34", "25-34 Age Band"),
        ("region", "Luzon", "Luzon Region"),
        ("sec_class", "C1", "Class C1"),
        ("inflow_type", "Salary", "Salary Inflows"),
        ("online_shopper", "High", "High Online Shoppers"),
    ],
)
def test_name_shows_focus_category_more_dropped_fewer_prefixed(column, category, phrase):
    cats = {column: [("zzz", 60), (category, 40)]}
    more = _profile([column], {column: "more"}, cats, {column: category})
    fewer = _profile([column], {column: "fewer"}, cats, {column: category})
    flat = _profile([column], {column: "flat"}, cats, {column: category})
    assert _name(more) == phrase
    assert _name(fewer) == f"Fewer {phrase}"
    assert _name(flat) == phrase


def test_two_part_text_name_example():
    p = _profile(
        ["age_band", "region"],
        {"age_band": "more", "region": "more"},
        {"age_band": [("35-44", 50), ("25-34", 30)], "region": [("NCR", 60), ("Luzon", 20)]},
        {"age_band": "25-34", "region": "Luzon"},
    )
    assert _name(p) == "25-34 Age Band / Luzon Region"


# --------------------------------------------------------------------------- #
# Flags and numerics unchanged                                                 #
# --------------------------------------------------------------------------- #
def test_flags_and_numerics_unchanged():
    p = _profile(
        ["digital_app_user", "total_out", "owns_investment"],
        {"digital_app_user": "fewer", "total_out": "high", "owns_investment": "more"},
        {
            "digital_app_user": [("0", 70), ("1", 30)],
            "owns_investment": [("1", 70), ("0", 30)],
        },
        numeric_mean={"total_out": 5.0},
    )
    assert _name(p) == "Fewer App Users / High Total Outflows"
    p2 = _profile(
        ["owns_investment", "total_out"],
        {"owns_investment": "more", "total_out": "low"},
        {"owns_investment": [("1", 70), ("0", 30)]},
        numeric_mean={"total_out": 5.0},
    )
    assert _name(p2) == "More Investment Account / Low Total Outflows"


# --------------------------------------------------------------------------- #
# Collisions: third attribute (max three parts), then letter suffix            #
# --------------------------------------------------------------------------- #
def _three_attr(label: int = 0) -> PersonaProfile:
    return _profile(
        ["age_band", "region", "sec_class", "total_out"],
        {"age_band": "more", "region": "more", "sec_class": "more", "total_out": "high"},
        {
            "age_band": [("25-34", 50)],
            "region": [("Luzon", 50)],
            "sec_class": [("C1", 50)],
        },
        {"age_band": "25-34", "region": "Luzon", "sec_class": "C1"},
        {"total_out": 1.0},
        label,
    )


def test_collision_extends_with_third_then_letters_and_caps_at_three_parts():
    p = _three_attr()
    base = "25-34 Age Band / Luzon Region"
    ext = f"{base} / Class C1"
    assert _name(p) == base
    assert _name(p, {base}) == ext
    assert _name(p, {base, ext}) == f"{ext} (A)"
    assert _name(p, {base, ext, f"{ext} (A)"}) == f"{ext} (B)"
    for taken in (set(), {base}, {base, ext}):
        assert _name(p, taken).split(" (")[0].count(" / ") <= 2


def test_names_unique_and_deterministic_over_a_set():
    def run() -> list[str]:
        namer, taken, out = RuleBasedNamer(), set(), []
        for i in range(5):
            n = namer.name(_three_attr(i), taken)["name"]
            taken.add(n)
            out.append(n)
        return out

    first = run()
    assert len(set(first)) == 5
    assert first == run()


# --------------------------------------------------------------------------- #
# Fallback to most common category                                             #
# --------------------------------------------------------------------------- #
def test_fallback_to_most_common_when_no_focus_entry():
    p = _profile(
        ["region"],
        {"region": "more"},
        {"region": [("NCR", 60), ("Luzon", 40)]},
    )
    r = RuleBasedNamer().name(p, set())
    assert r["name"] == "NCR Region"
    assert "region = NCR" in r["description"]
    assert "Lead the message on region = NCR" in r["actions"]


# --------------------------------------------------------------------------- #
# Description and action use the focus category                                #
# --------------------------------------------------------------------------- #
def test_description_and_action_use_focus_category_not_most_common():
    p = _profile(
        ["region", "age_band"],
        {"region": "more", "age_band": "more"},
        {"region": [("NCR", 60), ("Luzon", 20)], "age_band": [("35-44", 50), ("25-34", 30)]},
        {"region": "Luzon", "age_band": "25-34"},
    )
    r = RuleBasedNamer().name(p, set())
    assert r["name"] == "Luzon Region / 25-34 Age Band"
    assert "region = Luzon" in r["description"]
    assert "NCR" not in r["description"]
    assert "Lead the message on region = Luzon" in r["actions"]
    assert "Lead the message on age band = 25-34" in r["actions"]
    assert not any("NCR" in a or "35-44" in a for a in r["actions"])
