"""Focus category in trait tags and sentences (task 14.13; Requirements 4.10, 6.4).

Tags and sentences for non-flag text attributes name the persona's FOCUS category
(``PersonaProfile.focus_categories``), not its most common one; with no focus
entry they fall back to the most common category. Flags and numerics unchanged.

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
    focus: dict[str, str] | None = None,
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
        focus_categories=focus or {},
    )


def _one(column: str, direction: str, common: str, focus: str | None):
    top = {column: [(common, 60), ("other", 30), ("rare", 10)]}
    if focus is not None:
        top[column] = [(common, 60), (focus, 30), ("rare", 10)]
    p = _profile(
        [column], {column: direction}, top, {column: focus} if focus else {}
    )
    return persona_trait_tags(p)[0], distinguishing_sentences(p, [p])


CASES = [
    ("age_band", "More aged 25-34", "Fewer aged 25-34",
     "to be in the 25-34 age band"),
    ("region", "More from Luzon", "Fewer from Luzon", "to be in the Luzon region"),
    ("segment", "More in the Mass segment", "Fewer in the Mass segment",
     "to be in the Mass customer segment"),
    ("sec_class", "More in class C1", "Fewer in class C1",
     "to be in socio-economic class C1"),
    ("inflow_type", "More Salary-led money-in", "Fewer Salary-led money-in",
     "to have Salary as their main money-in type"),
    ("online_shopper", "More High-tier online shoppers",
     "Fewer High-tier online shoppers", "to be a high online shopper"),
]
_FOCUS = {
    "age_band": "25-34", "region": "Luzon", "segment": "Mass",
    "sec_class": "C1", "inflow_type": "Salary", "online_shopper": "High",
}


@pytest.mark.parametrize("column,more,fewer,tail", CASES)
def test_tag_and_sentence_name_focus_not_most_common(column, more, fewer, tail):
    focus = _FOCUS[column]
    tag, sentence = _one(column, "more", "ZZcommon", focus)
    assert tag == more
    assert "ZZcommon" not in tag and "ZZcommon" not in sentence
    assert f"more likely {tail}" in sentence.lower() or f"More likely {tail}" in sentence
    tag_f, sentence_f = _one(column, "fewer", "ZZcommon", focus)
    assert tag_f == fewer
    assert f"ess likely {tail}" in sentence_f
    assert "ZZcommon" not in sentence_f


def test_other_text_column_tag_uses_label_and_value():
    tag, sentence = _one("investment_propensity_decile", "more", "5", "7")
    assert tag.startswith("More ") and tag.endswith(": 7")
    assert "5" not in tag
    assert "of 7" in sentence
    tag_f, _ = _one("investment_propensity_decile", "fewer", "5", "7")
    assert tag_f.startswith("Fewer ") and tag_f.endswith(": 7")


@pytest.mark.parametrize("column,more,fewer,tail", CASES)
def test_fallback_to_most_common_without_focus_entry(column, more, fewer, tail):
    common = _FOCUS[column]
    tag, sentence = _one(column, "more", common, None)
    assert tag == more
    assert tail in sentence.lower() or tail in sentence


def test_flags_and_numerics_unchanged():
    p = _profile(
        ["digital_app_user", "owns_Deposit", "total_out"],
        {"digital_app_user": "fewer", "owns_Deposit": "more", "total_out": "high"},
        {"digital_app_user": [("0", 7), ("1", 3)], "owns_Deposit": [("1", 8), ("0", 2)]},
    )
    tags = persona_trait_tags(p)
    assert tags[0] == "Fewer app users"
    assert tags[-1] == "Higher total outflows"
    s = distinguishing_sentences(p, [p]).lower()
    assert "less likely to use the mobile app" in s
    assert "more likely to own deposit account" in s
    assert "higher total outflows" in s
