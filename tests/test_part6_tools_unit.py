"""Unit tests for the not-available / needs-a-run branches of the four tools.

These are concrete example/edge tests (not Hypothesis properties) covering the
``ok=False`` branches of ``src/assistant/tools.py`` (Requirements 1.4, 2.2,
2.5):

- :func:`get_card` and :func:`compare_segments` with ``run_result=None`` return
  a needs-a-run :class:`~assistant.models.ToolResult`, so a question that needs
  the current run is relayed rather than erroring (Requirement 1.4).
- :func:`get_card` for a segment with no card returns a not-available result
  (Requirement 2.2), while a card present for the segment returns ``ok=True``
  with the surfaced fields.
- :func:`past_promo_accuracy` returns a not-available result when
  ``outputs/cards.json`` or ``data/promo_leads.csv`` is missing (Requirement
  2.5); this is exercised by pointing the module's path constants at files that
  do not exist via ``monkeypatch.setattr``.

Nothing here touches AWS or the real on-disk artifacts, and any temporary paths
live under pytest's ``tmp_path`` (cleaned up automatically).
"""

from __future__ import annotations

import types

from assistant import tools
from assistant.models import ToolResult


def _fake_run_result(cards):
    """A minimal stand-in for ``RunResult`` exposing only ``.cards``.

    The card tools read ``run_result.cards`` and nothing else, so a
    ``SimpleNamespace`` with that one attribute is enough to drive both the
    present-card and no-card branches without building a full run.
    """
    return types.SimpleNamespace(cards=cards)


def test_get_card_needs_a_run_when_run_result_is_none():
    """get_card with no run yet returns ok=False and the needs-a-run note."""
    result = tools.get_card("Ready Toppers", None)

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.note == tools._NEEDS_A_RUN
    assert result.tool_name == "get_card"


def test_compare_segments_needs_a_run_when_run_result_is_none():
    """compare_segments with no run yet returns ok=False and needs-a-run."""
    result = tools.compare_segments(None)

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.note == tools._NEEDS_A_RUN
    assert result.tool_name == "compare_segments"


def test_get_card_not_available_when_segment_has_no_card():
    """A run whose cards omit the requested segment yields not-available."""
    # A run exists but carries a card for a *different* segment only.
    run_result = _fake_run_result(
        [{"segment": "Not Now", "action": "hold"}]
    )

    result = tools.get_card("Ready Toppers", run_result)

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.note == tools._NO_CARD
    assert result.tool_name == "get_card"


def test_get_card_not_available_when_cards_empty():
    """An empty cards list also yields the not-available note."""
    result = tools.get_card("Ready Toppers", _fake_run_result([]))

    assert result.ok is False
    assert result.note == tools._NO_CARD
    assert result.tool_name == "get_card"


def test_get_card_returns_surfaced_fields_when_card_present():
    """A card present for the segment returns ok=True with its fields.

    The positive path is checked lightly: ``ok`` is True, no note is set, and a
    representative surfaced field is passed through, while a non-surfaced key
    (``client_id``) never crosses the boundary (Requirement 2.6).
    """
    card = {
        "segment": "Ready Toppers",
        "action": "send",
        "dominant_channel": "In-app",
        "message_angle": "Top up to join",
        "expected_joiners": 120,
        "joiners_90_low": 90,
        "joiners_90_high": 150,
        "expected_value": 240000.0,
        "top_drivers": ["adb", "tenure"],
        "excluded_by_reason": {"low_adb": 5},
        "client_id": "SHOULD-NOT-LEAK",
    }
    run_result = _fake_run_result([card])

    result = tools.get_card("Ready Toppers", run_result)

    assert result.ok is True
    assert result.note == ""
    assert result.tool_name == "get_card"
    assert result.data["action"] == "send"
    assert result.data["expected_joiners"] == 120
    assert "client_id" not in result.data


def test_past_promo_accuracy_not_available_when_files_missing(tmp_path, monkeypatch):
    """Missing cards.json / promo_leads.csv yields a not-available result.

    Points both module path constants at files that do not exist so the open /
    read raises ``FileNotFoundError`` inside ``past_promo_accuracy`` and it
    returns ``ok=False`` with the not-available note (Requirement 2.5).
    """
    monkeypatch.setattr(tools, "_CARDS_JSON_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(tools, "_PROMO_LEADS_PATH", tmp_path / "nope.csv")

    result = tools.past_promo_accuracy("PROMO-2024-03")

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.note == tools._NOT_AVAILABLE
    assert result.tool_name == "past_promo_accuracy"
