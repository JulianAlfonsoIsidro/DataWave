"""Unit tests for the Expected Joiners By Persona view (Part 7 task 12.4).

Covers wording, the total row, the note, takeaway ties and the all-zero case,
the "personas not generated" line and the absence of any group index
(Requirements 7.4, 7.5, 7.7, 7.8, 7.9, 4.10).
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import theme  # noqa: E402
from webapp_core.persona_view import (  # noqa: E402
    NO_STAND_OUT_TAKEAWAY,
    OTHER_PERSONAS_NAME,
    UNAVAILABLE_TEXT,
    build_persona_section,
)
from webapp_core.personas import GroupCardBreakdown, PersonaJoinerRow  # noqa: E402

SEG = "Ready Toppers"


def _bd(rows, group_key=None):
    return GroupCardBreakdown(
        "P900", SEG, group_key or "25-34", tuple(rows), 100, 0.0, 0.0, 1000,
        "", None, "", False,
    )


def _row(name, leads, joiners):
    share = leads / 10.0
    rate = joiners / leads * 100.0 if leads else 0.0
    return PersonaJoinerRow(name, leads, share, joiners, rate, "")


def test_sentence_row_wording_and_zero_lead_row():
    sec = build_persona_section(_bd([_row("Savers", 80, 24.0), _row("Ghosts", 0, 0.0)]), 24.0, SEG)
    assert sec.lines[0].text == "Savers: about 24 of 80 likely to join (30%)"
    assert sec.lines[1].text == "Ghosts: no leads in this group"
    assert sec.lines[1].bar_pct == 0.0


def test_total_row_and_note():
    sec = build_persona_section(_bd([_row("Savers", 80, 24.0), _row("Spenders", 20, 2.0)]), 26.0, SEG)
    assert sec.total_line == f"Total For {SEG}"
    out = theme.persona_section_html(sec)
    assert f"Total For {SEG}: about 26 of 100 likely to join" in out
    assert sec.note == f"Savers is 24 of the {SEG} total"
    assert sec.takeaway == "Most likely joiners are in Savers; lead the message with them."


def test_other_personas_only_when_remainder_positive():
    rows = [_row("Savers", 80, 24.0)]
    assert [l.text.split(":")[0] for l in build_persona_section(_bd(rows), 24.0, SEG).lines] == ["Savers"]
    names = [l.text.split(":")[0] for l in build_persona_section(_bd(rows), 30.0, SEG).lines]
    assert names == ["Savers", OTHER_PERSONAS_NAME]


def test_takeaway_tie_picks_first_in_order():
    sec = build_persona_section(_bd([_row("Alpha", 50, 10.0), _row("Beta", 50, 10.0)]), 20.0, SEG)
    assert "Alpha" in sec.takeaway and "Beta" not in sec.takeaway
    assert sec.note.startswith("Alpha is 10")


def test_all_zero_joiners_gives_no_stand_out_takeaway():
    sec = build_persona_section(_bd([_row("Alpha", 50, 0.0), _row("Beta", 50, 0.0)]), 0.0, SEG)
    assert sec.takeaway == NO_STAND_OUT_TAKEAWAY
    assert sec.note == ""
    assert OTHER_PERSONAS_NAME not in [l.text.split(":")[0] for l in sec.lines]


def test_missing_persona_data_shows_not_generated_line():
    for bd in (None, _bd([])):
        sec = build_persona_section(bd, 10.0, SEG)
        assert sec.unavailable_text == UNAVAILABLE_TEXT
        assert sec.lines == ()
        out = theme.persona_section_html(sec)
        assert UNAVAILABLE_TEXT in out and "likely to join" not in out


def test_no_group_index_in_any_string():
    sec = build_persona_section(_bd([_row("Savers", 80, 24.0)], group_key="25-34"), 24.0, SEG)
    strings = [l.text for l in sec.lines] + [sec.total_line, sec.note, sec.takeaway]
    strings.append(theme.persona_section_html(sec))
    assert not any("25-34" in s or "across all groups" in s for s in strings)
