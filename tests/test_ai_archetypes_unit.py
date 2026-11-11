"""CRM-style persona archetype names (Demo Mode namer)."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from ai.archetypes import ARCHETYPES, archetype_name, people_with, trait_key  # noqa: E402
from ai.mocks import mock_persona_narration  # noqa: E402
from ai.persona_narrator import PersonaAggregate  # noqa: E402

VALS = list(ARCHETYPES.values())


def _valid(name: str | None) -> bool:
    return (bool(name) and 2 <= len(name.split()) <= 4 and len(name) <= 40
            and not any(c.isdigit() for c in name) and "_" not in name)


def test_every_single_trait_has_its_own_name():
    assert archetype_name([ARCHETYPES[("frugal_flag", "more")]], set()) == "Disciplined Saver"
    for a in VALS:
        assert _valid(archetype_name([a], set())), a


def test_every_two_trait_combination_has_a_valid_name():
    for a, b in itertools.permutations(VALS, 2):
        assert _valid(archetype_name([a, b], set())), (a, b)
    pair = [ARCHETYPES[("frugal_flag", "more")], ARCHETYPES[("digital_app_user", "more")]]
    assert archetype_name(pair, set()) == "Digital-First Saver"


def test_names_stay_unique_within_a_set_without_letters():
    traits = [ARCHETYPES[("frugal_flag", "more")], ARCHETYPES[("digital_app_user", "more")],
              ARCHETYPES[("tenure_years", "high")]]
    taken: set[str] = set()
    names = []
    for _ in range(6):
        n = archetype_name(traits, taken)
        assert _valid(n) and n.casefold() not in {t.casefold() for t in taken}
        assert "(" not in n
        names.append(n)
        taken.add(n)
    assert len(set(names)) == 6


def test_trait_keys_and_people_with():
    assert trait_key("age_band", "more", "25-34", False) == ("age_band", "25-34")
    assert trait_key("age_band", "fewer", "25-34", False) is None
    assert trait_key("digital_app_user", "high", None, True) == ("digital_app_user", "more")
    assert trait_key("total_out", "low", None, False) == ("total_out", "low")
    text = people_with([ARCHETYPES[("frugal_flag", "more")], ARCHETYPES[("digital_app_user", "more")]])
    assert text.startswith("a strong savings habit") and " and confidence using digital" in text


def test_mock_narration_uses_archetypes_and_stays_within_limits():
    agg = PersonaAggregate(size=59, share_pct=21.1, traits=(), top_categories=())
    traits = [ARCHETYPES[("frugal_flag", "more")], ARCHETYPES[("digital_app_user", "more")],
              ARCHETYPES[("investment_propensity_decile", "high")]]
    out = mock_persona_narration(agg, set(), traits)
    assert out["name"] == "Digital-First Saver"
    assert out["description"].startswith("This group is about 21% of the audience, with 59 customers.")
    assert "They are people with a strong savings habit" in out["description"]
    assert len(out["description"]) <= 300
