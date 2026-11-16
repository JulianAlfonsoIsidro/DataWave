"""Source scans for item 1.12: job-button detection in ui_interactions.js.

**Validates: Requirements 2.12, 3.11, 3.12**
"""
from __future__ import annotations

import re
from pathlib import Path

JS_SRC = (Path(__file__).resolve().parents[1] / "app" / "static" / "ui_interactions.js").read_text(
    encoding="utf-8"
)


def _body(name: str) -> str:
    m = re.search(r"function " + name + r"\([^)]*\)\s*\{(.*?)\n  \}", JS_SRC, re.S)
    assert m, f"{name} not found"
    return m.group(1)


def test_is_job_button_checks_ancestor_and_suggest_key():
    body = _body("isJobButton")
    assert "closest('[class*=\"st-key-p8_btn_\"]')" in body
    assert "st-key-persona_suggest" in body
    assert "st-key-persona_use_suggestion" in body


def test_click_handler_uses_is_job_button_and_stores_flag():
    assert "isJobButton(btn)" in JS_SRC
    assert "isJobKey(keyOf(btn))" not in JS_SRC
    assert "job: job" in JS_SRC


def test_settle_ms_reads_entry_job_flag():
    body = _body("settleMs")
    assert "entry.job" in body
    assert "return 300;" in body
    assert "settleMs(entry);" in JS_SRC


def test_job_keys_and_is_job_key_kept():
    assert "JOB_KEYS" in JS_SRC
    assert re.search(r"function isJobKey\(", JS_SRC)
