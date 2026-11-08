"""UI text rule test for Part 7 (task 17.1).

No user-visible Part 7 string may contain an em dash (U+2014) or the sequence
``--``. The test scans string constants (via ``ast``) of the new Part 7 modules
and the rendered text of a few outputs.

Exclusions (documented per the task):
- Docstrings and comments (comments never reach the AST).
- CSS custom property names (``--pan-*``) are removed before checking.
- CLI flags and code identifiers: none of the Part 7 modules define any.
- ``app/theme.py`` and ``app/main.py`` also hold pre-Part-7 code. They are
  scanned and any hit is reported, so a pre-Part-7 hit would need to be added to
  ``LEGACY_ALLOWED`` below.
- CSS class names such as ``pan-tile-k--spaced`` are removed like ``--pan-*``.
- Test fixtures that deliberately contain these characters (the export tests
  feed an em dash in on purpose to prove the workbook cleans it) are not
  scanned; only the module sources and rendered output are.

Validates: Requirements 10.9, 9.11
"""
from __future__ import annotations

import ast
import re
import sys
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import theme  # noqa: E402
from webapp_core.card_view import build_card_view  # noqa: E402
from webapp_core.export_workbook import build_workbook  # noqa: E402
from webapp_core.impact import compute_impact  # noqa: E402
from webapp_core.persona_view import build_persona_section  # noqa: E402
from webapp_core.personas import GroupCardBreakdown, PersonaJoinerRow  # noqa: E402

EM_DASH = "\u2014"
# CSS custom properties (--pan-*) and BEM class names (pan-*--modifier).
CSS_VAR = re.compile(r"(?:--)?pan-[A-Za-z0-9_-]*")

SCANNED = (
    [ROOT / "src" / "labels.py"]
    + sorted((ROOT / "src" / "ai").glob("*.py"))
    + [
        ROOT / "src" / "webapp_core" / f"{name}.py"
        for name in (
            "card_view",
            "threshold",
            "persona_view",
            "impact",
            "export_workbook",
            "similarity",
            "past_campaigns",
        )
    ]
    + [
        ROOT / "app" / f"{name}.py"
        for name in ("upload_panel", "assistant_page", "past_promos_page", "theme", "main")
    ]
)

# Pre-Part-7 strings allowed to contain the characters: {relative path: {strings}}.
# - export_workbook._clean: the em dash and "--" literals are the characters it
#   strips from cells; they are never displayed.
# - main.py: the pre-Part-7 "--" placeholder of the header stat tile (it exists
#   at HEAD before Part 7 and is outside this task's scope).
LEGACY_ALLOWED: dict[str, set[str]] = {
    "src/webapp_core/export_workbook.py": {" \u2014 ", "\u2014", "--"},
    "app/main.py": {"--"},
    # theme._kind_class builds BEM modifier class names (f" {prefix}--{kind}").
    "app/theme.py": {"--"},
}


def _violates(text: str) -> bool:
    return EM_DASH in text or "--" in CSS_VAR.sub("", text)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _violations(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree)
    allowed = LEGACY_ALLOWED.get(path.relative_to(ROOT).as_posix(), set())
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
            and node.value not in allowed
            and _violates(node.value)
        ):
            found.append((node.lineno, node.value[:80]))
    return found


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_module_string_constants_have_no_em_dash_or_double_hyphen(path: Path):
    assert path.exists(), f"Part 7 module missing: {path}"
    assert _violations(path) == []


def _card() -> dict:
    return {
        "promo_id": "NEW-001",
        "segment": "Untapped Wealth",
        "action": "Send",
        "dominant_channel": "Email",
        "message_angle": "Savings boost",
        "top_drivers": ["latest_adb", "digital_app_user"],
        "excluded_by_reason": {"ndb": 3},
        "expected_joiners": 10.5,
        "joiners_90_low": 4.2,
        "joiners_90_high": 20.7,
        "expected_value": 12345.5,
    }


