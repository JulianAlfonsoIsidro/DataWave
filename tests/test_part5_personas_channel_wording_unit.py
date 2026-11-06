"""Wording tests for the channel fallback action (task 8.1f, Requirement 4.5/4.6).

The fallback first action (no channel stands out) reads
"Reachable on every channel about equally; lead with {channel} (widest reach).
Offer angle: a {angle}." The stand-out wording and the legacy (empty
``channel_reach``) wording are unchanged.
"""

from __future__ import annotations

import re

import pytest

from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import PersonaProfile

FALLBACK_RE = re.compile(
    r"^Reachable on every channel about equally; lead with (In-app|Email|SMS) "
    r"\(widest reach\)\. Offer angle: an? .+\.$"
)


def _reach(**channels):
    names = {"In_app": "In-app", "Email": "Email", "SMS": "SMS"}
    return {
        names[k]: {"share": s, "overall": o, "n": float(n)}
        for k, (s, o, n) in channels.items()
    }


def _profile(reach=None, distinguishing=None, directions=None, label=0, top_categories=None):
    dist = ["inflow_share_payroll"] if distinguishing is None else distinguishing
    return PersonaProfile(
        cluster_label=label,
        size=100,
        pct_of_leads=25.0,
        numeric_mean={"inflow_share_payroll": 0.5},
        numeric_median={"inflow_share_payroll": 0.5},
        top_categories=top_categories or {},
        distinguishing=dist,
        distinguishing_directions=directions or {a: "high" for a in dist},
        channel_reach=reach if reach is not None else {},
    )


def _first(p):
    return RuleBasedNamer().name(p, set())["actions"][0]


def _no_stand_out(widest):
    """Reach where every gap is 0 (no stand-out) and ``widest`` has top share."""
    vals = {"In_app": 0.70, "Email": 0.70, "SMS": 0.70}
    vals[widest] = 0.72
    return _reach(**{k: (v, v, 300) for k, v in vals.items()})


@pytest.mark.parametrize(
    "key,channel", [("In_app", "In-app"), ("Email", "Email"), ("SMS", "SMS")]
)
def test_exact_fallback_text_per_channel_savings(key, channel):
    assert _first(_profile(_no_stand_out(key))) == (
        f"Reachable on every channel about equally; lead with {channel} "
        "(widest reach). Offer angle: a savings-bundle offer."
    )


def test_exact_fallback_text_tailored_offer():
    p = _profile(_no_stand_out("SMS"), distinguishing=["age_band"])
    assert _first(p) == (
        "Reachable on every channel about equally; lead with SMS "
        "(widest reach). Offer angle: a tailored offer."
    )


@pytest.mark.parametrize("dist", [["inflow_share_payroll"], ["age_band"], []])
@pytest.mark.parametrize("key", ["In_app", "Email", "SMS"])
def test_fallback_regex_and_no_double_with(dist, key):
    first = _first(_profile(_no_stand_out(key), distinguishing=dist))
    assert FALLBACK_RE.match(first)
    assert "(widest reach) with" not in first


def test_stand_out_wording_unchanged():
    p = _profile(_reach(In_app=(0.89, 0.74, 485), Email=(0.8, 0.8, 485), SMS=(0.7, 0.7, 485)))
    assert _first(p) == "Best reached by In-app with a savings-bundle offer"


def test_empty_reach_keeps_legacy_wording():
    p = _profile(top_categories={"digital_app_user": [("1", 90), ("0", 10)]})
    assert _first(p) == "Best reached by In-app with a savings-bundle offer"
    assert _first(_profile()) == "Best reached by Email with a savings-bundle offer"


def test_widest_reach_tie_order():
    e = (0.8, 0.8, 300)
    assert "lead with In-app (widest reach)." in _first(_profile(_reach(In_app=e, Email=e, SMS=e)))
    assert "lead with Email (widest reach)." in _first(
        _profile(_reach(In_app=(0.7, 0.7, 300), Email=e, SMS=e))
    )
    assert "lead with SMS (widest reach)." in _first(
        _profile(_reach(In_app=(0.7, 0.7, 300), Email=(0.7, 0.7, 300), SMS=e))
    )


def test_deterministic():
    p = _profile(_no_stand_out("Email"))
    assert RuleBasedNamer().name(p, set()) == RuleBasedNamer().name(p, set())


def test_name_identical_with_and_without_reach_and_unique():
    with_r = _profile(_no_stand_out("SMS"))
    without = _profile()
    assert RuleBasedNamer().name(with_r, set())["name"] == RuleBasedNamer().name(without, set())["name"]
    namer, taken, names = RuleBasedNamer(), set(), []
    for i in range(3):
        n = namer.name(_profile(_no_stand_out("SMS"), label=i), taken)["name"]
        taken.add(n)
        names.append(n)
    assert len(set(names)) == 3


@pytest.mark.parametrize("dist", [["inflow_share_payroll"], []])
def test_actions_length(dist):
    acts = RuleBasedNamer().name(_profile(_no_stand_out("SMS"), distinguishing=dist), set())["actions"]
    assert 2 <= len(acts) <= 3
