"""Lazy Export Summary workbook with a stable cache key (audit item 1.9).

**Validates: Requirements 2.9**
"""
from __future__ import annotations

import ast
from pathlib import Path

from webapp_core import review_signoff

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"
TREE = ast.parse(MAIN.read_text(encoding="utf-8"))


def _fn(name: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name)


def _src(name: str) -> str:
    return ast.get_source_segment(MAIN.read_text(encoding="utf-8"), _fn(name))


def test_cache_key_uses_signatures_and_persona_generation():
    src = _src("_export_inputs")
    assert "figures_signature" in src
    assert "persona_signature" in src
    assert 'generation("personas")' in src
    assert not [n for n in ast.walk(_fn("_export_inputs"))
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "id"]


def test_download_callable_does_not_touch_session_state():
    src = _src("_render_export_summary")
    inner = ast.get_source_segment(src, next(
        n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)
        and n.name == "_build_workbook_lazily"))
    assert "session_state" not in inner
    assert 'holder["error"] = True' in inner


def test_figures_signature_changes_with_run_seq_and_threshold():
    a = review_signoff.figures_signature("P9", "TOP_UP", 530000.0, 1)
    assert a == review_signoff.figures_signature("P9", "TOP_UP", 530000.0, 1)
    assert a != review_signoff.figures_signature("P9", "TOP_UP", 530000.0, 2)
    assert a != review_signoff.figures_signature("P9", "TOP_UP", 540000.0, 1)
