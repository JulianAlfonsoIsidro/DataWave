"""Source scans for item 1.14: scrim timing in watchJobClick.

**Validates: Requirements 2.14, 3.11**
"""
from __future__ import annotations

import re
from pathlib import Path

JS_SRC = (Path(__file__).resolve().parents[1] / "app" / "static" / "ui_interactions.js").read_text(
    encoding="utf-8"
)


def _watch_body() -> str:
    m = re.search(r"function\s+watchJobClick\s*\(\)\s*\{(.*?)\n  \}", JS_SRC, re.S)
    assert m, "watchJobClick not found"
    return m.group(1)


def test_constants_defined_as_plain_numbers():
    assert re.search(r"JOB_NO_RUN_MS\s*=\s*1500", JS_SRC)
    assert re.search(r"JOB_SAFETY_CAP_MS\s*=\s*15000", JS_SRC)
    assert "not design tokens" in JS_SRC


def test_watch_uses_constants_and_seen_busy_and_no_bare_3000():
    body = _watch_body()
    assert "JOB_NO_RUN_MS" in body and "JOB_SAFETY_CAP_MS" in body
    assert "jobSeenBusy" in body
    assert "3000" not in body


def test_watch_keeps_handoff_and_loader_return():
    assert ".pan-loading:not(.is-finishing)" in _watch_body()
    assert 'addEventListener("p9-job-handoff", clearJobClick)' in JS_SRC
