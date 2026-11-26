"""Webapp audit fixes: preservation tests (task 2).

Spec ``webapp-audit-fixes``, bugfix 3.1 to 3.6, 3.8, 3.10 to 3.15. These pin
behaviour observed on the UNFIXED code, so they PASS now and must still pass
after the fixes. The sign-off part runs against a small local helper that
follows the design contract of ``review_signoff.clear_stale_signoffs``.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from part4_cards import config as p4cfg  # noqa: E402
from webapp_core import help_content  # noqa: E402
from webapp_core.export_workbook import workbook_filename  # noqa: E402
from webapp_core.fairness import CAUTION_FACTOR, forecast_caution, historical_join_rate  # noqa: E402
from webapp_core.required_fields import required_message  # noqa: E402

MAIN_SRC = (REPO_ROOT / "app" / "main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SRC)
JS_SRC = (REPO_ROOT / "app" / "static" / "ui_interactions.js").read_text(encoding="utf-8")
FX_SRC = (REPO_ROOT / "app" / "ui_effects.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 3.1 / 3.2 same figures keep ticks (local stand-in for review_signoff)
# --------------------------------------------------------------------------
from webapp_core.review_signoff import (  # noqa: E402
    REVIEW_KEY_PREFIX as PREFIX,
    SIGNATURE_STATE_KEY as SIG_KEY,
    clear_stale_signoffs as _clear_stale,
)


_slugs = st.sampled_from(["ready_toppers", "untapped_wealth", "willing_but_stretched",
                          "not_now", "all_recommended"])
_sigs = st.tuples(st.text(max_size=6), st.sampled_from(["ABSOLUTE", "PERCENTILE"]),
                  st.floats(0, 1e7, allow_nan=False), st.integers(0, 50))


@settings(deadline=None, max_examples=60)
@given(ticks=st.dictionaries(_slugs, st.booleans()), sig=_sigs, repeats=st.integers(1, 5))
def test_unchanged_signature_keeps_every_tick(ticks, sig, repeats):
    """Validates: Requirements 3.1, 3.2"""
    state = {PREFIX + k: v for k, v in ticks.items()}
    state["unrelated"] = True
    _clear_stale(state, sig)  # first draw stores the signature
    expected = dict(state)
    for _ in range(repeats):
        assert _clear_stale(state, sig) is False
        assert state == expected
    for k, v in ticks.items():
        assert state[PREFIX + k] == v           # one tick never unlocks another
        assert not (v is False and state[PREFIX + k])


def test_sign_off_keys_and_checkbox_key_present_in_main():
    """Validates: Requirements 3.1, 3.13"""
    assert 'key=f"review_ok_{slug}"' in MAIN_SRC
    assert 'key="export_summary"' in MAIN_SRC
    assert 'key="export_summary_disabled"' in MAIN_SRC
    assert 'key=f"download_leads_{choice}"' in MAIN_SRC


# --------------------------------------------------------------------------
# 3.2 / 3.8 / 3.13 / 3.14 file names and download keys
# --------------------------------------------------------------------------
@given(promo=st.text(alphabet="PQR0123456789", min_size=1, max_size=8))
def test_workbook_filename_is_stable(promo):
    """Validates: Requirements 3.8, 3.14"""
    assert workbook_filename(promo) == f"{promo}_campaign_summary.xlsx"


def test_lead_file_name_helper_unchanged():
    """Validates: Requirements 3.2, 3.13"""
    fn = next(n for n in ast.walk(MAIN_TREE)
              if isinstance(n, ast.FunctionDef) and n.name == "_leads_file_name")
    src = ast.get_source_segment(MAIN_SRC, fn)
    assert "result.promo_spec.promo_id" in src
    assert "_threshold_slug(result)" in src
    assert 'segment_label.replace(\' \', \'_\').lower()' in src
    assert '_leads.csv' in src
    assert 'file_name=_leads_file_name(result, choice)' in MAIN_SRC
    assert 'mime="text/csv"' in MAIN_SRC


def test_export_workbook_mime_and_file_name_wiring():
    """Validates: Requirements 3.8, 3.14"""
    assert "file_name=workbook_filename(result.promo_spec.promo_id)" in MAIN_SRC
    assert "spreadsheetml.sheet" in MAIN_SRC


# --------------------------------------------------------------------------
# 3.3 finishing state: one session, write then read
# --------------------------------------------------------------------------
def test_finishing_sequence_logic_kept():
    """Validates: Requirement 3.3"""
    assert 'int(_state().get("p8_fin_seq", 0)) + 1' in FX_SRC
    assert '_state()["p8_fin_seq"] = seq' in FX_SRC
    assert 'record.get("headline")' in FX_SRC


# --------------------------------------------------------------------------
# 3.4 untouched help entries, formulas
# --------------------------------------------------------------------------
_REWRITTEN = {"recommended", "act_first"}
_FROZEN_QUESTIONS = {
    "sendable": "On the [[Results]] tab, why are the sendable leads fewer than the total clients in each segment?",
    "expected_joiners": "What does the Expected Joiners number at the top of [[Results]] and on the [[Results Grid]] actually mean?",
    "forecasted": "On the [[Results Grid]], why does Expected Joiners show a whole number like 87 and then (Forecasted: 87.3) beside it?",
    "totals": "In the [[What-If]] table, why don't the Expected Joiners rows add up exactly to the total?",
    "percentage": "What does the percentage under Expected Joiners at the top of [[Results]] mean?",
    "control": "What is the Control Group in the [[Download Leads]] rows, and why are some leads held back?",
    "not_contacted": "Who falls under Not Contacted on the [[Results]] tab, and why are they left out?",
    "threshold": "What does the threshold on the [[New Promo]] form do, and what changes when I move the [[What-If]] slider?",
    "whatif_mismatch": "Why does the [[New Promo]] form still show my old threshold after I changed it in [[What-If]]?",
    "likely_range": "What does the Likely Range on each [[Decision Card]] tell me?",
    "expected_value": "How is the Expected Value on each [[Decision Card]] calculated?",
    "impact": "What do Messages Saved, Joiners Kept and Cost Saved under the [[Results Grid]] mean?",
    "personas": "On the [[Personas]] tab, how are personas built, and why do the lead counts change with the grouping I pick?",
    "demo_mode": "Why do I see a [[Demo Mode]] badge in [[Ask Assistant]] or on the persona cards?",
    "page_lock": "Why does the page lock while [[Run Analysis]] or [[Build Personas]] is loading?",
    "ai_does": "What does the AI do in this app, and what does it never do?",
    "ai_why": "Why use AI here instead of only built-in rules?",
    "ai_privacy": "What data is sent to the AI, and how is it protected?",
    "ai_check_persona": "How do I check a persona name from Bedrock?",
    "ai_tokens": "How many tokens does the AI use?",
}


def test_untouched_help_entries_keep_id_and_question():
    """Validates: Requirement 3.4"""
    by_id = {e.id: e for e in help_content.ENTRIES}
    assert set(by_id) == set(_FROZEN_QUESTIONS) | _REWRITTEN
    for eid, q in _FROZEN_QUESTIONS.items():
        assert by_id[eid].question == q


def test_help_formulas_and_config_figures_unchanged():
    """Validates: Requirement 3.4"""
    names = [f.name for f in help_content.FORMULAS]
    assert names == ["Clients", "Expected Joiners", "Share Of Sendable Leads", "Likely Range (90%)",
                     "Expected Value", "Joiners Kept", "Similarity Score", "Gap"]
    eq = {f.name: f.equation for f in help_content.FORMULAS}
    assert f"{p4cfg.VALUE_PER_JOIN_PHP:,}" in eq["Expected Value"]
    assert "1.645" in eq["Likely Range (90%)"]
    assert eq["Clients"] == "Clients = Not Contacted + Control Group + Sendable"
    assert [n for n, _ in help_content.NEXT_STEPS] == ["Results", "What-If", "Personas"]
    assert p4cfg.CONTROL_FRACTION == 0.1


# --------------------------------------------------------------------------
# 3.6 forecast caution
# --------------------------------------------------------------------------
@settings(deadline=None, max_examples=80)
@given(forecast=st.floats(0, 5000, allow_nan=False), sendable=st.integers(0, 3000),
       hist=st.one_of(st.none(), st.floats(0, 1, allow_nan=False)))
def test_forecast_caution_matches_reference(forecast, sendable, hist):
    """Validates: Requirement 3.6"""
    got = forecast_caution(forecast, sendable, hist)
    if not sendable or hist is None or hist <= 0 or forecast / sendable < hist * CAUTION_FACTOR:
        assert got is None
    else:
        rate = forecast / sendable
        assert got == (
            f"This run expects {rate * 100:.1f}% of sendable leads to join, more than "
            f"{CAUTION_FACTOR:g} times the {hist * 100:.1f}% that joined past promos. "
            "Treat the forecast with care."
        )


def test_historical_join_rate_examples():
    """Validates: Requirement 3.6"""
    import pandas as pd

    df = pd.DataFrame({"control_group": [0, 0, 1, 0], "joined": [1, 0, 1, 0]})
    assert abs(historical_join_rate(df) - 1 / 3) < 1e-12
    assert historical_join_rate(pd.DataFrame({"x": [1]})) is None
    assert historical_join_rate(pd.DataFrame({"control_group": [1], "joined": [1]})) is None
    assert CAUTION_FACTOR == 2.0


# --------------------------------------------------------------------------
# 3.11 / 3.12 ui_interactions.js job clicks
# --------------------------------------------------------------------------
def _settle_body() -> str:
    m = re.search(r"function settleMs\([^)]*\)\s*\{(.*?)\n  \}", JS_SRC, re.S)
    assert m, "settleMs not found"
    return m.group(1)


def test_job_keys_and_click_handler_kept():
    """Validates: Requirements 3.11, 3.12"""
    assert re.search(r'JOB_KEYS\s*=\s*\[[^\]]*"st-key-p8_btn_"[^\]]*"st-key-persona_suggest"', JS_SRC)
    assert 'setAttribute("data-p9-job-click", "")' in JS_SRC
    assert 'addEventListener("p9-job-handoff", clearJobClick)' in JS_SRC
    assert 'removeAttribute("data-p9-job-click")' in JS_SRC


def test_settle_ms_300_default_and_finish_sum():
    """Validates: Requirements 3.11, 3.12"""
    body = _settle_body()
    assert "return 300;" in body
    assert 'tokenMs("--pan-dur-finish"' in body
    assert 'tokenMs("--pan-dur-hold"' in body
    assert 'tokenMs("--pan-dur-finish-linger"' in body
    assert body.count("300 +") == 1


def test_use_suggestion_is_not_a_job_key():
    """Validates: Requirement 3.12"""
    for key in re.search(r"JOB_KEYS\s*=\s*\[([^\]]*)\]", JS_SRC).group(1).split(","):
        key = key.strip().strip('"')
        assert not "st-key-persona_use_suggestion".startswith(key)


# --------------------------------------------------------------------------
# 3.15 New Promo required message
# --------------------------------------------------------------------------
@settings(deadline=None, max_examples=80)
@given(names=st.lists(st.text(alphabet="ABCdef gh", min_size=1, max_size=12), max_size=5))
def test_required_message_default_text_unchanged(names):
    """Validates: Requirement 3.15"""
    got = required_message(names)
    if not names:
        assert got == ""
        return
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    assert got == f"Fill in {joined} before running."


def test_required_message_examples_and_new_promo_caller():
    """Validates: Requirement 3.15"""
    assert required_message(["Channels"]) == "Fill in Channels before running."
    assert required_message(["Eligible Segments", "Channels"]) == (
        "Fill in Eligible Segments and Channels before running.")
    assert "st.error(required_message(required_missing))" in MAIN_SRC
    for node in ast.walk(MAIN_TREE):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "required_message":
            assert len(node.args) == 1 and not node.keywords
