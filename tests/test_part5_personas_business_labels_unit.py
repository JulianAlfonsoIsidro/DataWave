"""Business-label wording for RuleBasedNamer output (task 8.1h; Reqs 4.4, 4.5, 4.6, 4.9, 4.11).

No raw joined column name (underscored, or its space-separated form unless that
is also the business label) may appear in any persona name, description, or
action. Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import re

import pytest

from part5_personas.labels import attribute_label
from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import PersonaProfile

_CATEGORICAL: dict[str, tuple[str, str]] = {
    "segment": ("Mass", "Mid-Market"),
    "age_band": ("25-34", "35-44"),
    "region": ("Luzon", "NCR"),
    "sec_class": ("C1", "D"),
    "inflow_type": ("Salary", "Business"),
    "online_shopper": ("High", "Low"),
}
_FLAGS = [
    "digital_app_user", "frugal_flag", "email_valid", "mobile_valid",
    "owns_Credit Card", "owns_Deposit", "owns_Insurance", "owns_Investment", "owns_Loan",
]
_NUMERIC = [
    "tenure_years", "investment_propensity_decile", "total_out", "out_other_bank",
    "ext_outflow_ratio", "months_with_ext_transfer", "inflow_share_payroll",
    "inflow_share_remittance", "inflow_share_business_receipts",
    "spend_share_bank_transfer", "spend_share_e_commerce", "spend_share_education",
    "spend_share_fuel", "spend_share_grocery", "spend_share_health",
    "spend_share_insurance_premium", "spend_share_p2p_transfer",
    "spend_share_restaurants", "spend_share_retail", "spend_share_telco",
    "spend_share_travel", "spend_share_utilities",
]
_ALL = list(_CATEGORICAL) + _FLAGS + _NUMERIC


def _profile(column: str, direction: str, label: int = 0, extra: list[str] | None = None):
    attrs = [column] + (extra or [])
    cats: dict[str, list[tuple[str, int]]] = {}
    means: dict[str, float] = {}
    focus: dict[str, str] = {}
    dirs = {a: direction for a in attrs}
    for a in attrs:
        if a in _CATEGORICAL:
            c = _CATEGORICAL[a][0]
            cats[a] = [(c, 60), (_CATEGORICAL[a][1], 40)]
            focus[a] = c
            dirs[a] = "more" if direction in ("high", "more") else "fewer"
        elif a in _FLAGS:
            cats[a] = [("1", 70), ("0", 30)]
            dirs[a] = "more" if direction in ("high", "more") else "fewer"
        else:
            means[a] = 1210699.28 if a == "total_out" else 0.0813
            dirs[a] = "high" if direction in ("high", "more") else "low"
    return PersonaProfile(
        cluster_label=label, size=100, pct_of_leads=25.0,
        numeric_mean=means, numeric_median={}, top_categories=cats,
        distinguishing=attrs, distinguishing_directions=dirs, focus_categories=focus,
    )


def _texts(naming) -> list[str]:
    return [naming["name"], naming["description"], *naming["actions"]]


def _forbidden(column: str) -> list[str]:
    label = attribute_label(column).lower()
    forms = {column.lower(), column.lower().replace("_", " ")}
    return [f for f in forms if f != label and f not in label and (" " in f or "_" in f)]


@pytest.mark.parametrize("column", _ALL)
@pytest.mark.parametrize("direction", ["high", "low"])
def test_no_raw_column_wording(column, direction):
    extra = [c for c in ("total_out", "inflow_share_payroll") if c != column]
    naming = RuleBasedNamer().name(_profile(column, direction, extra=extra), set())
    for text in _texts(naming):
        low = text.lower()
        for col in [column, *extra]:
            for form in _forbidden(col):
                assert form not in low, f"{form!r} leaked in {text!r}"
        assert "_" not in text


@pytest.mark.parametrize("column", _ALL)
def test_every_joined_column_has_business_label(column):
    label = attribute_label(column)
    assert "_" not in label
    if len(column.split("_")) > 1 and not column.startswith("owns_"):
        assert label != column.replace("_", " ") or column in ("age_band", "sec_class")


def test_issue_samples_read_cleanly():
    r = RuleBasedNamer().name(
        _profile("total_out", "high", extra=["inflow_share_payroll"]), set()
    )
    assert "Highlight total outflows as the campaign hook" in r["actions"]
    assert "Highlight payroll income as the campaign hook" in r["actions"]
    assert "led by total outflows" in r["description"]
    assert not re.search(r"\d+\.\d{2}\b", r["description"])
    assert "1,210,699" in r["description"]


def test_share_columns_render_as_percent():
    r = RuleBasedNamer().name(_profile("inflow_share_payroll", "high"), set())
    assert "led by payroll income (avg 8%)" in r["description"]


def test_uniqueness_and_determinism_unchanged():
    namer = RuleBasedNamer()
    p0 = _profile("total_out", "high", 0, ["spend_share_fuel", "spend_share_retail"])
    p1 = _profile("total_out", "high", 1, ["spend_share_fuel", "spend_share_retail"])
    taken: set[str] = set()
    n0 = namer.name(p0, taken)
    taken.add(n0["name"])
    n1 = namer.name(p1, taken)
    assert n0["name"] != n1["name"]
    assert namer.name(p0, set()) == namer.name(p0, set())
