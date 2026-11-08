"""Unit tests for the Export_Workbook builder (Part 7 task 14.2).

Validates: Requirements 9.4, 9.7, 9.8, 9.9, 9.11, 10.8.
"""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
from openpyxl import load_workbook

from webapp_core.export_workbook import (
    NO_PERSONAS_TEXT,
    build_workbook,
    workbook_filename,
)

LONG_SEGMENT = "A Very Long Segment Name That Exceeds Thirty One Characters"


def _card(segment: str, action: str = "Send") -> dict:
    return {
        "promo_id": "P900",
        "segment": segment,
        "action": action,
        "dominant_channel": "Email",
        "message_angle": "Reward \u2014 earn more -- today",
        "top_drivers": ["out_other_bank", "ext_outflow_ratio"],
        "excluded_by_reason": {"ndb": 3, "over_contacted": 2},
        "expected_joiners": 10.5,
        "joiners_90_low": 5,
        "joiners_90_high": 15,
        "expected_value": 12345,
    }


def _frame(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "client_id": [f"C{i:04d}" for i in range(n)],
            "best_channel": ["Email"] * n,
            "p_join": [0.5] * n,
            "control": [i % 2 for i in range(n)],
        }
    )


def _run():
    spec = SimpleNamespace(
        promo_id="P900",
        product_type="Savings",
        mechanic="Cash Reward",
        threshold_type="Top-Up Amount",
        threshold_php=5000.0,
        threshold_pct=None,
        reward="Bonus \u2014 500",
        channels=["Email", "SMS"],
    )
    return SimpleNamespace(
        promo_spec=spec,
        cards=[
            _card("Ready Toppers"),
            _card(LONG_SEGMENT),
            _card("Not Now", action="Skip"),
            _card("Untapped Wealth"),
        ],
        sendable_by_segment={
            "Ready Toppers": _frame(3),
            LONG_SEGMENT: _frame(2),
            "Not Now": _frame(4),  # Skip action: no sheet
            "Untapped Wealth": _frame(0),  # empty: no sheet
        },
        scored=_frame(5),
    )


def _impact():
    return SimpleNamespace(
        available=True,
        messages_saved=100,
        joiners_kept_pct=95.0,
        cost_available=True,
        cost_saved=2500,
    )


def _open(persona_result=None):
    data = build_workbook(_run(), _impact(), persona_result, "Demo", date(2024, 5, 1))
    return load_workbook(BytesIO(data))


def _send_list_sheets(wb):
    return [ws for ws in wb.worksheets if ws["A1"].value == "client_id"]


def test_filename():
    assert workbook_filename("P900") == "P900_campaign_summary.xlsx"


def test_opens_and_required_sheets_present():
    wb = _open()
    for name in ("Summary", "Decision Cards", "Personas"):
        assert name in wb.sheetnames


def test_skip_and_empty_segments_have_no_send_list():
    wb = _open()
    names = wb.sheetnames
    assert "Not Now" not in names
    assert "Untapped Wealth" not in names
    assert "Ready Toppers" in names
    assert len(_send_list_sheets(wb)) == 2


def test_bold_header_and_freeze_panes_on_every_sheet():
    wb = _open()
    for ws in wb.worksheets:
        assert ws.freeze_panes == "A2", ws.title
        for cell in ws[1]:
            assert cell.font.bold, (ws.title, cell.coordinate)


def test_sheet_name_length_and_column_widths():
    wb = _open()
    for ws in wb.worksheets:
        assert len(ws.title) <= 31
        for idx in range(1, ws.max_column + 1):
            letter = ws.cell(row=1, column=idx).column_letter
            assert 10 <= ws.column_dimensions[letter].width <= 60, (ws.title, letter)


def test_no_raw_codes_or_client_id_outside_send_lists():
    wb = _open()
    send = {ws.title for ws in _send_list_sheets(wb)}
    for ws in wb.worksheets:
        if ws.title in send:
            continue
        for row in ws.iter_rows(values_only=True):
            for value in row:
                if isinstance(value, str):
                    assert "_" not in value, (ws.title, value)
                    assert "client_id" not in value.lower(), (ws.title, value)
                    assert not re.search(r"\bC\d{4}\b", value), (ws.title, value)


def test_no_em_dash_or_double_hyphen_anywhere():
    wb = _open()
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for value in row:
                if isinstance(value, str):
                    assert "\u2014" not in value, (ws.title, value)
                    assert "--" not in value, (ws.title, value)


def test_personas_not_generated_single_row():
    ws = _open(None)["Personas"]
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) == 2  # header plus one row
    assert rows[1][0] == NO_PERSONAS_TEXT
