"""Offline chat integration test for the Part 6 assistant (task 8.1).

# Feature: part6-assistant, Property 7: offline suggested questions answer end to end

Drives :func:`assistant.engine.answer_turn` end to end for each of the four
clickable Suggested_Questions with *no* credentials configured, asserting that
every one produces a non-empty, tool-cited, length-capped, logged reply with
``mode == "mock"`` and that no AWS client is ever constructed (Requirement 4.4,
Property 7).

Isolation strategy (an autouse fixture applies all four):

- ``assistant.engine.load_model_config`` returns ``ModelConfig(None, None,
  None, None)`` -- not usable -- so the engine takes the Mock path and never
  enters the Bedrock branch (which is the only place boto3 is imported).
- ``sys.modules["boto3"]`` is replaced with a fake whose ``.client(...)`` raises
  ``AssertionError``. This is a *tripwire*: if the engine ever constructed an
  AWS client the whole turn would blow up. Because the Mock path never touches
  boto3, the tripwire must never fire.
- ``assistant.engine.tools.build_run_context`` raises ``FileNotFoundError`` so
  ``run_context`` resolves to ``None`` and the turn stays fast and hermetic
  (no model artifact or data bundle is read).
- ``monkeypatch.chdir(tmp_path)`` so ``log_turn`` (which writes the relative
  path ``scratch/assistant_log.jsonl``) logs under ``tmp_path`` instead of
  polluting the repo. ``log_turn`` is deliberately *not* patched away -- the
  property asserts the turn was logged.

The four suggested questions all route to one of the four tools in the Mock
driver's first-match-wins table (with ``run_result=None`` each relays its
needs-a-run / not-available note but still carries the ``(source: <tool>)``
citation): the threshold what-if -> ``what_if``; "Why Is Ready Toppers
Prioritized?" -> ``get_card``; "Which Segment Should We Skip?" ->
``compare_segments``; "How Accurate Was P001?" -> ``what_if`` as well, because
the Mock amount parser reads the "P001" token as the peso amount ``P001`` (= 1)
and route 1 (a numeric amount) is checked before the promo-id route. The exact
tool is a routing detail; Property 7 only requires that a tool was called and is
cited, so the test asserts ``tool_called`` is one of the four tools and appears
in the reply text rather than pinning a specific tool per question.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from assistant import engine
from assistant.models import ModelConfig

# The four clickable Suggested_Questions, copied verbatim from
# ``app/main.py`` (SUGGESTED_QUESTIONS). Redefined here rather than imported so
# the test does not pull in Streamlit at import time.
SUGGESTED_QUESTIONS = [
    "What If The Threshold Is P300,000?",
    "Why Is Ready Toppers Prioritized?",
    "Which Segment Should We Skip?",
    "How Accurate Was P001?",
]


@pytest.fixture(autouse=True)
def _offline_engine(monkeypatch, tmp_path):
    """Make every turn offline, context-free, AWS-tripwired, and tmp-logged.

    Yields the ``scratch/`` directory under ``tmp_path`` where ``log_turn``
    appends ``assistant_log.jsonl`` (via the relative path, after ``chdir``).
    """
    # 1. No credentials -> not usable -> Mock path only.
    unusable = ModelConfig(None, None, None, None)
    assert unusable.is_usable is False
    monkeypatch.setattr(engine, "load_model_config", lambda: unusable, raising=True)

    # 2. boto3 tripwire: constructing any AWS client raises loudly. The Mock
    #    path never imports boto3, so this must never fire.
    fake_boto3 = types.ModuleType("boto3")

    def _no_client(*args, **kwargs):
        raise AssertionError("no AWS client should be constructed offline")

    fake_boto3.client = _no_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    # 3. No run context -> run_context resolves to None (fast, hermetic).
    def _raise_no_context(*args, **kwargs):
        raise FileNotFoundError("no run context in tests")

    monkeypatch.setattr(
        engine.tools, "build_run_context", _raise_no_context, raising=True
    )

    # 4. Isolate logging to tmp_path: log_turn writes the relative path
    #    "scratch/assistant_log.jsonl", so chdir sends it under tmp_path.
    monkeypatch.chdir(tmp_path)

    return tmp_path / "scratch"


# The four tool names any suggested question may route to in the Mock driver.
_KNOWN_TOOLS = {"get_card", "compare_segments", "what_if", "past_promo_accuracy"}


@pytest.mark.parametrize("question", SUGGESTED_QUESTIONS)
def test_suggested_question_answers_in_mock_mode_offline(question):
    """Each suggested question yields a non-empty, tool-cited, capped mock reply.

    With no credentials and a boto3 tripwire installed, the engine answers in
    Mock Mode without ever constructing an AWS client. The reply is a non-empty
    string, names the tool it called (tool-cited), and respects the ~120-word
    length cap (Requirement 4.4, Property 7).

    **Validates: Requirements 4.4**
    """
    reply = engine.answer_turn(question, None)

    # Mock mode (no AWS attempted; the tripwire did not fire).
    assert reply.mode == "mock"

    # Non-empty reply text.
    assert isinstance(reply.text, str)
    assert reply.text.strip() != ""

    # Tool-cited: all four suggested questions route to a tool even when
    # run_result is None (they relay the needs-a-run / not-available note but
    # still carry the "(source: <tool>)" citation). Which of the four tools a
    # question routes to is a Mock-driver routing detail; Property 7 only
    # requires that a tool was called and is named in the text.
    assert reply.tool_called is not None
    assert reply.tool_called in _KNOWN_TOOLS
    assert reply.tool_called in reply.text

    # Length cap: at most 120 words, plus a possible trailing ellipsis token.
    assert len(reply.text.split()) <= 121


def test_all_suggested_questions_logged_offline(_offline_engine):
    """Driving all four suggested questions logs four mock-mode JSON lines.

    After answering every suggested question, ``scratch/assistant_log.jsonl``
    under ``tmp_path`` exists and has at least four lines, each an independently
    valid JSON object with ``mode == "mock"`` -- so the offline turns are logged
    (Requirement 4.4, Property 7). No AWS client is constructed (guaranteed by
    the boto3 tripwire in the fixture not having fired).

    **Validates: Requirements 4.4**
    """
    scratch_dir = _offline_engine

    for question in SUGGESTED_QUESTIONS:
        reply = engine.answer_turn(question, None)
        assert reply.mode == "mock"
        assert reply.text.strip() != ""

    log_path = scratch_dir / "assistant_log.jsonl"
    assert log_path.exists()

    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) >= 4

    for line in lines:
        record = json.loads(line)  # each line independently valid JSON
        assert record["mode"] == "mock"
        assert record["answer"].strip() != ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
