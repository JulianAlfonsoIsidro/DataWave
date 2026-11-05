"""Example-based unit tests for the Persona_Pipeline rule-based namer.

Covers the public API of ``part5_personas.naming`` — the default
:class:`RuleBasedNamer` — with small, deterministic, directly constructed
:class:`~part5_personas.profile.PersonaProfile` instances. The cases exercise:

- the name and one-line description derived from the profile
  (Requirement 4.4);
- the 2-3 recommended campaign actions, where the first action is the revised
  combined channel + offer-angle recommendation of the form
  ``"Best reached by {channel} with a {angle}"`` naming one of exactly
  "In-app"/"Email"/"SMS" (Requirement 4.5);
- the deterministic channel precedence (explicit channel-like category first,
  then ownership/validity flags, then the "Email" default) and each
  offer-angle branch (savings-bundle, rewards, cross-sell bundle, and the
  "tailored offer" fallback);
- determinism of identical profile + identical ``taken`` (Requirement 4.6);
- the deterministic disambiguation suffix path (Requirement 4.9).

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import pytest

from part5_personas.naming import (
    _DEFAULT_CHANNEL,
    _VALID_CHANNELS,
    PersonaNaming,
    RuleBasedNamer,
)
from part5_personas.profile import PersonaProfile


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _profile(
    *,
    cluster_label: int = 0,
    size: int = 100,
    pct_of_leads: float = 25.0,
    numeric_mean: dict[str, float] | None = None,
    numeric_median: dict[str, float] | None = None,
    top_categories: dict[str, list[tuple[str, int]]] | None = None,
    distinguishing: list[str] | None = None,
) -> PersonaProfile:
    """Construct a PersonaProfile with light, overridable defaults."""
    return PersonaProfile(
        cluster_label=cluster_label,
        size=size,
        pct_of_leads=pct_of_leads,
        numeric_mean=numeric_mean or {},
        numeric_median=numeric_median or {},
        top_categories=top_categories or {},
        distinguishing=distinguishing or [],
    )


# --------------------------------------------------------------------------- #
# 1. channel from an explicit channel-like categorical attribute (Req 4.5)    #
# --------------------------------------------------------------------------- #
def test_channel_from_explicit_channel_category():
    """A channel-like attr whose dominant value is a valid label wins first."""
    profile = _profile(
        distinguishing=["total_inflow", "best_channel"],
        numeric_mean={"total_inflow": 1234.0},
        top_categories={"best_channel": [("SMS", 80), ("Email", 20)]},
    )

    result = RuleBasedNamer().name(profile, taken=set())
    first_action = result["actions"][0]

    # Exact first-action string: channel from the explicit category + an angle
    # derived from the inflow distinguishing attribute.
    assert first_action == "Best reached by SMS with a savings-bundle offer"
    # The channel named is always one of the three valid domain labels.
    assert "SMS" in _VALID_CHANNELS


# --------------------------------------------------------------------------- #
# 2. channel from an ownership/validity flag (Req 4.5)                         #
# --------------------------------------------------------------------------- #
def test_channel_from_ownership_validity_flag():
    """With no channel category, a flag dominant "1" maps to its channel."""
    profile = _profile(
        # No attribute name contains "channel", so the flag precedence applies.
        distinguishing=["monthly_income"],
        numeric_mean={"monthly_income": 4200.0},
        top_categories={"digital_app_user": [("1", 90), ("0", 10)]},
    )

    result = RuleBasedNamer().name(profile, taken=set())
    first_action = result["actions"][0]

    # digital_app_user dominant "1" -> In-app (first in the flag precedence).
    assert first_action.startswith("Best reached by In-app with a ")


def test_channel_flag_precedence_prefers_digital_app_user():
    """When several flags are "1", the fixed precedence picks In-app first."""
    profile = _profile(
        distinguishing=["monthly_income"],
        numeric_mean={"monthly_income": 4200.0},
        top_categories={
            "digital_app_user": [("1", 70), ("0", 30)],
            "email_valid": [("1", 60), ("0", 40)],
            "mobile_valid": [("1", 55), ("0", 45)],
        },
    )

    result = RuleBasedNamer().name(profile, taken=set())
    assert result["actions"][0].startswith("Best reached by In-app with a ")


def test_channel_flag_off_value_does_not_select():
    """A flag whose dominant category is "0" does not select its channel."""
    profile = _profile(
        distinguishing=["monthly_income"],
        numeric_mean={"monthly_income": 4200.0},
        # digital_app_user dominant is "0" -> skipped; email_valid "1" -> Email.
        top_categories={
            "digital_app_user": [("0", 80), ("1", 20)],
            "email_valid": [("1", 90), ("0", 10)],
        },
    )

    result = RuleBasedNamer().name(profile, taken=set())
    assert result["actions"][0].startswith("Best reached by Email with a ")


# --------------------------------------------------------------------------- #
# 3. no channel signal -> default "Email" (Req 4.5)                           #
# --------------------------------------------------------------------------- #
def test_channel_defaults_to_email_without_signal():
    """A profile carrying no channel signal falls back to Email."""
    profile = _profile(
        distinguishing=["monthly_income"],
        numeric_mean={"monthly_income": 4200.0},
        top_categories={},
    )

    result = RuleBasedNamer().name(profile, taken=set())
    first_action = result["actions"][0]

    assert first_action.startswith(f"Best reached by {_DEFAULT_CHANNEL} with a ")
    assert _DEFAULT_CHANNEL == "Email"


# --------------------------------------------------------------------------- #
# 4. offer-angle branches (Req 4.5)                                           #
# --------------------------------------------------------------------------- #
def test_offer_angle_savings_bundle_from_inflow():
    """An inflow/deposit/balance distinguishing attr yields a savings bundle."""
    profile = _profile(
        distinguishing=["avg_balance"],
        numeric_mean={"avg_balance": 10_000.0},
    )
    result = RuleBasedNamer().name(profile, taken=set())
    assert result["actions"][0].endswith("with a savings-bundle offer")


def test_offer_angle_rewards_from_spend():
    """A spend distinguishing attr yields a rewards offer."""
    profile = _profile(
        distinguishing=["monthly_spend"],
        numeric_mean={"monthly_spend": 2_500.0},
    )
    result = RuleBasedNamer().name(profile, taken=set())
    assert result["actions"][0].endswith("with a rewards offer")


def test_offer_angle_cross_sell_from_unowned_flag():
    """An owns_ flag with dominant "0" (not owned) yields a cross-sell bundle.

    The flag name must not also contain an earlier-ranked signal token (the
    ``invest``/``wealth`` tokens are matched before the ``owns_`` branch), so a
    plain ``owns_card`` flag is used to isolate the cross-sell path.
    """
    profile = _profile(
        distinguishing=["owns_card"],
        top_categories={"owns_card": [("0", 85), ("1", 15)]},
    )
    result = RuleBasedNamer().name(profile, taken=set())
    assert result["actions"][0].endswith("with a cross-sell bundle offer")


def test_offer_angle_tailored_fallback():
    """A distinguishing attr matching no known signal yields a tailored offer."""
    profile = _profile(
        distinguishing=["age_band"],
        top_categories={"age_band": [("35-44", 60), ("25-34", 40)]},
    )
    result = RuleBasedNamer().name(profile, taken=set())
    assert result["actions"][0].endswith("with a tailored offer")


# --------------------------------------------------------------------------- #
# 5. name + description content for a representative profile (Req 4.4)        #
# --------------------------------------------------------------------------- #
def test_name_and_description_content():
    """Name derives from top distinguishing attrs; description cites the lead."""
    profile = _profile(
        cluster_label=1,
        pct_of_leads=32.5,
        distinguishing=["monthly_income", "owns_investment"],
        numeric_mean={"monthly_income": 4200.0},
        top_categories={"owns_investment": [("1", 70), ("0", 30)]},
    )

    result = RuleBasedNamer().name(profile, taken=set())

    # Name is built from the first two distinguishing attributes, title-cased.
    assert result["name"] == "Monthly Income & Investment Ownership Persona"

    # Description opens with the lead share and names the top distinguishing
    # trait together with its backing numeric mean.
    description = result["description"]
    assert description.startswith("32.5% of clustered leads")
    assert "monthly income" in description
    assert "avg 4200.00" in description
    assert description.endswith(".")


def test_base_name_falls_back_without_distinguishing():
    """A profile with no distinguishing attributes gets a cluster-indexed name."""
    profile = _profile(cluster_label=2, distinguishing=[])
    result = RuleBasedNamer().name(profile, taken=set())
    # Cluster label 2 -> "Persona 3" (1-based display).
    assert result["name"] == "Persona 3"


# --------------------------------------------------------------------------- #
# 6. actions length is always 2 or 3 (Req 4.5)                                #
# --------------------------------------------------------------------------- #
def test_actions_length_within_two_and_three_minimal_profile():
    """A profile with a single distinguishing attr still yields >= 2 actions."""
    profile = _profile(
        distinguishing=["monthly_spend"],
        numeric_mean={"monthly_spend": 1_000.0},
    )
    actions = RuleBasedNamer().name(profile, taken=set())["actions"]
    assert 2 <= len(actions) <= 3


def test_actions_length_within_two_and_three_rich_profile():
    """A profile with three distinguishing attrs is capped at 3 actions."""
    profile = _profile(
        distinguishing=["total_inflow", "monthly_spend", "owns_investment"],
        numeric_mean={"total_inflow": 5_000.0, "monthly_spend": 1_000.0},
        top_categories={"owns_investment": [("1", 60), ("0", 40)]},
    )
    actions = RuleBasedNamer().name(profile, taken=set())["actions"]
    assert 2 <= len(actions) <= 3
    assert len(actions) == 3


def test_actions_empty_distinguishing_still_padded_to_two():
    """Even with no distinguishing attrs, padding yields exactly 2 actions."""
    profile = _profile(distinguishing=[])
    actions = RuleBasedNamer().name(profile, taken=set())["actions"]
    assert 2 <= len(actions) <= 3
    # First is still the channel + angle recommendation (default channel).
    assert actions[0].startswith("Best reached by Email with a ")


# --------------------------------------------------------------------------- #
# 7. determinism: identical inputs yield identical output (Req 4.6)           #
# --------------------------------------------------------------------------- #
def test_determinism_identical_inputs_equal_output():
    """Naming twice with identical profile + taken returns equal results."""
    profile = _profile(
        cluster_label=1,
        pct_of_leads=18.4,
        distinguishing=["total_inflow", "owns_investment"],
        numeric_mean={"total_inflow": 7_500.0},
        top_categories={
            "owns_investment": [("1", 55), ("0", 45)],
            "best_channel": [("Email", 70), ("SMS", 30)],
        },
    )

    namer = RuleBasedNamer()
    first = namer.name(profile, taken=set())
    second = namer.name(profile, taken=set())

    assert first == second
    assert first["name"] == second["name"]
    assert first["description"] == second["description"]
    assert first["actions"] == second["actions"]


# --------------------------------------------------------------------------- #
# 8. disambiguation suffix path (Req 4.9)                                     #
# --------------------------------------------------------------------------- #
def test_disambiguation_appends_cluster_suffix_on_collision():
    """A base name already taken gets the deterministic cluster suffix."""
    profile = _profile(
        cluster_label=4,
        distinguishing=["monthly_income", "owns_investment"],
        numeric_mean={"monthly_income": 4200.0},
        top_categories={"owns_investment": [("1", 70), ("0", 30)]},
    )
    base_name = "Monthly Income & Investment Ownership Persona"

    # Base name free -> returned unchanged.
    assert RuleBasedNamer().name(profile, taken=set())["name"] == base_name

    # Base name taken -> deterministic " (cluster N)" suffix using cluster_label.
    taken = {base_name}
    result = RuleBasedNamer().name(profile, taken=taken)
    assert result["name"] == f"{base_name} (cluster 4)"


def test_disambiguation_falls_back_to_integer_suffix():
    """When base and cluster-suffixed names both collide, an integer is added."""
    profile = _profile(
        cluster_label=4,
        distinguishing=["monthly_income", "owns_investment"],
        numeric_mean={"monthly_income": 4200.0},
        top_categories={"owns_investment": [("1", 70), ("0", 30)]},
    )
    base_name = "Monthly Income & Investment Ownership Persona"

    taken = {base_name, f"{base_name} (cluster 4)"}
    result = RuleBasedNamer().name(profile, taken=taken)
    assert result["name"] == f"{base_name} (cluster 4) 2"


def test_name_matches_persona_naming_typeddict_shape():
    """The returned mapping carries exactly name/description/actions keys."""
    profile = _profile(distinguishing=["monthly_spend"], numeric_mean={"monthly_spend": 500.0})
    result = RuleBasedNamer().name(profile, taken=set())

    assert set(result.keys()) == {"name", "description", "actions"}
    assert isinstance(result["name"], str)
    assert isinstance(result["description"], str)
    assert isinstance(result["actions"], list)
    assert all(isinstance(a, str) for a in result["actions"])