def _breakdown() -> GroupCardBreakdown:
    def row(name, leads, joiners):
        return PersonaJoinerRow(name, leads, leads / 10.0, joiners, joiners / leads * 100.0, "")

    return GroupCardBreakdown(
        "P900", "Ready Toppers", "25-34",
        (row("Savers", 80, 24.0), row("Spenders", 20, 2.0)),
        100, 0.0, 0.0, 1000, "", None, "", False,
    )


def _frame(rows):
    data = []
    for channel, p, n in rows:
        data += [{"client_id": f"C{len(data)}", "best_channel": channel, "p_join": p}] * n
    return pd.DataFrame(data, columns=["client_id", "best_channel", "p_join"])


def _impact_run():
    a = _frame([("In-app", 0.5, 4)])
    b = _frame([("Email", 0.2, 3), ("SMS", 0.1, 3)])
    return SimpleNamespace(
        non_excluded=pd.concat([a, b], ignore_index=True),
        sendable_by_segment={"A": a, "B": b},
        cards=[{"segment": "A", "action": "Send"}, {"segment": "B", "action": "Skip"}],
    )


COSTS = {"In-app": 1.0, "Email": 2.0, "SMS": 5.0}


def test_card_view_output_is_clean():
    view = build_card_view(_card())
    texts = [view.title, view.action, view.channel, view.angle, view.why_heading,
             view.not_contacted_heading, *view.drivers, *view.exclusions]
    for stat in view.stats:
        texts += [stat.label, stat.tooltip]
    assert texts and not [t for t in texts if _violates(t)]


def test_card_body_and_persona_section_html_are_clean():
    section = build_persona_section(_breakdown(), 26.0, "Ready Toppers")
    html_out = theme.persona_section_html(section)
    assert "Expected Joiners By Persona" in html_out
    assert not _violates(re.sub(r"<[^>]*>", "", html_out))
    unavailable = theme.persona_section_html(build_persona_section(None, 0.0, "Ready Toppers"))
    assert not _violates(re.sub(r"<[^>]*>", "", unavailable))
    body = theme.decision_card_body_html(build_card_view(_card()))
    assert not _violates(re.sub(r"<[^>]*>", "", body))


def test_impact_banner_and_messages_are_clean():
    available = compute_impact(_impact_run(), COSTS)
    assert available.banner
    empty = compute_impact(
        SimpleNamespace(non_excluded=_frame([]), sendable_by_segment={}, cards=[]), COSTS
    )
    no_cost = compute_impact(_impact_run(), None)
    for summary in (available, empty, no_cost):
        for text in (summary.banner, summary.neutral_message, summary.cost_message):
            assert text is None or not _violates(text)


def test_workbook_cells_are_clean_even_with_dirty_inputs():
    """Workbook text cells carry no em dash or ``--`` (Requirement 9.11)."""
    card = _card() | {"segment": "Ready Toppers", "message_angle": f"Reward {EM_DASH} earn -- today"}
    spec = SimpleNamespace(
        promo_id="P900", product_type="Savings", mechanic="Cash Reward",
        threshold_type="Top-Up Amount", threshold_php=5000.0, threshold_pct=None,
        reward=f"Bonus {EM_DASH} 500", channels=["Email", "SMS"],
    )
    sent = pd.DataFrame(
        {"client_id": ["C1", "C2"], "best_channel": ["Email"] * 2, "p_join": [0.5] * 2,
         "control": [0, 1]}
    )
    run = SimpleNamespace(
        promo_spec=spec, cards=[card], sendable_by_segment={"Ready Toppers": sent}, scored=sent
    )
    impact = SimpleNamespace(
        available=True, messages_saved=100, joiners_kept_pct=95.0, cost_available=True,
        cost_saved=2500,
    )
    wb = load_workbook(BytesIO(build_workbook(run, impact, None, "Demo", date(2024, 5, 1))))
    texts = [
        c.value for ws in wb.worksheets for row in ws.iter_rows() for c in row
        if isinstance(c.value, str)
    ]
    assert texts
    assert not [t for t in texts if _violates(t)]
