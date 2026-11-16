"""Unit tests for the Expected Joiners By Persona render helpers (spec part6 tasks 14.16, 14.18).

Covers the pure formatting helpers in ``app.persona_page``: the three-column
persona table (no rate column), the folded "Other personas" row showing only a
lead count, the total row, the group-scoped total/note, the "All groups" summary
rows, the too-few message, the Details rate lines, the takeaway, HTML escaping and
no raw column names (Requirements 7.1-7.5, 7.6a-c, 7.7, 7.8, 3.17).
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import app.persona_page as pp  # noqa: E402
import theme  # noqa: E402
from webapp_core.personas import (  # noqa: E402
    NO_GROUP_NAME,
    OTHER_PERSONAS_NAME,
    UNLABELED_NAME,
    CardGroupSummary,
    CardPersonaBreakdown,
    GroupCardBreakdown,
    GroupSummaryRow,
    PersonaJoinerRow,
)


def _breakdown(name: str = "Digital <b>Natives</b>") -> CardPersonaBreakdown:
    rows = (
        PersonaJoinerRow(name, 600, 60.0, 90.0, 15.0, "Push the <app> offer"),
        PersonaJoinerRow("Savers", 300, 30.0, 15.0, 5.0, "Same message as above."),
        PersonaJoinerRow(OTHER_PERSONAS_NAME, 60, 6.0, 3.0, 5.0, "", "other", False),
        PersonaJoinerRow(UNLABELED_NAME, 40, 4.0, 2.0, 5.0, "", "unlabeled", True),
    )
    return CardPersonaBreakdown(
        "P900", "Ready Toppers", rows, 1000, 110.0, "Takeaway & more: lead with it.",
        name, "Push the <app> offer",
    )


def _group_bd(too_few: bool = False) -> GroupCardBreakdown:
    rows = (
        PersonaJoinerRow("Savers", 80, 80.0, 24.0, 30.0, "Lead with <rewards>"),
        PersonaJoinerRow(OTHER_PERSONAS_NAME, 20, 20.0, 2.0, 10.0, "", "other", False),
    )
    return GroupCardBreakdown(
        "P900", "Ready Toppers", "25-34", rows, 100, 26.0, 110.0, 1000,
        "Savers join most.", "Savers", "Lead with <rewards>", too_few,
    )


def _summary(with_no_group: bool = True) -> CardGroupSummary:
    rows = [
        GroupSummaryRow("25-34", "25-34", 600, 60.0, 70.0),
        GroupSummaryRow("35-44", "35-44", 300, 30.0, 30.0),
    ]
    if with_no_group:
        rows.append(GroupSummaryRow(NO_GROUP_NAME, None, 100, 10.0, 10.0))
    return CardGroupSummary(
        "P900", "Ready Toppers", tuple(rows), 1000, sum(r.expected_joiners for r in rows)
    )


def test_columns_exactly_three_and_no_rate_column():
    assert pp.BREAKDOWN_COLUMNS == ["Persona", "Leads (share)", "Expected joiners"]
    for r in pp.breakdown_table_rows(_breakdown()):
        assert list(r) == pp.BREAKDOWN_COLUMNS
        assert "Rate" not in r and "Action" not in r
        assert "expected_joiners" not in r and "lead_share_pct" not in r
    # The card text now comes from the persona section (no rate column).
    assert "Rate" not in theme.persona_section_html(pp.persona_section_for(_breakdown(), "Ready Toppers"))


def test_folded_other_row_shows_only_lead_count():
    rows = pp.breakdown_table_rows(_breakdown())
    other = next(r for r in rows if r["Persona"] == OTHER_PERSONAS_NAME)
    assert other["Leads (share)"].startswith("60")
    assert other["Expected joiners"] == ""
    unl = next(r for r in rows if r["Persona"] == UNLABELED_NAME)
    assert unl["Expected joiners"] != ""


def test_unlabeled_row_only_when_present():
    b = _breakdown()
    kept = tuple(r for r in b.rows if r.kind != "unlabeled")
    b2 = CardPersonaBreakdown("P900", "X", kept, 960, 108.0, "t")
    names = [r["Persona"] for r in pp.breakdown_table_rows(b2)]
    assert UNLABELED_NAME not in names


def test_total_line_equals_card_expected_joiners():
    b = _breakdown()
    total = pp.breakdown_table_rows(b)[-1]
    assert total["Persona"] == "Total"
    assert total["Expected joiners"] == f"{b.total_expected_joiners:,.1f}"
    assert total["Leads (share)"].startswith("1,000")


def test_html_has_takeaway_escapes_and_no_actions():
    # Part 7 (7.1, 7.4, 7.7): sentence rows + "Total For" line + takeaway via persona_view.
    out = theme.persona_section_html(pp.persona_section_for(_breakdown(), "Ready Toppers"))
    assert "Expected Joiners By Persona" in out
    assert "likely to join" in out and "Leads (share)" not in out
    assert "Digital &lt;b&gt;Natives&lt;/b&gt;" in out
    assert "<b>Natives" not in out
    assert "Push the" not in out  # actions stay in the expander
    assert "Total For Ready Toppers: about 110 of 1,000 likely to join" in out
    assert "expected_joiners" not in out and "lead_share_pct" not in out


def test_empty_breakdown_shows_not_generated_line_only():
    # Part 7 (7.10): an empty breakdown gives the "personas not generated" line.
    b = CardPersonaBreakdown("P900", "Not Now", (), 0, 0.0, "No sendable leads in this card.")
    out = theme.persona_section_html(pp.persona_section_for(b, "Not Now"))
    assert "Personas were not generated for this run." in out
    assert "Total For" not in out
    assert pp.breakdown_table_rows(b) == []


def test_group_total_row_and_note_text_exact():
    # Part 7 (7.4, 7.5, 7.9): "Total For <Segment>" and no group index in any string.
    b = _group_bd()
    rows = pp.breakdown_table_rows(b)
    assert rows[-1]["Persona"] == "Total"
    assert rows[-1]["Expected joiners"] == "26.0"
    section = pp.persona_section_for(b, "Ready Toppers")
    assert section.total_line == "Total For Ready Toppers"
    out = theme.persona_section_html(section)
    assert "Total For Ready Toppers" in out
    assert "25-34" not in out and "across all groups" not in out
    assert "Savers is" in out  # note: "<top> is N of the <Segment> total"


def test_too_few_group_card_shows_not_generated_line():
    # Part 7: a too-few group card has no persona rows; it gets the "not generated" line.
    b = _group_bd(too_few=True)
    out = theme.persona_section_html(pp.persona_section_for(b, "Ready Toppers"))
    assert "Personas were not generated for this run." in out
    assert "<table" not in out and "across all groups" not in out


def test_all_groups_instruction_constant():
    assert pp.ALL_GROUPS_INSTRUCTION == "Pick a group above to see the persona detail."


def test_group_summary_rows_with_and_without_no_group_row():
    rows = pp.group_summary_rows(_summary(True))
    assert pp.SUMMARY_COLUMNS == ["Group", "Leads (share)", "Expected joiners"]
    assert all(list(r) == pp.SUMMARY_COLUMNS for r in rows)
    assert [r["Group"] for r in rows] == ["25-34", "35-44", NO_GROUP_NAME, "Total"]
    assert rows[-1]["Expected joiners"] == "110.0"
    assert rows[-1]["Leads (share)"].startswith("1,000")
    names = [r["Group"] for r in pp.group_summary_rows(_summary(False))]
    assert NO_GROUP_NAME not in names and names[-1] == "Total"
    assert "<table" in pp.group_summary_html(_summary(True))


def test_details_lines_show_rates_and_skip_folded_rows():
    lines = pp.rates_details_lines(_group_bd())
    assert lines == ["Savers: 30.0%"]
    all_lines = pp.rates_details_lines(_breakdown())
    assert all_lines[0].endswith(": 15.0%") and "Savers: 5.0%" in all_lines
    assert not any(OTHER_PERSONAS_NAME in ln for ln in all_lines)
    assert f"{UNLABELED_NAME}: 5.0%" in all_lines
