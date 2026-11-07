"""Unit tests for the Expected Joiners By Persona render helpers (spec part6 task 14.16).

Covers the pure formatting helpers in ``app.persona_page``
(``breakdown_table_rows`` / ``breakdown_html``): the "Expected joiners" column
label, the folded "Other personas" row showing only a lead count, the total line
matching the card's expected joiners, the takeaway and action text, no raw column
names, and HTML escaping (Requirements 7.1-7.5, 7.7, 7.8).
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import app.persona_page as pp  # noqa: E402
from webapp_core.personas import (  # noqa: E402
    EQUAL_TAKEAWAY,
    OTHER_PERSONAS_NAME,
    UNLABELED_NAME,
    CardPersonaBreakdown,
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
        "P900", "Ready Toppers", rows, 1000, 110.0, "Takeaway & more: lead with it."
    )


def test_column_labels_use_expected_joiners_not_joiners():
    rows = pp.breakdown_table_rows(_breakdown())
    assert pp.BREAKDOWN_COLUMNS == ["Persona", "Leads (share %)", "Expected joiners", "Rate"]
    for r in rows:
        assert "Expected joiners" in r
        assert "Joiners" not in r
        assert "expected_joiners" not in r and "lead_share_pct" not in r


def test_folded_other_row_shows_only_lead_count():
    rows = pp.breakdown_table_rows(_breakdown())
    other = next(r for r in rows if r["Persona"] == OTHER_PERSONAS_NAME)
    assert other["Leads (share %)"].startswith("60")
    assert other["Expected joiners"] == "" and other["Rate"] == ""
    unl = next(r for r in rows if r["Persona"] == UNLABELED_NAME)
    assert unl["Expected joiners"] != ""


def test_total_line_equals_card_expected_joiners():
    b = _breakdown()
    rows = pp.breakdown_table_rows(b)
    total = rows[-1]
    assert total["Persona"] == "Total"
    assert total["Expected joiners"] == f"{b.total_expected_joiners:,.1f}"
    assert total["Leads (share %)"].startswith("1,000")


def test_html_has_takeaway_actions_and_escapes():
    out = pp.breakdown_html(_breakdown())
    assert "Expected joiners" in out
    assert "Takeaway &amp; more: lead with it." in out
    assert "Push the &lt;app&gt; offer" in out
    assert "Same message as above." in out
    assert "Digital &lt;b&gt;Natives&lt;/b&gt;" in out
    assert "<b>Natives" not in out
    assert "Total" in out and "110.0" in out
    assert "expected_joiners" not in out and "lead_share_pct" not in out


def test_empty_breakdown_shows_takeaway_only():
    b = CardPersonaBreakdown("P900", "Not Now", (), 0, 0.0, "No sendable leads in this card.")
    out = pp.breakdown_html(b)
    assert "No sendable leads in this card." in out
    assert pp.breakdown_table_rows(b) == []
    assert EQUAL_TAKEAWAY not in out
