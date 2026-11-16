"""Export_Workbook builder (Part 7 Requirement 9).

Builds one .xlsx file with openpyxl from the in-memory run result, the
Impact_Summary, and the optional persona result. No Streamlit and no Bedrock:
every number comes from the arguments (Requirement 9.10). The only place
``client_id`` appears is on the Send List sheets, because the workbook is a
local file (Requirement 9.13).

Sheets: Summary, Decision Cards, Personas, and one Send List sheet per segment
whose action is not Skip and that has at least one sendable lead
(Requirements 9.3 to 9.8). Every sheet has Title Case headers, a bold header
row, ``freeze_panes = "A2"``, and column widths of 10 to 60 (Requirement 9.9).
Text cells never contain an em dash or ``--`` (Requirement 9.11).
"""

from __future__ import annotations

import math
import re
from datetime import date
from io import BytesIO
from typing import Any, Iterable, Sequence

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from webapp_core.card_view import build_card_view, round_half_up
from webapp_core.threshold import ThresholdType

SUMMARY_SHEET = "Summary"
CARDS_SHEET = "Decision Cards"
PERSONAS_SHEET = "Personas"
SKIP_ACTION = "Skip"

NO_PERSONAS_TEXT = "Personas were not generated for this run."
NOT_AVAILABLE = "Not Available"
SOURCE_DEMO = "Demo Mode"
SOURCE_BEDROCK = "Bedrock"

PERCENT_FORMAT = "0.0%"
PESO_FORMAT = '"₱"#,##0'
MIN_WIDTH = 10
MAX_WIDTH = 60
MAX_SHEET_NAME = 31

_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def workbook_filename(promo_id: str) -> str:
    """The download name ``<promo_id>_campaign_summary.xlsx`` (Requirement 9.1)."""
    return f"{promo_id}_campaign_summary.xlsx"


def _clean(value: Any) -> Any:
    """Strip em dashes and ``--`` from text cells (Requirement 9.11)."""
    if isinstance(value, str):
        text = value.replace(" \u2014 ", ", ").replace("\u2014", "-")
        text = text.replace("\u2013", "-")
        while "--" in text:
            text = text.replace("--", "-")
        return text
    return value


