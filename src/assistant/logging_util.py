"""Append-only per-turn logging to scratch/assistant_log.jsonl."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

__all__ = ["log_turn"]

_LOG_PATH = Path("scratch") / "assistant_log.jsonl"


def log_turn(
    question: str,
    tool_called: str | None,
    answer: str,
    mode: str,
) -> None:
    """Append one JSON object as a single line to scratch/assistant_log.jsonl.

    Records the timestamp, question, tool called (if any), answer, and mode.
    The ``answer`` is expected to be privacy-scrubbed before it is passed in
    (Requirement 6.3). The ``scratch/`` directory is created when missing
    (Requirement 6.4), and the record is appended without rewriting earlier
    lines so the file remains append-only valid JSON Lines (Requirement 6.2).
    """
    record = {
        "ts": datetime.now().isoformat(),
        "question": question,
        "tool_called": tool_called,
        "answer": answer,
        "mode": mode,
    }

    Path("scratch").mkdir(exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
