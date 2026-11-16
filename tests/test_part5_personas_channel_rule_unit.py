"""Tests for the data-driven channel suggestion (task 8.1e, Requirement 4.5).

Covers the ``channel_reach`` profile field (computed by ``build_profiles`` from an
optional ``reach_frame``), the grouping wiring, and the ``RuleBasedNamer`` rule:
a channel stands out when its gap over the group is >= 3 pp AND z >= 2; otherwise
the widest-reach channel is led with and the first action says so.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from part5_personas.config import Config
from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import CHANNEL_FLAGS, PersonaProfile, build_profiles
from webapp_core.personas import PersonaRunSpec, run_personas

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = ROOT / "outputs"

FALLBACK_PREFIX = "Reachable on every channel about equally; lead with "
BEST_PREFIX = "Best reached by "


def _reach(**channels: tuple[float, float, float]) -> dict[str, dict[str, float]]:
    """Build channel_reach from ``In_app=(share, overall, n)`` style kwargs."""
    names = {"In_app": "In-app", "Email": "Email", "SMS": "SMS"}
    return {
        names[k]: {"share": s, "overall": o, "n": float(n)}
        for k, (s, o, n) in channels.items()
    }


def _profile(reach=None, top_categories=None, distinguishing=None, directions=None):
    return PersonaProfile(
        cluster_label=0,
        size=100,
        pct_of_leads=25.0,
        numeric_mean={"total_inflow": 10.0},
        numeric_median={"total_inflow": 10.0},
        top_categories=top_categories or {},
        distinguishing=distinguishing if distinguishing is not None else ["total_inflow"],
        distinguishing_directions=directions or {"total_inflow": "high"},
        channel_reach=reach if reach is not None else {},
    )


def _first(profile: PersonaProfile) -> str:
    return RuleBasedNamer().name(profile, set())["actions"][0]


# (a) clear stand-out ------------------------------------------------------
def test_clear_in_app_stand_out():
    p = _profile(_reach(In_app=(0.89, 0.74, 485), Email=(0.80, 0.80, 485), SMS=(0.70, 0.70, 485)))
    assert _first(p) == "Best reached by In-app with a savings-bundle offer"


# (b) strongest z wins, even with smaller raw gap --------------------------
def test_highest_z_wins_over_bigger_gap():
    # In-app: gap 10pp, n=100 -> z = 0.10/sqrt(.25/100)=2.0
    # Email:  gap 6pp,  n=2000 -> z = 0.06/sqrt(.25/2000)=5.37
    p = _profile(_reach(In_app=(0.60, 0.50, 100), Email=(0.56, 0.50, 2000), SMS=(0.5, 0.5, 100)))
    assert _first(p).startswith("Best reached by Email with")


# (c) tie in z -> order ----------------------------------------------------
def test_z_tie_prefers_in_app_then_email_then_sms():
    same = (0.60, 0.50, 400)
    assert _first(_profile(_reach(In_app=same, Email=same, SMS=same))).startswith(
        "Best reached by In-app with"
    )
    assert _first(_profile(_reach(In_app=(0.5, 0.5, 400), Email=same, SMS=same))).startswith(
        "Best reached by Email with"
    )


# (d) gap >= 3pp but z < 2 -------------------------------------------------
def test_small_persona_large_gap_low_z_falls_back():
    p = _profile(_reach(In_app=(0.788, 0.74, 32), Email=(0.70, 0.70, 32), SMS=(0.60, 0.60, 32)))
    assert _first(p).startswith(FALLBACK_PREFIX)


# (e) z >= 2 but gap < 3pp -------------------------------------------------
def test_large_persona_small_gap_falls_back():
    # gap 2.5pp, n=100000 -> z huge
    p = _profile(_reach(In_app=(0.525, 0.50, 100000), Email=(0.4, 0.4, 100000), SMS=(0.3, 0.3, 100000)))
    assert _first(p).startswith(FALLBACK_PREFIX)
    assert "lead with In-app (widest reach)" in _first(p)


# (f) fallback widest reach + exact wording --------------------------------
def test_fallback_widest_reach_exact_wording():
    p = _profile(_reach(In_app=(0.70, 0.70, 300), Email=(0.71, 0.71, 300), SMS=(0.72, 0.72, 300)))
    assert _first(p) == (
        "Reachable on every channel about equally; lead with SMS (widest reach). "
        "Offer angle: a savings-bundle offer."
    )


def test_fallback_share_tie_order():
    e = (0.8, 0.8, 300)
    assert "lead with In-app (widest" in _first(_profile(_reach(In_app=e, Email=e, SMS=e)))
    assert "lead with Email (widest" in _first(
        _profile(_reach(In_app=(0.7, 0.7, 300), Email=e, SMS=e))
    )


# (g) se == 0 --------------------------------------------------------------
@pytest.mark.parametrize("overall", [0.0, 1.0])
def test_degenerate_overall_does_not_crash(overall):
    p = _profile(_reach(In_app=(overall, overall, 50), Email=(overall, overall, 50), SMS=(overall, overall, 50)))
    assert _first(p).startswith(FALLBACK_PREFIX)


# (h) empty channel_reach keeps old behaviour ------------------------------
def test_empty_reach_keeps_legacy_behaviour():
    explicit = _profile(
        distinguishing=["total_inflow", "best_channel"],
        top_categories={"best_channel": [("SMS", 80), ("Email", 20)]},
    )
    assert _first(explicit) == "Best reached by SMS with a savings-bundle offer"
    flag = _profile(top_categories={"digital_app_user": [("1", 90), ("0", 10)]})
    assert _first(flag).startswith("Best reached by In-app with")
    assert _first(_profile()).startswith("Best reached by Email with")


# (i) determinism, names unchanged ----------------------------------------
def test_deterministic_and_names_unchanged():
    reach = _reach(In_app=(0.89, 0.74, 485), Email=(0.8, 0.8, 485), SMS=(0.7, 0.7, 485))
    with_r, without_r = _profile(reach), _profile()
    a = RuleBasedNamer().name(with_r, set())
    b = RuleBasedNamer().name(with_r, set())
    c = RuleBasedNamer().name(without_r, set())
    assert a == b
    assert a["name"] == c["name"] and a["description"] == c["description"]
    assert a["actions"][1:] == c["actions"][1:]


# (j) actions length -------------------------------------------------------
@pytest.mark.parametrize(
    "p",
    [
        _profile(_reach(In_app=(0.9, 0.7, 500), Email=(0.7, 0.7, 500), SMS=(0.7, 0.7, 500))),
        _profile(_reach(In_app=(0.7, 0.7, 500)), distinguishing=[]),
        _profile(),
    ],
)
def test_actions_length(p):
    assert 2 <= len(RuleBasedNamer().name(p, set())["actions"]) <= 3


# (k) profile level --------------------------------------------------------
def test_build_profiles_channel_reach_hand_computed():
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0], "cat": list("aabbb")})
    labels = np.array([0, 0, 1, 1, 1])
    reach = pd.DataFrame(
        {
            "digital_app_user": [1, 1, 0, 1, np.nan],
            "email_valid": [1, 0, 0, 0, 0],
            "mobile_valid": [1, 1, 1, 1, 1],
        }
    )
    profs = build_profiles(frame, labels, ["x"], ["cat"], reach_frame=reach)
    assert [c for c, _ in CHANNEL_FLAGS] == ["In-app", "Email", "SMS"]
    p0, p1 = profs
    r0, r1 = p0.channel_reach, p1.channel_reach
    assert list(r0) == ["In-app", "Email", "SMS"]
    assert r0["In-app"] == {"share": 1.0, "overall": pytest.approx(0.75), "n": 2.0}
    assert r1["In-app"]["share"] == pytest.approx(0.5)  # NaN skipped
    assert r1["In-app"]["overall"] == pytest.approx(0.75)
    assert r0["Email"]["share"] == pytest.approx(0.5)
    assert r1["Email"]["share"] == 0.0
    assert r1["Email"]["overall"] == pytest.approx(0.2)
    assert r1["SMS"]["n"] == 3.0
    # flags are not clustering columns, yet reach is present
    assert "digital_app_user" not in p0.top_categories


def test_build_profiles_subset_flags_and_none():
    frame = pd.DataFrame({"x": [1.0, 2.0], "cat": ["a", "b"]})
    labels = np.array([0, 1])
    sub = pd.DataFrame({"email_valid": [1, 0]})
    p = build_profiles(frame, labels, ["x"], ["cat"], reach_frame=sub)
    assert list(p[0].channel_reach) == ["Email"]
    none = build_profiles(frame, labels, ["x"], ["cat"])
    assert all(q.channel_reach == {} for q in none)
    nocols = build_profiles(frame, labels, ["x"], ["cat"], reach_frame=pd.DataFrame({"z": [1, 2]}))
    assert all(q.channel_reach == {} for q in nocols)


# (l)/(m) real data ----------------------------------------------------------
def _cfg() -> Config:
    return Config(
        customer_dna_path=DATA_DIR / "customer_dna.csv",
        product_ownership_path=DATA_DIR / "product_ownership.csv",
        features_part2_path=OUTPUTS_DIR / "features_part2.csv",
        segments_path=OUTPUTS_DIR / "segments.csv",
        cards_path=OUTPUTS_DIR / "cards.json",
        leads_dir=OUTPUTS_DIR / "leads",
        promo_leads_path=DATA_DIR / "promo_leads.csv",
    )


def _personas(result):
    return [p for ps in result.persona_sets for p in ps.personas]


@pytest.fixture(scope="module")
def cfg():
    return _cfg()


def test_grouping_populates_reach_when_flag_not_clustered(cfg):
    spec = PersonaRunSpec(
        level="all",
        clustering_attributes=["age_band", "total_out", "inflow_share_payroll"],
        k=3,
    )
    personas = _personas(run_personas(spec, RuleBasedNamer(), cfg))
    assert personas
    for p in personas:
        assert p.profile.channel_reach, p.name
        for ch, v in p.profile.channel_reach.items():
            assert ch in ("In-app", "Email", "SMS")
            assert 0.0 <= v["share"] <= 1.0 and 0.0 <= v["overall"] <= 1.0
            assert v["n"] == p.profile.size
        first = p.actions[0]
        assert first.startswith(BEST_PREFIX) or first.startswith(FALLBACK_PREFIX)


def test_real_data_mix_of_stand_out_and_fallback_and_deterministic(cfg):
    spec = PersonaRunSpec(
        level="all",
        clustering_attributes=["age_band", "digital_app_user", "total_out", "inflow_share_payroll"],
        k=5,
    )
    r1 = run_personas(spec, RuleBasedNamer(), cfg)
    r2 = run_personas(spec, RuleBasedNamer(), cfg)
    firsts = [p.actions[0] for p in _personas(r1)]
    assert firsts == [p.actions[0] for p in _personas(r2)]
    assert any(f.startswith("Best reached by In-app") for f in firsts)
    assert any(f.startswith(FALLBACK_PREFIX) for f in firsts)
    for f in firsts:
        if f.startswith(BEST_PREFIX):
            assert f[len(BEST_PREFIX):].split(" with")[0] in ("In-app", "Email", "SMS")
        else:
            assert f[len(FALLBACK_PREFIX):].split(" (widest")[0] in ("In-app", "Email", "SMS")
    assert math.isfinite(len(firsts))
