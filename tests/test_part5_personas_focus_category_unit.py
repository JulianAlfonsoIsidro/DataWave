"""Unit tests for the focus category by lift (task 4.7; Requirements 4.3, 4.4, 4.6).

``PersonaProfile.focus_categories`` holds, per non-flag categorical attribute, the
category where the persona is most over-represented:
``lift = persona share / group overall share`` (full group counts, not the
truncated top-3). Ties go to the persona's most common category, then the
category name; only categories with >= 10% of the persona are candidates (all are
if none qualify). Direction compares the persona's share of its focus category
with the other personas' pooled share. Flags and the distinguishing ranking are
unchanged.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from part5_personas.profile import PersonaProfile, build_profiles

COL = "age_band"


def _build(per_persona: list[dict[str, int]], col: str = COL) -> list[PersonaProfile]:
    """One persona per ``{category: count}`` mapping, single categorical column."""
    values: list[str] = []
    labels: list[int] = []
    for label, counts in enumerate(per_persona):
        for cat, n in counts.items():
            values += [cat] * n
            labels += [label] * n
    return build_profiles(pd.DataFrame({col: values}), np.array(labels), [], [col])


def test_default_keeps_hand_built_profiles_working():
    p = PersonaProfile(
        cluster_label=0, size=1, pct_of_leads=100.0, numeric_mean={},
        numeric_median={}, top_categories={}, distinguishing=[],
    )
    assert p.focus_categories == {}


def test_smaller_category_with_higher_lift_wins_over_overall_most_common():
    # Overall: A=100 (most common), B=40. Persona 0: A=50, B=30 -> most common A,
    # but lift A = .625/.714=.875, lift B = .375/.286=1.3125 -> B wins.
    p0, p1 = _build([{"A": 50, "B": 30}, {"A": 50, "B": 10}])
    assert p0.top_categories[COL][0][0] == "A"
    assert p0.focus_categories[COL] == "B"


def test_lift_uses_full_counts_not_truncated_top3():
    # Five categories; the group-wide share of E comes from persona 1 only,
    # which a truncated top-3 would hide. Persona 0: A=30,B=30,C=30,D=5,E=5.
    # Persona 1 has E=60 so E overall is large -> E lift for p0 is small.
    # D overall = 5 (only p0) -> lift D is 2x its share vs group... D is below 10%
    # of p0 (5/100) so not a candidate; A/B/C compete on lift.
    p0, p1 = _build(
        [
            {"A": 30, "B": 30, "C": 30, "D": 5, "E": 5},
            {"A": 10, "B": 20, "C": 20, "E": 60},
        ]
    )
    # overall: A=40, B=50, C=50, D=5, E=65 ; total 210
    # p0 shares .3 each; lift = .3 / (n/210): A=1.575, B=C=1.26 -> A wins
    assert p0.focus_categories[COL] == "A"


def test_tie_on_lift_goes_to_persona_most_common_then_name():
    # Persona 0 and 1 are mirror images so every lift ties at 1.0.
    p0, p1 = _build([{"x": 6, "y": 4}, {"x": 6, "y": 4}])
    assert p0.focus_categories[COL] == "x"  # most common
    # Equal counts, equal lift -> alphabetical name.
    q0, q1 = _build([{"b": 5, "a": 5}, {"b": 5, "a": 5}])
    assert q0.focus_categories[COL] == "a"


def test_tie_on_lift_prefers_larger_count_before_name():
    # p0: z=6, a=3 ; p1: z=2, a=1 -> lifts z: .667/.667, a: .333/.333 -> tie at 1.
    p0, p1 = _build([{"z": 6, "a": 3}, {"z": 2, "a": 1}])
    assert p0.focus_categories[COL] == "z"


def test_ten_percent_floor_blocks_tiny_high_lift_category():
    # Persona 0: A=95, R=5 (R is 5% < 10%). R only exists in persona 0, so its
    # lift (2x-ish) would win without the floor.
    p0, p1 = _build([{"A": 95, "R": 5}, {"A": 200}])
    assert p0.focus_categories[COL] == "A"
    # Exactly 10% qualifies.
    q0, q1 = _build([{"A": 90, "R": 10}, {"A": 200}])
    assert q0.focus_categories[COL] == "R"


def test_no_candidate_above_floor_falls_back_to_all_categories():
    # 12 equal categories -> each 1/12 < 10%, so all are candidates; ties on
    # lift and count resolve by name.
    cats = {f"c{i:02d}": 1 for i in range(12)}
    (p0,) = _build([cats])
    assert p0.focus_categories[COL] == "c00"


def test_no_baseline_single_persona_most_common_wins():
    (p0,) = _build([{"A": 5, "B": 20, "C": 10}])
    assert p0.focus_categories[COL] == "B"


def test_flag_columns_have_no_focus_category_and_direction_unchanged():
    values = [1] * 80 + [0] * 20 + [1] * 30 + [0] * 70
    labels = np.array([0] * 100 + [1] * 100)
    p0, p1 = build_profiles(pd.DataFrame({"digital_app_user": values}), labels, [], ["digital_app_user"])
    assert "digital_app_user" not in p0.focus_categories
    assert p0.distinguishing_directions["digital_app_user"] == "more"
    assert p1.distinguishing_directions["digital_app_user"] == "fewer"


def test_direction_compares_focus_category_share_with_others():
    # p0 focus is B (see first test): share .375 vs others' B share 10/60=.167.
    p0, p1 = _build([{"A": 50, "B": 30}, {"A": 50, "B": 10}])
    assert p0.focus_categories[COL] == "B"
    assert p0.distinguishing_directions[COL] == "more"
    # p1: most common A (.833) ; lift A = .833/.714=1.167 vs B .167/.286=.583 -> A.
    assert p1.focus_categories[COL] == "A"
    assert p1.distinguishing_directions[COL] == "more"  # .833 > 50/80=.625


def test_distinguishing_ranking_unchanged_and_deterministic():
    spec = [{"A": 50, "B": 30, "C": 20}, {"A": 10, "B": 60, "C": 30}, {"A": 40, "B": 40, "C": 20}]
    first = _build(spec)
    second = _build(spec)
    assert [p.focus_categories for p in first] == [p.focus_categories for p in second]
    assert [p.distinguishing for p in first] == [p.distinguishing for p in second]
    assert all(p.distinguishing == [COL] for p in first)
