"""Per-session finishing state in ``app/ui_effects.py`` (task 3.3, item 1.3).

**Validates: Requirements 2.3**
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import ui_effects  # noqa: E402


def test_finish_state_is_per_session(monkeypatch):
    a: dict = {}
    b: dict = {}
    current = {"s": a}
    monkeypatch.setattr(ui_effects, "_state", lambda: current["s"])

    ui_effects._set_finish("Done A", 3)
    current["s"] = b
    assert ui_effects._get_finish() == (None, 0)
    ui_effects._set_finish("Done B", 5)
    current["s"] = a
    assert ui_effects._get_finish() == ("Done A", 3)
    assert a["p8_fin_headline"] == "Done A" and a["p8_fin_uid"] == 3


def test_pick_up_completions_writes_state_and_increments_uid(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(ui_effects, "_state", lambda: state)
    job = ui_effects._JOBS[0]
    records = {job: {"ok": True, "headline": "All set"}}
    monkeypatch.setattr(ui_effects, "_store", lambda key: records)

    assert ui_effects._pick_up_completions() == job
    assert ui_effects._get_finish() == ("All set", 1)
    records[job] = {"ok": True, "headline": "Again"}
    assert ui_effects._pick_up_completions() == job
    assert ui_effects._get_finish() == ("Again", 2)
