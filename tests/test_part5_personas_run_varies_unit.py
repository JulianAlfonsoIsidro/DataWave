"""A3 diagnostic / regression: persona runs must vary with the run spec.

Pure-Python (no Streamlit UI) checks that :func:`webapp_core.personas.run_personas`
returns genuinely different personas when the run spec differs only in one
dimension at a time -- level, clustering attributes, k, or the two-step grouping
attributes -- and that the Persona_Page cache fingerprint
(:func:`app.persona_page._spec_fingerprint`) likewise differs for each pair. This
pins the fix for the reported bug where changing those controls returned the same
personas (a stale ``st.cache_data`` hit from an over-collapsed cache key).

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path`` (never hardcoded).
The app package is importable headless because ``app/persona_page.py`` keeps
``import streamlit`` inside its render functions.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.persona_page import _spec_fingerprint
from webapp_core.personas import PersonaRunSpec, run_personas

SEED = 42


def _summary(result) -> list[tuple]:
    """A comparable digest of a run: (group_key, persona name, size) tuples."""
    out: list[tuple] = []
    for ps in result.persona_sets:
        for p in ps.personas:
            out.append((ps.group_key, p.name, p.profile.size))
    return out


# Four attributes that exist in the real joined set (customer_dna + features_part2).
_ATTRS_A = ["age_band", "digital_app_user", "total_out", "inflow_share_payroll"]
_ATTRS_B = ["region", "online_shopper", "out_other_bank", "spend_share_grocery"]


def test_fingerprint_differs_per_dimension():
    """The cache fingerprint changes when any single spec dimension changes."""
    base = PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3)
    by_level = PersonaRunSpec(level="business-segment", clustering_attributes=_ATTRS_A, k=3, business_segment_field="segment")
    by_attrs = PersonaRunSpec(level="all", clustering_attributes=_ATTRS_B, k=3)
    by_k = PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=5)
    by_group = PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3, grouping_attributes=["age_band"])

    fp_base = _spec_fingerprint(base, SEED)
    assert _spec_fingerprint(by_level, SEED) != fp_base
    assert _spec_fingerprint(by_attrs, SEED) != fp_base
    assert _spec_fingerprint(by_k, SEED) != fp_base
    assert _spec_fingerprint(by_group, SEED) != fp_base


def test_run_differs_when_attributes_change():
    """Different clustering attributes -> different personas."""
    a = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3))
    b = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_B, k=3))
    assert _summary(a) != _summary(b)


def test_run_differs_when_k_changes():
    """A different k -> a different number of personas."""
    a = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3))
    b = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=5))
    n_a = sum(len(ps.personas) for ps in a.persona_sets)
    n_b = sum(len(ps.personas) for ps in b.persona_sets)
    assert n_a != n_b


def test_run_differs_when_level_changes():
    """Level all vs business-segment -> different set structure."""
    a = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3))
    b = run_personas(PersonaRunSpec(level="business-segment", clustering_attributes=_ATTRS_A, k=3, business_segment_field="segment"))
    # business-segment yields one set per segment value; all yields exactly one.
    assert len(b.persona_sets) != len(a.persona_sets) or _summary(a) != _summary(b)


def test_run_differs_when_grouping_changes():
    """Adding a two-step grouping attribute -> a different partition of personas."""
    a = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3))
    b = run_personas(PersonaRunSpec(level="all", clustering_attributes=_ATTRS_A, k=3, grouping_attributes=["age_band"]))
    assert _summary(a) != _summary(b)
