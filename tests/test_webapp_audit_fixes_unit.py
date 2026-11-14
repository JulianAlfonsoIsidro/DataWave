"""Webapp audit fixes: bug condition exploration tests (task 1).

Spec ``webapp-audit-fixes``, bugfix items 1.1, 1.2, 1.3, 1.5, 1.9, 1.10,
1.12, 1.13, 1.14 and 1.15. These tests encode the EXPECTED behaviour, so they
FAIL on the unfixed code; each failure is a counterexample for its bug.
Item 1.1 uses Hypothesis against a stand-in for the old key logic; the rest
are text, ``ast`` or source scans.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import re
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webapp_core import help_content  # noqa: E402
from webapp_core import required_fields  # noqa: E402

MAIN_SRC = (REPO_ROOT / "app" / "main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SRC)
JS_SRC = (REPO_ROOT / "app" / "static" / "ui_interactions.js").read_text(encoding="utf-8")
CSS_SRC = (REPO_ROOT / "app" / "styles.css").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    out: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]):
    while node in parents:
        node = parents[node]
        yield node


def _func(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def _is_call_to(node: ast.AST, dotted: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f"{f.value.id}.{f.attr}" == dotted
    if isinstance(f, ast.Name):
        return f.id == dotted
    return False


# --------------------------------------------------------------------------
# 1.1 sign-off survives changed figures (stand-in for the old key logic)
# --------------------------------------------------------------------------
REVIEW_PREFIX = "review_ok_"


def _old_logic_after_change(state: dict, new_signature) -> dict:
    """Stand-in for the unfixed app: key is ``review_ok_<slug>`` and nothing
    ever clears it when the figures change."""
    return dict(state)


_slugs = st.sampled_from(
    ["ready_toppers", "untapped_wealth", "willing_but_stretched", "not_now", "all"]
)
_sig = st.tuples(
    st.sampled_from(["P100", "P200"]),
    st.sampled_from(["TOP_UP", "AVG_BALANCE"]),
    st.floats(min_value=1_000, max_value=2_000_000, allow_nan=False),
    st.integers(min_value=0, max_value=5),
)


@settings(deadline=None, max_examples=50)
@given(
    ticked=st.sets(_slugs, min_size=1),
    sig_a=_sig,
    sig_b=_sig,
)
def test_signoff_cleared_when_figures_change(ticked, sig_a, sig_b):
    """**Validates: Requirements 2.1** (bug condition 1.1)."""
    if sig_a == sig_b:
        return  # not the bug condition
    from webapp_core import review_signoff

    state = {f"{review_signoff.REVIEW_KEY_PREFIX}{s}": True for s in ticked}
    review_signoff.clear_stale_signoffs(state, sig_a)  # first call stores sig_a
    state.update({f"{review_signoff.REVIEW_KEY_PREFIX}{s}": True for s in ticked})
    review_signoff.clear_stale_signoffs(state, sig_b)
    after = state
    still_ticked = [k for k, v in after.items() if k.startswith(REVIEW_PREFIX) and v]
    assert not still_ticked, f"ticks survived {sig_a} -> {sig_b}: {still_ticked}"


# --------------------------------------------------------------------------
# 1.2 help text
# --------------------------------------------------------------------------
def _entry_text(entry) -> str:
    return " ".join(str(v) for v in dataclasses.astuple(entry) if v)


def test_help_text_has_no_stale_download_button():
    """**Validates: Requirements 2.2**"""
    blob = " ".join(_entry_text(e) for e in help_content.ENTRIES)
    assert "Download Recommended Leads" not in blob
    assert "line under the button" not in blob


def test_help_recommended_and_act_first_describe_real_flow():
    """**Validates: Requirements 2.2**"""
    by_id = {e.id: e for e in help_content.ENTRIES}
    for entry_id in ("recommended", "act_first"):
        text = _entry_text(by_id[entry_id])
        for phrase in ("Download Leads", "Choose Leads To Download", "Check Before You Download"):
            assert phrase in text, f"{entry_id} entry lacks {phrase!r}"


# --------------------------------------------------------------------------
# 1.3 finishing state is module-level
# --------------------------------------------------------------------------
def test_ui_effects_has_no_module_level_finish_lists():
    """**Validates: Requirements 2.3**"""
    tree = ast.parse((REPO_ROOT / "app" / "ui_effects.py").read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
    bad = [n for n in names if n in ("_FINISH_HEADLINE", "_FINISH_UID")]
    assert not bad, f"module-level shared state: {bad}"


# --------------------------------------------------------------------------
# 1.5 failed run still reruns
# --------------------------------------------------------------------------
def test_rerun_after_run_loader_is_under_if_ok():
    """**Validates: Requirements 2.5**"""
    parents = _parents(MAIN_TREE)
    ok_assigns = [
        n for n in ast.walk(MAIN_TREE)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ok" for t in n.targets)
    ]
    assert ok_assigns, "no `ok = ...` assignment found in app/main.py"
    start = ok_assigns[0].lineno
    reruns = [
        n for n in ast.walk(MAIN_TREE)
        if _is_call_to(n, "st.rerun") and start < n.lineno < start + 40
    ]
    assert reruns, "no st.rerun() after the Run Analysis loader"
    for call in reruns:
        guarded = any(
            isinstance(a, ast.If) and isinstance(a.test, ast.Name) and a.test.id == "ok"
            for a in _ancestors(call, parents)
        )
        assert guarded, f"st.rerun() at line {call.lineno} is not under `if ok`"


# --------------------------------------------------------------------------
# 1.9 eager workbook
# --------------------------------------------------------------------------
def test_export_summary_passes_callable_data():
    """**Validates: Requirements 2.9**"""
    fn = _func(MAIN_TREE, "_render_export_summary")
    data_values = []
    for node in ast.walk(fn):
        if _is_call_to(node, "st.download_button"):
            for kw in node.keywords:
                if kw.arg == "data" and not (
                    isinstance(kw.value, ast.Constant) and kw.value.value == b""
                ):
                    data_values.append(kw.value)
    assert data_values, "no st.download_button(data=...) for the workbook"
    for value in data_values:
        callable_ok = isinstance(value, ast.Lambda) or (
            isinstance(value, ast.Name) and value.id != "data"
        )
        assert callable_ok, f"data= is {ast.dump(value)}, not a lazy callable"
    # The build must not run directly in the render body.
    parents = _parents(fn)
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "_export_workbook_bytes":
            in_lazy = any(isinstance(a, (ast.Lambda, ast.FunctionDef)) for a in _ancestors(node, parents))
            assert in_lazy, "_export_workbook_bytes(result) is called eagerly"


def test_export_cache_key_does_not_use_id():
    """**Validates: Requirements 2.9**"""
    fn = _func(MAIN_TREE, "_export_workbook_bytes")
    uses_id = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name) and n.func.id == "id"]
    assert not uses_id, f"cache key uses id() at lines {[n.lineno for n in uses_id]}"


# --------------------------------------------------------------------------
# 1.10 bottom padding
# --------------------------------------------------------------------------
def test_block_container_bottom_padding_covers_help_button():
    """**Validates: Requirements 2.10**"""
    m = re.search(r"\.block-container\s*\{([^}]*)\}", CSS_SRC)
    assert m, "no .block-container rule"
    pad = re.search(r"padding-bottom:\s*([^;]+);", m.group(1))
    assert pad, "no padding-bottom in .block-container"
    value = pad.group(1)
    assert "--pan-control-h" in value and "--pan-space-5" in value, f"padding-bottom: {value}"


# --------------------------------------------------------------------------
# 1.12 Build Personas job click
# --------------------------------------------------------------------------
def test_js_has_is_job_button_used_by_click_and_settle():
    """**Validates: Requirements 2.12**"""
    assert re.search(r"function\s+isJobButton\s*\(", JS_SRC), "no isJobButton helper"
    assert "closest('[class*=\"st-key-p8_btn_\"]')" in JS_SRC or \
        'closest(\'[class*="st-key-p8_btn_"]\')' in JS_SRC, "no p8_btn_ ancestor lookup"
    assert "isJobButton(btn)" in JS_SRC, "click handler does not call isJobButton(btn)"
    assert "entry.job" in JS_SRC, "settleMs is not driven by entry.job"
    assert "isJobKey(keyOf(btn))" not in JS_SRC, "click handler relies on the nearest key only"


# --------------------------------------------------------------------------
# 1.13 Export Summary hidden with no sendable leads
# --------------------------------------------------------------------------
def test_export_summary_not_inside_else_branch():
    """**Validates: Requirements 2.13**"""
    fn = _func(MAIN_TREE, "_render_results_tab")
    parents = _parents(fn)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_render_export_summary"]
    assert len(calls) == 1, f"expected one _render_export_summary call, got {len(calls)}"
    call = calls[0]
    for anc in _ancestors(call, parents):
        if isinstance(anc, ast.With):
            break  # reached the expander body
        assert not isinstance(anc, ast.If), (
            f"_render_export_summary at line {call.lineno} is nested inside an if/else "
            f"(line {anc.lineno})"
        )


# --------------------------------------------------------------------------
# 1.14 scrim timing
# --------------------------------------------------------------------------
def test_js_scrim_uses_named_timing_constants():
    """**Validates: Requirements 2.14**"""
    assert re.search(r"JOB_NO_RUN_MS\s*=\s*1500", JS_SRC), "JOB_NO_RUN_MS missing"
    assert re.search(r"JOB_SAFETY_CAP_MS\s*=\s*15000", JS_SRC), "JOB_SAFETY_CAP_MS missing"
    m = re.search(r"function\s+watchJobClick\s*\(\)\s*\{(.*?)\n  \}", JS_SRC, re.S)
    assert m, "watchJobClick not found"
    assert not re.search(r"jobClickAt\s*>\s*3000", m.group(1)), "bare 3000 ms clear remains"


# --------------------------------------------------------------------------
# 1.15 Personas split wording
# --------------------------------------------------------------------------
def test_required_message_has_action_parameter():
    """**Validates: Requirements 2.15**"""
    params = inspect.signature(required_fields.required_message).parameters
    assert "action" in params, f"required_message parameters: {list(params)}"


def test_persona_page_passes_building_personas_action():
    """**Validates: Requirements 2.15**"""
    src = (REPO_ROOT / "app" / "persona_page.py").read_text(encoding="utf-8")
    assert 'action="building personas"' in src
