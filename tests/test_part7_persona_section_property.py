"""Property test for the Part 7 persona section rows.

Property 6: Persona rows account for the whole card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from webapp_core.persona_view import OTHER_PERSONAS_NAME, build_persona_section


@dataclass(frozen=True)
class _Row:
    """Stand-in with the row shape of ``webapp_core.personas.PersonaJoinerRow``."""

    name: str
    leads: int
    lead_share_pct: float
    expected_joiners: float
    rate_pct: float
    action: str
    kind: str = "persona"
    show_joiners: bool = True


@dataclass(frozen=True)
class _Breakdown:
    rows: tuple[_Row, ...]


# Joiners are multiples of 0.25 so float sums are exact.
_quarters = st.integers(min_value=0, max_value=40_000).map(lambda n: n / 4.0)


@st.composite
def _cases(draw):
    persona_specs = draw(
        st.lists(st.tuples(st.integers(0, 5_000), _quarters), min_size=1, max_size=8)
    )
    folded_leads = draw(st.one_of(st.just(0), st.integers(1, 5_000)))
    # Remainder is either exactly 0 or clearly positive (the "Other" row case).
    extra = draw(st.one_of(st.just(0.0), st.integers(1, 4_000).map(float)))
    rows = [
        _Row(f"Persona {i}", leads, 0.0, joiners, 0.0, "act")
        for i, (leads, joiners) in enumerate(persona_specs)
    ]
    if folded_leads:
        rows.append(_Row("Other personas", folded_leads, 0.0, 0.0, 0.0, "", kind="other",
                         show_joiners=False))
    total = sum(j for _, j in persona_specs) + extra
    return _Breakdown(tuple(rows)), total, extra, len(persona_specs)


@settings(max_examples=100, deadline=None)
@given(case=_cases())
def test_property_6_persona_rows_account_for_whole_card(case):
    """**Validates: Requirements 7.1, 7.2, 7.3, 7.6, 7.11**"""
    breakdown, total, extra, n_personas = case
    section = build_persona_section(breakdown, total, "Ready Toppers")

    assert section.unavailable_text is None
    assert section.total_line == "Total For Ready Toppers"

    # Other Personas appears only when the remainder is greater than 0.
    others = [l for l in section.lines if l.text.startswith(OTHER_PERSONAS_NAME)]
    assert len(others) == (1 if extra > 0 else 0)
    assert len(section.lines) == n_personas + len(others)

    for line in section.lines:
        assert 0.0 <= line.bar_pct <= 100.0
        match = re.search(r"\((\d+)%\)", line.text)
        if "no leads in this group" in line.text:
            assert match is None
            assert line.bar_pct == 0.0
        else:
            assert match is not None
            pct = int(match.group(1))
            assert 0 <= pct <= 100
            assert line.bar_pct == float(pct)

    # Rows (including Other Personas) account for the card total within 0.5.
    assert abs(sum(l.joiners for l in section.lines) - total) <= 0.5
