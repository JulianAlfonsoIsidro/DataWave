"""Webapp audit fixes, task 3.4 (item 1.5): a failed run does not rerun.

Source checks with ``ast`` on ``app/main.py``. Requirements 1.5, 2.5, 3.5.
"""
from __future__ import annotations

import ast
from pathlib import Path

MAIN_SRC = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
    encoding="utf-8"
)


def _run_block() -> ast.With:
    """The ``with theme.loading("analysis", ...)`` statement's enclosing If body."""
    tree = ast.parse(MAIN_SRC)
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "_render_fill_in_details":
            for node in ast.walk(fn):
                if isinstance(node, ast.If) and any(
                    isinstance(s, ast.With) and "theme.loading" in ast.unparse(s.items[0])
                    for s in node.body
                ):
                    return node
    raise AssertionError("Run Analysis block not found")


def _is_rerun(n: ast.AST) -> bool:
    return isinstance(n, ast.Expr) and ast.unparse(n.value) == "st.rerun()"


def test_rerun_only_under_if_ok():
    block = _run_block()
    ok_ifs = [
        n for n in block.body
        if isinstance(n, ast.If) and ast.unparse(n.test) == "ok" and any(map(_is_rerun, n.body))
    ]
    assert len(ok_ifs) == 1
    # No other st.rerun() directly in the block (outside the ok branch).
    assert not any(_is_rerun(n) for n in block.body)


def test_rerun_failure_path_shows_messages_once_and_pops_flash():
    block = _run_block()
    src = ast.unparse(block)
    after_ok = src.split("st.rerun()", 1)[1]
    assert "_show_messages(messages)" in after_ok
    assert "st.session_state.pop(FLASH_KEY, None)" in after_ok


def test_rerun_success_path_keeps_run_seq_and_flash():
    src = ast.unparse(_run_block())
    assert "st.session_state[FLASH_KEY] = messages" in src
    assert "run_seq" in src
    assert "loader.keep()" in src
    assert "go_to('Results')" in src
    assert "WHATIF_BASELINE_KEY" in src
