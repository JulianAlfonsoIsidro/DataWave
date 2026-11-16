"""Property: per-group totals plus the no-group row equal the card total (task 13.5; Requirement 7, 6b)."""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from part5_personas.grouping import Persona, PersonaSet
from webapp_core.personas import group_summary_by_card

SEG = "Ready Toppers"


@st.composite
def _scenario(draw):
    n = draw(st.integers(1, 60))
    groups = ["G1", "G2", "G3"]
    rows, labels = [], []
    for i in range(n):
        cid = f"C{i:04d}"
        p = draw(st.floats(0.0, 1.0))
        rows.append((cid, p))
        g = draw(st.sampled_from(groups + [None]))
        if g is not None:
            labels.append((cid, g, f"P-{g}"))
    return rows, labels


@settings(max_examples=60, deadline=None)
@given(_scenario())
def test_group_rows_sum_to_card(sc):
    rows, labels = sc
    sdf = pd.DataFrame(rows, columns=["client_id", "p_join"])
    ldf = pd.DataFrame(labels, columns=["client_id", "group", "persona_label"])
    psets = [
        PersonaSet(group_key=g, personas=[Persona(f"P-{g}", "", ["x"], None)], k_used=1, elbow_costs={})  # type: ignore[arg-type]
        for g in ("G1", "G2", "G3")
    ]
    cards = [{"promo_id": "NEW", "segment": SEG, "expected_joiners": float(sdf["p_join"].sum())}]
    out = group_summary_by_card(cards, {SEG: sdf}, ldf, psets)
    assert len(out) == 1
    s = out[0]
    assert sum(r.leads for r in s.rows) == len(sdf) == s.total_leads
    assert sum(r.expected_joiners for r in s.rows) == pytest.approx(cards[0]["expected_joiners"])
    assert s.total_expected_joiners == pytest.approx(cards[0]["expected_joiners"])
    assert all(r.leads > 0 for r in s.rows)
