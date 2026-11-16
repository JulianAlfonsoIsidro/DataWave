"""Unit tests for category-aware persona sentences (task 14.10; Requirement 4.10).

A non-binary categorical attribute must be described by the persona's DOMINANT
category (``top_categories[column][0][0]``), e.g. "more likely to be in the 35-44
age band", not by the attribute label. Binary 0/1 flags and numeric attributes
keep their existing wording.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import pytest

from app.persona_page import distinguishing_sentences, persona_trait_tags
from part5_personas.profile import PersonaProfile


def _profile(
    columns: list[str],
    directions: dict[str, str],
    top: dict[str, list[tuple[str, int]]] | None = None,
) -> PersonaProfile:
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


def _sentence(p: PersonaProfile) -> str:
    # decapitalize the first letter so phrases can be asserted mid-sentence
    s = _raw(p)
    return s[0].lower() + s[1:]


def _one(column: str, cats: list[tuple[str, int]], direction: str = "more") -> str:
    return _sentence(_profile([column], {column: direction}, {column: cats}))


def test_age_band_names_dominant_category():
    s = _one("age_band", [("35-44", 6), ("25-34", 3), ("18-24", 1)])
    assert s == "more likely to be in the 35-44 age band than other personas."


def test_age_band_fewer_direction():
    s = _one("age_band", [("55+", 6), ("25-34", 4)], "fewer")
    assert "less likely to be in the 55+ age band" in s.lower()


def test_region():
    s = _one("region", [("Visayas", 6), ("Luzon", 4)])
    assert "more likely to be in the Visayas region" in s


def test_segment():
    s = _one("segment", [("Mid-Market", 6), ("Affluent-Gold", 4)])
    assert "more likely to be in the Mid-Market customer segment" in s


def test_sec_class():
    s = _one("sec_class", [("C1", 6), ("A", 4)])
    assert "more likely to be in socio-economic class C1" in s


def test_inflow_type():
    s = _one("inflow_type", [("Salary", 6), ("Business", 4)])
    assert "more likely to have Salary as their main money-in type" in s


def test_online_shopper_ordinal():
    s = _one("online_shopper", [("Very High", 6), ("High", 4)])
    assert "more likely to be a very high online shopper" in s
    assert "shop online" not in s


def test_unknown_categorical_fallback():
    s = _one("investment_propensity_decile", [("7", 6), ("2", 4)])
    assert "more likely to have investment appetite of 7" in s


def test_categorical_without_top_category_falls_back_to_label():
    s = _sentence(_profile(["age_band"], {"age_band": "more"}, {}))
    assert "more likely to be age band" in s


def test_multi_attribute_joining_and_suffix():
    p = _profile(
        ["age_band", "digital_app_user", "total_out"],
        {"age_band": "more", "digital_app_user": "fewer", "total_out": "high"},
        {"age_band": [("35-44", 6), ("18-24", 4)], "digital_app_user": [("0", 7), ("1", 3)]},
    )
    assert _raw(p) == (
        "More likely to be in the 35-44 age band, less likely to use the mobile app "
        "and higher total outflows than other personas."
    )


def test_binary_flags_keep_wording():
    p = _profile(
        ["digital_app_user"], {"digital_app_user": "fewer"},
        {"digital_app_user": [("0", 7), ("1", 3)]},
    )
    assert "less likely to use the mobile app" in _sentence(p)
    q = _profile(
        ["owns_Deposit"], {"owns_Deposit": "more"}, {"owns_Deposit": [("1", 8), ("0", 2)]}
    )
    assert "more likely to own deposit account" in _sentence(q)


def test_numeric_wording_unchanged():
    p = _profile(["total_out"], {"total_out": "high"})
    assert _raw(p) == "Higher total outflows than other personas."


def test_trait_tags_unchanged():
    p = _profile(
        ["age_band", "total_out"],
        {"age_band": "more", "total_out": "high"},
        {"age_band": [("35-44", 6)]},
    )
    assert persona_trait_tags(p) == ["More aged 35-44", "Higher total outflows"]


def test_deterministic_and_no_label_only_phrase():
    p = _profile(
        ["age_band", "region"],
        {"age_band": "more", "region": "fewer"},
        {"age_band": [("45-54", 5), ("25-34", 5)], "region": [("NCR", 6), ("Luzon", 4)]},
    )
    assert _sentence(p) == _sentence(p)
    assert "likely to be age band" not in _sentence(p)
    assert "likely to be region" not in _sentence(p)


@pytest.mark.parametrize(
    "column,cat,expected",
    [
        ("age_band", "55+", "to be in the 55+ age band"),
        ("region", "NCR", "to be in the NCR region"),
        ("online_shopper", "Low", "to be a low online shopper"),
    ],
)
def test_phrase_uses_dominant_not_alphabetical_first(column, cat, expected):
    # the dominant category is listed first even though it is not alphabetically first
    s = _one(column, [(cat, 9), ("0a", 1)])
    assert expected in s
