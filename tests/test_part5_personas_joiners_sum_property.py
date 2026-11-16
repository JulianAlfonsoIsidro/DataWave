"""Property: persona joiner rows sum to the card's joiners (task 13.4).

**Validates: Requirements 7.1, 7.2, 7.7**
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from part5_personas.grouping import Persona, PersonaSet
from webapp_core.personas import expected_joiners_by_persona


@st.composite
def _cases(draw):
    n = draw(st.integers(min_value=0, max_value=60))
    p = draw(st.lists(st.floats(0.0, 1.0), min_size=n, max_size=n))
    groups = draw(st.lists(st.sampled_from(["", "g1", "g2"]), min_size=n, max_size=n))
    names = draw(st.lists(st.sampled_from(["A", "B", "C", None]), min_size=n, max_size=n))
    return p, groups, names


@settings(max_examples=60, deadline=None)
@given(_cases())
def test_rows_sum_to_card_totals(case):
    p, groups, names = case
    ids = [f"C{i}" for i in range(len(p))]
    sdf = pd.DataFrame({"client_id": ids, "p_join": p})
    rows = [(c, g if g else "g1", nm) for c, g, nm in zip(ids, groups, names) if nm]
    ldf = pd.DataFrame(rows, columns=["client_id", "group", "persona_label"])
    psets = [
        PersonaSet(
            group_key=g,
            personas=[Persona(n, "", [f"act {n}"], None) for n in "ABC"],  # type: ignore[arg-type]
            k_used=3,
            elbow_costs={},
        )
        for g in ("g1", "g2")
    ]
    cards = [{"promo_id": "NEW", "segment": "S", "expected_joiners": float(sum(p))}]
    (b,) = expected_joiners_by_persona(cards, {"S": sdf}, ldf, psets)
    assert sum(r.leads for r in b.rows) == len(p)
    assert b.total_expected_joiners == pytest.approx(sum(p), abs=1e-9)
    assert sum(r.expected_joiners for r in b.rows) == pytest.approx(sum(p), abs=1e-9)