def _finite(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _write_sheet(
    ws: Worksheet,
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    formats: dict[int, str] | None = None,
) -> None:
    """Write a header row plus data rows, then apply the shared formatting.

    ``formats`` maps a 0-based column index to a number format applied to that
    column's data cells.
    """
    formats = formats or {}
    ws.append([_clean(h) for h in headers])
    for row in rows:
        ws.append([_clean(v) for v in row])

    bold = Font(bold=True)
    for cell in ws[1]:
        cell.font = bold
    ws.freeze_panes = "A2"

    for col_idx, fmt in formats.items():
        for row in ws.iter_rows(min_row=2, min_col=col_idx + 1, max_col=col_idx + 1):
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = fmt

    for idx in range(1, len(headers) + 1):
        longest = 0
        for cell in ws[get_column_letter(idx)]:
            if cell.value is not None:
                longest = max(longest, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(idx)].width = max(
            MIN_WIDTH, min(MAX_WIDTH, longest + 2)
        )


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = _INVALID_SHEET_CHARS.sub(" ", str(name)).strip() or "Segment"
    candidate = base[:MAX_SHEET_NAME]
    n = 2
    while candidate.lower() in used:
        suffix = f" {n}"
        candidate = base[: MAX_SHEET_NAME - len(suffix)] + suffix
        n += 1
    used.add(candidate.lower())
    return candidate


def _threshold_type_text(spec: Any) -> str:
    t = getattr(spec, "threshold_type", None)
    if t is None:
        return NOT_AVAILABLE
    try:
        return ThresholdType(t).value
    except ValueError:
        return str(t)


def _summary_rows(run, impact, narration_source: str, run_date: date):
    """Rows of ``(field, value, number_format_or_None)`` for the Summary sheet."""
    spec = run.promo_spec
    # Part 9 round 3 (Requirement 31.7): follows the name set on screen.
    ai_source = {
        SOURCE_BEDROCK: SOURCE_BEDROCK,
        "Built-in": "Built-in names",
        "Mixed": "Mixed (Bedrock and built-in names)",
    }.get(narration_source, SOURCE_DEMO)

    rows: list[tuple[str, Any, str | None]] = [
        ("Promo Id", spec.promo_id, None),
        ("Product Type", spec.product_type, None),
        ("Mechanic", spec.mechanic, None),
        ("Threshold Type", _threshold_type_text(spec), None),
        ("Threshold Php", _finite(spec.threshold_php), PESO_FORMAT),
    ]
    pct = _finite(getattr(spec, "threshold_pct", None))
    if pct is not None:
        rows.append(("Threshold Percent Of Latest Adb", pct / 100.0, PERCENT_FORMAT))
    rows += [
        ("Reward", spec.reward, None),
        ("Channels", ", ".join(spec.channels or []), None),
    ]

    if impact is not None and impact.available:
        rows.append(("Messages Saved", int(impact.messages_saved), "#,##0"))
        rows.append(("Joiners Kept", impact.joiners_kept_pct / 100.0, PERCENT_FORMAT))
        if impact.cost_available and impact.cost_saved is not None:
            rows.append(("Cost Saved", int(impact.cost_saved), PESO_FORMAT))
        else:
            rows.append(("Cost Saved", NOT_AVAILABLE, None))
    else:
        rows += [
            ("Messages Saved", NOT_AVAILABLE, None),
            ("Joiners Kept", NOT_AVAILABLE, None),
            ("Cost Saved", NOT_AVAILABLE, None),
        ]

    rows.append(("Run Date", run_date.strftime("%Y-%m-%d"), None))
    rows.append(("Ai Source", ai_source, None))
    return rows


def _write_summary(wb: Workbook, run, impact, narration_source, run_date) -> None:
    ws = wb.active
    ws.title = SUMMARY_SHEET
    rows = _summary_rows(run, impact, narration_source, run_date)
    _write_sheet(ws, ["Field", "Value"], [(f, v) for f, v, _ in rows])
    for i, (_f, _v, fmt) in enumerate(rows, start=2):
        if fmt and isinstance(ws.cell(row=i, column=2).value, (int, float)):
            ws.cell(row=i, column=2).number_format = fmt


def _write_cards(wb: Workbook, run) -> None:
    ws = wb.create_sheet(CARDS_SHEET)
    headers = [
        "Promo Id",
        "Segment",
        "Action",
        "Channel",
        "Message Angle",
        "Why This Group",
        "Not Contacted",
        "Likely To Join",
        "Likely Range Low",
        "Likely Range High",
        "Expected Value",
    ]
    rows = []
    for card in run.cards or []:
        view = build_card_view(card)
        n = round_half_up(card.get("expected_joiners", 0) or 0)
        low = min(round_half_up(card.get("joiners_90_low", 0) or 0), n)
        high = max(round_half_up(card.get("joiners_90_high", 0) or 0), n)
        rows.append(
            [
                card.get("promo_id", ""),
                card.get("segment", ""),
                view.action,
                view.channel,
                view.angle,
                "; ".join(view.drivers),
                "; ".join(view.exclusions) if view.exclusions else "None",
                n,
                low,
                high,
                round_half_up(card.get("expected_value", 0) or 0),
            ]
        )
    _write_sheet(ws, headers, rows, formats={7: "#,##0", 8: "#,##0", 9: "#,##0", 10: PESO_FORMAT})


def _likely_joiners_by_client(run) -> dict[str, float]:
    scored = getattr(run, "scored", None)
    if scored is None or len(scored) == 0 or "p_join" not in scored.columns:
        return {}
    return {
        str(cid): float(p)
        for cid, p in zip(scored["client_id"].tolist(), scored["p_join"].tolist())
        if _finite(p) is not None
    }


def _persona_rows(run, persona_result) -> list[list[Any]]:
    labels = persona_result.labels
    p_by_client = _likely_joiners_by_client(run)
    label_col = (
        "persona_label" if "persona_label" in labels.columns else "persona_name"
    )
    sums: dict[tuple[str, str], float] = {}
    if label_col in labels.columns:
        group_col = "group" if "group" in labels.columns else None
        for _i, row in labels.iterrows():
            name = row[label_col]
            if name is None or pd.isna(name) or str(name) == "":
                continue
            group = "" if group_col is None or pd.isna(row[group_col]) else str(row[group_col])
            p = p_by_client.get(str(row["client_id"]))
            if p is not None:
                key = (group, str(name))
                sums[key] = sums.get(key, 0.0) + p

    sets = [ps for ps in persona_result.persona_sets if not ps.too_small]
    multi = len(sets) > 1
    rows: list[list[Any]] = []
    for ps in sets:
        for persona in ps.personas:
            name = f"{ps.group_key}: {persona.name}" if multi and ps.group_key else persona.name
            joiners = round_half_up(sums.get((str(ps.group_key), str(persona.name)), 0.0))
            rows.append(
                [
                    name,
                    persona.description,
                    int(persona.profile.size),
                    joiners,
                    " | ".join(str(a) for a in persona.actions),
                ]
            )
    return rows


def _write_personas(wb: Workbook, run, persona_result) -> None:
    ws = wb.create_sheet(PERSONAS_SHEET)
    headers = ["Persona Name", "Description", "Size", "Likely Joiners", "Recommended Actions"]
    rows = _persona_rows(run, persona_result) if persona_result is not None else []
    if not rows:
        rows = [[NO_PERSONAS_TEXT, "", "", "", ""]]
    _write_sheet(ws, headers, rows, formats={2: "#,##0", 3: "#,##0"})


def _write_send_lists(wb: Workbook, run) -> None:
    skipped = {
        str(c.get("segment")) for c in (run.cards or []) if c.get("action") == SKIP_ACTION
    }
    used = {SUMMARY_SHEET.lower(), CARDS_SHEET.lower(), PERSONAS_SHEET.lower()}
    for segment, frame in (run.sendable_by_segment or {}).items():
        if segment in skipped or frame is None or len(frame) == 0:
            continue
        ws = wb.create_sheet(_safe_sheet_name(segment, used))
        control = frame["control"] if "control" in frame.columns else [0] * len(frame)
        rows = [
            [str(cid), ch, float(p), "Yes" if int(c) == 1 else "No"]
            for cid, ch, p, c in zip(
                frame["client_id"].tolist(),
                frame["best_channel"].tolist(),
                frame["p_join"].tolist(),
                list(control),
            )
        ]
        _write_sheet(
            ws,
            ["client_id", "Best Channel", "Join Chance", "Control Flag"],
            rows,
            formats={2: PERCENT_FORMAT},
        )


def build_workbook(
    run,
    impact,
    persona_result,
    narration_source: str,
    run_date: date,
) -> bytes:
    """Build the Export_Workbook and return its .xlsx bytes (Requirements 9.3 to 9.11).

    Args:
        run: The in-memory :class:`~webapp_core.run_promo.RunResult`.
        impact: The :class:`~webapp_core.impact.ImpactSummary` for the run.
        persona_result: The :class:`~webapp_core.personas.PersonaRunResult`, or
            ``None`` when personas were not generated.
        narration_source: ``"Bedrock"`` or ``"Demo"``/``"Demo Mode"``; anything
            other than Bedrock is written as "Demo Mode".
        run_date: The run date, written as YYYY-MM-DD.
    """
    wb = Workbook()
    _write_summary(wb, run, impact, narration_source, run_date)
    _write_cards(wb, run)
    _write_personas(wb, run, persona_result)
    _write_send_lists(wb, run)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
