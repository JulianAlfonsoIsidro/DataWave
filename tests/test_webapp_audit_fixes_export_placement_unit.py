"""Export Summary placement in the Download Leads expander (item 1.13).

**Validates: Requirements 2.13, 3.13, 3.14**
"""
from __future__ import annotations

import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _results_fn() -> ast.FunctionDef:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_render_results_tab"
    )


def _is_export_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_render_export_summary"
    )


def _download_expander(fn: ast.FunctionDef) -> ast.With:
    for node in ast.walk(fn):
        if isinstance(node, ast.With) and any(
            "pan_download_leads" in ast.dump(item.context_expr) for item in node.items
        ):
            return node
    raise AssertionError("Download Leads expander not found")


def test_export_summary_called_once_in_function():
    calls = [n for n in ast.walk(_results_fn()) if _is_export_call(n)]
    assert len(calls) == 1


def test_export_summary_directly_in_expander_body_not_in_if():
    expander = _download_expander(_results_fn())
    direct = [
        s for s in expander.body
        if isinstance(s, ast.Expr) and _is_export_call(s.value)
    ]
    assert len(direct) == 1
    for stmt in expander.body:
        if isinstance(stmt, ast.If):
            assert not any(_is_export_call(n) for n in ast.walk(stmt))


def test_no_sendable_caption_stays_above_export_summary():
    expander = _download_expander(_results_fn())
    idx_if = next(i for i, s in enumerate(expander.body) if isinstance(s, ast.If))
    idx_call = next(
        i for i, s in enumerate(expander.body)
        if isinstance(s, ast.Expr) and _is_export_call(s.value)
    )
    assert idx_if < idx_call
    assert "No sendable leads" in ast.dump(expander.body[idx_if])
