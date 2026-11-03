"""Property-based test for the Part 6 assistant per-turn logging.

# Feature: part6-assistant, Property 6: Logging is append-only valid JSON Lines under scratch/

Covers Property 6 of the part6-assistant spec: for any sequence of answered
turns, :func:`assistant.logging_util.log_turn` appends one record per turn to
``scratch/assistant_log.jsonl`` such that each line is independently valid JSON
carrying the required keys (``ts``, ``question``, ``tool_called``, ``answer``,
``mode``), earlier lines are never rewritten, and the file (and its ``scratch/``
parent) is created when missing (Requirements 6.1, 6.2, 6.4).

Isolation: ``log_turn`` writes to the literal relative path
``scratch/assistant_log.jsonl``. Each example ``chdir``s into a fresh
``tmp_path`` for the duration of the call so ``scratch/`` is created under the
temporary directory -- exercising the real ``mkdir("scratch")`` path (Req 6.4)
-- and the project's real ``scratch/`` is never touched.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from assistant.logging_util import log_turn

# The keys every log record must carry (Requirements 6.1, 6.2).
REQUIRED_KEYS = {"ts", "question", "tool_called", "answer", "mode"}

# The two modes a turn may use (Requirement 6.1).
MODES = ["bedrock", "mock"]


@st.composite
def turns(draw: st.DrawFn, *, min_size: int = 1, max_size: int = 6) -> list[tuple]:
    """A non-empty sequence of ``(question, tool_called, answer, mode)`` turns.

    ``tool_called`` is either ``None`` (scope refusals / needs-a-run notices) or
    a tool name; ``mode`` is one of ``"bedrock"`` / ``"mock"``. Plain ``st.text``
    is used for free-form fields because ``json`` round-trips every string, so no
    character class needs excluding.
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    out: list[tuple] = []
    for _ in range(n):
        question = draw(st.text())
        tool_called = draw(st.one_of(st.none(), st.text()))
        answer = draw(st.text())
        mode = draw(st.sampled_from(MODES))
        out.append((question, tool_called, answer, mode))
    return out


@contextmanager
def _fresh_cwd():
    """Run the body with the cwd set to a brand-new empty temp directory.

    A fresh directory per example (with no ``scratch/`` yet) keeps each
    generated sequence independent -- unlike a function-scoped ``tmp_path``
    fixture, which Hypothesis does not reset between examples -- and leaves the
    project's real ``scratch/`` untouched. The original cwd is always restored.
    """
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(original)


@settings(max_examples=200, deadline=None)
@given(turn_list=turns())
def test_log_turn_is_append_only_valid_json_lines(turn_list):
    """Logging appends one valid JSON line per turn, append-only, under scratch/.

    **Validates: Requirements 6.1, 6.2, 6.4**
    """
    with _fresh_cwd():
        _assert_append_only_logging(turn_list)


def _assert_append_only_logging(turn_list):
    """Body of the property, run inside a fresh cwd with no scratch/ yet."""
    log_path = Path("scratch") / "assistant_log.jsonl"
    assert not log_path.exists()  # fresh start: file created on first write

    # Snapshot of the file's lines after each turn, to assert append-only.
    previous_lines: list[str] = []

    for index, (question, tool_called, answer, mode) in enumerate(turn_list):
        log_turn(question, tool_called, answer, mode)

        # Req 6.4: scratch/ and the log file are created when missing.
        assert log_path.exists()

        # Read raw lines (keep newline semantics out of the split).
        raw = log_path.read_text(encoding="utf-8")
        lines = raw.splitlines()

        # Req 6.2: exactly one record per turn so far.
        assert len(lines) == index + 1

        # Req 6.2 (append-only): every earlier line is byte-for-byte unchanged.
        assert lines[: len(previous_lines)] == previous_lines

        # Req 6.1 / 6.2: the just-appended line is independently valid JSON
        # with the required keys and round-trips the inputs.
        record = json.loads(lines[index])
        assert REQUIRED_KEYS <= set(record)
        assert record["question"] == question
        assert record["tool_called"] == tool_called
        assert record["answer"] == answer
        assert record["mode"] == mode

        previous_lines = lines

    # Final whole-file check: every line parses and the keys/values round-trip
    # to the inputs in order (Req 6.1, 6.2).
    final_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(final_lines) == len(turn_list)
    for (question, tool_called, answer, mode), line in zip(turn_list, final_lines):
        record = json.loads(line)
        assert REQUIRED_KEYS <= set(record)
        assert record["question"] == question
        assert record["tool_called"] == tool_called
        assert record["answer"] == answer
        assert record["mode"] == mode
